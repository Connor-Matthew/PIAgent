from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.tts.base import BaseTTSProvider
from backend.tts.fish_audio import FishAudioProvider
from backend.config import settings

TTS_PROVIDERS: dict[str, type[BaseTTSProvider]] = {
    "fish_audio": FishAudioProvider,
}


class TTSNode(BaseNode):
    node_type = "tts"

    def _get_tts_provider(self) -> BaseTTSProvider:
        provider_name = self.config.get("provider", "fish_audio")
        provider_cls = TTS_PROVIDERS.get(provider_name)
        if not provider_cls:
            raise ValueError(f"Unknown TTS provider: {provider_name}")
        return provider_cls()

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        text = state.get("llm_output") or state.get("input", "")

        provider = self._get_tts_provider()
        voice = self.config.get("voice", "default")

        audio_url = await provider.synthesize(
            text=text,
            voice=voice,
            output_dir=settings.audio_dir,
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
