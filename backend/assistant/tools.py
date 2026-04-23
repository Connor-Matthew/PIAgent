from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.core.crypto import decrypt, mask_key
from backend.core.graph_schema import get_node_config
from backend.models.knowledge_base import KnowledgeBase
from backend.models.provider import Provider
from backend.models.run import WorkflowRun
from backend.models.run_event import WorkflowRunEvent
from backend.models.workflow import Workflow
from backend.nodes.contracts import list_contracts
from backend.rag.vectorstore import get_vectorstore


class NodeConfigArgs(BaseModel):
    node_id: str


class PeekKnowledgeBaseArgs(BaseModel):
    kb_id: str
    query: str | None = None
    top_k: int = Field(default=3, ge=1, le=10)


class RecentRunsArgs(BaseModel):
    limit: int = Field(default=5, ge=1, le=20)


class RunEventsArgs(BaseModel):
    run_id: str


class AssistantTool(BaseTool):
    db: Session
    workflow_id: str
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _workflow(self) -> Workflow:
        workflow = self.db.query(Workflow).filter(Workflow.id == self.workflow_id).first()
        if not workflow:
            raise ValueError(f"Workflow not found: {self.workflow_id}")
        return workflow


class GetCurrentGraphTool(AssistantTool):
    name: str = "get_current_graph"
    description: str = "Return the current workflow graph and metadata."

    def _run(self) -> dict[str, Any]:
        workflow = self._workflow()
        return {
            "id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
            "graph": workflow.graph,
        }


class GetNodeConfigTool(AssistantTool):
    name: str = "get_node_config"
    description: str = "Return one node's type, label, and config."
    args_schema: type[BaseModel] = NodeConfigArgs

    def _run(self, node_id: str) -> dict[str, Any]:
        workflow = self._workflow()
        for node in workflow.graph.get("nodes", []):
            if node.get("id") == node_id:
                return {
                    "node_id": node_id,
                    "type": node.get("type"),
                    "label": node.get("label") or node.get("data", {}).get("label"),
                    "config": get_node_config(node),
                }
        raise ValueError(f"Node not found: {node_id}")


class ListNodeTypesTool(AssistantTool):
    name: str = "list_node_types"
    description: str = "List available node types and their schemas."

    def _run(self) -> dict[str, Any]:
        return {
            "node_types": [
                {
                    "node_type": contract.node_type,
                    "description": contract.description,
                    "config_fields": [field.model_dump() for field in contract.config_fields],
                    "input_refs": [ref.model_dump() for ref in contract.input_refs],
                    "output_fields": [field.model_dump() for field in contract.output_fields],
                }
                for contract in list_contracts()
            ]
        }


class ListProvidersTool(AssistantTool):
    name: str = "list_providers"
    description: str = "List configured LLM and TTS providers with API keys redacted."

    def _run(self) -> dict[str, Any]:
        providers = self.db.query(Provider).all()
        return {
            "providers": [
                {
                    "id": provider.id,
                    "type": provider.type,
                    "category": provider.category,
                    "name": provider.name,
                    "base_url": provider.base_url,
                    "api_key": mask_key(decrypt(provider.api_key_encrypted)),
                    "enabled": provider.enabled,
                    "selected_models": provider.selected_models or [],
                    "extra_config": provider.extra_config or {},
                }
                for provider in providers
            ]
        }


class ListKnowledgeBasesTool(AssistantTool):
    name: str = "list_knowledge_bases"
    description: str = "List available knowledge bases."

    def _run(self) -> dict[str, Any]:
        kbs = self.db.query(KnowledgeBase).all()
        return {
            "knowledge_bases": [
                {
                    "id": kb.id,
                    "name": kb.name,
                    "description": kb.description,
                    "doc_count": kb.doc_count,
                }
                for kb in kbs
            ]
        }


class PeekKnowledgeBaseTool(AssistantTool):
    name: str = "peek_knowledge_base"
    description: str = "Inspect representative chunks from a knowledge base."
    args_schema: type[BaseModel] = PeekKnowledgeBaseArgs

    def _run(self, kb_id: str, query: str | None = None, top_k: int = 3) -> dict[str, Any]:
        kb = self.db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        if not kb:
            raise ValueError(f"Knowledge base not found: {kb_id}")

        if not query:
            return {
                "kb_id": kb_id,
                "name": kb.name,
                "chunks": [],
                "message": "Provide a query to retrieve representative chunks.",
            }

        vectorstore = get_vectorstore(collection_name=kb_id)
        retriever = vectorstore.as_retriever(search_kwargs={"k": top_k})
        docs = retriever.invoke(query)
        return {
            "kb_id": kb_id,
            "name": kb.name,
            "chunks": [
                {"content": doc.page_content, "metadata": doc.metadata}
                for doc in docs
            ],
        }


class GetRecentRunsTool(AssistantTool):
    name: str = "get_recent_runs"
    description: str = "Return recent workflow runs for the current workflow."
    args_schema: type[BaseModel] = RecentRunsArgs

    def _run(self, limit: int = 5) -> dict[str, Any]:
        runs = (
            self.db.query(WorkflowRun)
            .filter(WorkflowRun.workflow_id == self.workflow_id)
            .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
            .limit(limit)
            .all()
        )
        return {
            "runs": [
                {
                    "id": run.id,
                    "status": run.status,
                    "input_text": run.input_text,
                    "output": run.output,
                    "duration": run.duration,
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                }
                for run in runs
            ]
        }


class GetRunEventsTool(AssistantTool):
    name: str = "get_run_events"
    description: str = "Return persisted SSE events for a workflow run."
    args_schema: type[BaseModel] = RunEventsArgs

    def _run(self, run_id: str) -> dict[str, Any]:
        run = (
            self.db.query(WorkflowRun)
            .filter(WorkflowRun.id == run_id)
            .filter(WorkflowRun.workflow_id == self.workflow_id)
            .first()
        )
        if not run:
            raise ValueError(f"Run not found: {run_id}")

        rows = (
            self.db.query(WorkflowRunEvent)
            .filter(WorkflowRunEvent.workflow_id == self.workflow_id)
            .filter(WorkflowRunEvent.run_id == run_id)
            .order_by(WorkflowRunEvent.seq)
            .all()
        )
        return {
            "run_id": run_id,
            "events": [row.event for row in rows],
        }


def build_readonly_tools(db: Session, workflow_id: str) -> list[BaseTool]:
    return [
        GetCurrentGraphTool(db=db, workflow_id=workflow_id),
        GetNodeConfigTool(db=db, workflow_id=workflow_id),
        ListNodeTypesTool(db=db, workflow_id=workflow_id),
        ListProvidersTool(db=db, workflow_id=workflow_id),
        ListKnowledgeBasesTool(db=db, workflow_id=workflow_id),
        PeekKnowledgeBaseTool(db=db, workflow_id=workflow_id),
        GetRecentRunsTool(db=db, workflow_id=workflow_id),
        GetRunEventsTool(db=db, workflow_id=workflow_id),
    ]
