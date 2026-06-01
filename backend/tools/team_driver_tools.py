"""车队/车手/赛事查询工具 — 给 intake agent 用，校验 prompt 里提到的实体并提供候选项。

数据策略：硬编码 2024-2026 三个赛季的车队/车手阵容（含中英文别名），
赛事查询走 jolpica.get_season_schedule 实时拿当年赛历。
"""

from __future__ import annotations

import logging
from typing import Any

from .registry import registry
from ..harness.time_context import current_season

logger = logging.getLogger(__name__)

# ============================================================
# 车队 / 车手 阵容（每年一份，硬编码）
# ============================================================
# 结构：season -> [{team_canonical, drivers: [driver_canonical, ...]}]
# 别名表全局共享：alias -> canonical（车队和车手分开）

_ROSTER_BY_SEASON: dict[int, list[dict]] = {
    2024: [
        {"team": "Red Bull Racing", "drivers": ["Max Verstappen", "Sergio Perez"]},
        {"team": "Ferrari", "drivers": ["Charles Leclerc", "Carlos Sainz"]},
        {"team": "Mercedes", "drivers": ["Lewis Hamilton", "George Russell"]},
        {"team": "McLaren", "drivers": ["Lando Norris", "Oscar Piastri"]},
        {"team": "Aston Martin", "drivers": ["Fernando Alonso", "Lance Stroll"]},
        {"team": "Alpine", "drivers": ["Pierre Gasly", "Esteban Ocon"]},
        {"team": "Williams", "drivers": ["Alexander Albon", "Logan Sargeant"]},
        {"team": "RB", "drivers": ["Daniel Ricciardo", "Yuki Tsunoda"]},
        {"team": "Kick Sauber", "drivers": ["Valtteri Bottas", "Zhou Guanyu"]},
        {"team": "Haas", "drivers": ["Kevin Magnussen", "Nico Hulkenberg"]},
    ],
    2025: [
        {"team": "Red Bull Racing", "drivers": ["Max Verstappen", "Yuki Tsunoda"]},
        {"team": "Ferrari", "drivers": ["Charles Leclerc", "Lewis Hamilton"]},
        {"team": "Mercedes", "drivers": ["George Russell", "Andrea Kimi Antonelli"]},
        {"team": "McLaren", "drivers": ["Lando Norris", "Oscar Piastri"]},
        {"team": "Aston Martin", "drivers": ["Fernando Alonso", "Lance Stroll"]},
        {"team": "Alpine", "drivers": ["Pierre Gasly", "Franco Colapinto"]},
        {"team": "Williams", "drivers": ["Alexander Albon", "Carlos Sainz"]},
        {"team": "Racing Bulls", "drivers": ["Liam Lawson", "Isack Hadjar"]},
        {"team": "Kick Sauber", "drivers": ["Nico Hulkenberg", "Gabriel Bortoleto"]},
        {"team": "Haas", "drivers": ["Esteban Ocon", "Oliver Bearman"]},
    ],
    2026: [
        # 注：2026 规则大改 + Cadillac 加盟成 11 队，部分阵容截止 2026-05 的公开信息
        {"team": "Red Bull Racing", "drivers": ["Max Verstappen", "Isack Hadjar"]},
        {"team": "Ferrari", "drivers": ["Charles Leclerc", "Lewis Hamilton"]},
        {"team": "Mercedes", "drivers": ["George Russell", "Andrea Kimi Antonelli"]},
        {"team": "McLaren", "drivers": ["Lando Norris", "Oscar Piastri"]},
        {"team": "Aston Martin", "drivers": ["Fernando Alonso", "Lance Stroll"]},
        {"team": "Alpine", "drivers": ["Pierre Gasly", "Franco Colapinto"]},
        {"team": "Williams", "drivers": ["Alexander Albon", "Carlos Sainz"]},
        {"team": "Racing Bulls", "drivers": ["Liam Lawson", "Arvid Lindblad"]},
        {"team": "Audi", "drivers": ["Nico Hulkenberg", "Gabriel Bortoleto"]},
        {"team": "Haas", "drivers": ["Esteban Ocon", "Oliver Bearman"]},
        {"team": "Cadillac", "drivers": ["Valtteri Bottas", "Sergio Perez"]},
    ],
}

