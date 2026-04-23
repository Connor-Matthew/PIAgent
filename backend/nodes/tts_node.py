from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.core.template import resolve_reference
from backend.tts import TTS_PROVIDER_REGISTRY, build_tts_provider
from backend.tts.parallel import synthesize_long_text
from backend.database import SessionLocal
from backend.models.provider import Provider
from backend.config import settings


class TTSNode(BaseNode):
    node_type = "tts"

    def _get_tts_provider_legacy(self, provider_id):
        db = SessionLocal()
        try:
            row = db.query(Provider).filter(Provider.id == provider_id).first()
            if not row:
                raise ValueError(f"Provider not found: {provider_id}")
            if not row.enabled:
                raise ValueError(f"Provider is disabled: {provider_id}")
            return build_tts_provider(row)
        finally:
            db.close()

    def _get_tts_provider(self, run_context=None):
        provider_id = self.config.get("provider_id")
        if not provider_id:
            raise ValueError("provider_id is required for TTS node")

        if run_context is not None:
            return run_context.get_tts_provider(int(provider_id))
        return self._get_tts_provider_legacy(provider_id)

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        # Prefer explicit text_ref, fallback to legacy state["llm_output"] / state["input"]
        text_ref = self.config.get("text_ref", "")
        if text_ref:
            text = resolve_reference(text_ref, state)
            if not text:
                text = ""
        else:
            text = state.get("llm_output") or state.get("input", "")
        on_event = kwargs.get("on_event")

        provider = self._get_tts_provider(kwargs.get("run_context"))
        voice = self.config.get("voice_id", "default")
        emotion = self.config.get("emotion", "happy")
        speed = self.config.get("speed", 1.0)
        max_chars = int(self.config.get("max_chars", 500))
        max_concurrency = int(self.config.get("max_concurrency", 5))

        progress = {"current": 0, "total": 0}

        async def on_progress(progress_event: dict):
            progress.update(progress_event)
            await self._emit(on_event, {
                "type": "node_stream",
                "node_id": self.node_id,
                "node_type": self.node_type,
                "delta": {
                    **progress_event,
                    "message": f"{progress_event['current']}/{progress_event['total']} 片",
                },
            })

        def heartbeat_message() -> str:
            if progress["total"] > 0:
                return f"语音合成中... {progress['current']}/{progress['total']} 片"
            return "语音合成中..."

        async with self.heartbeat(on_event, message=heartbeat_message):
            audio_url = await synthesize_long_text(
                provider=provider,
                text=text,
                voice=voice,
                output_dir=settings.audio_dir,
                max_chars=max_chars,
                max_concurrency=max_concurrency,
                on_progress=on_progress if on_event is not None else None,
                emotion=emotion,
                speed=speed,
            )

        # Rough duration estimate (~5 chars per second)
        duration = round(len(text) * 0.2, 1) if text else 0.0

        state["audio_url"] = audio_url
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.node_id] = {
            "audio_url": audio_url,
            "duration": duration,
        }

        return state
