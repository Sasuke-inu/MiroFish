"""
MiroFish Backend - Flask应用工厂
"""

import os
import warnings

# 抑制 multiprocessing resource_tracker 的警告（来自第三方库如 transformers）
# 需要在所有其他导入之前设置
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Flask应用工厂函数"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # 设置JSON编码：确保中文直接显示（而不是 \uXXXX 格式）
    # Flask >= 2.3 使用 app.json.ensure_ascii，旧版本使用 JSON_AS_ASCII 配置
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False
    
    # 设置日志
    logger = setup_logger('mirofish')
    
    # 只在 reloader 子进程中打印启动信息（避免 debug 模式下打印两次）
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process
    
    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish Backend 启动中...")
        logger.info("=" * 50)
    
    # 启用CORS：only the local dev origins this project actually serves.
    # The vite proxy rewrites to localhost:5001 and the direct client runs on
    # localhost:3000; everything else must not receive CORS headers.
    from .api.request_guard import TRUSTED_ORIGINS
    CORS(app, resources={r"/api/(?!(?:settings|workbench)(?:/|$)).*": {"origins": list(TRUSTED_ORIGINS)}})
    
    # 注册模拟进程清理函数（确保服务器关闭时终止所有模拟进程）
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("已注册模拟进程清理函数")

    # Uniform local-only + CSRF guard for every /api route (blueprint-level
    # guards, where they exist, keep their own extra rules).
    from .api.request_guard import csrf_token, guard_api_request
    app.before_request(guard_api_request)

    @app.route('/api/session')
    def api_session():
        """Bootstrap endpoint: legacy clients fetch the CSRF token here."""
        return {'success': True, 'data': {'csrf_token': csrf_token()}}
    
    # 请求日志中间件
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"请求: {request.method} {request.path}")
        # Research content, assumptions and credentials stay out of general logs.
    
    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(f"响应: {response.status_code}")
        return response
    
    # 注册蓝图
    from .api import graph_bp, simulation_bp, report_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    from .api.sources import sources_bp
    app.register_blueprint(sources_bp, url_prefix='/api/sources')
    from .api.settings import settings_bp
    app.register_blueprint(settings_bp, url_prefix='/api/settings')
    from .api.workbench import workbench_bp
    app.register_blueprint(workbench_bp, url_prefix='/api/workbench')
    
    # 健康检查
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}

    @app.route('/api/system/status')
    def system_status():
        # Health is process liveness; readiness also needs the graph service.
        from .provider_settings import get_model_settings, SettingsError
        try:
            llm_configured = bool(get_model_settings(app.config).get('api_key'))
        except SettingsError:
            llm_configured = False
        graph_errors = Config.graph_configuration_errors(app.config)
        graph_configured = not graph_errors
        provider = app.config.get('GRAPH_PROVIDER', 'zep')
        missing = []
        if not llm_configured:
            missing.append('LLM_API_KEY')
        if graph_errors:
            missing.extend(error.split(' ')[0] for error in graph_errors)
        if graph_configured and provider == 'graphiti':
            import httpx
            try:
                response = httpx.get(app.config['GRAPHITI_BASE_URL'].rstrip('/') + '/health',
                                     timeout=3, trust_env=False)
                graph_configured = response.status_code == 200 and response.json().get('status') == 'ok'
            except (httpx.HTTPError, ValueError):
                graph_configured = False
            if not graph_configured:
                missing.append('GRAPHITI_SERVICE')
        return {
            'success': True,
            'data': {
                'ready': not missing,
                'llm_configured': llm_configured,
                'graph_configured': graph_configured,
                'missing': missing,
                **({'graph_provider': 'graphiti', 'embedding': 'local'} if provider == 'graphiti' else {}),
            },
        }
    
    if should_log_startup:
        logger.info("MiroFish Backend 启动完成")
    
    return app

