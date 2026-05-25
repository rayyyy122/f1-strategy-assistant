"""工具注册中心 — 管理所有工具的定义、注册和执行。"""

from dataclasses import dataclass, field
from typing import Callable, Any


@dataclass
class Tool:
    name: str
    description: str
    func: Callable
    parameters_schema: dict

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


class ToolRegistry:
    """全局工具注册中心。"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._agent_tools: dict[str, list[str]] = {}  # agent_name → [tool_names]

    def register(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters_schema: dict,
        agents: list[str] | None = None,
    ):
        """注册工具。

        Args:
            name: 工具名
            description: 工具描述（Claude 依赖此描述决定何时使用）
            func: 工具函数
            parameters_schema: JSON Schema 格式的参数定义
            agents: 可使用此工具的 Agent 名称列表，None 表示所有 Agent 可用
        """
        tool = Tool(
            name=name,
            description=description,
            func=func,
            parameters_schema=parameters_schema,
        )
        self._tools[name] = tool
        if agents:
            for agent_name in agents:
                self._agent_tools.setdefault(agent_name, []).append(name)

    def get_schemas_for_agent(self, agent_name: str) -> list[dict]:
        """获取某 Agent 可用的工具 schema 列表（OpenAI 格式，按名称排序以保证缓存一致）。"""
        if agent_name in self._agent_tools:
            names = sorted(self._agent_tools[agent_name])
        else:
            names = sorted(self._tools.keys())

        return [self._tools[n].to_openai_schema() for n in names if n in self._tools]

    def get_schemas_for_agent_raw(self, agent_name: str) -> list[dict]:
        """获取某 Agent 可用的工具 schema 列表（Anthropic 原生格式）。"""
        if agent_name in self._agent_tools:
            names = sorted(self._agent_tools[agent_name])
        else:
            names = sorted(self._tools.keys())

        result = []
        for n in names:
            if n in self._tools:
                t = self._tools[n]
                result.append({
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters_schema,
                })
        return result

    def execute(self, tool_name: str, params: dict) -> Any:
        """执行工具调用。"""
        if tool_name not in self._tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        tool = self._tools[tool_name]
        return tool.func(**params)


# 全局单例
registry = ToolRegistry()