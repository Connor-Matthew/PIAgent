from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage


class Summarizer:
    """Summarize old conversation messages to cap context growth."""

    def __init__(
        self,
        model,
        trigger_messages: int = 30,
        keep_messages: int = 10,
    ):
        self.model = model
        self.trigger_messages = trigger_messages
        self.keep_messages = keep_messages

    def _find_safe_split(self, messages: list[BaseMessage], target_idx: int) -> int:
        idx = max(0, min(target_idx, len(messages)))
        if idx < len(messages) and isinstance(messages[idx], BaseMessage):
            msg_type = getattr(messages[idx], "type", "")
            if msg_type == "tool":
                tool_call_id = getattr(messages[idx], "tool_call_id", None)
                for back in range(idx - 1, -1, -1):
                    if getattr(messages[back], "type", "") == "ai":
                        tool_calls = getattr(messages[back], "tool_calls", None)
                        if tool_calls and any(
                            tc.get("id") == tool_call_id for tc in tool_calls
                        ):
                            idx = back
                            break
        return idx

    def _format_messages_for_summary(self, messages: list[BaseMessage]) -> str:
        lines = []
        for msg in messages:
            role = getattr(msg, "type", "unknown")
            content = msg.content or ""
            if role == "ai" and getattr(msg, "tool_calls", None):
                tc_summary = ", ".join(
                    f"{tc.get('name')}({tc.get('args')})"
                    for tc in msg.tool_calls
                )
                lines.append(f"AI [tool_calls]: {tc_summary}")
            elif role == "tool":
                name = getattr(msg, "name", "tool")
                text = content if len(content) < 500 else content[:500] + "..."
                lines.append(f"Tool ({name}): {text}")
            else:
                lines.append(f"{role.upper()}: {content}")
        return "\n".join(lines)

    def _generate_summary(self, messages: list[BaseMessage]) -> str:
        conversation_text = self._format_messages_for_summary(messages)
        prompt = (
            "Summarize the following conversation excerpt concisely. "
            "Preserve key facts, decisions, and tool outcomes that the assistant should remember.\n\n"
            f"{conversation_text}"
        )
        try:
            response = self.model.invoke([HumanMessage(content=prompt)])
            return str(response.content).strip()
        except Exception:
            return f"[Earlier conversation truncated: {len(messages)} messages]"

    def compress(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        if len(messages) <= self.trigger_messages:
            return list(messages)

        split_idx = len(messages) - self.keep_messages
        split_idx = self._find_safe_split(messages, split_idx)

        old_messages = messages[:split_idx]
        recent_messages = messages[split_idx:]

        summary_text = self._generate_summary(old_messages)
        summary_msg = SystemMessage(
            content=f"[Previous conversation summary]\n{summary_text}"
        )

        return [summary_msg] + list(recent_messages)