# ---- 车队别名（中英文，全部 lowercase 后比对）----
_TEAM_ALIASES: dict[str, str] = {
    # Red Bull
    "red bull": "Red Bull Racing", "redbull": "Red Bull Racing", "rbr": "Red Bull Racing",
    "红牛": "Red Bull Racing", "红牛车队": "Red Bull Racing",
    # Ferrari
    "ferrari": "Ferrari", "scuderia ferrari": "Ferrari",
    "法拉利": "Ferrari", "法拉利车队": "Ferrari", "马拉内罗": "Ferrari",
    # Mercedes
    "mercedes": "Mercedes", "merc": "Mercedes", "mercedes-amg": "Mercedes",
    "梅赛德斯": "Mercedes", "奔驰": "Mercedes", "银箭": "Mercedes",
    # McLaren
    "mclaren": "McLaren", "mcl": "McLaren",
    "迈凯伦": "McLaren", "迈凯轮": "McLaren",
    # Aston Martin
    "aston martin": "Aston Martin", "aston": "Aston Martin", "amr": "Aston Martin",
    "阿斯顿马丁": "Aston Martin", "阿斯顿": "Aston Martin",
    # Alpine
    "alpine": "Alpine", "renault": "Alpine",
    "阿尔派": "Alpine", "雷诺": "Alpine", "阿尔品": "Alpine", "阿尔聘": "Alpine",
    # Williams
    "williams": "Williams",
    "威廉姆斯": "Williams", 
    # Racing Bulls / RB
    "racing bulls": "Racing Bulls", "rb": "Racing Bulls", "vcarb": "Racing Bulls",
    "alphatauri": "Racing Bulls", "alpha tauri": "Racing Bulls",
    "小红牛": "Racing Bulls", "红牛二队": "Racing Bulls",
    # Sauber / Audi
    "kick sauber": "Kick Sauber", "sauber": "Kick Sauber", "stake": "Kick Sauber",
    "索伯": "Kick Sauber",
    "audi": "Audi", "奥迪": "Audi",
    # Haas
    "haas": "Haas",
    "哈斯": "Haas",
    # Cadillac (2026)
    "cadillac": "Cadillac", "cadillac f1": "Cadillac",
    "凯迪拉克": "Cadillac",
}

