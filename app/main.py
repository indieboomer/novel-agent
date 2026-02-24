"""FastAPI web application: dashboard + SSE + agent control endpoints."""

import asyncio
import json
import os
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

load_dotenv()  # Load .env at startup

import memory as mem
from agent import NovelAgent
from models import AgentState, AgentStatus, GenStep, LogEntry, STEP_LABELS

# ── App setup ─────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Novel Agent Dashboard", docs_url=None, redoc_url=None)

# ── Shared state ──────────────────────────────────────────────────────────────

_agent_state: AgentState = mem.load_state()
_agent_task: asyncio.Task | None = None
_agent_instance: NovelAgent | None = None

# Pre-load logs from previous run
for _entry in mem.load_logs_from_file(100):
    mem._in_memory_logs.append(_entry)


# ── Log helper ────────────────────────────────────────────────────────────────

async def _log(
    msg: str,
    level: str = "info",
    chapter: int | None = None,
    page: int | None = None,
    step: str | None = None,
):
    entry = mem.make_log(msg, level=level, chapter=chapter, page=page, step=step)
    await mem.append_log(entry)


# ── Agent control ─────────────────────────────────────────────────────────────

async def _run_agent():
    global _agent_state, _agent_instance
    _agent_instance = NovelAgent(state=_agent_state, log_fn=_log)
    await _agent_instance.run()


@app.post("/api/start")
async def start_agent():
    global _agent_task, _agent_state

    if _agent_task and not _agent_task.done():
        return {"status": "already_running"}

    if _agent_state.status == AgentStatus.COMPLETE:
        return {"status": "already_complete", "message": "Powieść jest już gotowa. Użyj /api/reset aby zacząć od nowa."}

    # If stopped/idle, resume from saved position
    _agent_state.status = AgentStatus.RUNNING
    _agent_state.error = None
    mem.save_state(_agent_state)

    _agent_task = asyncio.create_task(_run_agent())
    await _log("Agent uruchomiony.", level="success")
    return {"status": "started", "chapter": _agent_state.chapter, "page": _agent_state.page}


@app.post("/api/stop")
async def stop_agent():
    global _agent_task, _agent_instance

    if _agent_instance:
        _agent_instance.stop()

    if _agent_task and not _agent_task.done():
        _agent_task.cancel()
        try:
            await asyncio.wait_for(_agent_task, timeout=5)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    _agent_state.status = AgentStatus.STOPPED
    _agent_state.step = GenStep.IDLE
    mem.save_state(_agent_state)
    await _log("Agent zatrzymany.", level="warning")
    return {"status": "stopped"}


@app.post("/api/reset")
async def reset_agent():
    global _agent_task, _agent_instance, _agent_state

    # Stop if running
    if _agent_instance:
        _agent_instance.stop()
    if _agent_task and not _agent_task.done():
        _agent_task.cancel()
        try:
            await asyncio.wait_for(_agent_task, timeout=5)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    # Reset state to initial
    _agent_state = AgentState()
    mem.save_state(_agent_state)

    # Remove output files to start fresh
    for f in [mem.MEMORY_FILE, mem.OUTLINE_FILE, mem.MANUSCRIPT_FILE, mem.REPORT_FILE]:
        if f.exists():
            f.unlink()

    # Clear in-memory logs
    mem._in_memory_logs.clear()
    await _log("Reset zakończony. Możesz rozpocząć generowanie od nowa.", level="info")
    return {"status": "reset"}


# ── Data endpoints ────────────────────────────────────────────────────────────

@app.get("/api/state")
async def get_state():
    state_dict = _agent_state.model_dump()
    state_dict["step_label"] = STEP_LABELS.get(_agent_state.step, _agent_state.step)
    state_dict["progress_pct"] = (
        round(_agent_state.pages_done / _agent_state.pages_target * 100, 1)
        if _agent_state.pages_target > 0 else 0
    )
    state_dict["is_running"] = (
        _agent_task is not None and not _agent_task.done()
    )
    return state_dict


@app.get("/api/logs")
async def get_logs(n: int = 50):
    return [e.model_dump() for e in mem.get_logs(n)]


@app.get("/api/preview")
async def get_preview():
    return {
        "text": _agent_state.preview,
        "chapter": _agent_state.chapter,
        "page": _agent_state.page,
        "chapter_title": _agent_state.chapter_title,
    }


@app.get("/api/outline")
async def get_outline():
    outline = mem.load_outline()
    if not outline:
        return {"chapters": []}
    return outline.model_dump()


@app.get("/api/memory")
async def get_memory():
    m = mem.load_memory()
    return m.model_dump()


# ── Download ──────────────────────────────────────────────────────────────────

@app.get("/api/download")
async def download_manuscript(format: str = "md"):
    if not mem.MANUSCRIPT_FILE.exists():
        raise HTTPException(status_code=404, detail="Rękopis nie jest jeszcze dostępny.")

    if format == "txt":
        # Strip markdown headers for plain text
        text = mem.get_manuscript_text()
        text = "\n".join(
            line for line in text.splitlines()
            if not line.startswith("#")
        )
        return StreamingResponse(
            iter([text]),
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=zosia_i_miasto_szeptow.txt"
            },
        )

    return FileResponse(
        path=str(mem.MANUSCRIPT_FILE),
        media_type="text/markdown; charset=utf-8",
        filename="zosia_i_miasto_szeptow.md",
    )


@app.get("/api/report")
async def download_report():
    if not mem.REPORT_FILE.exists():
        raise HTTPException(status_code=404, detail="Raport edytora nie jest jeszcze dostępny.")
    return FileResponse(
        path=str(mem.REPORT_FILE),
        media_type="text/markdown; charset=utf-8",
        filename="editor_report.md",
    )


# ── SSE stream ────────────────────────────────────────────────────────────────

@app.get("/progress")
async def progress_stream(request: Request):
    async def event_generator() -> AsyncGenerator[dict, None]:
        while True:
            if await request.is_disconnected():
                break

            state_dict = _agent_state.model_dump()
            state_dict["step_label"] = STEP_LABELS.get(_agent_state.step, _agent_state.step)
            state_dict["progress_pct"] = (
                round(_agent_state.pages_done / _agent_state.pages_target * 100, 1)
                if _agent_state.pages_target > 0 else 0
            )
            state_dict["is_running"] = (
                _agent_task is not None and not _agent_task.done()
            )

            logs = mem.get_logs(20)
            payload = {
                "state": state_dict,
                "logs": [e.model_dump() for e in logs],
            }

            yield {
                "event": "update",
                "data": json.dumps(payload, ensure_ascii=False),
            }
            await asyncio.sleep(2)

    return EventSourceResponse(event_generator())


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    mem.ensure_output_dir()
    global _agent_state
    _agent_state = mem.load_state()
    # Reload logs from file
    for entry in mem.load_logs_from_file(100):
        if entry not in mem._in_memory_logs:
            mem._in_memory_logs.append(entry)
