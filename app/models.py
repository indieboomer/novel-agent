from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"
    STOPPED = "stopped"


class GenStep(str, Enum):
    IDLE = "idle"
    INITIALIZING = "initializing"
    GENERATING_OUTLINE = "generating_outline"
    CHAPTER_CONTRACT = "chapter_contract"
    PAGE_PLAN = "page_plan"
    DRAFT = "draft"
    CRITIQUE = "critique"
    REWRITE = "rewrite"
    MEMORY_UPDATE = "memory_update"
    CHAPTER_VERIFY = "chapter_verify"
    COMPLETE = "complete"
    ERROR = "error"


STEP_LABELS = {
    GenStep.IDLE: "Oczekiwanie",
    GenStep.INITIALIZING: "Inicjalizacja",
    GenStep.GENERATING_OUTLINE: "Generowanie konspektu",
    GenStep.CHAPTER_CONTRACT: "Kontrakt rozdziału",
    GenStep.PAGE_PLAN: "Plan strony",
    GenStep.DRAFT: "Szkic",
    GenStep.CRITIQUE: "Redakcja",
    GenStep.REWRITE: "Przepisywanie",
    GenStep.MEMORY_UPDATE: "Aktualizacja pamięci",
    GenStep.CHAPTER_VERIFY: "Weryfikacja rozdziału",
    GenStep.COMPLETE: "Zakończono",
    GenStep.ERROR: "Błąd",
}


class LogEntry(BaseModel):
    ts: str
    level: str  # info, success, warning, error
    msg: str
    chapter: Optional[int] = None
    page: Optional[int] = None
    step: Optional[str] = None


class AgentState(BaseModel):
    status: AgentStatus = AgentStatus.IDLE
    step: GenStep = GenStep.IDLE
    chapter: int = 1
    chapter_title: str = ""
    page: int = 1
    total_chapters: int = 26
    pages_target: int = 450
    pages_done: int = 0
    words: int = 0
    started: Optional[str] = None
    updated: Optional[str] = None
    error: Optional[str] = None
    preview: str = ""
    ready: bool = False


class ChapterDef(BaseModel):
    num: int
    title: str
    purpose: str
    emotional_shift: str
    beats: List[str]
    ending: str
    act: int
    pages: int = 17


class Outline(BaseModel):
    chapters: List[ChapterDef] = Field(default_factory=list)
    beats_done: Dict[str, List[str]] = Field(default_factory=dict)


class Memory(BaseModel):
    summary: str = ""
    facts: Dict[str, str] = Field(default_factory=dict)
    threads: List[str] = Field(default_factory=list)
    chars: Dict[str, str] = Field(default_factory=dict)


class PagePlan(BaseModel):
    scene_goal: str
    location: str
    characters: List[str]
    beats: List[str]
    continuity_risks: List[str]
    foreshadow: List[str]


class CritiqueResult(BaseModel):
    issues: List[Dict[str, str]] = Field(default_factory=list)
    recommended_fixes: List[str] = Field(default_factory=list)
    continuity_updates: List[str] = Field(default_factory=list)
    overall_score: int = 7
    fatal: bool = False


class MemoryUpdate(BaseModel):
    new_summary: str
    new_facts: Dict[str, str] = Field(default_factory=dict)
    closed_threads: List[str] = Field(default_factory=list)
    new_threads: List[str] = Field(default_factory=list)
    char_updates: Dict[str, str] = Field(default_factory=dict)