# ---- 车手别名 ----
_DRIVER_ALIASES: dict[str, str] = {
    # Verstappen
    "verstappen": "Max Verstappen", "max": "Max Verstappen", "ver": "Max Verstappen",
    "维斯塔潘": "Max Verstappen", "马克斯": "Max Verstappen", "汽车人": "Max Verstappen",
    # Perez
    "perez": "Sergio Perez", "checo": "Sergio Perez", "per": "Sergio Perez",
    "佩雷兹": "Sergio Perez", "切科": "Sergio Perez", "塞尔吉奥": "Sergio Perez",
    # Leclerc
    "leclerc": "Charles Leclerc", "charles": "Charles Leclerc", "lec": "Charles Leclerc",
    "勒克莱尔": "Charles Leclerc", "夏尔": "Charles Leclerc", "老四": "Charles Leclerc",
    # Sainz
    "sainz": "Carlos Sainz", "carlos sainz": "Carlos Sainz", "sai": "Carlos Sainz",
    "塞恩斯": "Carlos Sainz", "卡洛斯": "Carlos Sainz",
    # Hamilton
    "hamilton": "Lewis Hamilton", "lewis": "Lewis Hamilton", "ham": "Lewis Hamilton",
    "汉密尔顿": "Lewis Hamilton", "老汉": "Lewis Hamilton", "刘易斯": "Lewis Hamilton",
    # Russell
    "russell": "George Russell", "george": "George Russell", "rus": "George Russell",
    "拉塞尔": "George Russell", "乔治": "George Russell", "赛车皇帝": "George Russell",
    # Norris
    "norris": "Lando Norris", "lando": "Lando Norris", "nor": "Lando Norris",
    "诺里斯": "Lando Norris", "兰多": "Lando Norris",
    # Piastri
    "piastri": "Oscar Piastri", "oscar": "Oscar Piastri", "pia": "Oscar Piastri",
    "皮亚斯特里": "Oscar Piastri", "奥斯卡": "Oscar Piastri",
    # Alonso
    "alonso": "Fernando Alonso", "fernando": "Fernando Alonso", "alo": "Fernando Alonso",
    "阿隆索": "Fernando Alonso", "费尔南多": "Fernando Alonso", "头哥": "Fernando Alonso",
    # Stroll
    "stroll": "Lance Stroll", "lance": "Lance Stroll", "str": "Lance Stroll",
    "斯特罗尔": "Lance Stroll", "兰斯": "Lance Stroll",
    # Gasly
    "gasly": "Pierre Gasly", "pierre": "Pierre Gasly", "gas": "Pierre Gasly",
    "加斯利": "Pierre Gasly", "皮埃尔": "Pierre Gasly",
    # Ocon
    "ocon": "Esteban Ocon", "esteban": "Esteban Ocon", "oco": "Esteban Ocon",
    "奥康": "Esteban Ocon", "皮鞋": "Esteban Ocon", "埃斯特班": "Esteban Ocon",
    # Albon
    "albon": "Alexander Albon", "alex": "Alexander Albon", "alb": "Alexander Albon",
    "阿尔本": "Alexander Albon", "亚历山大": "Alexander Albon",
    # Tsunoda
    "tsunoda": "Yuki Tsunoda", "yuki": "Yuki Tsunoda", "tsu": "Yuki Tsunoda",
    "角田": "Yuki Tsunoda", "角田裕毅": "Yuki Tsunoda", "小雪": "Yuki Tsunoda",
    # Hulkenberg
    "hulkenberg": "Nico Hulkenberg", "hulk": "Nico Hulkenberg", "hul": "Nico Hulkenberg",
    "霍肯伯格": "Nico Hulkenberg", "尼科": "Nico Hulkenberg",
    # Bottas
    "bottas": "Valtteri Bottas", "valtteri": "Valtteri Bottas", "bot": "Valtteri Bottas",
    "博塔斯": "Valtteri Bottas", "瓦尔特利": "Valtteri Bottas",
    # Antonelli
    "antonelli": "Andrea Kimi Antonelli", "kimi antonelli": "Andrea Kimi Antonelli",
    "安东内利": "Andrea Kimi Antonelli", "基米": "Andrea Kimi Antonelli",
    # Lawson
    "lawson": "Liam Lawson", "liam": "Liam Lawson", "law": "Liam Lawson",
    "劳森": "Liam Lawson", "里亚姆": "Liam Lawson",
    # Hadjar
    "hadjar": "Isack Hadjar", "isack": "Isack Hadjar",
    "哈贾尔": "Isack Hadjar", "伊萨克": "Isack Hadjar",
    # Bortoleto
    "bortoleto": "Gabriel Bortoleto", "gabriel": "Gabriel Bortoleto",
    "博托莱托": "Gabriel Bortoleto", "加布里埃尔": "Gabriel Bortoleto",
    # Bearman
    "bearman": "Oliver Bearman", "oliver": "Oliver Bearman", "ollie": "Oliver Bearman",
    "贝尔曼": "Oliver Bearman", "比尔曼": "Oliver Bearman", "奥利弗": "Oliver Bearman",
    # Colapinto
    "colapinto": "Franco Colapinto", "franco": "Franco Colapinto",
    "科拉平托": "Franco Colapinto", "克拉平托": "Franco Colapinto",
    # Zhou (2024)
    "zhou": "Zhou Guanyu", "zhou guanyu": "Zhou Guanyu", "guanyu": "Zhou Guanyu",
    "周冠宇": "Zhou Guanyu", "周": "Zhou Guanyu",
    # Magnussen (2024)
    "magnussen": "Kevin Magnussen", "kmag": "Kevin Magnussen", "mag": "Kevin Magnussen",
    "马格努森": "Kevin Magnussen", "凯文": "Kevin Magnussen",
    # Ricciardo (2024)
    "ricciardo": "Daniel Ricciardo", "daniel": "Daniel Ricciardo", "ric": "Daniel Ricciardo",
    "里卡多": "Daniel Ricciardo", "丹尼尔": "Daniel Ricciardo",
    # Sargeant (2024)
    "sargeant": "Logan Sargeant", "logan": "Logan Sargeant",
    "萨金特": "Logan Sargeant", "洛根": "Logan Sargeant",
}


def _norm(s: str) -> str:
    return (s or "").lower().strip()


# ============================================================
# 混合阵容获取：本地优先，缺则走 Jolpica API
# ============================================================

# API 拉取结果的内存缓存，避免对同一赛季重复请求
_API_ROSTER_CACHE: dict[int, list[dict]] = {}


