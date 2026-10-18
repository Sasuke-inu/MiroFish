"""\n配置管理\n统一从项目根目录的 .env 文件加载配置\n"""

import os
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
# 路径: MiroFish/.env (相对于 backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=False)
else:
    # 如果根目录没有 .env，尝试加载环境变量（用于生产环境）
    load_dotenv(override=False)


class Config:
    """Flask配置类"""
    
    # Flask配置
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # JSON配置 - 禁用ASCII转义，让中文直接显示
    JSON_AS_ASCII = False
    
    # LLM配置（统一使用OpenAI格式）
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    
    # Zep配置
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    # Keep Cloud available for existing installations; the local Compose uses Graphiti.
    GRAPH_PROVIDER = os.environ.get('GRAPH_PROVIDER', 'zep').strip().lower()
    GRAPHITI_BASE_URL = os.environ.get('GRAPHITI_BASE_URL', 'http://graphiti:5010')
    GRAPHITI_API_KEY = os.environ.get('GRAPHITI_API_KEY', '')

    # Optional input collection. The local integration never falls back to Cloud.
    FIRECRAWL_ENABLED = os.environ.get('FIRECRAWL_ENABLED', 'false').lower() == 'true'
    FIRECRAWL_BASE_URL = os.environ.get('FIRECRAWL_BASE_URL', 'http://127.0.0.1:3002')
    FIRECRAWL_API_KEY = os.environ.get('FIRECRAWL_API_KEY', '')
    FIRECRAWL_MAX_PAGES_PER_JOB = os.environ.get('FIRECRAWL_MAX_PAGES_PER_JOB', '3')
    FIRECRAWL_DAILY_PAGE_LIMIT = os.environ.get('FIRECRAWL_DAILY_PAGE_LIMIT', '10')
    FIRECRAWL_BUDGET_TIMEZONE = os.environ.get('FIRECRAWL_BUDGET_TIMEZONE', 'Australia/Sydney')

    @classmethod
    def graph_configuration_errors(cls, settings=None) -> list[str]:
        get = settings.get if settings is not None else lambda key, default=None: getattr(cls, key, default)
        provider = get('GRAPH_PROVIDER', 'zep')
        if provider == 'graphiti':
            return [f'{key} 未配置' for key in ('GRAPHITI_BASE_URL', 'GRAPHITI_API_KEY') if not get(key)]
        if provider != 'zep':
            return ['GRAPH_PROVIDER 必須是 graphiti 或 zep']
        errors = [] if get('ZEP_API_KEY') else ['ZEP_API_KEY 未配置']
        if os.environ.get('ZEP_API_URL'):
            errors.append('ZEP_API_URL 不受支持；Cloud 模式僅連接 Zep Cloud')
        return errors
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # 文本处理配置
    DEFAULT_CHUNK_SIZE = 500  # 默认切块大小
    DEFAULT_CHUNK_OVERLAP = 50  # 默认重叠大小
    
    # OASIS模拟配置
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASIS平台可用动作配置
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Report Agent配置
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    
    @classmethod
    def validate(cls) -> list[str]:
        """验证必要配置"""
        errors: list[str] = []
        from .provider_settings import get_model_settings, SettingsError
        try:
            current = get_model_settings({key: getattr(cls, key) for key in ('LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL_NAME', 'UPLOAD_FOLDER')})
            if not current.get('api_key'):
                errors.append("LLM_API_KEY 未配置")
        except SettingsError as error:
            errors.append(str(error))
        errors.extend(cls.graph_configuration_errors())
        if cls.DEBUG:
            import warnings
            warnings.warn("Flask DEBUG mode is enabled. Do not use in production.", RuntimeWarning)
        return errors
