from backend.nodes.base import BaseNode
from backend.core.state import WorkflowState
from backend.rag.vectorstore import get_vectorstore


class RAGNode(BaseNode):
    node_type = "rag"

    def _get_retriever(self):
        kb_id = self.config.get("knowledge_base_id", "default")
        top_k = self.config.get("top_k", 3)
        vectorstore = get_vectorstore(collection_name=kb_id)
        return vectorstore.as_retriever(search_kwargs={"k": top_k})

    async def execute(self, state: WorkflowState, **kwargs) -> WorkflowState:
        query = state.get("input", "")
        retriever = self._get_retriever()

        docs = await retriever.ainvoke(query)
        context = "\n\n".join(doc.page_content for doc in docs)

        state["context"] = context
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.config.get("id", "rag")] = {
            "retrieved_docs": len(docs),
            "context_preview": context[:200],
        }

        return state