async def _fetch_roster_from_api(season: int) -> list[dict]:
    """从 Jolpica API 抓取某赛季的车队 + 各队车手，整合成本地格式。

    返回结构与 _ROSTER_BY_SEASON 一致：
        [{"team": "Ferrari", "drivers": ["Charles Leclerc", "Carlos Sainz"]}, ...]
    """
    from ..data import jolpica_client

    try:
        constructors = await jolpica_client.get_constructors(season)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Jolpica get_constructors({season}) 失败: {e}")
        return []

    roster: list[dict] = []
    for c in constructors:
        cid = c.get("constructorId", "")
        team_name = c.get("name", "")
        if not cid or not team_name:
            continue
        try:
            drivers_raw = await jolpica_client.get_constructor_drivers(season, cid)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Jolpica get_constructor_drivers({season}, {cid}) 失败: {e}")
            drivers_raw = []
        drivers = [
            f"{d.get('givenName', '').strip()} {d.get('familyName', '').strip()}".strip()
            for d in drivers_raw
            if d.get("familyName")
        ]
        roster.append({"team": team_name, "drivers": drivers})

    logger.info(f"Jolpica roster cached for {season}: {len(roster)} teams")
    return roster


async def _get_roster(season: int) -> list[dict]:
    """获取某赛季完整阵容。本地优先，缺则走 API 缓存。"""
    if season in _ROSTER_BY_SEASON:
        return _ROSTER_BY_SEASON[season]
    if season in _API_ROSTER_CACHE:
        return _API_ROSTER_CACHE[season]
    roster = await _fetch_roster_from_api(season)
    if roster:
        _API_ROSTER_CACHE[season] = roster
    return roster


def _resolve_team(name: str) -> str | None:
    """模糊解析车队名 → 规范名。仅对本地别名表生效。"""
    if not name:
        return None
    key = _norm(name)
    if key in _TEAM_ALIASES:
        return _TEAM_ALIASES[key]
    # 包含匹配（"红牛车队"含"红牛"）
    for alias, canonical in _TEAM_ALIASES.items():
        if alias in key or key in alias:
            return canonical
    return None


def _resolve_driver(name: str) -> str | None:
    """模糊解析车手名 → 规范名。仅对本地别名表生效。"""
    if not name:
        return None
    key = _norm(name)
    if key in _DRIVER_ALIASES:
        return _DRIVER_ALIASES[key]
    # 全名后缀匹配（"max verstappen" 含 "verstappen"）
    for alias, canonical in _DRIVER_ALIASES.items():
        if alias in key or key in alias:
            return canonical
    return None


def _resolve_team_in_roster(name: str, roster: list[dict]) -> str | None:
    """在给定的 roster 中模糊匹配车队规范名。供历史赛季（API 数据）使用。"""
    if not name or not roster:
        return None
    key = _norm(name)
    for entry in roster:
        team = entry["team"]
        if _norm(team) == key:
            return team
    for entry in roster:
        team = entry["team"]
        if _norm(team) in key or key in _norm(team):
            return team
    return None


def _resolve_driver_in_roster(name: str, roster: list[dict]) -> str | None:
    """在给定的 roster 中模糊匹配车手规范名。供历史赛季（API 数据）使用。"""
    if not name or not roster:
        return None
    key = _norm(name)
    for entry in roster:
        for d in entry["drivers"]:
            if _norm(d) == key:
                return d
    for entry in roster:
        for d in entry["drivers"]:
            d_low = _norm(d)
            if d_low in key or key in d_low:
                return d
            # 姓氏匹配（"verstappen" 命中 "Max Verstappen"）
            last = d_low.split()[-1] if d_low else ""
            if last and (last == key or last in key):
                return d
    return None


async def _team_drivers(season: int, team_canonical: str) -> list[str]:
    """某赛季某车队的车手列表。"""
    roster = await _get_roster(season)
    for entry in roster:
        if entry["team"] == team_canonical:
            return list(entry["drivers"])
    return []


async def _driver_team(season: int, driver_canonical: str) -> str | None:
    """某赛季某车手所属车队。"""
    roster = await _get_roster(season)
    for entry in roster:
        if driver_canonical in entry["drivers"]:
            return entry["team"]
    return None


async def _all_teams(season: int) -> list[str]:
    roster = await _get_roster(season)
    return [e["team"] for e in roster]


async def _all_drivers(season: int) -> list[str]:
    roster = await _get_roster(season)
    return [d for e in roster for d in e["drivers"]]


# ============================================================
# 工具实现
# ============================================================

