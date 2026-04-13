import json
import asyncio
import time
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from backend.database import get_db
from backend.models.workflow import Workflow
from backend.models.run import WorkflowRun
from backend.core.engine import ExecutionEngine

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    graph: dict


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    graph: dict | None = None


class RunCreate(BaseModel):
    input: str


# --- CRUD ---

@router.post("", status_code=201)
def create_workflow(body: WorkflowCreate, db: Session = Depends(get_db)):
    wf = Workflow(name=body.name, description=body.description)
    wf.graph = body.graph
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "graph": wf.graph,
        "created_at": str(wf.created_at),
    }


@router.get("")
def list_workflows(db: Session = Depends(get_db)):
    workflows = db.query(Workflow).all()
    return [
        {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "created_at": str(w.created_at),
        }
        for w in workflows
    ]


@router.get("/{workflow_id}")
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "graph": wf.graph,
        "created_at": str(wf.created_at),
    }


@router.put("/{workflow_id}")
def update_workflow(workflow_id: str, body: WorkflowUpdate, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if body.name is not None:
        wf.name = body.name
    if body.description is not None:
        wf.description = body.description
    if body.graph is not None:
        wf.graph = body.graph
    db.commit()
    db.refresh(wf)
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "graph": wf.graph,
    }


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: str, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.delete(wf)
    db.commit()
    return Response(status_code=204)


# --- Execution ---

@router.post("/{workflow_id}/run")
async def run_workflow(workflow_id: str, body: RunCreate, db: Session = Depends(get_db)):
    wf = await run_in_threadpool(lambda: db.query(Workflow).filter(Workflow.id == workflow_id).first())
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    run = WorkflowRun(workflow_id=wf.id, input_text=body.input, status="running")
    await run_in_threadpool(lambda: db.add(run))
    await run_in_threadpool(lambda: db.commit())
    await run_in_threadpool(lambda: db.refresh(run))

    engine = ExecutionEngine()
    start = time.time()
    try:
        result = await engine.run(wf.graph, user_input=body.input)
    except Exception as exc:
        duration = round(time.time() - start, 3)
        run.status = "failed"
        run.output = {"error": str(exc)}
        run.duration = duration
        await run_in_threadpool(lambda: db.commit())
        return {"run_id": run.id, "status": "failed", "output": run.output}

    duration = round(time.time() - start, 3)
    run.status = "completed"
    run.output = result
    run.duration = duration
    await run_in_threadpool(lambda: db.commit())

    return {"run_id": run.id, "status": "completed", "output": result}


@router.get("/{workflow_id}/runs/{run_id}/events")
async def stream_run_events(workflow_id: str, run_id: str, db: Session = Depends(get_db)):
    """SSE endpoint for real-time workflow execution events."""
    wf = await run_in_threadpool(lambda: db.query(Workflow).filter(Workflow.id == workflow_id).first())
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    run = await run_in_threadpool(lambda: db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first())
    if not run or run.workflow_id != workflow_id:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_event(event):
            await queue.put(event)

        engine = ExecutionEngine()

        async def execute():
            try:
                result = await engine.run(wf.graph, user_input=run.input_text, on_event=on_event)
            except Exception as exc:
                await queue.put({"type": "workflow_end", "status": "failed", "error": str(exc)})
            finally:
                await queue.put(None)

        task = asyncio.create_task(execute())

        while True:
            event = await queue.get()
            if event is None:
                break
            if event.get("type") == "workflow_end" and event.get("status") == "failed":
                yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                break
            yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

        await task

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{workflow_id}/runs")
def list_runs(workflow_id: str, db: Session = Depends(get_db)):
    runs = db.query(WorkflowRun).filter(WorkflowRun.workflow_id == workflow_id).all()
    return [
        {
            "id": r.id,
            "status": r.status,
            "duration": r.duration,
            "created_at": str(r.created_at),
        }
        for r in runs
    ]
