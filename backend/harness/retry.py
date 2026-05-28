"""轻量重试 helper — 只重试瞬态错误（网络/超时/5xx/429），不重试业务错误（401/400）。

设计目标：
- 不引入第三方库
- 接收 awaitable 工厂（每次重试都重新构造），适配 to_thread 的同步阻塞调用
- 默认不重试已经向用户流式过部分输出的 LLM 调用（避免重复 token）
"""

import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _default_should_retry(exc: BaseException) -> bool:
    """默认重试策略：网络/超时/5xx/429 → 重试；401/400/404/校验错误 → 不重试。"""
    # 调用方标记已经流式过部分内容时绝对不重试（避免前端看到重复 token）
    if getattr(exc, "_streamed_partial", False):
        return False

    if isinstance(exc, asyncio.TimeoutError):
        return True

    try:
        from openai import (
            APIConnectionError,
            APITimeoutError,
            RateLimitError,
            InternalServerError,
            AuthenticationError,
            BadRequestError,
            NotFoundError,
            PermissionDeniedError,
        )
        if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)):
            return True
        if isinstance(exc, (AuthenticationError, BadRequestError, NotFoundError, PermissionDeniedError)):
            return False
    except ImportError:
        pass

    try:
        import httpx
        if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            return code >= 500 or code == 429
    except ImportError:
        pass

    if isinstance(exc, (ConnectionError, OSError)):
        return True

    return False


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    name: str = "",
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 8.0,
    timeout: float | None = None,
    should_retry: Callable[[BaseException], bool] | None = None,
) -> T:
    """通用异步重试。

    Args:
        fn: 每次尝试都被调用的工厂；返回 Awaitable[T]
        name: 日志前缀
        attempts: 总尝试次数（含首次）
        base_delay: 第一次失败后的等待秒数
        max_delay: 退避上限
        timeout: 每次尝试的超时；None 则不显式超时
        should_retry: 给定异常返回是否重试；默认 _default_should_retry
    """
    check = should_retry or _default_should_retry
    last_exc: BaseException | None = None

    for i in range(1, attempts + 1):
        try:
            if timeout is not None:
                return await asyncio.wait_for(fn(), timeout=timeout)
            return await fn()
        except asyncio.CancelledError:
            raise
        except BaseException as e:  # noqa: BLE001
            last_exc = e
            if i == attempts or not check(e):
                logger.warning(
                    f"retry[{name}] attempt {i}/{attempts} failed (no more retries): {type(e).__name__}: {e}"
                )
                raise
            delay = min(base_delay * (2 ** (i - 1)), max_delay)
            wait_s = delay + delay * 0.2 * random.random()
            logger.info(
                f"retry[{name}] attempt {i}/{attempts} failed: {type(e).__name__}: {e}; retry in {wait_s:.2f}s"
            )
            await asyncio.sleep(wait_s)

    assert last_exc is not None
    raise last_exc
