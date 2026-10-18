"""
OASIS模拟运行器
在后台运行模拟并记录每个Agent的动作，支持实时状态监控
"""

import os
import sys
import json
import time
import asyncio
import threading
import subprocess
import signal
import atexit
import hashlib
import re
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from queue import Queue

from ..config import Config
from ..utils.logger import get_logger
from ..utils.locale import get_locale, set_locale
from ..utils.interview_history import order_interview_history
from ..utils.zep import (
    ZEP_HTTP_REQUEST_TIMEOUT_SECONDS,
    ZEP_INGESTION_WAIT_TIMEOUT_SECONDS,
)
from .zep_graph_memory_updater import ZepGraphMemoryManager
from .simulation_ipc import SimulationIPCClient, CommandType, IPCResponse
from ..models.execution import RunStore, WORKER_ID, worker_alive, worker_identity, utc_now, public_manifest
from ..utils.atomic import write_json

logger = get_logger('mirofish.simulation_runner')

# 标记是否已注册清理函数
_cleanup_registered = False

# 平台检测
IS_WINDOWS = sys.platform == 'win32'


class RunnerStatus(str, Enum):
    """运行器状态"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    FINALIZING = "finalizing"
    INTERRUPTED = "interrupted"
    NEEDS_REVIEW = "needs_review"


class SimulationStopPending(TimeoutError):
    """The monitor still owns a bounded graph-ingestion finalization."""


@dataclass
class AgentAction:
    """Agent动作记录"""
    round_num: int
    timestamp: str
    platform: str  # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str  # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None
    success: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "timestamp": self.timestamp,
            "platform": self.platform,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action_type": self.action_type,
            "action_args": self.action_args,
            "result": self.result,
            "success": self.success,
        }


@dataclass
class RoundSummary:
    """每轮摘要"""
    round_num: int
    start_time: str
    end_time: Optional[str] = None
    simulated_hour: int = 0
    twitter_actions: int = 0
    reddit_actions: int = 0
    active_agents: List[int] = field(default_factory=list)
    actions: List[AgentAction] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "simulated_hour": self.simulated_hour,
            "twitter_actions": self.twitter_actions,
            "reddit_actions": self.reddit_actions,
            "active_agents": self.active_agents,
            "actions_count": len(self.actions),
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass
class SimulationRunState:
    """模拟运行状态（实时）"""
    simulation_id: str
    runner_status: RunnerStatus = RunnerStatus.IDLE
    run_id: Optional[str] = None
    attempt_id: Optional[str] = None
    worker_id: Optional[str] = None
    owner: Dict[str, Any] = field(default_factory=dict)
    heartbeat: Optional[str] = None
    enabled_platforms: List[str] = field(default_factory=list)
    graph_ready: bool = False
    # None = legacy state without a graph-write claim; otherwise
    # 'not_requested' | 'confirmed' | 'failed'
    graph_update_status: Optional[str] = None
    manifest: Dict[str, Any] = field(default_factory=dict)
    
    # 动作日志读取缺口（完整但损毁的行，不静默视为完整输入）
    log_gaps: List[Dict[str, Any]] = field(default_factory=list)
    
    # 进度信息
    current_round: int = 0
    total_rounds: int = 0
    simulated_hours: float = 0
    total_simulation_hours: float = 0
    
    # 各平台独立轮次和模拟时间（用于双平台并行显示）
    twitter_current_round: int = 0
    reddit_current_round: int = 0
    twitter_simulated_hours: float = 0
    reddit_simulated_hours: float = 0
    
    # 平台状态
    twitter_running: bool = False
    reddit_running: bool = False
    twitter_actions_count: int = 0
    reddit_actions_count: int = 0
    
    # 平台完成状态（通过检测 actions.jsonl 中的 simulation_end 事件）
    twitter_completed: bool = False
    reddit_completed: bool = False
    
    # 每轮摘要
    rounds: List[RoundSummary] = field(default_factory=list)
    
    # 最近动作（用于前端实时展示）
    recent_actions: List[AgentAction] = field(default_factory=list)
    max_recent_actions: int = 50
    
    # 时间戳
    started_at: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    
    # 错误信息
    error: Optional[str] = None
    
    # 进程ID（用于停止）
    process_pid: Optional[int] = None
    
    def add_action(self, action: AgentAction):
        """添加动作到最近动作列表"""
        self.recent_actions.insert(0, action)
        if len(self.recent_actions) > self.max_recent_actions:
            self.recent_actions = self.recent_actions[:self.max_recent_actions]
        
        if action.platform == "twitter":
            self.twitter_actions_count += 1
        else:
            self.reddit_actions_count += 1
        
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "simulation_id": self.simulation_id,
            "runner_status": self.runner_status.value,
            "run_id": self.run_id,
            "attempt_id": self.attempt_id,
            "worker_id": self.worker_id,
            "heartbeat": self.heartbeat,
            "enabled_platforms": self.enabled_platforms,
            "graph_ready": bool(self.graph_ready and self.run_id and self.runner_status == RunnerStatus.COMPLETED),
            "manifest": self.manifest,
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "simulated_hours": self.simulated_hours,
            "total_simulation_hours": self.total_simulation_hours,
            "progress_percent": round(self.current_round / max(self.total_rounds, 1) * 100, 1),
            # 各平台独立轮次和时间
            "twitter_current_round": self.twitter_current_round,
            "reddit_current_round": self.reddit_current_round,
            "twitter_simulated_hours": self.twitter_simulated_hours,
            "reddit_simulated_hours": self.reddit_simulated_hours,
            "twitter_running": self.twitter_running,
            "reddit_running": self.reddit_running,
            "twitter_completed": self.twitter_completed,
            "reddit_completed": self.reddit_completed,
            "twitter_actions_count": self.twitter_actions_count,
            "reddit_actions_count": self.reddit_actions_count,
            "total_actions_count": self.twitter_actions_count + self.reddit_actions_count,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "process_pid": self.process_pid,
            "log_gaps": self.log_gaps,
        }
        # 旧状态没有图谱更新宣告时保持栏位缺席
        if self.graph_update_status is not None:
            result["graph_update_status"] = self.graph_update_status
        return result
    
    def to_detail_dict(self) -> Dict[str, Any]:
        """包含最近动作的详细信息"""
        result = self.to_dict()
        result["recent_actions"] = [a.to_dict() for a in self.recent_actions]
        result["rounds_count"] = len(self.rounds)
        return result


class SimulationRunner:
    """
    模拟运行器
    
    负责：
    1. 在后台进程中运行OASIS模拟
    2. 解析运行日志，记录每个Agent的动作
    3. 提供实时状态查询接口
    4. 支持暂停/停止/恢复操作
    """
    
    # 运行状态存储目录
    RUN_STATE_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../uploads/simulations'
    )
    
    # 脚本目录
    SCRIPTS_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../scripts'
    )
    
    # 内存中的运行状态
    _run_states: Dict[str, SimulationRunState] = {}
    _processes: Dict[str, subprocess.Popen] = {}
    _action_queues: Dict[str, Queue] = {}
    _monitor_threads: Dict[str, threading.Thread] = {}
    _stdout_files: Dict[str, Any] = {}  # 存储 stdout 文件句柄
    _stderr_files: Dict[str, Any] = {}  # 存储 stderr 文件句柄
    
    # 图谱记忆更新配置
    _graph_memory_enabled: Dict[str, bool] = {}  # simulation_id -> enabled
    _finalization_locks: Dict[str, threading.Lock] = {}
    _finalization_locks_guard = threading.Lock()
    _manual_stop_requests: set[str] = set()

    @classmethod
    def _simulation_dir(cls, simulation_id: str) -> str:
        if not isinstance(simulation_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', simulation_id):
            raise ValueError('Invalid simulation identity')
        root = os.path.realpath(cls.RUN_STATE_DIR)
        path = os.path.realpath(os.path.join(root, simulation_id))
        if os.path.commonpath([root, path]) != root:
            raise ValueError('Invalid simulation directory')
        return path

    @classmethod
    def _finalization_lock(cls, simulation_id: str) -> threading.Lock:
        cls._simulation_dir(simulation_id)
        with cls._finalization_locks_guard:
            return cls._finalization_locks.setdefault(
                simulation_id, threading.RLock()
            )

    @classmethod
    def _sync_simulation_status(
        cls,
        simulation_id: str,
        runner_status: RunnerStatus,
        error: str | None = None,
    ) -> None:
        """Keep persisted simulation metadata aligned with run_state.json."""

        from .simulation_manager import SimulationManager, SimulationStatus

        status_map = {
            RunnerStatus.RUNNING: SimulationStatus.RUNNING,
            RunnerStatus.STOPPING: SimulationStatus.STOPPING,
            RunnerStatus.STOPPED: SimulationStatus.STOPPED,
            RunnerStatus.COMPLETED: SimulationStatus.COMPLETED,
            RunnerStatus.FAILED: SimulationStatus.FAILED,
            RunnerStatus.FINALIZING: SimulationStatus.FINALIZING,
            RunnerStatus.INTERRUPTED: SimulationStatus.INTERRUPTED,
            RunnerStatus.NEEDS_REVIEW: SimulationStatus.NEEDS_REVIEW,
        }
        status = status_map.get(runner_status)
        if status is None:
            return
        try:
            manager = SimulationManager()
            simulation = manager.get_simulation(simulation_id)
            if simulation is None:
                return
            simulation.status = status
            simulation.error = error
            manager._save_simulation_state(simulation)
        except Exception as sync_error:
            # state.json is a secondary projection. Never let a projection
            # failure skip the authoritative run-state finalization or Zep
            # ingestion drain.
            logger.error(
                "同步模拟状态失败: simulation_id=%s, status=%s, error=%s",
                simulation_id,
                runner_status.value,
                sync_error,
            )
    
    @classmethod
    def get_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """获取运行状态"""
        cls._simulation_dir(simulation_id)
        row = RunStore.get(simulation_id, reconcile=True)
        state = cls._run_states.get(simulation_id) or cls._load_run_state(simulation_id)
        if row:
            if state is None:
                state = SimulationRunState(simulation_id=simulation_id)
            state.run_id = row['run_id']
            state.attempt_id = row['attempt_id']
            state.worker_id = row['worker_id']
            state.owner = row['owner']
            state.heartbeat = row['heartbeat']
            state.manifest = row['manifest']
            state.enabled_platforms = row['manifest'].get('platforms', [])
            state.runner_status = RunnerStatus(row['status'])
            state.graph_ready = row['graph_ready']
        elif state and state.runner_status in {RunnerStatus.STARTING, RunnerStatus.RUNNING, RunnerStatus.PAUSED, RunnerStatus.STOPPING, RunnerStatus.FINALIZING}:
            state.runner_status = RunnerStatus.NEEDS_REVIEW
            state.graph_ready = False
            state.error = 'Legacy execution ownership cannot be verified; create a new simulation.'
        if state:
            cls._run_states[simulation_id] = state
        return state
    
    @classmethod
    def _load_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """从文件加载运行状态"""
        state_file = os.path.join(cls._simulation_dir(simulation_id), "run_state.json")
        if not os.path.exists(state_file):
            return None
        
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            state = SimulationRunState(
                simulation_id=simulation_id,
                runner_status=RunnerStatus(data.get("runner_status", "idle")),
                run_id=data.get('run_id'),
                attempt_id=data.get('attempt_id'),
                worker_id=data.get('worker_id'),
                owner=data.get('owner', {}),
                heartbeat=data.get('heartbeat'),
                enabled_platforms=data.get('enabled_platforms', []),
                graph_ready=False,
                graph_update_status=data.get('graph_update_status'),
                log_gaps=data.get('log_gaps', []),
                manifest=data.get('manifest', {}),
                current_round=data.get("current_round", 0),
                total_rounds=data.get("total_rounds", 0),
                simulated_hours=data.get("simulated_hours", 0),
                total_simulation_hours=data.get("total_simulation_hours", 0),
                # 各平台独立轮次和时间
                twitter_current_round=data.get("twitter_current_round", 0),
                reddit_current_round=data.get("reddit_current_round", 0),
                twitter_simulated_hours=data.get("twitter_simulated_hours", 0),
                reddit_simulated_hours=data.get("reddit_simulated_hours", 0),
                twitter_running=data.get("twitter_running", False),
                reddit_running=data.get("reddit_running", False),
                twitter_completed=data.get("twitter_completed", False),
                reddit_completed=data.get("reddit_completed", False),
                twitter_actions_count=data.get("twitter_actions_count", 0),
                reddit_actions_count=data.get("reddit_actions_count", 0),
                started_at=data.get("started_at"),
                updated_at=data.get("updated_at", datetime.now().isoformat()),
                completed_at=data.get("completed_at"),
                error=data.get("error"),
                process_pid=data.get("process_pid"),
            )
            
            # 加载最近动作
            actions_data = data.get("recent_actions", [])
            for a in actions_data:
                state.recent_actions.append(AgentAction(
                    round_num=a.get("round_num", 0),
                    timestamp=a.get("timestamp", ""),
                    platform=a.get("platform", ""),
                    agent_id=a.get("agent_id", 0),
                    agent_name=a.get("agent_name", ""),
                    action_type=a.get("action_type", ""),
                    action_args=a.get("action_args", {}),
                    result=a.get("result"),
                    success=a.get("success", True),
                ))
            
            return state
        except Exception as e:
            logger.error(f"加载运行状态失败: {str(e)}")
            return None
    
    @classmethod
    def _save_run_state(cls, state: SimulationRunState):
        """保存运行状态到文件"""
        sim_dir = cls._simulation_dir(state.simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        state_file = os.path.join(sim_dir, "run_state.json")
        
        data = state.to_detail_dict()
        data['owner'] = state.owner
        if state.run_id:
            row = RunStore.update(state.simulation_id, state.runner_status.value,
                                  graph_ready=state.graph_ready, completed_at=state.completed_at,
                                  error=state.error, state=data)
            state.heartbeat = row['heartbeat']
            data['heartbeat'] = state.heartbeat
        write_json(state_file, data)
        
        cls._run_states[state.simulation_id] = state
    
    @classmethod
    def start_simulation(
        cls, simulation_id: str, platform: str = 'parallel', max_rounds: int = None,
        enable_graph_memory_update: bool = False, graph_id: str = None,
    ) -> SimulationRunState:
        # All local start/stop transitions share this lock. The durable claim
        # below supplies the corresponding exclusion between server workers.
        with cls._finalization_lock(simulation_id):
            existing = cls.get_run_state(simulation_id)
            if existing and existing.runner_status != RunnerStatus.IDLE:
                return existing
            return cls._start_simulation_once(simulation_id, platform, max_rounds,
                                             enable_graph_memory_update, graph_id)

    @classmethod
    def _start_simulation_once(
        cls,
        simulation_id: str,
        platform: str = "parallel",  # twitter / reddit / parallel
        max_rounds: int = None,  # 最大模拟轮数（可选，用于截断过长的模拟）
        enable_graph_memory_update: bool = False,  # 是否将活动更新到Zep图谱
        graph_id: str = None  # Zep图谱ID（启用图谱更新时必需）
    ) -> SimulationRunState:
        """
        启动模拟
        
        Args:
            simulation_id: 模拟ID
            platform: 运行平台 (twitter/reddit/parallel)
            max_rounds: 最大模拟轮数（可选，用于截断过长的模拟）
            enable_graph_memory_update: 是否将Agent活动动态更新到Zep图谱
            graph_id: Zep图谱ID（启用图谱更新时必需）
            
        Returns:
            SimulationRunState
        """
        # 加载模拟配置
        sim_dir = cls._simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")

        runtime_files = ('run_state.json', 'simulation.log', 'twitter_simulation.db', 'reddit_simulation.db',
                         'actions.jsonl', 'twitter/actions.jsonl', 'reddit/actions.jsonl')
        if any(os.path.exists(os.path.join(sim_dir, name)) for name in runtime_files):
            # Another worker may have claimed between the public entry check
            # and this filesystem check; it still owns the original identity.
            if RunStore.get(simulation_id) is not None:
                return cls.get_run_state(simulation_id)
            raise ValueError('Files from an existing execution must be preserved; clone this simulation first.')
        
        if not os.path.exists(config_path):
            raise ValueError(f"模拟配置不存在，请先调用 /prepare 接口")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        if enable_graph_memory_update and not graph_id:
            raise ValueError('graph_id is required when graph updates are enabled')
        if platform not in {'twitter', 'reddit', 'parallel'}:
            raise ValueError('Unsupported simulation platform')
        from ..provider_settings import get_model_settings, model_environment
        prepared_path = os.path.join(sim_dir, 'state.json')
        if not os.path.exists(prepared_path):
            raise ValueError('Prepared simulation identity is missing.')
        if os.path.exists(prepared_path):
            with open(prepared_path, encoding='utf-8') as handle:
                prepared_state = json.load(handle)
            if (prepared_state.get('graph_namespace_status') != 'ready'
                    or not prepared_state.get('source_graph_id')
                    or prepared_state['source_graph_id'] == prepared_state.get('graph_id')):
                raise ValueError('An isolated graph namespace is required for every new execution.')
            if enable_graph_memory_update and graph_id != prepared_state.get('graph_id'):
                raise ValueError('Graph writes must target this simulation\'s isolated graph.')
        frozen_model = prepared_state.get('simulation_model_snapshot')
        if not isinstance(frozen_model, dict) or not all(key in frozen_model for key in ('provider', 'base_url', 'model')):
            raise ValueError('The isolated graph has no frozen simulation model; create a new simulation.')
        current_connection = get_model_settings(profile_id=frozen_model.get('profile_id') or 'default')
        if any(current_connection.get(key) != frozen_model[key] for key in ('provider', 'base_url')):
            raise ValueError('The frozen model connection changed; create a new simulation.')
        fingerprint = frozen_model.get('connection_fingerprint')
        if fingerprint and fingerprint != hashlib.sha256(current_connection.get('api_key', '').encode()).hexdigest():
            raise ValueError('The frozen model credential changed; create a new simulation.')
        model_snapshot = {**current_connection, **frozen_model}
        # Preparation and execution may use distinct configured stages. Each
        # snapshot stays attached to the work it actually performed.
        platforms = ['twitter', 'reddit'] if platform == 'parallel' else [platform]
        source_versions = []
        project_id = prepared_state.get('project_id')
        if project_id:
            from ..models.project import ProjectManager
            project = ProjectManager.get_project(project_id)
            if project and project.graph_id == prepared_state['source_graph_id']:
                source_versions = getattr(project, 'source_versions', []) or []
        def file_hash(path):
            if not os.path.isfile(path):
                return None
            digest = hashlib.sha256()
            with open(path, 'rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(chunk)
            return digest.hexdigest()
        profiles = {name: file_hash(os.path.join(sim_dir, name))
                    for name in ('twitter_profiles.csv', 'reddit_profiles.json')}
        def semantic_inputs(value):
            if isinstance(value, dict):
                return {key: semantic_inputs(item) for key, item in value.items()
                        if key not in {'simulation_id', 'graph_id', 'project_id', 'entity_uuid', 'source_entity_uuid', 'run_id', 'attempt_id'}}
            if isinstance(value, list):
                return [semantic_inputs(item) for item in value]
            return value
        roles = []
        for selected_platform in platforms:
            name = 'twitter_profiles.csv' if selected_platform == 'twitter' else 'reddit_profiles.json'
            try:
                with open(os.path.join(sim_dir, name), encoding='utf-8', newline='') as handle:
                    if name.endswith('.csv'):
                        import csv
                        role_data = list(csv.DictReader(handle))
                    else:
                        role_data = json.load(handle)
                if isinstance(role_data, list) and role_data:
                    roles.append({'platform': selected_platform, 'count': len(role_data),
                        'sha256': hashlib.sha256(json.dumps(semantic_inputs(role_data), ensure_ascii=False, sort_keys=True).encode()).hexdigest()})
            except (OSError, ValueError):
                # Incomplete legacy metadata is not fabricated as a known role
                # snapshot; quality evaluation will explicitly exclude it.
                pass
        semantic_config = semantic_inputs({key: value for key, value in config.items() if key not in {'llm_model', 'llm_base_url'}})
        code_hashes = {name: file_hash(os.path.join(cls.SCRIPTS_DIR, name))
                       for name in ('run_parallel_simulation.py', 'action_logger.py')}
        for name in ('simulation_runner.py', 'simulation_config_generator.py', 'oasis_profile_generator.py'):
            code_hashes[name] = file_hash(os.path.join(os.path.dirname(__file__), name))
        manifest = public_manifest({
            'project_id': project_id, 'captured_at': utc_now(),
            'platforms': platforms, 'max_rounds': max_rounds,
            'graph_id': prepared_state['graph_id'],
            'source_graph_id': prepared_state['source_graph_id'],
            'source_versions': source_versions,
            'source_lineage_status': 'graph_build_snapshot' if source_versions else 'unverified',
            'graph_memory_enabled': enable_graph_memory_update,
            'config_sha256': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
            'configuration': config, 'profile_hashes': profiles, 'code_hashes': code_hashes,
            'configuration_comparison_sha256': hashlib.sha256(json.dumps(semantic_config, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            'roles': roles, 'roles_snapshot_status': 'complete' if len(roles) == len(platforms) else 'incomplete',
            'model': model_snapshot, 'preparation_model': prepared_state.get('model_snapshot', {}),
            'model_frozen_at': prepared_state.get('simulation_model_frozen_at'),
            'model_resolution': {'requested': {key: model_snapshot.get(key) for key in ('provider', 'base_url', 'model')},
                                 'actual': {'status': 'unknown', 'model': None}},
            'seed': config.get('seed', {'status': 'unknown', 'value': None}),
            'assumptions': config.get('assumptions', {'status': 'unknown', 'value': None}),
            'budget': config.get('budget', {'status': 'unknown', 'value': None}),
            'prompt_version': {'status': 'unknown', 'value': None},
        })
        
        # 初始化运行状态
        time_config = config.get("time_config", {})
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)
        total_rounds = int(total_hours * 60 / minutes_per_round)
        
        # 如果指定了最大轮数，则截断
        if max_rounds is not None and max_rounds > 0:
            original_rounds = total_rounds
            total_rounds = min(total_rounds, max_rounds)
            if total_rounds < original_rounds:
                logger.info(f"轮数已截断: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")
        
        state = SimulationRunState(
            simulation_id=simulation_id,
            runner_status=RunnerStatus.STARTING,
            total_rounds=total_rounds,
            total_simulation_hours=total_hours,
            started_at=datetime.now().isoformat(),
        )
        
        # Atomically claim this simulation ID. The expensive updater/process
        # startup happens after releasing the lock, while the persisted
        # STARTING state makes every concurrent start fail closed.
        with cls._finalization_lock(simulation_id):
            row, created = RunStore.claim(simulation_id, manifest)
            if not created:
                return cls.get_run_state(simulation_id)
            state.run_id, state.attempt_id = row['run_id'], row['attempt_id']
            state.worker_id, state.owner = row['worker_id'], row['owner']
            state.manifest, state.enabled_platforms = row['manifest'], platforms
            state.heartbeat = row['heartbeat']
            cls._save_run_state(state)
        
        # 如果启用图谱记忆更新，创建更新器
        if enable_graph_memory_update:
            if not graph_id:
                raise ValueError("启用图谱记忆更新时必须提供 graph_id")
            
            try:
                ZepGraphMemoryManager.create_updater(simulation_id, graph_id, model_snapshot=model_snapshot)
                cls._graph_memory_enabled[simulation_id] = True
                logger.info(f"已启用图谱记忆更新: simulation_id={simulation_id}, graph_id={graph_id}")
            except Exception as e:
                logger.error('创建图谱记忆更新器失败: %s', type(e).__name__)
                cls._graph_memory_enabled[simulation_id] = False
                state.runner_status = RunnerStatus.FAILED
                state.error = f"圖譜更新器初始化未完成 ({type(e).__name__})。"
                with cls._finalization_lock(simulation_id):
                    cls._save_run_state(state)
                    cls._sync_simulation_status(
                        simulation_id,
                        RunnerStatus.FAILED,
                        state.error,
                    )
                raise RuntimeError(state.error) from None
        else:
            cls._graph_memory_enabled[simulation_id] = False
        
        # 确定运行哪个脚本（脚本位于 backend/scripts/ 目录）
        if platform == "twitter":
            script_name = "run_parallel_simulation.py"
            state.twitter_running = True
        elif platform == "reddit":
            script_name = "run_parallel_simulation.py"
            state.reddit_running = True
        else:
            script_name = "run_parallel_simulation.py"
            state.twitter_running = True
            state.reddit_running = True
        
        script_path = os.path.join(cls.SCRIPTS_DIR, script_name)
        
        if not os.path.exists(script_path):
            cleanup_error = None
            if cls._graph_memory_enabled.get(simulation_id, False):
                try:
                    ZepGraphMemoryManager.stop_updater(simulation_id)
                    cls._graph_memory_enabled.pop(simulation_id, None)
                except Exception as error:
                    cleanup_error = error
            state.runner_status = RunnerStatus.FAILED
            state.twitter_running = False
            state.reddit_running = False
            state.error = '執行程式缺失；請核對服務安裝。'
            if cleanup_error is not None:
                state.error += f" 圖譜寫入清理未完成 ({type(cleanup_error).__name__})。"
            with cls._finalization_lock(simulation_id):
                cls._save_run_state(state)
                cls._sync_simulation_status(
                    simulation_id,
                    RunnerStatus.FAILED,
                    state.error,
                )
            raise ValueError(state.error)
        
        # 创建动作队列
        action_queue = Queue()
        cls._action_queues[simulation_id] = action_queue

        process = None
        main_log_file = None

        # 启动模拟进程
        try:
            # 构建运行命令，使用完整路径
            # 新的日志结构：
            #   twitter/actions.jsonl - Twitter 动作日志
            #   reddit/actions.jsonl  - Reddit 动作日志
            #   simulation.log        - 主进程日志
            
            cmd = [
                sys.executable,  # Python解释器
                script_path,
                "--config", config_path,  # 使用完整配置文件路径
            ]
            if platform in {'twitter', 'reddit'}:
                cmd.append(f'--{platform}-only')
            
            # 如果指定了最大轮数，添加到命令行参数
            if max_rounds is not None and max_rounds > 0:
                cmd.extend(["--max-rounds", str(max_rounds)])
            
            # 创建主日志文件，避免 stdout/stderr 管道缓冲区满导致进程阻塞
            main_log_path = os.path.join(sim_dir, "simulation.log")
            main_log_file = open(main_log_path, 'a', encoding='utf-8')
            
            # 设置子进程环境变量，确保 Windows 上使用 UTF-8 编码
            # 这可以修复第三方库（如 OASIS）读取文件时未指定编码的问题
            env = os.environ.copy()
            env.update(model_environment(model_snapshot))
            env['MIROFISH_RUN_ID'] = state.run_id
            env['MIROFISH_ATTEMPT_ID'] = state.attempt_id
            env['PYTHONUTF8'] = '1'  # Python 3.7+ 支持，让所有 open() 默认使用 UTF-8
            env['PYTHONIOENCODING'] = 'utf-8'  # 确保 stdout/stderr 使用 UTF-8
            
            # 设置工作目录为模拟目录（数据库等文件会生成在此）
            # 使用 start_new_session=True 创建新的进程组，确保可以通过 os.killpg 终止所有子进程
            process = subprocess.Popen(
                cmd,
                cwd=sim_dir,
                stdout=main_log_file,
                stderr=subprocess.STDOUT,  # stderr 也写入同一个文件
                text=True,
                encoding='utf-8',  # 显式指定编码
                bufsize=1,
                env=env,  # 传递带有 UTF-8 设置的环境变量
                start_new_session=True,  # 创建新进程组，确保服务器关闭时能终止所有相关进程
            )
            
            # Capture locale before spawning monitor thread
            current_locale = get_locale()

            monitor_thread = threading.Thread(
                target=cls._monitor_simulation,
                args=(simulation_id, current_locale),
                daemon=True
            )

            # Atomically publish every resource needed by stop/finalization.
            # The monitor is registered before start; if it exits immediately,
            # it waits on the same lock until RUNNING is fully visible.
            with cls._finalization_lock(simulation_id):
                cls._stdout_files[simulation_id] = main_log_file
                cls._stderr_files[simulation_id] = None
                state.process_pid = process.pid
                state.runner_status = RunnerStatus.RUNNING
                cls._processes[simulation_id] = process
                cls._monitor_threads[simulation_id] = monitor_thread
                cls._save_run_state(state)
                cls._sync_simulation_status(
                    simulation_id,
                    RunnerStatus.RUNNING,
                )
                monitor_thread.start()
            
            logger.info(f"模拟启动成功: {simulation_id}, pid={process.pid}, platform={platform}")
            
        except Exception as e:
            cleanup_errors = []
            if process is not None and process.poll() is None:
                try:
                    cls._terminate_process(process, simulation_id)
                except Exception as error:
                    cleanup_errors.append(f"子程序停止未完成 ({type(error).__name__})")
            cls._processes.pop(simulation_id, None)
            cls._monitor_threads.pop(simulation_id, None)
            cls._action_queues.pop(simulation_id, None)
            cls._stdout_files.pop(simulation_id, None)
            cls._stderr_files.pop(simulation_id, None)
            if main_log_file is not None:
                try:
                    main_log_file.close()
                except Exception as error:
                    cleanup_errors.append(f"紀錄關閉未完成 ({type(error).__name__})")
            if cls._graph_memory_enabled.get(simulation_id, False):
                try:
                    ZepGraphMemoryManager.stop_updater(simulation_id)
                    cls._graph_memory_enabled.pop(simulation_id, None)
                except Exception as error:
                    cleanup_errors.append(f"圖譜寫入清理未完成 ({type(error).__name__})")
            state.runner_status = RunnerStatus.FAILED
            state.twitter_running = False
            state.reddit_running = False
            state.error = f"執行啟動未完成 ({type(e).__name__})。"
            if cleanup_errors:
                state.error += "; " + "; ".join(cleanup_errors)
            with cls._finalization_lock(simulation_id):
                cls._save_run_state(state)
                cls._sync_simulation_status(
                    simulation_id,
                    RunnerStatus.FAILED,
                    state.error,
                )
            raise RuntimeError(state.error) from None
        
        return state
    
    @classmethod
    def _monitor_simulation(cls, simulation_id: str, locale: str = 'zh'):
        """监控模拟进程，解析动作日志"""
        set_locale(locale)
        sim_dir = cls._simulation_dir(simulation_id)
        
        # 新的日志结构：分平台的动作日志
        twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        
        process = cls._processes.get(simulation_id)
        state = cls.get_run_state(simulation_id)
        
        if not process or not state:
            return
        
        twitter_position = 0
        reddit_position = 0
        
        monitor_error: Exception | None = None
        exit_code: int | None = None
        try:
            while process.poll() is None:  # 进程仍在运行
                # 读取 Twitter 动作日志
                if os.path.exists(twitter_actions_log):
                    twitter_position = cls._read_action_log(
                        twitter_actions_log, twitter_position, state, "twitter"
                    )
                
                # 读取 Reddit 动作日志
                if os.path.exists(reddit_actions_log):
                    reddit_position = cls._read_action_log(
                        reddit_actions_log, reddit_position, state, "reddit"
                    )

                # The producer deliberately stays alive for interviews after
                # emitting all platform end markers. Drain its accepted graph
                # episodes now; waiting for process exit would block reports
                # forever and force users to close the interview environment.
                if cls._check_all_platforms_completed(state):
                    with cls._finalization_lock(simulation_id):
                        if state.runner_status in {
                            RunnerStatus.STARTING,
                            RunnerStatus.RUNNING,
                            RunnerStatus.PAUSED,
                        } and simulation_id not in cls._manual_stop_requests:
                            cls._finish_run(state, RunnerStatus.COMPLETED)
                
                # 更新状态
                if state.run_id and state.worker_id != WORKER_ID:
                    raise RuntimeError('Execution ownership changed')
                cls._save_run_state(state)
                time.sleep(2)
            
            # 进程结束后，最后读取一次日志
            if os.path.exists(twitter_actions_log):
                cls._read_action_log(twitter_actions_log, twitter_position, state, "twitter")
            if os.path.exists(reddit_actions_log):
                cls._read_action_log(reddit_actions_log, reddit_position, state, "reddit")
            
            exit_code = process.returncode
            
        except Exception as e:
            logger.error('监控线程异常: %s, error=%s', simulation_id, type(e).__name__)
            monitor_error = e
        
        finally:
            # Manual stop and natural completion can observe the same process
            # exit. Serialize terminal state and updater drain so only one path
            # owns the final result.
            with cls._finalization_lock(simulation_id):
                latest_state = cls.get_run_state(simulation_id)
                if latest_state is not None:
                    state = latest_state

                if state.runner_status not in {
                    RunnerStatus.STOPPED,
                    RunnerStatus.FAILED,
                    RunnerStatus.COMPLETED,
                    RunnerStatus.INTERRUPTED,
                    RunnerStatus.NEEDS_REVIEW,
                }:
                    manual_stop = simulation_id in cls._manual_stop_requests
                    desired_status = (
                        RunnerStatus.STOPPED
                        if manual_stop
                        else RunnerStatus.COMPLETED
                    )
                    error_message = None
                    if not manual_stop and monitor_error is not None:
                        desired_status = RunnerStatus.FAILED
                        error_message = f"執行監控未完成 ({type(monitor_error).__name__})。"
                    elif not manual_stop and exit_code != 0:
                        desired_status = RunnerStatus.FAILED
                        error_message = f"執行程序未正常完成，退出碼：{exit_code}。內部紀錄未包含於公開資料。"

                    cls._finish_run(state, desired_status, error_message)
                cls._manual_stop_requests.discard(simulation_id)
            
            # 清理进程资源
            cls._processes.pop(simulation_id, None)
            cls._action_queues.pop(simulation_id, None)
            cls._monitor_threads.pop(simulation_id, None)
            
            # 关闭日志文件句柄
            if simulation_id in cls._stdout_files:
                try:
                    cls._stdout_files[simulation_id].close()
                except Exception:
                    pass
                cls._stdout_files.pop(simulation_id, None)
            if simulation_id in cls._stderr_files and cls._stderr_files[simulation_id]:
                try:
                    cls._stderr_files[simulation_id].close()
                except Exception:
                    pass
                cls._stderr_files.pop(simulation_id, None)
    
    @classmethod
    def _finish_run(cls, state, desired_status, error_message=None):
        """Publish a terminal result under the simulation finalization lock."""
        simulation_id = state.simulation_id
        state.graph_ready = False
        if desired_status == RunnerStatus.COMPLETED and not cls._check_all_platforms_completed(state):
            desired_status = RunnerStatus.FAILED
            error_message = 'The process exited without valid completion receipts for every selected platform.'
        state.twitter_running = False
        state.reddit_running = False
        # 图谱写入完成与模拟循环完成分开保存：只有确实要求更新且 updater
        # 干净收尾时，才能宣告图谱就绪。
        graph_update_status = 'not_requested'
        if cls._graph_memory_enabled.get(simulation_id, False):
            state.runner_status = RunnerStatus.FINALIZING
            cls._save_run_state(state)
            cls._sync_simulation_status(simulation_id, RunnerStatus.FINALIZING)
            try:
                ZepGraphMemoryManager.stop_updater(simulation_id)
                cls._graph_memory_enabled.pop(simulation_id, None)
                graph_update_status = 'confirmed'
                logger.info("图谱记忆写入完成: simulation_id=%s", simulation_id)
            except Exception as error:
                graph_update_status = 'failed'
                logger.error('停止图谱记忆更新器失败: %s', type(error).__name__)
                desired_status = RunnerStatus.FAILED
                error_message = f"圖譜寫入未完整完成 ({type(error).__name__})。"
        state.runner_status = desired_status
        state.graph_update_status = graph_update_status
        state.graph_ready = bool(
            desired_status == RunnerStatus.COMPLETED
            and state.run_id
            and state.attempt_id
            and graph_update_status == 'confirmed'
        )
        state.error = error_message
        state.completed_at = datetime.now().isoformat()
        cls._save_run_state(state)
        cls._sync_simulation_status(simulation_id, desired_status, error_message)
        logger.info("模拟完成状态: %s, status=%s", simulation_id, desired_status.value)

    @classmethod
    def _read_action_log(
        cls, 
        log_path: str, 
        position: int, 
        state: SimulationRunState,
        platform: str
    ) -> int:
        """
        读取动作日志文件
        
        Args:
            log_path: 日志文件路径
            position: 上次读取位置
            state: 运行状态对象
            platform: 平台名称 (twitter/reddit)
            
        Returns:
            新的读取位置
        """
        # 检查是否启用了图谱记忆更新
        graph_memory_enabled = cls._graph_memory_enabled.get(state.simulation_id, False)
        graph_updater = None
        if graph_memory_enabled:
            graph_updater = ZepGraphMemoryManager.get_updater(state.simulation_id)
        
        try:
            # 位元组位移追踪：只消费完整行（以 \n 结尾），未完成的尾行保留
            # 在原位移，补齐后再读取一次，不重复写入事件。游标只在整行
            # 成功处理、或已留下可见缺口之后才前进：解析失败（超长整数
            # ValueError、过深嵌套 RecursionError 也算损毁完整行）与处理
            # 异常都不得带着已前进的游标跳过未记录的行。
            with open(log_path, 'rb') as f:
                f.seek(position)
                while True:
                    line = f.readline()
                    if not line or not line.endswith(b'\n'):
                        return position
                    line_offset = position
                    next_position = position + len(line)
                    if not line.strip():
                        position = next_position
                        continue
                    try:
                        action_data = json.loads(line.decode('utf-8'))
                    except UnicodeDecodeError:
                        cls._record_log_gap(state, platform, line_offset, 'utf8_decode_error')
                        position = next_position
                        continue
                    except (ValueError, RecursionError):  # JSONDecodeError 即 ValueError 子类
                        cls._record_log_gap(state, platform, line_offset, 'json_decode_error')
                        position = next_position
                        continue
                    if not isinstance(action_data, dict):
                        cls._record_log_gap(state, platform, line_offset, 'not_a_json_object')
                        position = next_position
                        continue
                    if state.run_id and (
                        action_data.get('run_id') != state.run_id
                        or action_data.get('attempt_id') != state.attempt_id
                    ):
                        position = next_position
                        continue
                    try:
                        cls._ingest_action_data(state, platform, graph_updater, action_data)
                    except Exception as error:  # 跳过的事件必须留下可见缺口
                        cls._record_log_gap(state, platform, line_offset,
                                            f'processing_error:{type(error).__name__}')
                    position = next_position
        except Exception as e:
            logger.warning(f"读取动作日志失败: {log_path}, error={e}")
            return position

    @classmethod
    def _ingest_action_data(cls, state: SimulationRunState, platform: str, graph_updater, action_data: Dict[str, Any]):
        """处理一条完整事件记录；抛出的错误由调用者记成可见缺口。"""
        # 处理事件类型的条目
        if "event_type" in action_data:
            event_type = action_data.get("event_type")

            # 检测 simulation_end 事件，标记平台已完成
            if event_type == "simulation_end":
                total_rounds = action_data.get("total_rounds")
                planned_rounds = action_data.get("planned_rounds")
                exit_reason = action_data.get("exit_reason")
                # 回条必须证明自然跑完计划轮数：提前退出（外部
                # SIGTERM/SIGINT）不得被视为正常完成。
                # 旧格式回条（完全没有 exit_reason 与 planned_rounds 两栏，
                # 无法区分自然完成与被终止后的补写）沿用历史行为视为完成；
                # 只要出现其中一栏，就必须是完整的新格式完成证明。
                legacy_receipt = 'exit_reason' not in action_data and 'planned_rounds' not in action_data
                new_receipt_complete = (
                    exit_reason == "completed"
                    and isinstance(total_rounds, int) and not isinstance(total_rounds, bool)
                    and isinstance(planned_rounds, int) and not isinstance(planned_rounds, bool)
                    and total_rounds == planned_rounds
                )
                receipt_complete = legacy_receipt or new_receipt_complete
                if platform == "twitter":
                    state.twitter_running = False
                elif platform == "reddit":
                    state.reddit_running = False
                if not receipt_complete:
                    logger.warning(
                        "平台结束回条未证明正常完成，平台保持未完成: "
                        "platform=%s, exit_reason=%s, total_rounds=%s, planned_rounds=%s",
                        platform, exit_reason, total_rounds, planned_rounds,
                    )
                elif platform == "twitter":
                    state.twitter_completed = True
                    logger.info(f"Twitter 模拟已完成: {state.simulation_id}, total_rounds={total_rounds}, total_actions={action_data.get('total_actions')}")
                elif platform == "reddit":
                    state.reddit_completed = True
                    logger.info(f"Reddit 模拟已完成: {state.simulation_id}, total_rounds={total_rounds}, total_actions={action_data.get('total_actions')}")
                else:
                    return

                # 检查是否所有启用的平台都已完成
                # 如果只运行了一个平台，只检查那个平台
                # 如果运行了两个平台，需要两个都完成
                if receipt_complete and cls._check_all_platforms_completed(state):
                    # The monitor publishes the terminal
                    # status after ingestion has drained,
                    # while retaining the interview process.
                    logger.info(
                        f"所有平台已结束，等待图谱写入完成: "
                        f"{state.simulation_id}"
                    )

            # 更新轮次信息（从 round_end 事件）
            elif event_type == "round_end":
                round_num = action_data.get("round", 0)
                if not isinstance(round_num, int):
                    round_num = 0
                simulated_hours = action_data.get("simulated_hours")
                hours_present = (
                    isinstance(simulated_hours, (int, float))
                    and not isinstance(simulated_hours, bool)
                )

                # 更新各平台独立的轮次和时间
                if platform == "twitter":
                    if round_num > state.twitter_current_round:
                        state.twitter_current_round = round_num
                    if hours_present:
                        state.twitter_simulated_hours = simulated_hours
                elif platform == "reddit":
                    if round_num > state.reddit_current_round:
                        state.reddit_current_round = round_num
                    if hours_present:
                        state.reddit_simulated_hours = simulated_hours

                # 总体轮次取两个平台的最大值
                if round_num > state.current_round:
                    state.current_round = round_num
                # 总体时间取两个平台的最大值；旧资料缺栏时保留原值
                if hours_present:
                    state.simulated_hours = max(state.twitter_simulated_hours, state.reddit_simulated_hours)

            return

        action = AgentAction(
            round_num=action_data.get("round", 0),
            timestamp=action_data.get("timestamp", datetime.now().isoformat()),
            platform=platform,
            agent_id=action_data.get("agent_id", 0),
            agent_name=action_data.get("agent_name", ""),
            action_type=action_data.get("action_type", ""),
            action_args=action_data.get("action_args", {}),
            result=action_data.get("result"),
            success=action_data.get("success", True),
        )
        state.add_action(action)

        # 更新轮次
        if action.round_num and action.round_num > state.current_round:
            state.current_round = action.round_num

        # 如果启用了图谱记忆更新，将活动发送到Zep
        if graph_updater:
            graph_updater.add_activity_from_dict(action_data, platform)

    @staticmethod
    def _record_log_gap(state: SimulationRunState, platform: str, offset: int, reason: str):
        """记录被跳过的损毁完整行，状态栏位可见，不静默视为完整输入。"""
        state.log_gaps.append({'platform': platform, 'offset': offset, 'reason': reason})
        del state.log_gaps[:-20]
        logger.warning(
            "动作日志缺口（完整行无法解析）: platform=%s, offset=%s, reason=%s",
            platform, offset, reason,
        )
    
    @classmethod
    def _check_all_platforms_completed(cls, state: SimulationRunState) -> bool:
        """
        检查所有启用的平台是否都已完成模拟
        
        通过检查对应的 actions.jsonl 文件是否存在来判断平台是否被启用
        
        Returns:
            True 如果所有启用的平台都已完成
        """
        platforms = state.enabled_platforms
        return bool(platforms) and all(
            platform in {'twitter', 'reddit'} and getattr(state, f'{platform}_completed', False)
            for platform in platforms
        )
    
    @classmethod
    def _terminate_process(cls, process: subprocess.Popen, simulation_id: str, timeout: int = 10):
        """
        跨平台终止进程及其子进程
        
        Args:
            process: 要终止的进程
            simulation_id: 模拟ID（用于日志）
            timeout: 等待进程退出的超时时间（秒）
        """
        if IS_WINDOWS:
            # Windows: 使用 taskkill 命令终止进程树
            # /F = 强制终止, /T = 终止进程树（包括子进程）
            logger.info(f"终止进程树 (Windows): simulation={simulation_id}, pid={process.pid}")
            try:
                # 先尝试优雅终止
                subprocess.run(
                    ['taskkill', '/PID', str(process.pid), '/T'],
                    capture_output=True,
                    timeout=5
                )
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # 强制终止
                    logger.warning(f"进程未响应，强制终止: {simulation_id}")
                    subprocess.run(
                        ['taskkill', '/F', '/PID', str(process.pid), '/T'],
                        capture_output=True,
                        timeout=5
                    )
                    process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"taskkill 失败，尝试 terminate: {e}")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        else:
            # Unix: 使用进程组终止
            # 由于使用了 start_new_session=True，进程组 ID 等于主进程 PID
            pgid = os.getpgid(process.pid)
            logger.info(f"终止进程组 (Unix): simulation={simulation_id}, pgid={pgid}")
            
            # 先发送 SIGTERM 给整个进程组
            os.killpg(pgid, signal.SIGTERM)
            
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # 如果超时后还没结束，强制发送 SIGKILL
                logger.warning(f"进程组未响应 SIGTERM，强制终止: {simulation_id}")
                os.killpg(pgid, signal.SIGKILL)
                process.wait(timeout=5)
    
    @classmethod
    def stop_simulation(cls, simulation_id: str) -> SimulationRunState:
        """停止模拟"""
        with cls._finalization_lock(simulation_id):
            state = cls.get_run_state(simulation_id)
            if not state:
                raise ValueError(f"模拟不存在: {simulation_id}")
            if state.runner_status == RunnerStatus.STOPPED:
                return state
            if state.runner_status == RunnerStatus.COMPLETED and simulation_id not in cls._processes:
                return state
            if state.runner_status in {RunnerStatus.INTERRUPTED, RunnerStatus.NEEDS_REVIEW}:
                raise RuntimeError('Execution ownership is unresolved; create a new simulation.')
            if state.worker_id != WORKER_ID and worker_alive(state.owner) is True:
                raise RuntimeError('This execution belongs to another active worker; its state was preserved.')
            if state.worker_id != WORKER_ID or worker_alive(state.owner) is not True:
                alive = worker_alive(state.owner)
                state.runner_status = RunnerStatus.INTERRUPTED if alive is False else RunnerStatus.NEEDS_REVIEW
                state.graph_ready = False
                state.error = 'Execution owner cannot be verified; no process was signalled.'
                cls._save_run_state(state)
                raise RuntimeError(state.error)
            if state.runner_status == RunnerStatus.COMPLETED:
                process = cls._processes.get(simulation_id)
                if process and process.poll() is None:
                    cls._terminate_process(process, simulation_id)
                return state
            if state.runner_status == RunnerStatus.FAILED:
                process = cls._processes.get(simulation_id)
                if process and process.poll() is None:
                    cls._terminate_process(process, simulation_id)
                raise RuntimeError(state.error or 'The failed execution is preserved; create a new simulation.')

            pending_updater = ZepGraphMemoryManager.get_updater(simulation_id)
            retrying_finalization = (
                pending_updater is not None
                and state.runner_status in {
                    RunnerStatus.STOPPING,
                    RunnerStatus.FINALIZING,
                }
            )
            if (
                state.runner_status not in [
                    RunnerStatus.STARTING,
                    RunnerStatus.RUNNING,
                    RunnerStatus.PAUSED,
                    RunnerStatus.STOPPING,
                    RunnerStatus.FINALIZING,
                    RunnerStatus.COMPLETED,
                ]
                and not retrying_finalization
            ):
                raise ValueError(
                    f"模拟未在运行: {simulation_id}, status={state.runner_status}"
                )

            state.runner_status = RunnerStatus.STOPPING
            cls._manual_stop_requests.add(simulation_id)
            cls._save_run_state(state)
            cls._sync_simulation_status(simulation_id, RunnerStatus.STOPPING)

            # 终止进程
            process = cls._processes.get(simulation_id)
            if process and process.poll() is None:
                try:
                    cls._terminate_process(process, simulation_id)
                except ProcessLookupError:
                    pass
                except Exception as e:
                    logger.error(f"终止进程组失败: {simulation_id}, error={e}")
                    try:
                        process.terminate()
                        process.wait(timeout=5)
                    except Exception:
                        process.kill()

        # Let the monitor consume the final action-log tail and own the single
        # updater drain. It will publish STOPPED (rather than COMPLETED) because
        # the manual-stop marker is set above.
        monitor = cls._monitor_threads.get(simulation_id)
        if (
            not retrying_finalization
            and
            monitor is not None
            and monitor is not threading.current_thread()
            and monitor.is_alive()
        ):
            wait_timeout = max(
                30.0,
                ZEP_INGESTION_WAIT_TIMEOUT_SECONDS
                + ZEP_HTTP_REQUEST_TIMEOUT_SECONDS
                + 5,
            )
            monitor.join(timeout=wait_timeout)
            if monitor.is_alive():
                # The monitor still owns finalization and may be inside one
                # bounded HTTP request. Do not block on or overwrite its lock;
                # leave the observable state as STOPPING and let polling expose
                # the eventual STOPPED/FAILED result.
                raise SimulationStopPending(
                    f"模拟仍在停止中，图谱写入未在 {wait_timeout:.0f}s 内完成"
                )
        else:
            # Restart recovery or tests may have no monitor thread. Complete
            # the same barrier synchronously in this request.
            with cls._finalization_lock(simulation_id):
                state = cls.get_run_state(simulation_id) or state
                if cls._graph_memory_enabled.get(simulation_id, False):
                    try:
                        ZepGraphMemoryManager.stop_updater(simulation_id)
                        cls._graph_memory_enabled.pop(simulation_id, None)
                    except Exception as error:
                        state.runner_status = RunnerStatus.FAILED
                        state.twitter_running = False
                        state.reddit_running = False
                        state.completed_at = datetime.now().isoformat()
                        state.error = f"圖譜寫入未完整完成 ({type(error).__name__})。"
                        cls._save_run_state(state)
                        cls._sync_simulation_status(
                            simulation_id,
                            RunnerStatus.FAILED,
                            state.error,
                        )
                        raise RuntimeError(state.error) from None
                state.runner_status = RunnerStatus.STOPPED
                state.twitter_running = False
                state.reddit_running = False
                state.completed_at = datetime.now().isoformat()
                state.error = None
                cls._save_run_state(state)
                cls._sync_simulation_status(
                    simulation_id,
                    RunnerStatus.STOPPED,
                )
                cls._manual_stop_requests.discard(simulation_id)

        state = cls.get_run_state(simulation_id) or state
        if state.runner_status == RunnerStatus.FAILED:
            raise RuntimeError(state.error or "模拟停止失败")
        if state.runner_status != RunnerStatus.STOPPED:
            raise RuntimeError(
                f"模拟停止未达到终态: {simulation_id}, status={state.runner_status}"
            )

        logger.info(f"模拟已停止: {simulation_id}")
        return state

    @classmethod
    def _read_actions_from_file(
        cls,
        file_path: str,
        default_platform: Optional[str] = None,
        platform_filter: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        从单个动作文件中读取动作
        
        Args:
            file_path: 动作日志文件路径
            default_platform: 默认平台（当动作记录中没有 platform 字段时使用）
            platform_filter: 过滤平台
            agent_id: 过滤 Agent ID
            round_num: 过滤轮次
        """
        if not os.path.exists(file_path):
            return []
        
        actions = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    
                    # 跳过非动作记录（如 simulation_start, round_start, round_end 等事件）
                    if "event_type" in data:
                        continue
                    
                    # 跳过没有 agent_id 的记录（非 Agent 动作）
                    if "agent_id" not in data:
                        continue
                    
                    # 获取平台：优先使用记录中的 platform，否则使用默认平台
                    record_platform = data.get("platform") or default_platform or ""
                    
                    # 过滤
                    if platform_filter and record_platform != platform_filter:
                        continue
                    if agent_id is not None and data.get("agent_id") != agent_id:
                        continue
                    if round_num is not None and data.get("round") != round_num:
                        continue
                    
                    actions.append(AgentAction(
                        round_num=data.get("round", 0),
                        timestamp=data.get("timestamp", ""),
                        platform=record_platform,
                        agent_id=data.get("agent_id", 0),
                        agent_name=data.get("agent_name", ""),
                        action_type=data.get("action_type", ""),
                        action_args=data.get("action_args", {}),
                        result=data.get("result"),
                        success=data.get("success", True),
                    ))
                    
                except json.JSONDecodeError:
                    continue
        
        return actions
    
    @classmethod
    def get_all_actions(
        cls,
        simulation_id: str,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        获取所有平台的完整动作历史（无分页限制）
        
        Args:
            simulation_id: 模拟ID
            platform: 过滤平台（twitter/reddit）
            agent_id: 过滤Agent
            round_num: 过滤轮次
            
        Returns:
            完整的动作列表（按时间戳排序，新的在前）
        """
        sim_dir = cls._simulation_dir(simulation_id)
        actions = []
        
        # 读取 Twitter 动作文件（根据文件路径自动设置 platform 为 twitter）
        twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        if not platform or platform == "twitter":
            actions.extend(cls._read_actions_from_file(
                twitter_actions_log,
                default_platform="twitter",  # 自动填充 platform 字段
                platform_filter=platform,
                agent_id=agent_id, 
                round_num=round_num
            ))
        
        # 读取 Reddit 动作文件（根据文件路径自动设置 platform 为 reddit）
        reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        if not platform or platform == "reddit":
            actions.extend(cls._read_actions_from_file(
                reddit_actions_log,
                default_platform="reddit",  # 自动填充 platform 字段
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            ))
        
        # 如果分平台文件不存在，尝试读取旧的单一文件格式
        if not actions:
            actions_log = os.path.join(sim_dir, "actions.jsonl")
            actions = cls._read_actions_from_file(
                actions_log,
                default_platform=None,  # 旧格式文件中应该有 platform 字段
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            )
        
        # 按时间戳排序（新的在前）
        actions.sort(key=lambda x: x.timestamp, reverse=True)
        
        return actions
    
    @classmethod
    def get_actions(
        cls,
        simulation_id: str,
        limit: int = 100,
        offset: int = 0,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        获取动作历史（带分页）
        
        Args:
            simulation_id: 模拟ID
            limit: 返回数量限制
            offset: 偏移量
            platform: 过滤平台
            agent_id: 过滤Agent
            round_num: 过滤轮次
            
        Returns:
            动作列表
        """
        actions = cls.get_all_actions(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )
        
        # 分页
        return actions[offset:offset + limit]
    
    @classmethod
    def get_timeline(
        cls,
        simulation_id: str,
        start_round: int = 0,
        end_round: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取模拟时间线（按轮次汇总）
        
        Args:
            simulation_id: 模拟ID
            start_round: 起始轮次
            end_round: 结束轮次
            
        Returns:
            每轮的汇总信息
        """
        actions = cls.get_actions(simulation_id, limit=10000)
        
        # 按轮次分组
        rounds: Dict[int, Dict[str, Any]] = {}
        
        for action in actions:
            round_num = action.round_num
            
            if round_num < start_round:
                continue
            if end_round is not None and round_num > end_round:
                continue
            
            if round_num not in rounds:
                rounds[round_num] = {
                    "round_num": round_num,
                    "twitter_actions": 0,
                    "reddit_actions": 0,
                    "active_agents": set(),
                    "action_types": {},
                    "first_action_time": action.timestamp,
                    "last_action_time": action.timestamp,
                }
            
            r = rounds[round_num]
            
            if action.platform == "twitter":
                r["twitter_actions"] += 1
            else:
                r["reddit_actions"] += 1
            
            r["active_agents"].add(action.agent_id)
            r["action_types"][action.action_type] = r["action_types"].get(action.action_type, 0) + 1
            r["last_action_time"] = action.timestamp
        
        # 转换为列表
        result = []
        for round_num in sorted(rounds.keys()):
            r = rounds[round_num]
            result.append({
                "round_num": round_num,
                "twitter_actions": r["twitter_actions"],
                "reddit_actions": r["reddit_actions"],
                "total_actions": r["twitter_actions"] + r["reddit_actions"],
                "active_agents_count": len(r["active_agents"]),
                "active_agents": list(r["active_agents"]),
                "action_types": r["action_types"],
                "first_action_time": r["first_action_time"],
                "last_action_time": r["last_action_time"],
            })
        
        return result
    
    @classmethod
    def get_agent_stats(cls, simulation_id: str) -> List[Dict[str, Any]]:
        """
        获取每个Agent的统计信息
        
        Returns:
            Agent统计列表
        """
        actions = cls.get_actions(simulation_id, limit=10000)
        
        agent_stats: Dict[int, Dict[str, Any]] = {}
        
        for action in actions:
            agent_id = action.agent_id
            
            if agent_id not in agent_stats:
                agent_stats[agent_id] = {
                    "agent_id": agent_id,
                    "agent_name": action.agent_name,
                    "total_actions": 0,
                    "twitter_actions": 0,
                    "reddit_actions": 0,
                    "action_types": {},
                    "first_action_time": action.timestamp,
                    "last_action_time": action.timestamp,
                }
            
            stats = agent_stats[agent_id]
            stats["total_actions"] += 1
            
            if action.platform == "twitter":
                stats["twitter_actions"] += 1
            else:
                stats["reddit_actions"] += 1
            
            stats["action_types"][action.action_type] = stats["action_types"].get(action.action_type, 0) + 1
            stats["last_action_time"] = action.timestamp
        
        # 按总动作数排序
        result = sorted(agent_stats.values(), key=lambda x: x["total_actions"], reverse=True)
        
        return result
    
    @classmethod
    def cleanup_simulation_logs(cls, simulation_id: str) -> Dict[str, Any]:
        """Execution history is immutable; another attempt needs a new identity."""
        return {"success": False, "cleaned_files": [],
                "errors": ["Existing execution data cannot be cleared; clone the simulation instead."]}

    # 防止重复清理的标志
    _cleanup_done = False
    
    @classmethod
    def cleanup_all_simulations(cls):
        """
        清理所有运行中的模拟进程
        
        在服务器关闭时调用，确保所有子进程被终止
        """
        # 防止重复清理
        if cls._cleanup_done:
            return
        cls._cleanup_done = True

        updater_ids = set(ZepGraphMemoryManager.get_simulation_ids())
        simulation_ids = sorted(
            set(cls._processes)
            | set(cls._graph_memory_enabled)
            | updater_ids
        )
        if not simulation_ids:
            return

        logger.info("正在安全完成所有模拟进程与图谱写入...")
        cleanup_failed = False

        # Each simulation follows the normal stop/finalization path: terminate
        # its producer, let the monitor consume the final action-log tail, and
        # only then drain Zep. This avoids dropping actions emitted during
        # SIGTERM handling.
        for simulation_id in simulation_ids:
            try:
                state = cls.get_run_state(simulation_id)
                updater = ZepGraphMemoryManager.get_updater(simulation_id)
                process = cls._processes.get(simulation_id)

                if state is None:
                    # Missing/corrupt state is exceptional, but retain the
                    # critical producer-before-consumer shutdown ordering.
                    if process is not None and process.poll() is None:
                        cls._terminate_process(process, simulation_id, timeout=5)
                    if updater is not None:
                        ZepGraphMemoryManager.stop_updater(simulation_id)
                    continue

                if updater is not None:
                    cls._graph_memory_enabled[simulation_id] = True
                    if state.runner_status in {
                        RunnerStatus.IDLE,
                        RunnerStatus.STOPPED,
                        RunnerStatus.COMPLETED,
                    }:
                        # Preserve the uncertainty; a terminal claim cannot be
                        # resurrected into a successful stop during shutdown.
                        state.runner_status = RunnerStatus.NEEDS_REVIEW
                        state.graph_ready = False
                        state.error = 'A terminal execution still has unresolved graph writes.'
                        cls._save_run_state(state)
                        cls._sync_simulation_status(
                            simulation_id,
                            RunnerStatus.NEEDS_REVIEW,
                            state.error,
                        )

                needs_finalization = bool(
                    (process is not None and process.poll() is None)
                    or updater is not None
                    or state.runner_status in {
                        RunnerStatus.STARTING,
                        RunnerStatus.RUNNING,
                        RunnerStatus.PAUSED,
                        RunnerStatus.STOPPING,
                        RunnerStatus.FINALIZING,
                    }
                )
                if needs_finalization:
                    cls.stop_simulation(simulation_id)

                # A recovery path without a monitor does not run the monitor's
                # resource cleanup block. Release only successfully stopped
                # resources; FAILED/STOPPING resources remain retryable.
                latest = cls.get_run_state(simulation_id)
                if latest and latest.runner_status == RunnerStatus.STOPPED:
                    stopped_process = cls._processes.get(simulation_id)
                    if stopped_process is None or stopped_process.poll() is not None:
                        cls._processes.pop(simulation_id, None)
                        cls._action_queues.pop(simulation_id, None)
                        cls._monitor_threads.pop(simulation_id, None)
                        for file_map in (cls._stdout_files, cls._stderr_files):
                            file_handle = file_map.pop(simulation_id, None)
                            if file_handle:
                                try:
                                    file_handle.close()
                                except Exception:
                                    pass
            except Exception as error:
                cleanup_failed = True
                logger.error(
                    "清理模拟失败，保留状态以便重试: simulation_id=%s, error=%s",
                    simulation_id,
                    error,
                )

        if cleanup_failed:
            # Retained updaters and FAILED run states continue to block report
            # generation and graph deletion. Permit an explicit retry.
            cls._cleanup_done = False
            logger.error("部分模拟未安全完成清理")
        else:
            logger.info("模拟进程与图谱写入清理完成")
    
    @classmethod
    def register_cleanup(cls):
        """
        注册清理函数
        
        在 Flask 应用启动时调用，确保服务器关闭时清理所有模拟进程
        """
        global _cleanup_registered
        
        if _cleanup_registered:
            return
        
        # Flask debug 模式下，只在 reloader 子进程中注册清理（实际运行应用的进程）
        # WERKZEUG_RUN_MAIN=true 表示是 reloader 子进程
        # 如果不是 debug 模式，则没有这个环境变量，也需要注册
        is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
        is_debug_mode = os.environ.get('FLASK_DEBUG') == '1' or os.environ.get('WERKZEUG_RUN_MAIN') is not None
        
        # 在 debug 模式下，只在 reloader 子进程中注册；非 debug 模式下始终注册
        if is_debug_mode and not is_reloader_process:
            _cleanup_registered = True  # 标记已注册，防止子进程再次尝试
            return
        
        # 保存原有的信号处理器
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        # SIGHUP 只在 Unix 系统存在（macOS/Linux），Windows 没有
        original_sighup = None
        has_sighup = hasattr(signal, 'SIGHUP')
        if has_sighup:
            original_sighup = signal.getsignal(signal.SIGHUP)
        
        def cleanup_handler(signum=None, frame=None):
            """信号处理器：先清理模拟进程，再调用原处理器"""
            # 只有在有进程需要清理时才打印日志
            if cls._processes or cls._graph_memory_enabled:
                logger.info(f"收到信号 {signum}，开始清理...")
            cls.cleanup_all_simulations()
            
            # 调用原有的信号处理器，让 Flask 正常退出
            if signum == signal.SIGINT and callable(original_sigint):
                original_sigint(signum, frame)
            elif signum == signal.SIGTERM and callable(original_sigterm):
                original_sigterm(signum, frame)
            elif has_sighup and signum == signal.SIGHUP:
                # SIGHUP: 终端关闭时发送
                if callable(original_sighup):
                    original_sighup(signum, frame)
                else:
                    # 默认行为：正常退出
                    sys.exit(0)
            else:
                # 如果原处理器不可调用（如 SIG_DFL），则使用默认行为
                raise KeyboardInterrupt
        
        # 注册 atexit 处理器（作为备用）
        atexit.register(cls.cleanup_all_simulations)
        
        # 注册信号处理器（仅在主线程中）
        try:
            # SIGTERM: kill 命令默认信号
            signal.signal(signal.SIGTERM, cleanup_handler)
            # SIGINT: Ctrl+C
            signal.signal(signal.SIGINT, cleanup_handler)
            # SIGHUP: 终端关闭（仅 Unix 系统）
            if has_sighup:
                signal.signal(signal.SIGHUP, cleanup_handler)
        except ValueError:
            # 不在主线程中，只能使用 atexit
            logger.warning("无法注册信号处理器（不在主线程），仅使用 atexit")
        
        _cleanup_registered = True
    
    @classmethod
    def get_running_simulations(cls) -> List[str]:
        """
        获取所有正在运行的模拟ID列表
        """
        running = []
        for sim_id, process in cls._processes.items():
            if process.poll() is None:
                running.append(sim_id)
        return running
    
    # ============== Interview 功能 ==============
    
    @classmethod
    def check_env_alive(cls, simulation_id: str) -> bool:
        """
        检查模拟环境是否存活（可以接收Interview命令）

        Args:
            simulation_id: 模拟ID

        Returns:
            True 表示环境存活，False 表示环境已关闭
        """
        sim_dir = cls._simulation_dir(simulation_id)
        if not os.path.exists(sim_dir):
            return False
        # A recent heartbeat can outlive the producer. Only this worker's
        # retained Popen handle proves it still owns a live command consumer.
        # After a restart/foreign worker, history remains readable but new
        # commands fail closed instead of guessing from a PID or stale file.
        process = cls._processes.get(simulation_id)
        if process is None or process.poll() is not None:
            return False
        ipc_client = SimulationIPCClient(sim_dir)
        return ipc_client.check_env_alive()

    @classmethod
    def get_env_status_detail(cls, simulation_id: str) -> Dict[str, Any]:
        """
        获取模拟环境的详细状态信息

        Args:
            simulation_id: 模拟ID

        Returns:
            状态详情字典，包含 status, twitter_available, reddit_available, timestamp
        """
        sim_dir = cls._simulation_dir(simulation_id)
        status_file = os.path.join(sim_dir, "env_status.json")
        
        default_status = {
            "status": "stopped",
            "twitter_available": False,
            "reddit_available": False,
            "timestamp": None
        }
        
        if not os.path.exists(status_file):
            return default_status
        
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            if not cls.check_env_alive(simulation_id):
                return default_status
            return {
                "status": status.get("status", "stopped"),
                "twitter_available": status.get("twitter_available", False),
                "reddit_available": status.get("reddit_available", False),
                "timestamp": status.get("timestamp")
            }
        except (json.JSONDecodeError, OSError):
            return default_status

    @classmethod
    def interview_agent(
        cls,
        simulation_id: str,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """
        采访单个Agent

        Args:
            simulation_id: 模拟ID
            agent_id: Agent ID
            prompt: 采访问题
            platform: 指定平台（可选）
                - "twitter": 只采访Twitter平台
                - "reddit": 只采访Reddit平台
                - None: 双平台模拟时同时采访两个平台，返回整合结果
            timeout: 超时时间（秒）

        Returns:
            采访结果字典

        Raises:
            ValueError: 模拟不存在或环境未运行
            TimeoutError: 等待响应超时
        """
        sim_dir = cls._simulation_dir(simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"模拟不存在: {simulation_id}")

        if not cls.check_env_alive(simulation_id):
            raise ValueError(f"模拟环境未运行或已关闭，无法执行Interview: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        logger.info(f"发送Interview命令: simulation_id={simulation_id}, agent_id={agent_id}, platform={platform}")

        response = ipc_client.send_interview(
            agent_id=agent_id,
            prompt=prompt,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "agent_id": agent_id,
                "prompt": prompt,
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "agent_id": agent_id,
                "prompt": prompt,
                "error": response.error,
                "timestamp": response.timestamp
            }
    
    @classmethod
    def interview_agents_batch(
        cls,
        simulation_id: str,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> Dict[str, Any]:
        """
        批量采访多个Agent

        Args:
            simulation_id: 模拟ID
            interviews: 采访列表，每个元素包含 {"agent_id": int, "prompt": str, "platform": str(可选)}
            platform: 默认平台（可选，会被每个采访项的platform覆盖）
                - "twitter": 默认只采访Twitter平台
                - "reddit": 默认只采访Reddit平台
                - None: 双平台模拟时每个Agent同时采访两个平台
            timeout: 超时时间（秒）

        Returns:
            批量采访结果字典

        Raises:
            ValueError: 模拟不存在或环境未运行
            TimeoutError: 等待响应超时
        """
        sim_dir = cls._simulation_dir(simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"模拟不存在: {simulation_id}")

        if not cls.check_env_alive(simulation_id):
            raise ValueError(f"模拟环境未运行或已关闭，无法执行Interview: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        logger.info(f"发送批量Interview命令: simulation_id={simulation_id}, count={len(interviews)}, platform={platform}")

        response = ipc_client.send_batch_interview(
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "interviews_count": len(interviews),
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "interviews_count": len(interviews),
                "error": response.error,
                "timestamp": response.timestamp
            }
    
    @classmethod
    def interview_all_agents(
        cls,
        simulation_id: str,
        prompt: str,
        platform: str = None,
        timeout: float = 180.0
    ) -> Dict[str, Any]:
        """
        采访所有Agent（全局采访）

        使用相同的问题采访模拟中的所有Agent

        Args:
            simulation_id: 模拟ID
            prompt: 采访问题（所有Agent使用相同问题）
            platform: 指定平台（可选）
                - "twitter": 只采访Twitter平台
                - "reddit": 只采访Reddit平台
                - None: 双平台模拟时每个Agent同时采访两个平台
            timeout: 超时时间（秒）

        Returns:
            全局采访结果字典
        """
        sim_dir = cls._simulation_dir(simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"模拟不存在: {simulation_id}")

        # 从配置文件获取所有Agent信息
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            raise ValueError(f"模拟配置不存在: {simulation_id}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        agent_configs = config.get("agent_configs", [])
        if not agent_configs:
            raise ValueError(f"模拟配置中没有Agent: {simulation_id}")

        # 构建批量采访列表
        interviews = []
        for agent_config in agent_configs:
            agent_id = agent_config.get("agent_id")
            if agent_id is not None:
                interviews.append({
                    "agent_id": agent_id,
                    "prompt": prompt
                })

        logger.info(f"发送全局Interview命令: simulation_id={simulation_id}, agent_count={len(interviews)}, platform={platform}")

        return cls.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )
    
    @classmethod
    def close_simulation_env(
        cls,
        simulation_id: str,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        关闭模拟环境（而不是停止模拟进程）
        
        向模拟发送关闭环境命令，使其优雅退出等待命令模式
        
        Args:
            simulation_id: 模拟ID
            timeout: 超时时间（秒）
            
        Returns:
            操作结果字典
        """
        sim_dir = cls._simulation_dir(simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"模拟不存在: {simulation_id}")
        
        ipc_client = SimulationIPCClient(sim_dir)
        
        if not ipc_client.check_env_alive():
            return {
                "success": True,
                "message": "环境已经关闭"
            }
        
        logger.info(f"发送关闭环境命令: simulation_id={simulation_id}")
        
        try:
            response = ipc_client.send_close_env(timeout=timeout)
            
            return {
                "success": response.status.value == "completed",
                "message": "环境关闭命令已发送",
                "result": response.result,
                "timestamp": response.timestamp
            }
        except TimeoutError:
            # 超时可能是因为环境正在关闭
            return {
                "success": True,
                "message": "环境关闭命令已发送（等待响应超时，环境可能正在关闭）"
            }
    
    @classmethod
    def _get_interview_history_from_db(
        cls,
        db_path: str,
        platform_name: str,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """从单个数据库获取Interview历史"""
        import sqlite3
        
        if not os.path.exists(db_path):
            return []
        
        results = []
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            if agent_id is not None:
                cursor.execute("""
                    SELECT user_id, info, created_at
                    FROM trace
                    WHERE action = 'interview' AND user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (agent_id, limit))
            else:
                cursor.execute("""
                    SELECT user_id, info, created_at
                    FROM trace
                    WHERE action = 'interview'
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            
            for user_id, info_json, created_at in cursor.fetchall():
                try:
                    info = json.loads(info_json) if info_json else {}
                except json.JSONDecodeError:
                    info = {"raw": info_json}
                
                results.append({
                    "agent_id": user_id,
                    "response": info.get("response", info),
                    "prompt": info.get("prompt", ""),
                    "timestamp": created_at,
                    "platform": platform_name
                })
            
            conn.close()
            
        except Exception as e:
            logger.error(f"读取Interview历史失败 ({platform_name}): {e}")
        
        return results

    @classmethod
    def get_interview_history(
        cls,
        simulation_id: str,
        platform: str = None,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取Interview历史记录（从数据库读取）
        
        Args:
            simulation_id: 模拟ID
            platform: 平台类型（reddit/twitter/None）
                - "reddit": 只获取Reddit平台的历史
                - "twitter": 只获取Twitter平台的历史
                - None: 获取两个平台的所有历史
            agent_id: 指定Agent ID（可选，只获取该Agent的历史）
            limit: 每个平台返回数量限制
            
        Returns:
            Interview历史记录列表
        """
        sim_dir = cls._simulation_dir(simulation_id)
        
        results = []
        
        # 确定要查询的平台
        if platform in ("reddit", "twitter"):
            platforms = [platform]
        else:
            # 不指定platform时，查询两个平台
            platforms = ["twitter", "reddit"]
        
        for p in platforms:
            db_path = os.path.join(sim_dir, f"{p}_simulation.db")
            platform_results = cls._get_interview_history_from_db(
                db_path=db_path,
                platform_name=p,
                agent_id=agent_id,
                limit=limit
            )
            results.extend(platform_results)
        
        # 按时间降序排序
        results = order_interview_history(results, sim_dir)
        
        # 如果查询了多个平台，限制总数
        if len(platforms) > 1 and len(results) > limit:
            results = results[:limit]
        
        return results
