"""三层记忆管理器。"""

import json
from typing import Any
from dataclasses import dataclass, field

from ..models.schemas import RaceContextOutput, TireStrategyOutput, CompetitorOutput, SynthesisOutput


@dataclass
class WorkingMemory:
    """工作记忆——当前分析会话的结构化中间结果。"""
    session_id: str = ""
    intent: dict = field(default_factory=dict)
    race_data: dict = field(default_factory=dict)
    agent_outputs: dict[str, Any] = field(default_factory=dict)
    final_strategy: dict | None = None

    def set_agent_output(self, agent_name: str, output: Any):
        self.agent_outputs[agent_name] = output

    def get_agent_outputs(self) -> dict[str, Any]:
        return dict(self.agent_outputs)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "intent": self.intent,
            "race_data": self.race_data,
            "agent_outputs": {k: (v.data if hasattr(v, "data") else v) for k, v in self.agent_outputs.items()},
            "final_strategy": self.final_strategy,
        }


class ShortTermMemory:
    """短期记忆——对话历史。"""

    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self.messages: list[dict] = []

    def add_user_message(self, text: str):
        self.messages.append({"role": "user", "content": text})
        self._trim()

    def add_assistant_message(self, text: str):
        self.messages.append({"role": "assistant", "content": text})
        self._trim()

    def get_history(self) -> list[dict]:
        return list(self.messages)

    def _trim(self):
        while len(self.messages) > self.max_turns * 2:
            self.messages = self.messages[2:]


class MemoryManager:
    """统一记忆管理接口。"""

    def __init__(self):
        self.short_term = ShortTermMemory()
        self.working = WorkingMemory()

    def new_session(self, session_id: str):
        """开始新会话。"""
        self.working = WorkingMemory(session_id=session_id)

    def start_follow_up(self):
        """开始追问——保留工作记忆，清空部分短期记忆。"""
        # 保留上一轮的工作记忆，不清空
        pass