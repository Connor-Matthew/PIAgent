from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy.orm import Session

from backend.models.assistant_session import AssistantSession


def get_or_create_session(db: Session, workflow_id: str) -> AssistantSession:
    session = (
        db.query(AssistantSession)
        .filter(AssistantSession.workflow_id == workflow_id)
        .first()
    )
    if session:
        return session

    session = AssistantSession(workflow_id=workflow_id)
    session.messages = []
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def append_turn(db: Session, session: AssistantSession, user_text: str, assistant_text: str) -> None:
    messages = list(session.messages)
    messages.append({"role": "user", "content": user_text})
    messages.append({"role": "assistant", "content": assistant_text})
    session.messages = messages
    db.commit()
    db.refresh(session)


def to_langchain_messages(session: AssistantSession, user_text: str) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for item in session.messages:
        role = item.get("role")
        content = item.get("content", "")
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    messages.append(HumanMessage(content=user_text))
    return messages
