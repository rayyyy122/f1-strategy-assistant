import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Project root
BASE_DIR = Path(__file__).resolve().parent.parent

# DeepSeek API (OpenAI 兼容)
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or None
LLM_BASE_URL = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1"
LLM_MODEL = os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"

# FastF1 cache
FASTF1_CACHE_DIR = BASE_DIR / ".fastf1_cache"

# SQLite (长期记忆 + 轨迹)
DATABASE_PATH = BASE_DIR / "data" / "f1_strategy.db"

# Trace storage (RL)
TRACE_DIR = BASE_DIR / "data" / "traces"

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
LOG_DIR = BASE_DIR / "logs"

# Frontend access key (防止 /api 被公网蹭用；留空则不校验)
FRONTEND_API_KEY = os.getenv("FRONTEND_API_KEY") or None

# Brave Search API（可选；配置后 web_search 优先走 Brave，未配置走免费多源级联）
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY") or None