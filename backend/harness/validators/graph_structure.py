from __future__ import annotations

from backend.core.compiler import GraphCompiler, CompilerError, CycleDetectedError
from backend.harness.schemas import GraphCriticReport, SubAgentReport


class GraphStructureValidator:
    name = "graph_structure"

    async def analyze(self, ctx: dict) -> SubAgentReport:
        graph = ctx.get("graph", {})
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])

        risks: list[dict] = []
        score = 100

        if not nodes:
            risks.append({"level": "error", "message": "图中没有任何节点"})
            score -= 50
        else:
            node_ids = {node.get("id") for node in nodes if node.get("id")}
            node_types = {node.get("id"): node.get("type") for node in nodes if node.get("id")}

            # Check for missing start/end nodes
            has_start = any(t == "start" for t in node_types.values())
            has_end = any(t == "end" for t in node_types.values())
            if not has_start:
                risks.append({"level": "warning", "message": "缺少 start 节点，工作流可能无法接收输入"})
                score -= 15
            if not has_end:
                risks.append({"level": "warning", "message": "缺少 end 节点，工作流可能没有明确输出"})
                score -= 15

            # Check for dangling edges
            for edge in edges:
                src = edge.get("source")
                tgt = edge.get("target")
                if src and src not in node_ids:
                    risks.append({"level": "error", "message": f"边引用了不存在的源节点: {src}"})
                    score -= 20
                if tgt and tgt not in node_ids:
                    risks.append({"level": "error", "message": f"边引用了不存在的目标节点: {tgt}"})
                    score -= 20

            # Check for isolated nodes (no incoming or outgoing edges)
            connected_ids = set()
            for edge in edges:
                connected_ids.add(edge.get("source"))
                connected_ids.add(edge.get("target"))
            isolated = [nid for nid in node_ids if nid not in connected_ids]
            if isolated:
                risks.append(
                    {
                        "level": "warning",
                        "message": f"存在孤立节点（无连接）: {', '.join(isolated)}",
                    }
                )
                score -= 10

            # Compiler-level validation (topological sort and cycle detection)
            compiler = GraphCompiler()
            try:
                compiler.validate(graph)
            except CycleDetectedError as exc:
                risks.append({"level": "error", "message": f"检测到环路: {exc}"})
                score -= 40
            except CompilerError as exc:
                risks.append({"level": "error", "message": f"图编译失败: {exc}"})
                score -= 30

        critic_report = GraphCriticReport(risks=risks, score=max(0, score))

        return SubAgentReport(
            agent_name=self.name,
            observations=[critic_report.model_dump()],
            warnings=[r["message"] for r in risks if r["level"] == "warning"],
        )
