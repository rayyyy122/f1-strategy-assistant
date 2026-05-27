"""Web 搜索工具 — 兜底冷门赛道 / 通用知识查询。

使用 DuckDuckGo (ddgs) 作为搜索引擎，对维基百科结果做摘要增强。
设计目标：知识库 miss 时让 race_context Agent 能继续作答而不是放弃。
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from .registry import registry
from ..harness.retry import retry_async

logger = logging.getLogger(__name__)

_TIMEOUT_SEC = 10.0
_WIKI_REST_BASE = "https://en.wikipedia.org/api/rest_v1/page/summary/"


def _ddgs_search_sync(query: str, max_results: int) -> list[dict]:
    """在工作线程里跑同步 ddgs 调用。"""
    from ddgs import DDGS

    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results) or [])


async def _enrich_with_wikipedia(url: str) -> str | None:
    """如果 URL 是英文维基条目，抓取摘要补充更可靠的事实。"""
    prefix = "https://en.wikipedia.org/wiki/"
    if not url.startswith(prefix):
        return None
    title = url[len(prefix):].split("#", 1)[0]
    if not title:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(_WIKI_REST_BASE + title)
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data.get("extract") or None
    except Exception as e:  # noqa: BLE001
        logger.debug("Wikipedia enrichment failed for %s: %s", title, e)
        return None


async def _web_search(query: str, max_results: int = 5) -> dict:
    """通用 web 搜索。返回结构化结果列表，失败时 found=false。"""
    if not query or not query.strip():
        return {"found": False, "error": "query is empty"}

    try:
        raw = await retry_async(
            lambda: asyncio.to_thread(_ddgs_search_sync, query, max_results),
            name=f"ddgs[{query[:30]}]",
            attempts=2,
            base_delay=0.3,
            max_delay=1.0,
            timeout=_TIMEOUT_SEC,
            # ddgs 的内部异常类型五花八门（rate limit / 解析失败 / network），统一允许重试一次，
            # 但跳过被取消的情况
            should_retry=lambda e: not isinstance(e, asyncio.CancelledError),
        )
    except asyncio.TimeoutError:
        return {"found": False, "query": query, "error": f"timed out after {_TIMEOUT_SEC}s"}
    except Exception as e:  # noqa: BLE001
        logger.warning("web_search failed for query=%r: %s", query, e)
        return {"found": False, "query": query, "error": str(e)}

    if not raw:
        return {"found": False, "query": query, "results": [], "message": "无相关搜索结果"}

    enrich_targets = [
        (i, r.get("href", ""))
        for i, r in enumerate(raw)
        if r.get("href", "").startswith("https://en.wikipedia.org/wiki/")
    ][:2]
    enrichments = await asyncio.gather(
        *(_enrich_with_wikipedia(u) for _, u in enrich_targets),
        return_exceptions=True,
    )
    enrich_map = {
        i: extract
        for (i, _), extract in zip(enrich_targets, enrichments)
        if isinstance(extract, str) and extract
    }

    results = []
    for i, r in enumerate(raw):
        snippet = enrich_map.get(i) or r.get("body", "")
        results.append({
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": snippet[:600],
        })

    return {"found": True, "query": query, "results": results}


registry.register(
    name="web_search",
    description=(
        "通用 Web 搜索（DuckDuckGo + Wikipedia 摘要增强）。"
        "用于知识库未覆盖的赛道、车手、车队、规则变化、新闻等查询。"
        "**调用时机**：当 get_circuit_profile/get_historical_strategies 返回 found=false，"
        "或问题涉及 2024 年后的新事件时使用。"
        "返回结构：{found, results: [{title, url, snippet}, ...]}。"
        "snippet 已截断至 600 字。请基于这些结果作答，不要再编造。"
    ),
    func=_web_search,
    parameters_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "搜索查询，建议英文+具体关键词以提高命中率。"
                    "例：'Istanbul Park F1 circuit length corners'，'Madrid F1 2026 layout'。"
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "返回结果数，默认 5，最多 10",
            },
        },
        "required": ["query"],
    },
    agents=["race_context"],
)
