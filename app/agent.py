"""Core novel generation agent implementing the Plan→Draft→Critique→Rewrite→Memory loop."""

import asyncio
import json
import os
import re
from typing import Optional, Callable, Any
from datetime import datetime, timezone

from openai import AsyncOpenAI
from pydantic import ValidationError

import memory as mem
import prompts as p
from models import (
    AgentState,
    AgentStatus,
    ChapterDef,
    CritiqueResult,
    GenStep,
    Memory,
    MemoryUpdate,
    Outline,
    PagePlan,
)

# ── Config ────────────────────────────────────────────────────────────────────

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
INTER_CALL_DELAY = 0.5  # seconds between API calls


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> str:
    """Strip markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[^\n]*\n", "", text)
        text = re.sub(r"```\s*$", "", text)
    return text.strip()


def _parse_json_tolerant(text: str) -> Any:
    """Parse JSON, attempting to repair truncated arrays/objects if needed."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to salvage a truncated JSON array by closing it
        repaired = text.rstrip().rstrip(",")
        if repaired.startswith("["):
            # Close any open string, then close the last object and array
            # Find the last complete '}'  and close there
            last_close = repaired.rfind("}")
            if last_close != -1:
                repaired = repaired[: last_close + 1] + "]"
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass
        elif repaired.startswith("{"):
            last_close = repaired.rfind("}")
            if last_close != -1:
                try:
                    return json.loads(repaired[: last_close + 1])
                except json.JSONDecodeError:
                    pass
        # Re-raise original error
        raise


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _facts_summary(facts: dict, max_items: int = 20) -> str:
    if not facts:
        return "Brak zarejestrowanych faktów."
    items = list(facts.items())[:max_items]
    return "\n".join(f"- {k}: {v}" for k, v in items)


def _threads_summary(threads: list, max_items: int = 10) -> str:
    if not threads:
        return "Brak otwartych wątków."
    return "\n".join(f"- {t}" for t in threads[:max_items])


def _to_str_list(raw: Any) -> list[str]:
    """Normalize a JSON list that may contain strings OR dicts with a text field."""
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            # Pick the first string value found (handles {"beat": "..."}, {"text": "..."}, etc.)
            for v in item.values():
                if isinstance(v, str):
                    result.append(v)
                    break
    return result


def _last_sentences(text: str, n: int = 3) -> str:
    """Return the last n sentences of a text."""
    sentences = [s.strip() for s in re.split(r'(?<=[.!?…])\s+', text) if s.strip()]
    return " ".join(sentences[-n:]) if sentences else text[-500:]


def _fmt(template: str, **kwargs) -> str:
    """Safe prompt template substitution.

    Unlike str.format(), this is immune to curly braces inside substituted
    values (e.g. JSON contract strings with {"beat": "..."}).
    Works in a single regex pass so values are never re-scanned.
    Handles {{...}} → {...} escaping for literal braces in prompts.
    """
    def _replacer(m: re.Match) -> str:
        key = m.group(1)
        return str(kwargs[key]) if key in kwargs else m.group(0)

    result = re.sub(r"\{(\w+)\}", _replacer, template)
    # Unescape double-braces that were used for literal { } in the prompt
    return result.replace("{{", "{").replace("}}", "}")


# ── OpenAI wrapper ────────────────────────────────────────────────────────────

