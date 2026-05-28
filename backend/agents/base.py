"""Agent 基类 — 封装 DeepSeek API 调用 + 工具循环 + streaming。"""

import json
import asyncio
import logging
from dataclasses import dataclass, field

from openai import OpenAI

from ..llm_client import get_client
from ..tools.registry import registry
from ..harness.time_context import current_time_prefix
from ..harness.retry import retry_async

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
    # 强制首次 LLM 调用必须使用工具（防止 LLM 跳过工具直接幻觉）
    force_first_tool_call: bool = False


class BaseAgent:
    """所有 Agent 的基类。"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.client = get_client()

    async def run(
        self,
        context: dict,
        event_queue: asyncio.Queue | None = None,
        force_first_tool_call: bool | None = None,
    ) -> AgentOutput:
        """标准 Agent 循环（streaming + tool use）。

        Args:
            force_first_tool_call: 覆盖 config 默认值。True 时强制首轮必须调用工具。
                None 时使用 config.force_first_tool_call。
        """
        loop = asyncio.get_running_loop()
        force_tool = (
            force_first_tool_call
            if force_first_tool_call is not None
            else self.config.force_first_tool_call
        )

        messages: list[dict] = [
            {"role": "system", "content": current_time_prefix() + "\n\n" + self.config.system_prompt},
        ]

        # 注入对话历史（前端传入，已限制 last 10 条）。role="agent" 转换为 OpenAI 协议的 "assistant"。
        for h in context.get("history", []) or []:
            role = h.get("role", "user")
            if role == "agent":
                role = "assistant"
            if role not in ("user", "assistant"):
                continue
            content = str(h.get("content", "")).strip()
            if not content:
                continue
            messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": self._build_user_message(context)})

        tool_schemas = self._get_tool_schemas()
        iteration = 0

        while True:
            iteration += 1
            kwargs = {
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "messages": messages,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if tool_schemas:
                kwargs["tools"] = tool_schemas
                # 强制首轮必须调用工具（防幻觉）
                if iteration == 1 and force_tool:
                    kwargs["tool_choice"] = "required"

            response = await retry_async(
                lambda: asyncio.to_thread(self._call_api, kwargs, event_queue, loop),
                name=f"agent[{self.config.name}].iter{iteration}",
                attempts=3,
                base_delay=1.0,
                max_delay=8.0,
                timeout=120.0,
            )

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
                logger.info(f"Agent [{self.config.name}] OUTPUT:\n----\n{content}\n----")
                return AgentOutput(
                    agent_name=self.config.name,
                    data=data,
                    raw_text=content,
                )

            elif finish_reason == "tool_calls":
                tool_messages = await self._execute_tools(tool_calls, event_queue)
                messages.extend(tool_messages)

            elif finish_reason == "length":
                raise AgentError("max_tokens 超限，需要增大 max_tokens")

            else:
                raise AgentError(f"未知 finish_reason: {finish_reason}")

    def _get_tool_schemas(self) -> list[dict] | None:
        """获取本 Agent 可用工具的 OpenAI function-calling schema。

        registry 已经返回完整 {type, function} 信封，直接透传给 DeepSeek API。
        """
        schemas = registry.get_schemas_for_agent(self.config.name)
        return schemas or None

    def _call_api(self, kwargs: dict, event_queue: asyncio.Queue | None, loop: asyncio.AbstractEventLoop | None = None) -> dict | None:
        """同步调用 DeepSeek API（streaming），通过 loop.call_soon_threadsafe 推送事件到 event_queue。"""
        from ..harness.logger import token_tracker

        def safe_put(item: dict):
            """跨线程安全地往 asyncio.Queue 投递事件。"""
            if event_queue is None or loop is None:
                return
            def _put():
                try:
                    event_queue.put_nowait(item)
                except asyncio.QueueFull:
                    pass
            loop.call_soon_threadsafe(_put)

        content_parts: list[str] = []
        tool_calls_map: dict[int, dict] = {}
        finish_reason = "stop"
        chunk_count = 0
        streamed_to_user = False  # 一旦给前端投递过文本/思考 token，重试会重复输出 → 不能重试

        try:
            stream = self.client.chat.completions.create(**kwargs)

            for chunk in stream:
                chunk_count += 1

                # 末尾的 usage 块（include_usage=True 时）
                if getattr(chunk, "usage", None):
                    token_tracker.record(
                        input_tokens=getattr(chunk.usage, "prompt_tokens", 0) or 0,
                        output_tokens=getattr(chunk.usage, "completion_tokens", 0) or 0,
                    )

                if not chunk.choices:
                    continue

                choice = chunk.choices[0]

                # 检查 finish_reason
                if choice.finish_reason:
                    finish_reason = choice.finish_reason

                delta = choice.delta
                if delta is None:
                    continue

                # reasoning_content (deepseek-reasoner 模型)
                reasoning_delta = getattr(delta, "reasoning_content", None)
                if reasoning_delta:
                    safe_put({
                        "type": "agent_thinking",
                        "agent": self.config.name,
                        "delta": reasoning_delta,
                    })
                    streamed_to_user = True

                # 文本 delta
                if delta.content:
                    content_parts.append(delta.content)
                    safe_put({
                        "type": "agent_text",
                        "agent": self.config.name,
                        "delta": delta.content,
                    })
                    streamed_to_user = True

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
        except BaseException as e:
            # 标记给前端投递过的失败，避免被 retry 重新跑一遍导致重复 token
            if streamed_to_user:
                try:
                    setattr(e, "_streamed_partial", True)
                except (AttributeError, TypeError):
                    pass
            raise

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
    ) -> list[dict]:
        """执行 tool_calls，返回每次调用对应的 tool 消息列表（含 tool_call_id）。

        OpenAI/DeepSeek 规范：N 个 tool_call 必须对应 N 条 `{"role":"tool", "tool_call_id":..., "content":...}`，
        否则下一轮请求会 400。
        """
        tool_messages: list[dict] = []

        for tc in tool_calls:
            fn = tc["function"]
            tool_name = fn["name"]
            tool_call_id = tc.get("id", "")
            try:
                args = json.loads(fn["arguments"]) if fn["arguments"] else {}
            except json.JSONDecodeError:
                args = {}

            logger.info(f"Agent [{self.config.name}] TOOL CALL: {tool_name}({json.dumps(args, ensure_ascii=False)})")

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
                result = {"error": str(e)}
            except Exception as e:  # noqa: BLE001
                logger.exception(f"Tool {tool_name} crashed")
                result = {"error": f"tool execution failed: {e}"}

            # 完整结果给 API；截断版本只用于日志
            try:
                result_str = json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                result_str = str(result)
            log_str = result_str if len(result_str) <= 500 else result_str[:500] + f"... [+{len(result_str)-500} chars]"
            logger.info(f"Agent [{self.config.name}] TOOL RESULT [{tool_name}]: {log_str}")

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

            tool_messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result_str,
            })

        return tool_messages

    def _build_user_message(self, context: dict) -> str:
        """构建 user message。"""
        parts = []

        if "task" in context:
            parts.append(f"## 任务\n{context['task']}")

        if "race_context" in context:
            parts.append(f"## 比赛信息\n{json.dumps(context['race_context'], ensure_ascii=False, indent=2)}")

        if "race_data" in context:
            parts.append(f"## 比赛数据\n{json.dumps(context['race_data'], ensure_ascii=False, indent=2, default=str)}")

        if "upstream_outputs" in context:
            for name, output in context["upstream_outputs"].items():
                if hasattr(output, "data"):
                    output = output.data
                parts.append(f"## {name} 输出\n{json.dumps(output, ensure_ascii=False, indent=2)}")

        # 分析对象（车队/车手）— pre_race intake gate 之后才会有
        if "target" in context and context["target"]:
            target = context["target"]
            target_lines = []
            if target.get("team"):
                target_lines.append(f"- 车队：{target['team']}")
            if target.get("driver"):
                target_lines.append(f"- 车手：{target['driver']}")
            if target_lines:
                parts.append("## 分析对象\n" + "\n".join(target_lines))

        # 当前 intent（intake agent 看部分已知字段）
        if "current_intent" in context and context["current_intent"]:
            ci = context["current_intent"]
            ci_lines = [f"- {k}: {v}" for k, v in ci.items() if v is not None]
            if ci_lines:
                parts.append("## 已知字段（来自 router 提取）\n" + "\n".join(ci_lines))

        # 用户原始问题 — 始终添加（如果有）
        if "prompt" in context and context["prompt"]:
            parts.append(f"## 用户原始问题\n{context['prompt']}")

        if not parts:
            return "请开始分析。"

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