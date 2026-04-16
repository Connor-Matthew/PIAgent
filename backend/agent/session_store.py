from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.agent.schemas import AgentSessionRead, ClarificationTurn, RecipeIR
from backend.models.agent_session import AgentSession as AgentSessionModel


class AgentSessionStore:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        user_goal: str,
        status: str,
        clarification_turns: list[ClarificationTurn] | None = None,
        answered_dims: dict | None = None,
        events: list[dict] | None = None,
        recipe_ir: RecipeIR | None = None,
        generated_graph: dict | None = None,
        rationale_text: str | None = None,
    ) -> AgentSessionModel:
        record = AgentSessionModel(
            user_goal=user_goal,
            status=status,
            rationale_text=rationale_text,
        )
        record.turns = [turn.model_dump() for turn in (clarification_turns or [])]
        record.answered_dims = answered_dims or {}
        record.events = events or []
        record.recipe = recipe_ir.model_dump() if recipe_ir else None
        record.graph = generated_graph
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get(self, session_id: str) -> AgentSessionModel | None:
        return (
            self.db.query(AgentSessionModel)
            .filter(AgentSessionModel.id == session_id)
            .first()
        )

    def get_or_404(self, session_id: str) -> AgentSessionModel:
        record = self.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Agent session not found")
        return record

    def mark_applied(self, record: AgentSessionModel, workflow_id: str) -> AgentSessionModel:
        record.workflow_id = workflow_id
        record.status = "applied"
        self.db.commit()
        self.db.refresh(record)
        return record

    def save(self, record: AgentSessionModel) -> AgentSessionModel:
        self.db.commit()
        self.db.refresh(record)
        return record

    def append_event(self, record: AgentSessionModel, event: dict) -> AgentSessionModel:
        events = list(record.events)
        events.append(event)
        record.events = events
        return self.save(record)

    def append_events(
        self,
        record: AgentSessionModel,
        new_events: list[dict],
    ) -> AgentSessionModel:
        events = list(record.events)
        events.extend(new_events)
        record.events = events
        return self.save(record)

    def to_read_model(self, record: AgentSessionModel) -> AgentSessionRead:
        return AgentSessionRead(
            session_id=record.id,
            user_goal=record.user_goal,
            status=record.status,
            clarification_turns=[
                ClarificationTurn.model_validate(turn) for turn in record.turns
            ],
            answered_dims=record.answered_dims,
            recipe_ir=RecipeIR.model_validate(record.recipe) if record.recipe else None,
            generated_graph=record.graph,
            rationale_text=record.rationale_text,
            workflow_id=record.workflow_id,
        )
