"""DeepSeek API 客户端 (OpenAI 兼容)。"""

from openai import OpenAI
from .config import LLM_API_KEY, LLM_BASE_URL


def get_client() -> OpenAI:
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)