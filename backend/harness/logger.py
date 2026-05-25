"""全链路日志 + token 追踪 — 同时输出到终端和文件。"""

import logging
import sys
from pathlib import Path
from datetime import datetime

from ..config import LOG_LEVEL, LOG_DIR

# 确保日志目录存在
LOG_DIR.mkdir(parents=True, exist_ok=True)

_loggers: dict[str, logging.Logger] = {}
_file_handler: logging.FileHandler | None = None


def _get_file_handler() -> logging.FileHandler:
    global _file_handler
    if _file_handler is None:
        log_file = LOG_DIR / f"backend_{datetime.now().strftime('%Y%m%d')}.log"
        _file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        _file_handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
    return _file_handler


def get_logger(name: str) -> logging.Logger:
    """获取或创建 logger — 同时输出到终端(stdout)和日志文件。"""
    if name not in _loggers:
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
        logger.propagate = False

        if not logger.handlers:
            # 终端 handler
            console = logging.StreamHandler(sys.stdout)
            console.setFormatter(logging.Formatter(
                "[%(asctime)s] %(name)s | %(levelname)s | %(message)s",
                datefmt="%H:%M:%S",
            ))
            logger.addHandler(console)

            # 文件 handler
            logger.addHandler(_get_file_handler())

        _loggers[name] = logger

    return _loggers[name]


class TokenTracker:
    """追踪 LLM token 使用。"""

    def __init__(self):
        self.total_input = 0
        self.total_output = 0

    def record(self, input_tokens: int, output_tokens: int):
        self.total_input += input_tokens
        self.total_output += output_tokens

    def summary(self) -> dict:
        return {
            "total_input_tokens": self.total_input,
            "total_output_tokens": self.total_output,
        }


token_tracker = TokenTracker()