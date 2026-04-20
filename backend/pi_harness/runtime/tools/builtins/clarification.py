import contextvars
import json

from langchain_core.tools import BaseTool

_agent_mode: contextvars.ContextVar[str] = contextvars.ContextVar("agent_mode", default="api")


def set_agent_mode(mode: str) -> None:
    _agent_mode.set(mode)


def get_agent_mode() -> str:
    return _agent_mode.get()


class AskClarificationTool(BaseTool):
    """Tool for the agent to ask the user for clarification."""

    name: str = "ask_clarification"
    description: str = (
        "Ask the user a clarifying question when information is missing, "
        "requirements are ambiguous, or a choice needs to be made. "
        "Use this instead of guessing."
    )

    def _run(
        self,
        question: str,
        type: str = "missing_info",
        context: str = "",
        options: list[str] | None = None,
    ) -> str:
        return self._execute(question, type, context, options)

    async def _arun(
        self,
        question: str,
        type: str = "missing_info",
        context: str = "",
        options: list[str] | None = None,
    ) -> str:
        return self._execute(question, type, context, options)

    def _execute(
        self,
        question: str,
        type: str,
        context: str,
        options: list[str] | None,
    ) -> str:
        mode = get_agent_mode()

        if mode == "cli":
            return self._run_interactive(question, type, context, options)

        payload = {
            "__clarification__": True,
            "question": question,
            "type": type,
            "context": context,
            "options": options or [],
        }
        return json.dumps(payload, ensure_ascii=False)

    def _run_interactive(
        self,
        question: str,
        type: str,
        context: str,
        options: list[str] | None,
    ) -> str:
        print(f"\n[{type.replace('_', ' ').title()}]")
        if context:
            print(f"Context: {context}")
        print(f"Question: {question}")
        if options:
            for i, opt in enumerate(options, 1):
                print(f"  {i}. {opt}")
            print("(Enter the number or type your answer)")

        try:
            answer = input("Your answer: ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = "(no response)"

        return f"User clarification: {answer}"