class NovelAgent:
    def __init__(self, state: AgentState, log_fn: Callable):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.state = state
        self.log = log_fn
        self._stop = False

    def stop(self):
        self._stop = True

    async def _call(
        self,
        system: str,
        user: str,
        temperature: float = 0.8,
        max_tokens: int = 1200,
    ) -> str:
        """Call OpenAI with retry logic."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                await asyncio.sleep(INTER_CALL_DELAY)
                return response.choices[0].message.content or ""
            except Exception as e:
                if attempt < MAX_RETRIES:
                    wait = RETRY_DELAY * attempt
                    await self.log(
                        f"API error (attempt {attempt}/{MAX_RETRIES}): {e}. Retrying in {wait}s...",
                        level="warning",
                    )
                    await asyncio.sleep(wait)
                else:
                    raise

    async def _call_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Any:
        raw = await self._call(system, user, temperature=temperature, max_tokens=max_tokens)
        return _parse_json_tolerant(_extract_json(raw))

    # ── Step: Generate outline ────────────────────────────────────────────────

    async def generate_outline(self, brief_text: str) -> Outline:
        await self.log("Generowanie konspektu 26 rozdziałów...", level="info", step="outline")
        self._set_step(GenStep.GENERATING_OUTLINE)

        raw = await self._call_json(
            system=p.OUTLINE_SYSTEM,
            user=_fmt(p.OUTLINE_USER, brief=brief_text),
            temperature=0.5,
            max_tokens=8000,
        )

        chapters = []
        for ch in raw:
            try:
                # Normalize beats in case the model returned list-of-dicts
                if "beats" in ch:
                    ch["beats"] = _to_str_list(ch["beats"])
                chapters.append(ChapterDef(**ch))
            except (ValidationError, KeyError) as e:
                await self.log(f"Błąd w rozdziale {ch.get('num', '?')}: {e}", level="warning")

        outline = Outline(chapters=chapters)
        await mem.async_save_outline(outline)
        await self.log(f"Konspekt wygenerowany: {len(chapters)} rozdziałów.", level="success")
        return outline

    # ── Step: Chapter contract ────────────────────────────────────────────────

    async def generate_chapter_contract(self, chapter: ChapterDef, memory: Memory) -> dict:
        await self.log(
            f"Kontrakt rozdziału {chapter.num}: {chapter.title}",
            level="info",
            chapter=chapter.num,
            step="contract",
        )
        self._set_step(GenStep.CHAPTER_CONTRACT)

        return await self._call_json(
            system=p.CONTRACT_SYSTEM,
            user=_fmt(
                p.CONTRACT_USER,
                num=chapter.num,
                title=chapter.title,
                purpose=chapter.purpose,
                shift=chapter.emotional_shift,
                beats="\n".join(f"- {b}" for b in chapter.beats),
                ending=chapter.ending,
                pages=chapter.pages,
                summary=memory.summary or "Brak (pierwszy rozdział).",
                facts=_facts_summary(memory.facts),
                threads=_threads_summary(memory.threads),
            ),
            temperature=0.3,
        )

    # ── Step: Page plan ───────────────────────────────────────────────────────

    async def generate_page_plan(
        self,
        chapter: ChapterDef,
        page_num: int,
        contract: dict,
        memory: Memory,
        prev_page: str,
    ) -> PagePlan:
        self._set_step(GenStep.PAGE_PLAN)
        self.state.page = page_num

        raw = await self._call_json(
            system=p.PLAN_SYSTEM,
            user=_fmt(
                p.PLAN_USER,
                page=page_num,
                pages_total=chapter.pages,
                num=chapter.num,
                title=chapter.title,
                contract=json.dumps(contract, ensure_ascii=False, indent=2),
                summary=memory.summary or "Brak (początek powieści).",
                facts=_facts_summary(memory.facts),
                prev_ending=_last_sentences(prev_page, 3) if prev_page else "Początek rozdziału.",
            ),
            temperature=0.6,
        )

        return PagePlan(
            scene_goal=raw.get("scene_goal", ""),
            location=raw.get("location", ""),
            characters=_to_str_list(raw.get("characters", ["Zosia"])) or ["Zosia"],
            beats=_to_str_list(raw.get("beats", [])),
            continuity_risks=_to_str_list(raw.get("continuity_risks", [])),
            foreshadow=_to_str_list(raw.get("foreshadow", [])),
        )

    # ── Step: Draft ───────────────────────────────────────────────────────────

    async def draft_page(
        self,
        chapter: ChapterDef,
        page_num: int,
        plan: PagePlan,
        memory: Memory,
        prev_page: str,
    ) -> str:
        self._set_step(GenStep.DRAFT)

        return await self._call(
            system=p.STYLE_SYSTEM,
            user=_fmt(
                p.DRAFT_USER,
                page=page_num,
                pages_total=chapter.pages,
                num=chapter.num,
                title=chapter.title,
                scene_goal=plan.scene_goal,
                location=plan.location,
                characters=", ".join(plan.characters),
                beats="\n".join(f"- {b}" for b in plan.beats),
                prev_ending=_last_sentences(prev_page, 4) if prev_page else "Początek rozdziału.",
                summary=memory.summary[:1500] if memory.summary else "Brak.",
            ),
            temperature=0.85,
            max_tokens=700,
        )

    # ── Step: Critique ────────────────────────────────────────────────────────

    async def critique_page(
        self,
        chapter: ChapterDef,
        page_num: int,
        draft: str,
        contract: dict,
    ) -> CritiqueResult:
        self._set_step(GenStep.CRITIQUE)

        try:
            raw = await self._call_json(
                system=p.CRITIQUE_SYSTEM,
                user=_fmt(
                    p.CRITIQUE_USER,
                    num=chapter.num,
                    title=chapter.title,
                    page=page_num,
                    contract=json.dumps(contract, ensure_ascii=False, indent=2),
                    page_text=draft,
                ),
                temperature=0.2,
            )
            return CritiqueResult(
                issues=raw.get("issues", []),
                recommended_fixes=raw.get("recommended_fixes", []),
                continuity_updates=raw.get("continuity_updates", []),
                overall_score=raw.get("overall_score", 7),
                fatal=raw.get("fatal", False),
            )
        except Exception as e:
            await self.log(f"Błąd krytyki: {e}", level="warning")
            return CritiqueResult(overall_score=7)

    # ── Step: Rewrite ─────────────────────────────────────────────────────────

    async def rewrite_page(
        self,
        chapter: ChapterDef,
        page_num: int,
        draft: str,
        critique: CritiqueResult,
        plan: PagePlan,
    ) -> str:
        self._set_step(GenStep.REWRITE)

        # If critique score is high and no fatal issues, skip costly rewrite
        if critique.overall_score >= 8 and not critique.fatal and not critique.issues:
            return draft

        issues_text = "\n".join(
            f"- [{i.get('severity','?')}] {i.get('description','')}"
            for i in critique.issues
        ) or "Brak poważnych problemów."

        return await self._call(
            system=p.STYLE_SYSTEM,
            user=_fmt(
                p.REWRITE_USER,
                draft=draft,
                score=critique.overall_score,
                issues=issues_text,
                fixes="\n".join(f"- {f}" for f in critique.recommended_fixes) or "Brak.",
                num=chapter.num,
                title=chapter.title,
                page=page_num,
                scene_goal=plan.scene_goal,
            ),
            temperature=0.75,
            max_tokens=700,
        )

    # ── Step: Memory update ───────────────────────────────────────────────────

    async def update_memory(
        self,
        chapter: ChapterDef,
        page_num: int,
        final_page: str,
        critique: CritiqueResult,
        memory: Memory,
    ) -> Memory:
        self._set_step(GenStep.MEMORY_UPDATE)

        try:
            raw = await self._call_json(
                system=p.MEMORY_SYSTEM,
                user=_fmt(
                    p.MEMORY_USER,
                    summary=memory.summary[:2000] or "Brak.",
                    facts=json.dumps(dict(list(memory.facts.items())[:30]), ensure_ascii=False),
                    threads="\n".join(memory.threads[:15]) or "Brak.",
                    chars=json.dumps(memory.chars, ensure_ascii=False),
                    num=chapter.num,
                    title=chapter.title,
                    page=page_num,
                    final_page=final_page,
                    continuity_updates="\n".join(critique.continuity_updates) or "Brak.",
                ),
                temperature=0.3,
            )

            update = MemoryUpdate(
                new_summary=raw.get("new_summary", memory.summary),
                new_facts=raw.get("new_facts", {}),
                closed_threads=raw.get("closed_threads", []),
                new_threads=raw.get("new_threads", []),
                char_updates=raw.get("char_updates", {}),
            )

            # Apply updates
            memory.summary = update.new_summary
            memory.facts.update(update.new_facts)
            for t in update.closed_threads:
                if t in memory.threads:
                    memory.threads.remove(t)
            memory.threads.extend(update.new_threads)
            memory.chars.update(update.char_updates)

            # Compress if summary is too long (~1000+ words)
            if len(memory.summary.split()) > 1000:
                memory.summary = await self._compress_summary(memory)

        except Exception as e:
            await self.log(f"Błąd aktualizacji pamięci: {e}", level="warning")

        await mem.async_save_memory(memory)
        return memory

    async def _compress_summary(self, memory: Memory) -> str:
        await self.log("Kompresja podsumowania pamięci...", level="info")
        try:
            compressed = await self._call(
                system=p.MEMORY_SYSTEM,
                user=_fmt(
                    p.COMPRESS_SUMMARY_USER,
                    summary=memory.summary,
                    facts=json.dumps(dict(list(memory.facts.items())[:20]), ensure_ascii=False),
                ),
                temperature=0.2,
                max_tokens=900,
            )
            return compressed.strip()
        except Exception:
            return memory.summary[:3000]

    # ── Step: Chapter verify ──────────────────────────────────────────────────

    async def verify_chapter(
        self,
        chapter: ChapterDef,
        contract: dict,
        beats_done: list,
        chapter_pages: list,
        memory: Memory,
    ) -> dict:
        self._set_step(GenStep.CHAPTER_VERIFY)

        last_page = chapter_pages[-1] if chapter_pages else ""
        chapter_summary = memory.summary[-1000:] if memory.summary else ""

        try:
            return await self._call_json(
                system=p.CONTRACT_SYSTEM,
                user=_fmt(
                    p.CHAPTER_VERIFY_USER,
                    num=chapter.num,
                    title=chapter.title,
                    contract=json.dumps(contract, ensure_ascii=False, indent=2),
                    beats_done="\n".join(f"- {b}" for b in beats_done),
                    chapter_summary=chapter_summary,
                    last_page=last_page,
                ),
                temperature=0.2,
            )
        except Exception as e:
            await self.log(f"Błąd weryfikacji rozdziału: {e}", level="warning")
            return {"verdict": "pass", "notes": ""}

    # ── Main generation loop ──────────────────────────────────────────────────

    async def run(self):
        """Main novel generation loop."""
        self.state.status = AgentStatus.RUNNING
        self.state.started = _now()
        mem.save_state(self.state)

        try:
            brief_text = await asyncio.to_thread(mem.load_brief)
            await self.log("Brief załadowany.", level="info")

            # Initialize manuscript file
            await asyncio.to_thread(mem.init_manuscript)

            # Load or generate outline
            self._set_step(GenStep.INITIALIZING)
            outline = await asyncio.to_thread(mem.load_outline)
            if not outline or not outline.chapters:
                outline = await self.generate_outline(brief_text)

            self.state.total_chapters = len(outline.chapters)

            # Load memory
            memory = await asyncio.to_thread(mem.load_memory)

            # Determine starting point from saved state
            start_chapter_idx = max(0, self.state.chapter - 1)
            # Clamp to valid range
            start_chapter_idx = min(start_chapter_idx, len(outline.chapters) - 1)

            await self.log(
                f"Rozpoczynam od rozdziału {start_chapter_idx + 1}/{len(outline.chapters)}.",
                level="info",
            )

            # ── Chapter loop ──────────────────────────────────────────────────
            for chapter in outline.chapters[start_chapter_idx:]:
                if self._stop:
                    break

                self.state.chapter = chapter.num
                self.state.chapter_title = chapter.title
                mem.save_state(self.state)

                await self.log(
                    f"=== Rozdział {chapter.num}: {chapter.title} (Akt {chapter.act}) ===",
                    level="success",
                    chapter=chapter.num,
                )

                # Chapter header in manuscript
                await mem.async_append_chapter_header(chapter.num, chapter.title)

                # Report header
                await mem.async_append_to_report(
                    f"\n## Rozdział {chapter.num}: {chapter.title}\n"
                )

                # Generate chapter contract
                contract = await self.generate_chapter_contract(chapter, memory)

                prev_page = ""
                chapter_pages = []
                beats_done = []

                # Determine start page within the chapter
                start_page = 1
                if chapter.num == self.state.chapter and self.state.page > 1:
                    start_page = self.state.page

                # ── Page loop ─────────────────────────────────────────────────
                for page_num in range(start_page, chapter.pages + 1):
                    if self._stop:
                        break

                    await self.log(
                        f"Strona {page_num}/{chapter.pages}",
                        level="info",
                        chapter=chapter.num,
                        page=page_num,
                    )

                    # 1. PLAN
                    plan = await self.generate_page_plan(
                        chapter, page_num, contract, memory, prev_page
                    )

                    # 2. DRAFT
                    draft = await self.draft_page(
                        chapter, page_num, plan, memory, prev_page
                    )

                    # 3. CRITIQUE
                    critique = await self.critique_page(
                        chapter, page_num, draft, contract
                    )

                    # 4. REWRITE
                    final_page = await self.rewrite_page(
                        chapter, page_num, draft, critique, plan
                    )

                    # 5. MEMORY UPDATE
                    memory = await self.update_memory(
                        chapter, page_num, final_page, critique, memory
                    )

                    # 6. Persist page to manuscript
                    await mem.async_append_page(final_page)

                    # Update state
                    self.state.pages_done += 1
                    self.state.words = await asyncio.to_thread(mem.count_words_in_manuscript)
                    self.state.preview = final_page[:600]
                    self.state.updated = _now()
                    mem.save_state(self.state)

                    # Track beats
                    beats_done.extend(plan.beats[:2])
                    chapter_pages.append(final_page)
                    prev_page = final_page

                    # Log critique score to report
                    report_entry = (
                        f"- Page {page_num}: score={critique.overall_score}/10 "
                        f"issues={len(critique.issues)}"
                    )
                    await mem.async_append_to_report(report_entry)

                    await self.log(
                        f"Strona {page_num} ukończona. Wynik krytyki: {critique.overall_score}/10",
                        level="success" if critique.overall_score >= 7 else "warning",
                        chapter=chapter.num,
                        page=page_num,
                    )

                # ── Chapter verification ──────────────────────────────────────
                if chapter_pages and not self._stop:
                    verdict = await self.verify_chapter(
                        chapter, contract, beats_done, chapter_pages, memory
                    )
                    v = verdict.get("verdict", "pass")
                    await self.log(
                        f"Weryfikacja rozdziału {chapter.num}: {v}. {verdict.get('notes', '')}",
                        level="success" if v == "pass" else "warning",
                        chapter=chapter.num,
                    )

                # Advance chapter pointer
                self.state.chapter = chapter.num + 1
                self.state.page = 1
                mem.save_state(self.state)

            # ── Completion ────────────────────────────────────────────────────
            if not self._stop:
                self.state.status = AgentStatus.COMPLETE
                self.state.step = GenStep.COMPLETE
                self.state.ready = True
                self.state.updated = _now()
                mem.save_state(self.state)
                await self.log(
                    f"Powieść ukończona! {self.state.pages_done} stron, "
                    f"{self.state.words} słów.",
                    level="success",
                )
            else:
                self.state.status = AgentStatus.STOPPED
                self.state.updated = _now()
                mem.save_state(self.state)
                await self.log("Generowanie zatrzymane przez użytkownika.", level="warning")

        except Exception as e:
            self.state.status = AgentStatus.ERROR
            self.state.step = GenStep.ERROR
            self.state.error = str(e)
            self.state.updated = _now()
            mem.save_state(self.state)
            await self.log(f"Krytyczny błąd: {e}", level="error")
            raise

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_step(self, step: GenStep):
        self.state.step = step
        self.state.updated = _now()
