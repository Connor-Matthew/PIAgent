from __future__ import annotations

from inspect import signature
from typing import Any

from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)
from langchain_core.runnables.config import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.tools.structured import _get_runnable_config_param


class CompatStructuredTool(StructuredTool):
    """StructuredTool variant tolerant of callers that omit the config kwarg."""

    def _run(
        self,
        *args: Any,
        config: RunnableConfig | None = None,
        run_manager: CallbackManagerForToolRun | None = None,
        **kwargs: Any,
    ) -> Any:
        if self.func:
            if run_manager and signature(self.func).parameters.get("callbacks"):
                kwargs["callbacks"] = run_manager.get_child()
            if config is not None and (
                config_param := _get_runnable_config_param(self.func)
            ):
                kwargs[config_param] = config
            return self.func(*args, **kwargs)

        msg = "StructuredTool does not support sync invocation."
        raise NotImplementedError(msg)

    async def _arun(
        self,
        *args: Any,
        config: RunnableConfig | None = None,
        run_manager: AsyncCallbackManagerForToolRun | None = None,
        **kwargs: Any,
    ) -> Any:
        if self.coroutine:
            if run_manager and signature(self.coroutine).parameters.get("callbacks"):
                kwargs["callbacks"] = run_manager.get_child()
            if config is not None and (
                config_param := _get_runnable_config_param(self.coroutine)
            ):
                kwargs[config_param] = config
            return await self.coroutine(*args, **kwargs)

        if config is not None:
            kwargs["config"] = config
        return await BaseTool._arun(self, *args, run_manager=run_manager, **kwargs)
