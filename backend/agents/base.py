"""Agent 基类 — 封装 DeepSeek API 调用 + 工具循环 + streaming。"""

import json
import asyncio
import logging
from dataclasses import dataclass, field

from openai import OpenAI

from ..llm_client import get_client
from ..tools.registry import registry

logger = logging.getLogger(__name__)


@dataclass
class AgentOutput:
    agent_name: str
    data: dict
    raw_text: str = ""


class AgentError(Exception):
    """Agent 运行错误。"""


@dataclass
class AgentConfig:
    name: str
    system_prompt: str
    model: str = "deepseek-chat"
    max_tokens: int = 8192
    tools: list[str] = field(default_factory=list)


class BaseAgent:
    """所有 Agent 的基类。"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.client = get_client()

    async def run(
        self,
        context: dict,
        event_queue: asyncio.Queue | None = None,
    ) -> AgentOutput:
        """标准 Agent 循环（streaming + tool use）。

        1. 构建 messages
        2. streaming 调用 API
        3. 流式推送 text delta 到 event_queue
        4. 处理 tool_calls → 执行工具 → 回填 → 循环
        5. finish_reason == "stop" → 解析输出
        """
        messages: list[dict] = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": self._build_user_message(context)},
        ]

        tool_schemas = self._get_tool_schemas()

        while True:
            kwargs = {
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "messages": messages,
                "stream": True,
            }
            if tool_schemas:
                kwargs["tools"] = tool_schemas

            response = await asyncio.to_thread(self._call_api, kwargs, event_queue)

            if response is None:
                raise AgentError("API 调用返回空响应")

            finish_reason = response.get("finish_reason", "stop")
            content = response.get("content", "")
            tool_calls = response.get("tool_calls") or []

            # 追加 assistant 消息
            assistant_msg: dict = {"role": "assistant", "content": content or None}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

            if finish_reason == "stop":
                data = self._parse_structured_output(content)
                return AgentOutput(
                    agent_name=self.config.name,
                    data=data,
                    raw_text=content,
                )

            elif finish_reason == "tool_calls":
                tool_results = await self._execute_tools(tool_calls, event_queue)
                messages.append({"role": "tool", "content": json.dumps(tool_results, ensure_ascii=False, default=str)})

            elif finish_reason == "length":
                raise AgentError("max_tokens 超限，需要增大 max_tokens")

            else:
                raise AgentError(f"未知 finish_reason: {finish_reason}")

    def _get_tool_schemas(self) -> list[dict] | None:
        """获取本 Agent 可用工具的 OpenAI function-calling schema。"""
        schemas = registry.get_schemas_for_agent(self.config.name)
        if not schemas:
            return None
        return [s["function"] for s in schemas]

    def _call_api(self, kwargs: dict, event_queue: asyncio.Queue | None) -> dict | None:
        """同步调用 DeepSeek API（streaming），推送事件到 event_queue。"""
        stream = self.client.chat.completions.create(**kwargs)

        content_parts: list[str] = []
        tool_calls_map: dict[int, dict] = {}
        finish_reason = "stop"
        chunk_count = 0

        for chunk in stream:
            chunk_count += 1
            if not chunk.choices:
                continue

            choice = chunk.choices[0]

            # 检查 finish_reason
            if choice.finish_reason:
                finish_reason = choice.finish_reason

            delta = choice.delta
            if delta is None:
                continue

            # 文本 delta
            if delta.content:
                content_parts.append(delta.content)
                if event_queue:
                    try:
                        event_queue.put_nowait({
                            "type": "agent_text",
                            "agent": self.config.name,
                            "delta": delta.content,
                        })
                    except asyncio.QueueFull:
                        pass

            # 工具调用 delta
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index if tc.index is not None else 0
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {"id": tc.id or "", "function": {"name": "", "arguments": ""}}
                    if tc.id:
                        tool_calls_map[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_map[idx]["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls_map[idx]["function"]["arguments"] += tc.function.arguments

        content = "".join(content_parts)
        logger.info(f"Agent [{self.config.name}] finish={finish_reason}, chunks={chunk_count}, content_len={len(content)}, tool_calls={len(tool_calls_map)}")

        # 转换 tool_calls_map 为列表
        tool_calls = None
        if tool_calls_map:
            tool_calls = [
                {
                    "id": v["id"],
                    "type": "function",
                    "function": {"name": v["function"]["name"], "arguments": v["function"]["arguments"]},
                }
                for v in sorted(tool_calls_map.values(), key=lambda x: list(tool_calls_map.keys())[list(tool_calls_map.values()).index(x)])
            ]

        return {
            "finish_reason": finish_reason,
            "content": content,
            "tool_calls": tool_calls,
        }

    async def _execute_tools(
        self,
        tool_calls: list[dict],
        event_queue: asyncio.Queue | None,
    ) -> str:
        """执行 tool_calls 中的所有函数调用，返回 tool 消息内容。"""
        for tc in tool_calls:
            fn = tc["function"]
            tool_name = fn["name"]
            try:
                args = json.loads(fn["arguments"]) if fn["arguments"] else {}
            except json.JSONDecodeError:
                args = {}

            # 推送 tool_call 事件
            if event_queue:
                try:
                    event_queue.put_nowait({
                        "type": "agent_tool_call",
                        "agent": self.config.name,
                        "tool": tool_name,
                        "params": args,
                    })
                except asyncio.QueueFull:
                    pass

            # 执行工具
            try:
                result = registry.execute(tool_name, args)
                if asyncio.iscoroutine(result):
                    result = await result
            except ValueError as e:
                result = f"Error: {e}"

            # 推送 tool_result 事件
            if event_queue:
                try:
                    event_queue.put_nowait({
                        "type": "agent_tool_result",
                        "agent": self.config.name,
                        "tool": tool_name,
                        "result": result,
                    })
                except asyncio.QueueFull:
                    pass

        # 返回所有工具结果的汇总
        return json.dumps({"tool_results": "completed"}, ensure_ascii=False, default=str)

    def _build_user_message(self, context: dict) -> str:
        """构建 user message。"""
        parts = []

        if "task" in context:
            parts.append(f"## 任务\n{context['task']}")

        if "race_context" in context:
            parts.append(f"## 比赛信息\n{json.dumps(context['race_context'], ensure_ascii=False, indent=2)}")

        if "upstream_outputs" in context:
            for name, output in context["upstream_outputs"].items():
                if hasattr(output, "data"):
                    output = output.data
                parts.append(f"## {name} 输出\n{json.dumps(output, ensure_ascii=False, indent=2)}")

        if not parts:
            return context.get("prompt", "请开始分析。")

        return "\n\n".join(parts)

    def _parse_structured_output(self, raw_text: str) -> dict:
        """尝试从 raw_text 中解析 JSON。"""
        if "```json" in raw_text:
            start = raw_text.index("```json") + 7
            end = raw_text.index("```", start)
            raw_text = raw_text[start:end].strip()
        elif raw_text.strip().startswith("{"):
            pass
        else:
            return {"summary": raw_text}

        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            return {"summary": raw_text}