async def _lookup_team(name: str, season: int | None = None) -> dict[str, Any]:
    """解析车队名，返回规范名 + 该赛季阵容。

    先用本地别名表（覆盖现役车队）；不命中再到该赛季 roster 里做字符串模糊匹配
    （覆盖历史车队，如 'Renault'、'Lotus'）。
    """
    season = season or current_season()
    roster = await _get_roster(season)
    canonical = _resolve_team(name)
    # 别名命中后，还要核验该规范名是否真的出现在目标赛季
    if canonical is not None and not any(e["team"] == canonical for e in roster):
        canonical = None
    if canonical is None:
        canonical = _resolve_team_in_roster(name, roster)
    if canonical is None:
        available = [e["team"] for e in roster]
        return {
            "found": False,
            "input": name,
            "season": season,
            "available_teams": available,
            "message": f"无法解析车队 '{name}' for season {season}。可选：{', '.join(available)}",
        }
    drivers = next((list(e["drivers"]) for e in roster if e["team"] == canonical), [])
    return {
        "found": True,
        "input": name,
        "season": season,
        "team": canonical,
        "drivers": drivers,
    }


async def _lookup_driver(name: str, season: int | None = None) -> dict[str, Any]:
    """解析车手名，返回规范名 + 所属车队。

    本地别名表优先，未命中则在该赛季 roster 里做字符串匹配。
    """
    season = season or current_season()
    roster = await _get_roster(season)

    # 先用本地别名（且校验真的在该赛季）
    canonical = _resolve_driver(name)
    if canonical is not None and not any(canonical in e["drivers"] for e in roster):
        canonical = None
    # 别名未命中或不在该季 → roster 内字符串匹配
    if canonical is None:
        canonical = _resolve_driver_in_roster(name, roster)

    if canonical is None:
        all_drivers = [d for e in roster for d in e["drivers"]]
        return {
            "found": False,
            "input": name,
            "season": season,
            "available_drivers": all_drivers,
            "message": f"无法解析车手 '{name}' for season {season}。该赛季阵容：{', '.join(all_drivers)}",
        }
    team = next((e["team"] for e in roster if canonical in e["drivers"]), None)
    if team is None:
        all_drivers = [d for e in roster for d in e["drivers"]]
        return {
            "found": False,
            "input": name,
            "season": season,
            "driver": canonical,
            "message": f"车手 '{canonical}' 不在 {season} 赛季阵容中（可能转会/退役）",
            "available_drivers": all_drivers,
        }
    return {
        "found": True,
        "input": name,
        "season": season,
        "driver": canonical,
        "team": team,
    }


async def _lookup_race(season: int, query: str) -> dict[str, Any]:
    """根据 query（赛道名/国家/轮次数字）匹配 round。

    查询走 jolpica 拿当年赛历做模糊匹配；jolpica 失败时降级到 None。
    query 为空字符串或仅空白时 → 返回完整赛历（给前端做选项列表）。
    """
    from ..data import jolpica_client

    try:
        races = await jolpica_client.get_season_schedule(season)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"jolpica.get_season_schedule({season}) 失败: {e}")
        return {
            "found": False,
            "input": query,
            "season": season,
            "error": f"赛历查询失败: {e}",
            "message": "请用户直接提供轮次编号（如「第8站」）",
        }

    # 空 query → 返回完整赛历作为 options 列表
    q = _norm(query)
    if not q:
        schedule = [
            {
                "round": int(r.get("round", 0)),
                "race_name": r.get("raceName", ""),
                "circuit_name": r.get("Circuit", {}).get("circuitName", ""),
                "country": r.get("Circuit", {}).get("Location", {}).get("country", ""),
            }
            for r in races
        ]
        return {"found": True, "input": "", "season": season, "schedule": schedule, "is_full_schedule": True}

    # 数字提取（"第10站"、"round 10"、"r10"）
    import re
    digit_match = re.search(r"\d+", q)
    if digit_match:
        try:
            target_round = int(digit_match.group())
            for r in races:
                if int(r.get("round", 0)) == target_round:
                    return {
                        "found": True,
                        "input": query,
                        "season": season,
                        "round": target_round,
                        "race_name": r.get("raceName", ""),
                        "circuit_name": r.get("Circuit", {}).get("circuitName", ""),
                        "country": r.get("Circuit", {}).get("Location", {}).get("country", ""),
                    }
        except ValueError:
            pass

    # 文本模糊匹配 — 用赛道工具的别名表反查 country/locality
    from .circuit_tools import _resolve_track_key
    key = _resolve_track_key(query)

    candidates: list[tuple[int, dict]] = []  # (score, race)
    for r in races:
        race_name = _norm(r.get("raceName", ""))
        country = _norm(r.get("Circuit", {}).get("Location", {}).get("country", ""))
        circuit_name = _norm(r.get("Circuit", {}).get("circuitName", ""))
        locality = _norm(r.get("Circuit", {}).get("Location", {}).get("locality", ""))

        score = 0
        haystacks = [race_name, country, circuit_name, locality]
        if any(q and q in h for h in haystacks):
            score += 3
        if any(h and h in q for h in haystacks if len(h) >= 4):
            score += 2
        if key and key.lower() in race_name + country + circuit_name:
            score += 5

        if score > 0:
            candidates.append((score, r))

    if candidates:
        candidates.sort(key=lambda x: -x[0])
        best = candidates[0][1]
        return {
            "found": True,
            "input": query,
            "season": season,
            "round": int(best.get("round", 0)),
            "race_name": best.get("raceName", ""),
            "circuit_name": best.get("Circuit", {}).get("circuitName", ""),
            "country": best.get("Circuit", {}).get("Location", {}).get("country", ""),
        }

    # 没匹配上 — 返回完整赛历给 LLM 看
    schedule_summary = [
        {
            "round": int(r.get("round", 0)),
            "race_name": r.get("raceName", ""),
            "country": r.get("Circuit", {}).get("Location", {}).get("country", ""),
        }
        for r in races
    ]
    return {
        "found": False,
        "input": query,
        "season": season,
        "schedule": schedule_summary,
        "message": f"未找到匹配 '{query}' 的比赛。{season} 赛季共 {len(races)} 站，请从赛历中选一站。",
    }


