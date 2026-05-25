from pydantic import BaseModel
from typing import Optional


# ---- 数据模型 ----

class TrackInfo(BaseModel):
    circuit_name: str
    locality: str
    country: str
    length_km: float
    corners: int
    drs_zones: int
    overtaking_difficulty: str   # "极难" | "困难" | "中等" | "容易"
    lap_record: Optional[str] = None
    first_gp_year: Optional[int] = None


class WeatherData(BaseModel):
    session_type: str            # "FP1" | "FP2" | "FP3" | "Qualifying" | "Race"
    air_temp_c: float
    track_temp_c: float
    humidity_pct: float
    rainfall: bool
    wind_speed_kmh: float
    wind_direction: str


class QualifyingResult(BaseModel):
    position: int
    driver_name: str
    team: str
    q1_time: Optional[str] = None
    q2_time: Optional[str] = None
    q3_time: Optional[str] = None


class PracticeLongRun(BaseModel):
    driver_name: str
    team: str
    compound: str               # "SOFT" | "MEDIUM" | "HARD"
    lap_count: int
    avg_lap_time: float
    degradation_rate: float      # s/lap


class PracticeData(BaseModel):
    session: str                 # "FP1" | "FP2" | "FP3"
    long_runs: list[PracticeLongRun]


# ---- Agent 输出模型 ----

class RaceContextOutput(BaseModel):
    track_summary: str
    weather_assessment: str
    historical_patterns: str
    key_factors: list[str]


class TireStrategyOutput(BaseModel):
    recommended_compound: str    # "MEDIUM" | "HARD" | "SOFT"
    pit_window_start: int
    pit_window_end: int
    degradation_rate_soft: Optional[float] = None
    degradation_rate_medium: Optional[float] = None
    degradation_rate_hard: Optional[float] = None
    stint_length_estimate: int
    alternatives: list[str]
    confidence: float
    reasoning: str


class CompetitorOutput(BaseModel):
    threats: list[str]           # 威胁车手排序（最危险的在前）
    grid_assessment: str
    form_analysis: str
    key_battles: list[str]


class SynthesisOutput(BaseModel):
    recommended_strategy: str
    pit_window: str
    predicted_position: str
    predicted_total_time: Optional[str] = None
    key_assumptions: list[str]
    risk_factors: list[str]
    alternatives: list[str]
    confidence: float
    reasoning: str


# ---- 轨迹模型 (RL) ----

class TraceRecord(BaseModel):
    trace_id: str
    mode: str                    # "pre_race" | "post_race" | ...
    season: int
    round: int
    prompt: str
    state: dict                  # 比赛状态快照
    agent_outputs: dict          # 各 Agent 输出
    final_prediction: dict       # 最终预测
    actual_outcome: Optional[dict] = None   # 赛后回填
    reward: Optional[float] = None          # 自动计算


# ---- 意图路由模型 ----

class Intent(BaseModel):
    mode: str                    # "pre_race" | "post_race" | "track_info" | "quick_question" | "follow_up"
    season: Optional[int] = None
    round: Optional[int] = None
    params: dict = {}