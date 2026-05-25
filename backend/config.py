import os
from pathlib import Path

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