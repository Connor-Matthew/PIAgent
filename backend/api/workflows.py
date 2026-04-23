import json
import asyncio
import contextlib
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from backend.database import get_db
from backend.models.workflow import Workflow
from backend.models.run import WorkflowRun
from backend.models.run_event import WorkflowRunEvent
from backend.core.engine import ExecutionEngine
from backend.core.compiler import GraphCompiler, CompilerError, CycleDetectedError
from backend.core.graph_schema import dump_graph, load_graph

router = APIRouter(prefix="/api/workflows", tags=["workflows"])
RUN_TASKS: dict[str, asyncio.Task] = {}


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    graph: dict


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    graph: dict | None = None


class RunCreate(BaseModel):
    inputs: dict | None = None
    input: str | None = None


def _normalize_graph_payload(graph: dict) -> dict:
    return dump_graph(load_graph(graph))


def _serialize_state(state: dict) -> dict:
    """Serialize a WorkflowState for JSON response, handling LangChain messages."""
    result = dict(state)
    if "messages" in result:
        serialized_messages = []
        for msg in result["messages"]:
            if hasattr(msg, "model_dump"):
                serialized_messages.append(msg.model_dump())
            elif hasattr(msg, "dict"):
                serialized_messages.append(msg.dict())
            elif hasattr(msg, "content"):
                serialized_messages.append({"type": getattr(msg, "type", "unknown"), "content": msg.content})
            else:
                serialized_messages.append(str(msg))
        result["messages"] = serialized_messages
    return result


# --- CRUD ---

@router.post("", status_code=201)
def create_workflow(body: WorkflowCreate, db: Session = Depends(get_db)):
    graph = _normalize_graph_payload(body.graph)
    compiler = GraphCompiler()
    try:
        compiler.validate(graph, db=db)
    except (CompilerError, ValueError, CycleDetectedError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    wf = Workflow(name=body.name, description=body.description)
    wf.graph = graph
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
    graph = _normalize_graph_payload(body.graph) if body.graph is not None else None
    if graph is not None:
        compiler = GraphCompiler()
        try:
            compiler.validate(graph, db=db)
        except (CompilerError, ValueError, CycleDetectedError) as e:
            raise HTTPException(status_code=400, detail=str(e))
    if body.name is not None:
        wf.name = body.name
    if body.description is not None:
        wf.description = body.description
    if graph is not None:
        wf.graph = graph
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

    compiler = GraphCompiler()
    try:
        compiler.validate(wf.graph, db=db)
    except (CompilerError, ValueError, CycleDetectedError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    inputs = body.inputs or {}
    user_input = body.input if body.input is not None else inputs.get("input", "")

    # Persist run input: prefer JSON-serialized inputs, fall back to plain input text
    if body.inputs is not None:
        run_input_text = json.dumps(body.inputs, ensure_ascii=False)
    else:
        run_input_text = user_input

    run = WorkflowRun(workflow_id=wf.id, input_text=run_input_text, status="running")
    await run_in_threadpool(lambda: db.add(run))
    await run_in_threadpool(lambda: db.commit())
    await run_in_threadpool(lambda: db.refresh(run))
    return {
        "run_id": run.id,
        "status": "running",
        "output": {},
        "answer": "",
        "outputs": {},
    }


@router.post("/{workflow_id}/runs/{run_id}/stop")
async def stop_run(workflow_id: str, run_id: str, db: Session = Depends(get_db)):
    run = await run_in_threadpool(lambda: db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first())
    if not run or run.workflow_id != workflow_id:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status in {"completed", "failed", "cancelled"}:
        return {
            "run_id": run.id,
            "status": run.status,
            "message": "Run already finished",
        }

    run.status = "cancelled"
    run.output = {
        "message": "Execution cancelled by user",
        "answer": "",
        "outputs": {},
    }
    await run_in_threadpool(lambda: db.commit())

    task = RUN_TASKS.get(run_id)
    if task is not None and not task.done():
        task.cancel()

    return {
        "run_id": run.id,
        "status": "cancelled",
        "message": "Execution cancelled by user",
    }


@router.get("/{workflow_id}/runs/{run_id}/events")
async def stream_run_events(
    workflow_id: str,
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """SSE endpoint for real-time workflow execution events."""
    wf = await run_in_threadpool(lambda: db.query(Workflow).filter(Workflow.id == workflow_id).first())
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    compiler = GraphCompiler()
    try:
        compiler.validate(wf.graph, db=db)
    except (CompilerError, ValueError, CycleDetectedError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    run = await run_in_threadpool(lambda: db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first())
    if not run or run.workflow_id != workflow_id:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status in {"completed", "failed", "cancelled"}:
        payload = {
            "type": "workflow_end",
            "status": run.status,
            "duration": run.duration,
            "answer": run.output.get("answer", ""),
            "outputs": run.output.get("outputs", {}),
        }
        if run.status == "cancelled":
            payload["message"] = run.output.get("message", "Execution cancelled by user")

        async def replay_generator():
            yield f"event: workflow_end\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            replay_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Decode persisted input
    try:
        parsed = json.loads(run.input_text)
        if isinstance(parsed, dict):
            inputs = parsed
            user_input = inputs.get("input", "")
        else:
            inputs = {}
            user_input = run.input_text or ""
    except (json.JSONDecodeError, TypeError):
        inputs = {}
        user_input = run.input_text or ""

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        event_seq = 0

        async def on_event(event):
            nonlocal event_seq
            event_seq += 1
            event_row = WorkflowRunEvent(
                workflow_id=workflow_id,
                run_id=run_id,
                seq=event_seq,
                event_type=event.get("type", "unknown"),
            )
            event_row.event = event
            await run_in_threadpool(lambda: db.add(event_row))
            await run_in_threadpool(lambda: db.commit())
            await queue.put(event)
            await asyncio.sleep(0)

        engine = ExecutionEngine()

        async def execute():
            run.status = "running"
            await run_in_threadpool(lambda: db.commit())
            started_at = time.time()
            try:
                result = await engine.run(wf.graph, user_input=user_input, inputs=inputs, on_event=on_event)
                serializable_result = _serialize_state(result)
                run.status = "completed"
                run.output = serializable_result
                run.duration = round(time.time() - started_at, 3)
                await run_in_threadpool(lambda: db.commit())
            except asyncio.CancelledError:
                cancelled_duration = round(time.time() - started_at, 3)
                await on_event({
                    "type": "workflow_end",
                    "status": "cancelled",
                    "duration": cancelled_duration,
                    "answer": "",
                    "outputs": {},
                    "message": "Execution cancelled by user",
                })
                run.status = "cancelled"
                run.output = {
                    "message": "Execution cancelled by user",
                    "answer": "",
                    "outputs": {},
                }
                run.duration = cancelled_duration
                await run_in_threadpool(lambda: db.commit())
                raise
            except Exception as exc:
                run.status = "failed"
                run.output = {"error": str(exc)}
                run.duration = round(time.time() - started_at, 3)
                await run_in_threadpool(lambda: db.commit())
            finally:
                RUN_TASKS.pop(run_id, None)
                await queue.put(None)

        task = asyncio.create_task(execute())
        RUN_TASKS[run_id] = task

        try:
            while True:
                if await request.is_disconnected():
                    if not task.done():
                        task.cancel()
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    continue

                if event is None:
                    break
                if event.get("type") == "workflow_end" and event.get("status") == "failed":
                    yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    break
                yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
