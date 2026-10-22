"""Web 搜索工具 — 兜底冷门赛道 / 通用知识查询。

多源级联（2026-10 重写）：
0. 配置 BRAVE_SEARCH_API_KEY 时优先走 Brave Search API（稳定，免费档 2000 次/月）
1. Wikipedia search API — 必跑（本网络 100% 可靠的保底源，F1 实体覆盖度高）
2. DuckDuckGo lite — 能过反爬挑战就用（结果精确但不稳定）
3. Bing HTML — 兜底，带软降权垃圾守卫

背景：单一免费搜索引擎在本网络都不可靠——Bing 对实体类查询软降权
（返回 200 但有机结果是随机填充垃圾，页面含 no-results 标记），
DDG 多数人机挑战 202，Google/Mojeek 不可用。级联后任意一路命中即可作答，
三源全挂才 found=false。ddgs SDK 同样因多引擎探测延迟 8-21s 不可控而弃用。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import urllib.parse

import httpx

from .registry import registry
from ..config import BRAVE_SEARCH_API_KEY, LLM_API_KEY, LLM_BASE_URL

logger = logging.getLogger(__name__)


def _deepseek_tools_url(path: str) -> str:
    """DeepSeek Search/Fetch API 端点（与 chat 同 base URL 同 key）。"""
    return f"{LLM_BASE_URL.rstrip('/')}/tools/{path}"


# ---- 源 0：DeepSeek Search API（自研引擎，本网络与 chat 同域最可靠）----

async def _deepseek_search(query: str, max_results: int) -> list[dict]:
    """DeepSeek Search API。summary 字段（600-800 字，专为模型阅读设计）作为 body。"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            _deepseek_tools_url("search"),
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={"query": query, "count": min(max_results, 10), "need_content": False},
        )
        resp.raise_for_status()
    return [
        {"title": r.get("title", ""), "href": r.get("url", ""), "body": r.get("summary") or r.get("snippet", "")}
        for r in resp.json().get("results", [])
    ]

_WIKI_UA = "F1StrategyAssistant/1.0 (research; local deployment)"
_WIKI_URL_RE = re.compile(r"^https://([a-z-]+)\.wikipedia\.org/wiki/([^#]+)")
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


# ---- 源 0：Brave Search API（配 key 优先）----

async def _brave_search(query: str, max_results: int) -> list[dict]:
    async with httpx.AsyncClient(
        timeout=8.0,
        headers={"X-Subscription-Token": BRAVE_SEARCH_API_KEY or "", "Accept": "application/json"},
    ) as client:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(max_results, 10)},
        )
        resp.raise_for_status()
    return [
        {"title": r.get("title", ""), "href": r.get("url", ""), "body": r.get("description", "")}
        for r in resp.json().get("web", {}).get("results", [])
    ]


# ---- 源 1：Wikipedia search API（保底）----

_WIKI_GENERIC_CJK = {"最新消息", "最新", "消息", "新闻", "动态", "情况", "如何", "怎么样", "怎么", "什么", "是谁", "介绍", "赛季"}


def _wiki_host(query: str) -> str:
    """中文查询走中文维基，其余走英文维基。"""
    return "zh.wikipedia.org" if re.search(r"[一-鿿]", query) else "en.wikipedia.org"


def _wiki_cjk_core(query: str) -> list[str]:
    """中文查询的实体词（去掉"最新消息"这类泛词）。空列表 = 非中文查询。"""
    return [r for r in re.findall(r"[一-鿿]+", query) if r not in _WIKI_GENERIC_CJK and len(r) >= 2]


async def _wiki_search(query: str, limit: int = 3) -> list[dict]:
    host = _wiki_host(query)
    core = _wiki_cjk_core(query)
    async with httpx.AsyncClient(timeout=5.0, headers={"User-Agent": _WIKI_UA}) as client:
        results = await _wiki_query_once(client, host, query, limit)
        if core:
            # wiki 中文全文搜索对长查询经常返回无关结果（非零命中，不触发空值重试）：
            # 结果标题/摘要都不含实体词 → 视为不相关，缩减为实体词重查
            relevant = any(any(c in (r["title"] + r["body"]) for c in core) for r in results)
            if not relevant:
                reduced = " ".join(core[:2])
                logger.info(f"wiki 原查询结果不相关，缩减重试: {reduced!r}")
                results = await _wiki_query_once(client, host, reduced, limit)
                # 缩减后仍无结果就如实返回空，不保留无关结果误导 Agent
    return results


