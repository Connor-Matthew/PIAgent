from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.harness.tools.base import Tool


class ListProvidersInput(BaseModel):
    type: Literal["llm", "tts", "all"] = "all"
    detailed: bool = False


class LLMProviderInfo(BaseModel):
    id: int
    name: str
    type: str
    default_model: str


class TTSProviderInfo(BaseModel):
    id: int
    name: str
    type: str
    voices: list[dict] = Field(default_factory=list)


class ListProvidersOutput(BaseModel):
    llm_providers: list[LLMProviderInfo] = Field(default_factory=list)
    tts_providers: list[TTSProviderInfo] = Field(default_factory=list)


class ListProvidersTool:
    name = "list_providers"
    input_schema = ListProvidersInput
    output_schema = ListProvidersOutput
    side_effects = False

    def __init__(self, capabilities):
        self.capabilities = capabilities

    async def run(self, args: ListProvidersInput) -> ListProvidersOutput:
        llm = []
        tts = []
        if args.type in ("llm", "all"):
            for p in self.capabilities.llm_providers:
                info = LLMProviderInfo(
                    id=p.id,
                    name=p.name,
                    type=p.type,
                    default_model=p.default_model,
                )
                llm.append(info)
        if args.type in ("tts", "all"):
            for p in self.capabilities.tts_providers:
                voices = []
                if args.detailed and hasattr(p, "voices") and p.voices:
                    voices = [{"id": v, "name": v} for v in p.voices]
                info = TTSProviderInfo(
                    id=p.id,
                    name=p.name,
                    type=p.type,
                    voices=voices,
                )
                tts.append(info)
        return ListProvidersOutput(llm_providers=llm, tts_providers=tts)
