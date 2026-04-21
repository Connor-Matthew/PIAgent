"""Ask-user tool and pause exception for the ReAct builder agent."""

from __future__ import annotations

import json
import uuid
from typing import Any

from langchain_core.tools import tool

from backend.harness.react_tools.base import ToolContext, _json_compact


class PauseAgentRun(Exception):
    """Raised by ask_user tool to pause the ReAct loop and wait for user input."""

    def __init__(self, question_id: str, question: str, options: list[str] | None = None):
        self.question_id = question_id
        self.question = question
        self.options = options
        super().__init__(f"Paused awaiting user input: {question}")


def make_ask_user_tool(ctx: ToolContext) -> Any:
    """Build the ask_user LangChain tool bound to a ToolContext."""

    @tool
    def ask_user(question: str, options: list[str] | None = None) -> str:
        """Ask the user a clarifying question and pause the agent run.

        Use this when information is missing, requirements are ambiguous,
        or a choice needs to be made. Do NOT guess.

        Args:
            question: The clarifying question to ask the user.
            options: Optional list of choice strings. If provided, the user can pick one.
        """
        qid = str(uuid.uuid4())
        ctx.workspace.set_open_question(question, options, question_id=qid)
        # Return a marker that the runner layer detects to emit awaiting_user_input
        # and end the stream gracefully. This avoids exception-based interruption
        # and keeps the checkpointer in a clean resumable state.
        return json.dumps({
            "__pause__": True,
            "question_id": qid,
            "question": question,
            "options": options or [],
        }, ensure_ascii=False)

    return ask_user