async def _wiki_query_once(client: httpx.AsyncClient, host: str, query: str, limit: int) -> list[dict]:
    resp = await client.get(
        f"https://{host}/w/api.php",
        params={
            "action": "query", "list": "search", "srsearch": query,
            "format": "json", "srlimit": limit,
        },
    )
    resp.raise_for_status()
    results = []
    for hit in resp.json().get("query", {}).get("search", []):
        title = hit.get("title", "")
        if not title:
            continue
        results.append({
            "title": title,
            "href": f"https://{host}/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
            "body": re.sub(r"<[^>]+>", "", hit.get("snippet", "")),
        })
    return results


# ---- 源 2：DuckDuckGo lite（能过挑战就用）----

async def _ddg_lite_search(query: str, max_results: int) -> list[dict]:
    from lxml import html as lh

    async with httpx.AsyncClient(
        timeout=4.0, headers={"User-Agent": _BROWSER_UA}, follow_redirects=True
    ) as client:
        resp = await client.post("https://lite.duckduckgo.com/lite/", data={"q": query})
    if resp.status_code != 200:
        logger.debug(f"ddg lite status={resp.status_code}（人机挑战），跳过")
        return []
    doc = lh.fromstring(resp.text)
    links = doc.xpath("//a[@class='result-link']")
    snippets = [s.text_content().strip() for s in doc.xpath("//td[@class='result-snippet']")]
    results = []
    for i, a in enumerate(links[:max_results]):
        title = a.text_content().strip()
        href = _resolve_ddg_redirect(a.get("href", ""))
        if not title or not href.startswith("http"):
            continue
        results.append({"title": title, "href": href, "body": snippets[i] if i < len(snippets) else ""})
    return results


def _resolve_ddg_redirect(href: str) -> str:
    """duckduckgo.com/l/?uddg=<urlencoded> 跳转链接还原。"""
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urllib.parse.urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            uddg = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
            if uddg:
                return uddg
    except Exception:  # noqa: BLE001
        pass
    return href


# ---- 源 3：Bing HTML（兜底 + 垃圾守卫）----

async def _bing_search(query: str, max_results: int) -> list[dict]:
    from lxml import html as lh

    async with httpx.AsyncClient(
        timeout=6.0, headers={"User-Agent": _BROWSER_UA}, follow_redirects=True
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

    if _is_bing_garbage(resp.text, query, results):
        logger.info(f"bing 返回软降权垃圾页，整页丢弃: query={query!r}")
        return []
    return results


def _is_bing_garbage(page_html: str, query: str, results: list[dict]) -> bool:
    """Bing 软降权页判定：页面含 no-results 标记，且所有结果标题与查询词零重叠。

    降权页特征：状态 200、有 b_algo 结果块，但内容是随机填充（每次刷新都不同），
    页面里同时藏着 no-results 文本。两个条件同时满足才丢弃，避免误杀
    Bing 语义匹配出的合法弱相关结果。
    """
    if not results:
        return False
    text = page_html.lower()
    if "no results" not in text and "没有与此相关的结果" not in text:
        return False
    tokens = {
        t for t in re.findall(r"[a-z0-9]+", query.lower())
        if len(t) >= 3 and not t.isdigit()  # 纯数字（年份）满大街都是，不作数
    }
    tokens -= {"the", "and", "for", "with"}
    tokens |= set(re.findall(r"[一-鿿]+", query))  # 中文整串也作为匹配 token
    if not tokens:
        return True
    titles = " ".join(r["title"].lower() for r in results)
    return not any(t in titles for t in tokens)


def _resolve_bing_redirect(url: str) -> str:
    """把 bing.com/ck/a 跳转链接还原为目标 URL（u 参数 = 'a1' + base64url(目标)），
    还原不了就原样返回。"""
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


# ---- Wikipedia 摘要增强（沿用）----

async def _enrich_with_wikipedia(url: str) -> str | None:
    """如果 URL 是维基条目（任意语种），抓取摘要补充更可靠的事实。"""
    m = _WIKI_URL_RE.match(url)
    if not m:
        return None
    lang, title = m.group(1), m.group(2)
    try:
        async with httpx.AsyncClient(timeout=5.0, headers={"User-Agent": _WIKI_UA}) as client:
            resp = await client.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}")
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data.get("extract") or None
    except Exception as e:  # noqa: BLE001
        logger.debug("Wikipedia enrichment failed for %s: %s", title, e)
        return None


