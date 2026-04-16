from backend.agent.capabilities import AgentCapabilities
from backend.agent.defaults import (
    DEFAULT_NODE_POSITIONS,
    build_llm_system_prompt,
    make_node_data,
)
from backend.agent.schemas import RecipeIR
from backend.agent.validator import ensure_valid_recipe_ir
from backend.core.compiler import GraphCompiler


class AgentAdapterError(Exception):
    pass


class WorkflowGraphAdapter:
    def __init__(self, capabilities: AgentCapabilities):
        self.capabilities = capabilities

    def build_graph(
        self,
        recipe_ir: RecipeIR,
        *,
        system_prompt_override: str | None = None,
    ) -> dict:
        ensure_valid_recipe_ir(recipe_ir, self.capabilities)

        llm_provider = self.capabilities.get_llm_provider(
            recipe_ir.llm_provider_id
        ) or self.capabilities.first_llm_provider()
        if llm_provider is None:
            raise AgentAdapterError("No enabled LLM provider is available")

        tts_provider = None
        tts_voice_id = None
        if "tts" in recipe_ir.recipe:
            tts_provider = self.capabilities.get_tts_provider(
                recipe_ir.tts_provider_id
            ) or self.capabilities.first_tts_provider()
            if tts_provider is None:
                raise AgentAdapterError("No enabled TTS provider is available")
            tts_voice_id = recipe_ir.tts_voice_id or (
                tts_provider.voices[0] if tts_provider.voices else "default"
            )

        knowledge_base = None
        if "rag" in recipe_ir.recipe:
            knowledge_base = self.capabilities.get_knowledge_base(
                recipe_ir.knowledge_base_id
            ) or self.capabilities.first_knowledge_base()
            if knowledge_base is None:
                raise AgentAdapterError("No knowledge base is available for RAG recipe")

        nodes: list[dict] = []
        edges: list[dict] = []

        nodes.append(
            self._make_node(
                node_id="start_1",
                node_type="start",
                label="用户输入",
                config={
                    "inputs": [
                        {
                            "name": "input",
                            "type": "text",
                            "required": False,
                            "default": recipe_ir.goal_summary,
                        }
                    ]
                },
            )
        )

        previous_node_id = "start_1"
        if knowledge_base is not None:
            nodes.append(
                self._make_node(
                    node_id="rag_1",
                    node_type="rag",
                    label="知识检索",
                    config={
                        "knowledge_base_id": knowledge_base.id,
                        "top_k": 3,
                    },
                )
            )
            edges.append({"source": previous_node_id, "target": "rag_1"})
            previous_node_id = "rag_1"

        nodes.append(
            self._make_node(
                node_id="llm_1",
                node_type="llm",
                label="脚本生成",
                config={
                    "provider_id": llm_provider.id,
                    "model": llm_provider.default_model,
                    "temperature": 0.7,
                    "system_prompt": (
                        system_prompt_override.strip()
                        if system_prompt_override and system_prompt_override.strip()
                        else build_llm_system_prompt(recipe_ir)
                    ),
                },
            )
        )
        edges.append({"source": previous_node_id, "target": "llm_1"})
        previous_node_id = "llm_1"

        if tts_provider is not None:
            nodes.append(
                self._make_node(
                    node_id="tts_1",
                    node_type="tts",
                    label="语音合成",
                    config={
                        "provider_id": tts_provider.id,
                        "voice_id": tts_voice_id,
                    },
                )
            )
            edges.append({"source": previous_node_id, "target": "tts_1"})
            previous_node_id = "tts_1"

        nodes.append(
            self._make_node(
                node_id="end_1",
                node_type="end",
                label="结束",
                config=self._build_end_config(include_audio=tts_provider is not None),
                locked=True,
            )
        )
        edges.append({"source": previous_node_id, "target": "end_1"})

        graph = {"nodes": nodes, "edges": edges}
        GraphCompiler().validate(graph)
        return graph

    def _make_node(
        self,
        *,
        node_id: str,
        node_type: str,
        label: str,
        config: dict,
        locked: bool = False,
    ) -> dict:
        return {
            "id": node_id,
            "type": node_type,
            "position": DEFAULT_NODE_POSITIONS[node_id],
            "data": make_node_data(
                node_type=node_type,
                label=label,
                config=config,
                locked=locked or node_type in {"start", "end"},
            ),
        }

    def _build_end_config(self, *, include_audio: bool) -> dict:
        outputs = [
            {
                "name": "script",
                "source": "reference",
                "value": "{{llm_1.text}}",
            }
        ]
        answer = "{{script}}"

        if include_audio:
            outputs.append(
                {
                    "name": "audio_url",
                    "source": "reference",
                    "value": "{{tts_1.audio_url}}",
                }
            )
            outputs.append(
                {
                    "name": "duration",
                    "source": "reference",
                    "value": "{{tts_1.duration}}",
                }
            )
            answer = "{{audio_url}}"

        return {
            "outputs": outputs,
            "answer": answer,
        }
