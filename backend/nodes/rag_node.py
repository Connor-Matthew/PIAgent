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
        on_event = kwargs.get("on_event")
        # run_context = kwargs.get("run_context")  # reserved for future use

        async with self.heartbeat(on_event, message="检索知识库中..."):
            docs = await retriever.ainvoke(query)
        context = "\n\n".join(doc.page_content for doc in docs)

        state["context"] = context
        state.setdefault("node_outputs", {})
        state["node_outputs"][self.node_id] = {
            "context": context,
            "documents": [
                {"page_content": doc.page_content, "metadata": doc.metadata}
                for doc in docs
            ],
        }

        return state