# ---- 级联入口 ----

async def _web_search(query: str, max_results: int = 5) -> dict:
    """通用 web 搜索。多源级联，返回结构化结果列表，全部失败时 found=false。"""
    if not query or not query.strip():
        return {"found": False, "error": "query is empty"}
    query = query.strip()

    raw: list[dict] = []

    # 源 0a：DeepSeek Search API（与 LLM 同 key 同域，本网络最可靠；失败降级）
    if LLM_API_KEY:
        try:
            raw = await _deepseek_search(query, max_results)
            if raw:
                logger.info(f"web_search[deepseek] {len(raw)} results")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"DeepSeek 搜索失败，降级: {e}")
            raw = []

    # 源 0b：Brave API（配了 key 且 DeepSeek 没拿到结果时；失败降级免费级联）
    if not raw and BRAVE_SEARCH_API_KEY:
        try:
            raw = await _brave_search(query, max_results)
            if raw:
                logger.info(f"web_search[brave] {len(raw)} results")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Brave 搜索失败，降级到免费级联: {e}")
            raw = []

    if not raw:
        # 源 1+2 并行：Wikipedia 保底 + DDG lite
        wiki_res, ddg_res = await asyncio.gather(
            _wiki_search(query),
            _ddg_lite_search(query, max_results),
            return_exceptions=True,
        )
        wiki_results = wiki_res if isinstance(wiki_res, list) else []
        if isinstance(wiki_res, Exception):
            logger.debug(f"wiki search failed: {wiki_res}")
        web_results = ddg_res if isinstance(ddg_res, list) else []

        # 源 3：DDG 没拿到 → Bing 兜底（自带垃圾守卫）
        if not web_results:
            try:
                web_results = await _bing_search(query, max_results)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"bing fallback failed: {e}")
                web_results = []

        # 合并去重（按 URL），网页结果在前、wiki 命中在后
        seen: set[str] = set()
        for r in web_results + wiki_results:
            if r["href"] not in seen:
                seen.add(r["href"])
                raw.append(r)

    if not raw:
        return {"found": False, "query": query, "results": [], "message": "无相关搜索结果"}

    # Wikipedia 摘要增强（最多 2 条 wiki 结果，任意语种）
    enrich_targets = [
        (i, r.get("href", ""))
        for i, r in enumerate(raw)
        if _WIKI_URL_RE.match(r.get("href", ""))
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
        "通用 Web 搜索（DeepSeek 自研搜索引擎优先，Wikipedia/DDG/Bing 级联兜底 + Wikipedia 摘要增强）。"
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


# ---- Fetch API：打开单个网页抓正文 ----

async def _fetch_page(url: str) -> dict:
    """抓取单个网页正文（Markdown）。用于搜索摘要不够、需要完整表格/榜单/全文时。"""
    url = (url or "").strip()
    if not url.startswith("http"):
        return {"found": False, "error": f"invalid url: {url!r}"}
    if not LLM_API_KEY:
        return {"found": False, "error": "未配置 DEEPSEEK_API_KEY"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _deepseek_tools_url("fetch"),
                headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                json={"url": url},
            )
            resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"fetch_page failed for {url[:60]}: {e}")
        return {"found": False, "url": url, "error": str(e)}

    data = resp.json()
    content = (data.get("content") or "")[:8000]  # 控制 token 量
    if not content:
        return {"found": False, "url": url, "message": "页面内容为空或无法抓取"}
    return {"found": True, "url": url, "title": data.get("title", ""), "content": content}


registry.register(
    name="fetch_page",
    description=(
        "打开指定 URL 抓取网页正文（Markdown，DeepSeek Fetch API）。"
        "**调用时机**：web_search 返回的摘要不够详细时——例如需要完整的积分榜/排名表格、"
        "新闻全文、技术参数表——对最相关的 1-2 个结果 URL 调用本工具。"
        "返回结构：{found, title, content}，content 截断至 8000 字符。"
    ),
    func=_fetch_page,
    parameters_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要抓取的网页 URL（通常来自 web_search 结果的 url 字段）",
            },
        },
        "required": ["url"],
    },
    agents=["race_context"],
)
