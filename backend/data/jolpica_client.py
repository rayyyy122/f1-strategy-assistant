"""Jolpica F1 API 客户端 — 历史成绩、赛道信息、赛季日程。"""

import httpx

from ..harness.retry import retry_async

BASE_URL = "https://api.jolpi.ca/ergast/f1"
_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)


async def _get_json(path: str) -> dict:
    """带重试 + 超时的 GET。"""
    async def _attempt() -> dict:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{BASE_URL}/{path}")
            resp.raise_for_status()
            return resp.json()

    return await retry_async(
        _attempt,
        name=f"jolpica[{path}]",
        attempts=2,
        base_delay=0.5,
        max_delay=2.0,
    )


async def get_season_schedule(year: int) -> list[dict]:
    """获取赛季日程。

    Returns:
        [{"round": 1, "raceName": "Australian Grand Prix", "Circuit": {...}, "date": "..."}, ...]
    """
    data = await _get_json(f"{year}.json")
    return data["MRData"]["RaceTable"]["Races"]


async def get_circuit_info(year: int, round_num: int) -> dict:
    """获取某场比赛的赛道详情。

    Returns:
        {"circuitName": "Albert Park Grand Prix Circuit",
         "Location": {"locality": "Melbourne", "country": "Australia"},
         "url": "..."}
    """
    data = await _get_json(f"{year}/{round_num}/circuits.json")
    circuits = data["MRData"]["CircuitTable"]["Circuits"]
    return circuits[0] if circuits else {}


async def get_qualifying_results(year: int, round_num: int) -> list[dict]:
    """获取排位赛结果。

    Returns:
        [{"position": "1", "Driver": {"givenName": "...", "familyName": "..."},
          "Constructor": {"name": "..."}, "Q1": "1:10.270", ...}, ...]
    """
    data = await _get_json(f"{year}/{round_num}/qualifying.json")
    races = data["MRData"]["RaceTable"]["Races"]
    return races[0].get("QualifyingResults", []) if races else []


async def get_driver_standings(year: int, round_num: int | None = None) -> list[dict]:
    """获取车手积分榜。

    Args:
        year: 赛季年份
        round_num: 比赛轮次（None = 赛季结束时的最终排名）
    """
    path = f"{year}/{round_num}/driverStandings.json" if round_num else f"{year}/driverStandings.json"
    data = await _get_json(path)
    standings = data["MRData"]["StandingsTable"]["StandingsLists"]
    return standings[0].get("DriverStandings", []) if standings else []


async def get_constructors(year: int) -> list[dict]:
    """获取某赛季的所有车队。

    Returns:
        [{"constructorId": "ferrari", "name": "Ferrari", "nationality": "Italian"}, ...]
    """
    data = await _get_json(f"{year}/constructors.json")
    return data["MRData"]["ConstructorTable"].get("Constructors", [])


async def get_constructor_drivers(year: int, constructor_id: str) -> list[dict]:
    """获取某赛季某车队的所有车手（含 mid-season 替换）。

    Args:
        year: 赛季年份
        constructor_id: Ergast 车队 ID（小写，如 "ferrari"、"red_bull"）

    Returns:
        [{"driverId": "leclerc", "givenName": "Charles", "familyName": "Leclerc", ...}, ...]
    """
    data = await _get_json(f"{year}/constructors/{constructor_id}/drivers.json")
    return data["MRData"]["DriverTable"].get("Drivers", [])
