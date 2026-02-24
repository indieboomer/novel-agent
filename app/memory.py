"""File-based state persistence for the novel agent."""

import json
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from models import AgentState, Memory, Outline, LogEntry, AgentStatus, GenStep


OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/output"))
STATE_FILE = OUTPUT_DIR / "agent_state.json"
MEMORY_FILE = OUTPUT_DIR / "memory.json"
OUTLINE_FILE = OUTPUT_DIR / "outline_state.json"
LOGS_FILE = OUTPUT_DIR / "logs.jsonl"
MANUSCRIPT_FILE = OUTPUT_DIR / "manuscript.md"
REPORT_FILE = OUTPUT_DIR / "editor_report.md"


def ensure_output_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── State ────────────────────────────────────────────────────────────────────

def load_state() -> AgentState:
    ensure_output_dir()
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            state = AgentState(**data)
            # If it was running when interrupted, mark as stopped
            if state.status == AgentStatus.RUNNING:
                state.status = AgentStatus.STOPPED
            return state
        except Exception:
            pass
    return AgentState()


def save_state(state: AgentState):
    ensure_output_dir()
    STATE_FILE.write_text(
        state.model_dump_json(indent=2), encoding="utf-8"
    )


async def async_save_state(state: AgentState):
    await asyncio.to_thread(save_state, state)


# ── Memory ───────────────────────────────────────────────────────────────────

def load_memory() -> Memory:
    ensure_output_dir()
    if MEMORY_FILE.exists():
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            return Memory(**data)
        except Exception:
            pass
    return Memory()


def save_memory(mem: Memory):
    ensure_output_dir()
    MEMORY_FILE.write_text(
        mem.model_dump_json(indent=2), encoding="utf-8"
    )


async def async_save_memory(mem: Memory):
    await asyncio.to_thread(save_memory, mem)


# ── Outline ──────────────────────────────────────────────────────────────────

def load_outline() -> Optional[Outline]:
    ensure_output_dir()
    if OUTLINE_FILE.exists():
        try:
            data = json.loads(OUTLINE_FILE.read_text(encoding="utf-8"))
            return Outline(**data)
        except Exception:
            pass
    return None


def save_outline(outline: Outline):
    ensure_output_dir()
    OUTLINE_FILE.write_text(
        outline.model_dump_json(indent=2), encoding="utf-8"
    )


async def async_save_outline(outline: Outline):
    await asyncio.to_thread(save_outline, outline)


# ── Logs ─────────────────────────────────────────────────────────────────────

_in_memory_logs: list[LogEntry] = []
_log_lock = asyncio.Lock()


async def append_log(entry: LogEntry):
    async with _log_lock:
        _in_memory_logs.append(entry)
        if len(_in_memory_logs) > 500:
            _in_memory_logs.pop(0)
    # Persist to file
    line = entry.model_dump_json() + "\n"
    await asyncio.to_thread(_write_log_line, line)


def _write_log_line(line: str):
    ensure_output_dir()
    with open(LOGS_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def get_logs(n: int = 50) -> list[LogEntry]:
    return _in_memory_logs[-n:]


def load_logs_from_file(n: int = 100) -> list[LogEntry]:
    if not LOGS_FILE.exists():
        return []
    entries = []
    try:
        lines = LOGS_FILE.read_text(encoding="utf-8").strip().splitlines()
        for line in lines[-n:]:
            try:
                entries.append(LogEntry(**json.loads(line)))
            except Exception:
                pass
    except Exception:
        pass
    return entries


def make_log(
    msg: str,
    level: str = "info",
    chapter: Optional[int] = None,
    page: Optional[int] = None,
    step: Optional[str] = None,
) -> LogEntry:
    return LogEntry(
        ts=now_iso(),
        level=level,
        msg=msg,
        chapter=chapter,
        page=page,
        step=step,
    )


# ── Manuscript ───────────────────────────────────────────────────────────────

def init_manuscript(title: str = "Zosia i Miasto Szeptów"):
    ensure_output_dir()
    if not MANUSCRIPT_FILE.exists():
        MANUSCRIPT_FILE.write_text(
            f"# {title}\n\n", encoding="utf-8"
        )


def append_chapter_header(chapter_num: int, chapter_title: str):
    ensure_output_dir()
    with open(MANUSCRIPT_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n## Rozdział {chapter_num}: {chapter_title}\n\n")


def append_page(page_text: str):
    ensure_output_dir()
    with open(MANUSCRIPT_FILE, "a", encoding="utf-8") as f:
        f.write(page_text.strip() + "\n\n")


async def async_append_page(page_text: str):
    await asyncio.to_thread(append_page, page_text)


async def async_append_chapter_header(num: int, title: str):
    await asyncio.to_thread(append_chapter_header, num, title)


def get_manuscript_text() -> str:
    if MANUSCRIPT_FILE.exists():
        return MANUSCRIPT_FILE.read_text(encoding="utf-8")
    return ""


def count_words_in_manuscript() -> int:
    text = get_manuscript_text()
    return len(text.split())


# ── Editor Report ─────────────────────────────────────────────────────────────

def append_to_report(entry: str):
    ensure_output_dir()
    with open(REPORT_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


async def async_append_to_report(entry: str):
    await asyncio.to_thread(append_to_report, entry)


# ── Brief ─────────────────────────────────────────────────────────────────────

def load_brief() -> str:
    brief_path = Path(__file__).parent / "brief.txt"
    if brief_path.exists():
        return brief_path.read_text(encoding="utf-8")
    return ""
