"""时间上下文 — 统一注入 agent / router 的"当前日期"前缀，避免 LLM 用训练截止时间作答。"""

from datetime import datetime

_WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


def current_season() -> int:
    """当前 F1 赛季年份（按本地系统时间）。"""
    return datetime.now().year


def current_time_prefix() -> str:
    """注入到 system prompt 前的实时时间块。LLM 据此推断"现在/本赛季/下一场"等相对时间。"""
    now = datetime.now()
    return (
        f"[当前日期：{now.strftime('%Y-%m-%d')}（周{_WEEKDAY_CN[now.weekday()]}）。"
        f"当前 F1 赛季：{now.year}。"
        "用户提到「现在/本赛季/下一场/上一赛季」等相对时间时，"
        "请基于此日期推断；若未指定年份且询问当前 F1 状态，默认使用当前赛季。"
        "不要使用你的训练截止日期作为「现在」。]"
    )
