import pytest

from backend.core.run_context import RunContext
from backend.models.provider import Provider


def test_run_context_reuses_built_llm_provider(db, monkeypatch):
    row = Provider(
        id=11,
        type="openai",
        name="test",
        api_key_encrypted="enc",
        enabled=True,
        category="llm",
    )
    db.add(row)
    db.commit()

    calls = []

    class BuiltProvider:
        pass

    def fake_build_provider(provider_row):
        calls.append(provider_row.id)
        return BuiltProvider()

    monkeypatch.setattr("backend.core.run_context.build_provider", fake_build_provider)

    ctx = RunContext(db_factory=lambda: db, owns_db_session=False)

    first = ctx.get_llm_provider(11)
    second = ctx.get_llm_provider(11)

    assert first is second
    assert calls == [11]


@pytest.mark.asyncio
async def test_run_context_emit_forwards_event():
    events = []

    async def on_event(event):
        events.append(event)

    ctx = RunContext(on_event=on_event)

    await ctx.emit({"type": "workflow_start"})

    assert events == [{"type": "workflow_start"}]
