"""Web 搜索工具 — 兜底冷门赛道 / 通用知识查询。

直接抓取 Bing 搜索 HTML 结果页（lxml 解析），对维基百科结果做摘要增强。
设计目标：知识库 miss 时让 race_context Agent 能继续作答而不是放弃。

为什么不走搜索 SDK：ddgs 库的 auto 模式会依次探测多引擎（本网络部分不可用），
延迟 8-21s 且波动大，频繁超出外层 10s 超时；直连 Bing HTML 实测 <2s 稳定。
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
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


async def _bing_search(query: str, max_results: int) -> list[dict]:
    """抓 Bing HTML 结果页，解析出有机结果（title/href/body，与历史 ddgs 返回同构）。"""
    from lxml import html as lh

    async with httpx.AsyncClient(
        timeout=8.0, headers={"User-Agent": _BROWSER_UA}, follow_redirects=True
    ) as client:
        resp = await client.get(
            "https://www.bing.com/search",
            params={"q": query, "count": str(min(max_results, 10))},
        )
        resp.raise_for_status()

    doc = lh.fromstring(resp.text)
    results: list[dict] = []
    for li in doc.xpath("//li[contains(@class,'b_algo')]"):
        anchors = li.xpath(".//h2/a")
        if not anchors:
            continue
        a = anchors[0]
        title = a.text_content().strip()
        href = _resolve_bing_redirect(a.get("href", ""))
        if not title or not href.startswith("http"):
            continue
        caps = li.xpath(".//*[contains(@class,'b_caption')]//p")
        snippet = caps[0].text_content().strip() if caps else ""
        results.append({"title": title, "href": href, "body": snippet})
        if len(results) >= max_results:
            break
    return results


def _resolve_bing_redirect(url: str) -> str:
    """把 bing.com/ck/a 跳转链接还原为目标 URL（u 参数 = 'a1' + base64url(目标)），
    还原不了就原样返回。"""
    import base64
    import urllib.parse

    try:
        parsed = urllib.parse.urlparse(url)
        if "bing.com" not in parsed.netloc or not parsed.path.startswith("/ck/"):
            return url
        u = urllib.parse.parse_qs(parsed.query).get("u", [""])[0]
        if u.startswith("a1"):
            payload = u[2:]
            payload += "=" * (-len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload).decode("utf-8", "ignore")
            return decoded if decoded.startswith("http") else url
    except Exception:  # noqa: BLE001
        pass
    return url


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
            lambda: _bing_search(query, max_results),
            name=f"bing[{query[:30]}]",
            attempts=2,
            base_delay=0.3,
            max_delay=1.0,
            timeout=_TIMEOUT_SEC,
            # 网络/解析异常统一允许重试一次，但跳过被取消的情况
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
        "通用 Web 搜索（Bing + Wikipedia 摘要增强）。"
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
