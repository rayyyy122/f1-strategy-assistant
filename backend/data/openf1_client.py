"""OpenF1 API 客户端 — 实时计时数据和天气。"""

import httpx

from ..harness.retry import retry_async

BASE_URL = "https://api.openf1.org/v1"
_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)


async def _get_json(path: str, params: dict | None = None):
    """带重试 + 超时的 GET。"""
    async def _attempt():
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{BASE_URL}/{path}", params=params or {})
            resp.raise_for_status()
            return resp.json()

    return await retry_async(
        _attempt,
        name=f"openf1[{path}]",
        attempts=2,
        base_delay=0.5,
        max_delay=2.0,
    )


async def get_weather_forecast(
    year: int | None = None,
    session_key: int | None = None,
) -> list[dict]:
    """获取天气数据。

    Args:
        year: 赛季年份（可选，用于过滤）
        session_key: OpenF1 session key（可选）

    Returns:
        [{"air_temperature": 22.5, "track_temperature": 45.0,
          "humidity": 55.0, "rainfall": False, "wind_speed": 3.2,
          "wind_direction": 180, "date": "..."}, ...]
    """
    params = {}
    if year:
        params["year"] = year
    if session_key:
        params["session_key"] = session_key

    return await _get_json("weather", params)


async def get_session_key(year: int, round_num: int, session_name: str) -> int | None:
    """根据年份、轮次、节名称查找 OpenF1 的 session_key。

    Args:
        year: 赛季年份
        round_num: F1 轮次（OpenF1 的 meeting_key 与 Jolpica 的 round 不同，需查表）
        session_name: "Practice 1" | "Practice 2" | "Practice 3" | "Qualifying" | "Race"
    """
    # OpenF1 用 meeting_key 不用 round，先查 meeting
    await _get_json("meetings", {"year": year})
    # 按 meeting_official_name 或 country 匹配 round（需要外部映射）
    # 简单实现：直接返回 None，使用 FastF1 作为备选
    return None