async def _list_season_teams(season: int) -> dict[str, Any]:
    """列出指定赛季的全部车队。本地优先，缺则走 Jolpica。"""
    teams = await _all_teams(season)
    source = "local" if season in _ROSTER_BY_SEASON else ("api" if teams else "none")
    return {
        "found": bool(teams),
        "season": season,
        "source": source,
        "teams": [{"value": t, "label": t} for t in teams],
    }


# ============================================================
# 注册
# ============================================================

registry.register(
    name="list_season_teams",
    description=(
        "列出指定赛季的全部车队（规范英文名）。"
        "用于 intake agent 在 season 已确定但 team 未选时生成选项列表。"
    ),
    func=_list_season_teams,
    parameters_schema={
        "type": "object",
        "properties": {
            "season": {"type": "integer", "description": "赛季年份"},
        },
        "required": ["season"],
    },
    agents=["intake"],
)

registry.register(
    name="lookup_team",
    description=(
        "解析车队名（中英文别名都支持），返回规范名和该赛季的车手阵容。"
        "用于 intake agent 校验用户提到的车队是否在指定赛季存在。"
        "如返回 found=false，会附带可用车队列表，用于反问用户。"
    ),
    func=_lookup_team,
    parameters_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "车队名（如 'ferrari'/'法拉利'/'红牛'）"},
            "season": {"type": "integer", "description": "赛季年份；省略则用当前赛季"},
        },
        "required": ["name"],
    },
    agents=["intake"],
)

registry.register(
    name="lookup_driver",
    description=(
        "解析车手名（中英文别名都支持），返回规范名和所属车队。"
        "用于 intake agent 校验用户提到的车手是否在指定赛季有效。"
        "如返回 found=false，会附带该赛季阵容列表。"
    ),
    func=_lookup_driver,
    parameters_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "车手名（如 'leclerc'/'勒克莱尔'/'verstappen'）"},
            "season": {"type": "integer", "description": "赛季年份；省略则用当前赛季"},
        },
        "required": ["name"],
    },
    agents=["intake"],
)

registry.register(
    name="lookup_race",
    description=(
        "根据查询词匹配某赛季的一场或全部比赛。"
        "有 query：模糊匹配赛道/国家/轮次 → 返回单场 round。"
        "无 query：返回完整赛历（24 站）→ is_full_schedule=true。"
    ),
    func=_lookup_race,
    parameters_schema={
        "type": "object",
        "properties": {
            "season": {"type": "integer", "description": "赛季年份"},
            "query": {"type": "string", "description": "赛道/国家/轮次；留空则返回完整赛历"},
        },
        "required": ["season"],
    },
    agents=["intake"],
)
