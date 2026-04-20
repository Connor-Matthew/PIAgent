import hashlib
import json
from typing import Any

from langchain_core.tools import BaseTool


class LoopDetector:
    """Detect repetitive tool-call patterns."""

    def __init__(
        self,
        window_size: int = 20,
        warn_threshold: int = 3,
        hard_limit: int = 5,
    ):
        self.window_size = window_size
        self.warn_threshold = warn_threshold
        self.hard_limit = hard_limit
        self._history: list[str] = []
        self._warned_hashes: set[str] = set()
        self._stopped_hashes: set[str] = set()

    @staticmethod
    def _normalize_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(args)
        if tool_name == "read_file" and "file_path" in normalized:
            normalized = {"file_path": normalized["file_path"]}
        return normalized

    @staticmethod
    def _hash_call(tool_name: str, args: dict[str, Any]) -> str:
        normalized = LoopDetector._normalize_args(tool_name, args)
        payload = json.dumps({"name": tool_name, "args": normalized}, sort_keys=True)
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    def record(self, tool_name: str, args: dict[str, Any]) -> str:
        call_hash = self._hash_call(tool_name, args)
        self._history.append(call_hash)
        if len(self._history) > self.window_size:
            self._history.pop(0)
        return call_hash

    def check(self, call_hash: str) -> str | None:
        count = self._history.count(call_hash)

        if count >= self.hard_limit and call_hash not in self._stopped_hashes:
            self._stopped_hashes.add(call_hash)
            return "hard"

        if count >= self.warn_threshold and call_hash not in self._warned_hashes:
            self._warned_hashes.add(call_hash)
            return "warn"

        return None

    def get_warning_message(self, tool_name: str) -> str:
        return (
            f"[LOOP DETECTED] You are repeatedly calling '{tool_name}' "
            f"with the same arguments. Consider a different approach."
        )

    def get_hard_stop_message(self, tool_name: str) -> str:
        return (
            f"[FORCED STOP] Repetitive calls to '{tool_name}' exceeded the safety limit. "
            f"Please summarize what you have learned so far and respond to the user."
        )


class LoopDetectionWrapper(BaseTool):
    """Wrap a BaseTool to inject loop-detection logic."""

    def __init__(self, tool: BaseTool, detector: LoopDetector):
        super().__init__(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema if hasattr(tool, "args_schema") else None,
        )
        self._tool = tool
        self._detector = detector

    async def _arun(self, *args, **kwargs):
        call_hash = self._detector.record(self._tool.name, kwargs or {})
        status = self._detector.check(call_hash)

        if status == "hard":
            return self._detector.get_hard_stop_message(self._tool.name)

        result = await self._tool._arun(*args, **kwargs)

        if status == "warn":
            result = f"{result}\n\n{self._detector.get_warning_message(self._tool.name)}"

        return result

    def _run(self, *args, **kwargs):
        call_hash = self._detector.record(self._tool.name, kwargs or {})
        status = self._detector.check(call_hash)

        if status == "hard":
            return self._detector.get_hard_stop_message(self._tool.name)

        result = self._tool._run(*args, **kwargs)

        if status == "warn":
            result = f"{result}\n\n{self._detector.get_warning_message(self._tool.name)}"

        return result


def wrap_tools_with_loop_detection(
    tools: list[BaseTool],
    warn_threshold: int = 3,
    hard_limit: int = 5,
) -> list[BaseTool]:
    detector = LoopDetector(
        warn_threshold=warn_threshold,
        hard_limit=hard_limit,
    )
    return [LoopDetectionWrapper(t, detector) for t in tools]

