# Project name (working): Outline-to-Novel Agent
Goal: Generate a full-length novel from a structured outline, producing the book page-by-page (or scene-by-scene), with an iterative critique + rewrite loop, while enforcing chapter structure, plot constraints, continuity, and target length.

# Inputs

Novel Brief
Language, genre, tone, POV (e.g., 3rd limited), tense, target audience, target length (pages/words).
Style constraints (e.g., “modern readable fantasy”, “no purple prose”, “dialogue-forward”).
Story Blueprint
Chapter list + per-chapter intent (theme, main beats, turning point, hook).
Global “spine” of events (must-happen milestones).
Character sheets (goals, secrets, arcs, voice notes).
World bible (rules, factions, magic system, glossary).

# Production Targets
Pages (or words) per chapter, pacing rules (e.g., “end each chapter with an unresolved question”).
Page format constraints (approx words per page).
Optional: “Previously written text” (if resuming), plus last-page context.
Core loop (per page)
For each Chapter C, Page p = 1..N:
 Plan step (lightweight)
 Create a short “page plan”:
 Scene goal, conflict, revealed info, micro-beat list (5–10 bullets),
 continuity checks (who is present, location, time),
 foreshadow / callbacks to earlier facts.
 
# Output is a structured JSON object:
{"chapter":C,"page":p,"scene_goal":...,"beats":[...],"constraints":[...],"continuity_risks":[...]}

# Draft step
Generate Page Draft v1 using: the page plan,the rolling story summary (see Memory), the chapter schema constraints, optionally the previous page text (for smooth transitions).
Enforce word target (e.g., 250–350 words/page).

# Critique step
Run a “brutally honest editor” pass: continuity errors, pacing issues, unclear motivations, repetitive phrasing, weak sensory grounding, dialogue authenticity, POV violations, 
“does this page advance the chapter goal?”

# Produce:
issues[] (severity, explanation),
recommended_fixes[],
line_edits[] (optional: small patches),
continuity_updates[] (facts to add to memory).

# Rewrite step
Create Page Final by applying critique:
keep what works, fix what doesn’t,
preserve continuity and chapter intent,
tighten prose to target length.

Output only the final page text.

# Memory update step
Append final page to manuscript.
Update and persist:
Rolling Summary (compact, 300–800 tokens max),
Facts Ledger (canonical facts: names, dates, locations, injuries, promises, revealed secrets),
Open Threads (unresolved questions / foreshadowed items),
Character State (goal progress, emotional state shifts),
Chapter Progress (beats completed vs remaining).
If summary grows too large: compress it (summarization pass) while keeping the ledger authoritative.

# Chapter enforcement & guardrails
Before starting a chapter: generate a Chapter Contract:
required beats checklist,
expected turning point page range,
climax and chapter hook rules,
“no-contradiction constraints” from Facts Ledger.

# Mid-chapter: if pacing deviates (e.g., too slow), the agent can:
merge beats,
shorten exposition,
introduce a conflict earlier.
End-of-chapter: verify:
all required beats met,
chapter ends with a hook,
rolling summary + ledger updated.

# Outputs
manuscript.md (or .docx later)
outline_state.json (chapter/page counters, beat checklist)
memory.json (summary + facts ledger + threads)
Optional: editor_report.md (aggregated critique stats per chapter)

# Implementation notes (practical)
Keep API access data in local (not on github) .env file
Use deterministic structure with JSON schemas for plan/critique/memory.
Prefer Batch API for cost reduction if you don’t need real-time generation.

Consider a fallback “continuity judge” pass only when critique flags a high-severity issue.
