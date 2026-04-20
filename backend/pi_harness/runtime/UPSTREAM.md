# pi_harness runtime upstream notes

This directory contains a minimal vendored subset of `/Users/mac/Desktop/mini-harness`.

Goals:

- Keep only the reusable agent runtime core needed by PIAgent.
- Adapt that core to PIAgent's current LangGraph/LangChain versions.
- Avoid pulling in mini-harness API, CLI, config, or sandbox layers as runtime dependencies.

Current source mapping:

- `agent/graph.py` <- `mini_harness/agent/graph.py` (adapted for injected model/tools and no config dependency)
- `agent/loop_detection.py` <- `mini_harness/agent/loop_detection.py`
- `skills/loader.py` <- `mini_harness/skills/loader.py`
- `skills/models.py` <- `mini_harness/skills/models.py`
- `skills/prompt.py` <- `mini_harness/skills/prompt.py`
- `memory/summarizer.py` <- `mini_harness/memory/summarizer.py`
- `tools/builtins/clarification.py` <- `mini_harness/tools/builtins/clarification.py`
- `tools/registry.py` <- simplified local adaptation of `mini_harness/tools/registry.py`

Intentionally excluded:

- `mini_harness/api/`
- `mini_harness/cli.py`
- `mini_harness/config/`
- `mini_harness/sandbox/`
- builtins unrelated to the PIAgent harness migration

Sync policy:

- Only sync upstream changes for modules that PIAgent actively uses.
- Prefer copying targeted logic changes instead of bulk directory replacement.
- Re-run `backend/tests/test_pi_harness_runtime.py` after any upstream sync.
