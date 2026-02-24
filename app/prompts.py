"""All LLM prompts for the novel generation agent."""

NOVEL_BRIEF = """
Tytuł: Zosia i Miasto Szeptów
Język: Polski
Gatunek: Literatura współczesna z elementami realizmu magicznego
Subgatunek: Miejska powieść inicjacyjna / subtelny thriller psychologiczny
Odbiorca: Young Adult / dorośli (18–40)
Ton: Atmosferyczny, refleksyjny, momentami niepokojący
POV: 3rd person limited (blisko Zosi), czas przeszły

BOHATEROWIE:
- Zofia "Zosia" Barska, 21 lat: wróciła do Otwocka po rozstaniu i życiowym zawieszeniu. Ironiczna, melancholijna, uważna obserwatorka. Arc: zamknięta → świadoma swojej roli.
- Marek: lokalny dziennikarz badający historię miasta. Sam słyszał szepty w dzieciństwie.
- Miasto (antagonista nieosobowy): zbiorowy byt pragnący zachować pamięć. Potrzebuje Zosi jako medium.

ŚWIAT I REGUŁY:
- Otwock, współczesna Polska
- Szepty są fragmentaryczne, niewidowiskowe, powiązane z konkretnymi miejscami
- Nie da się ich nagrać
- Brak widowiskowej magii — realizm codzienności dominuje
- Granica między realnym a wyobraźnią musi pozostać niejasna

STYL:
- Klimatyczne opisy przestrzeni miejskiej
- Sensoryczne detale (zapach kurzu, echo klatki schodowej, wilgoć piwnicy)
- Dialogi naturalne i oszczędne, gęstość ok. 40%
- Bez długich monologów wewnętrznych
- Bez ekspozycji wprost
- Bez "purpurowej prozy"
"""

STYLE_SYSTEM = """Jesteś polskim pisarzem literackim o mistrzowskim wyczuciu prozy współczesnej. Piszesz "Zosia i Miasto Szeptów" — powieść z elementami realizmu magicznego osadzoną w Otwocku.

STYL:
- Pisz wyłącznie po polsku
- Narracja trzecioosobowa ograniczona, blisko Zosi, czas przeszły
- Atmosferyczne, sensoryczne opisy przestrzeni
- Dialogi naturalne i ekonomiczne
- Bez długich monologów wewnętrznych
- Bez bezpośredniej ekspozycji ("jak wiemy, X był...")
- Realizm codzienności — żadna magia nie jest oczywista ani nazwana wprost
- Cel: 280–320 słów na stronę"""


OUTLINE_SYSTEM = """You are a master story architect specializing in contemporary Polish literary fiction with magical realism elements."""

OUTLINE_USER = """Based on this novel brief, generate a complete 26-chapter schema for "Zosia i Miasto Szeptów".

Three-act structure:
- Act I: Chapters 1–7 (Setup, inciting incident, first turning point)
- Act II: Chapters 8–20 (Escalation, midpoint family revelation, crisis)
- Act III: Chapters 21–26 (Climax at the city core, resolution, dawn)

BRIEF:
{brief}

Return a JSON array of exactly 26 chapter objects. Each object must have:
- num: chapter number (1-26)
- title: Polish title (e.g. "Powrót", "Szepty")
- purpose: 1-sentence description of the chapter's role in the story
- emotional_shift: e.g. "Obojętność → niepokój"
- beats: array of 3-5 required story beats (in Polish)
- ending: the ending hook requirement (in Polish)
- act: 1, 2, or 3
- pages: target pages (15-20, average 17)

Return ONLY the JSON array, no markdown, no explanation."""


CONTRACT_SYSTEM = """You are a story structure analyst helping maintain narrative discipline."""

CONTRACT_USER = """Generate a Chapter Contract for this chapter.

CHAPTER:
Num: {num}
Title: {title}
Purpose: {purpose}
Emotional shift: {shift}
Required beats: {beats}
Ending requirement: {ending}
Target pages: {pages}

CURRENT MEMORY:
{summary}

FACTS LEDGER (relevant):
{facts}

OPEN THREADS:
{threads}

Return a JSON object with:
- beats_checklist: list of beats with done=false
- no_contradiction_rules: list of facts that must not be violated (from ledger)
- turning_point_range: e.g. "pages 8-12"
- hook_rule: string describing the required ending hook
- pacing_notes: brief pacing guidance

Return ONLY the JSON, no markdown."""


PLAN_SYSTEM = """You are a scene architect for a Polish literary novel. You plan individual pages."""

PLAN_USER = """Plan page {page} of {pages_total} for Chapter {num}: "{title}".

CHAPTER CONTRACT:
{contract}

ROLLING SUMMARY:
{summary}

RELEVANT FACTS:
{facts}

PREVIOUS PAGE ENDING (last 3 sentences):
{prev_ending}

Return a JSON object with:
- scene_goal: string (what this page must accomplish)
- location: string
- characters: list of characters present
- beats: list of 3-6 micro-beats to cover on this page
- continuity_risks: list of potential continuity issues to watch for
- foreshadow: list of callbacks or foreshadowing to weave in

Return ONLY the JSON, no markdown."""


DRAFT_USER = """Write page {page}/{pages_total} of Chapter {num}: "{title}".

PAGE PLAN:
Cel sceny: {scene_goal}
Lokacja: {location}
Bohaterowie: {characters}
Mikro-beaty:
{beats}

POPRZEDNIA STRONA (zakończenie):
{prev_ending}

PODSUMOWANIE DOTYCHCZASOWE:
{summary}

Napisz stronę teraz. Cel: 280–320 słów. Tylko tekst strony, bez komentarzy, bez nagłówków."""


CRITIQUE_SYSTEM = """You are a brutally honest but constructive literary editor specializing in Polish contemporary fiction. You evaluate pages rigorously."""

CRITIQUE_USER = """Evaluate this page from "Zosia i Miasto Szeptów" (Chapter {num}: "{title}", page {page}).

CHAPTER CONTRACT REQUIREMENTS:
{contract}

PAGE TEXT:
{page_text}

Evaluate against these criteria:
1. Atmosphere (does it feel like Otwock / magical realism?)
2. Realism coherence (no obvious magic, no breaking world rules)
3. Dialogue authenticity (natural Polish dialogue, not stiff)
4. Tension and pacing (does the page pull the reader forward?)
5. Over-literalness (showing vs telling — avoid stating emotions directly)
6. POV discipline (3rd limited, Zosia's perception only)
7. Chapter goal advancement (does this page earn its place?)
8. Word count appropriateness (280-320 words)

Return a JSON object:
{{
  "issues": [
    {{"severity": "low|medium|high", "type": "string", "description": "string", "fix": "string"}}
  ],
  "recommended_fixes": ["string"],
  "continuity_updates": ["fact to record in the ledger"],
  "overall_score": 1-10,
  "fatal": false
}}

Return ONLY the JSON, no markdown."""


REWRITE_USER = """Rewrite this page incorporating the editorial critique.

ORIGINAL PAGE:
{draft}

CRITIQUE:
Score: {score}/10
Issues:
{issues}

Fixes to apply:
{fixes}

CHAPTER CONTEXT:
Chapter {num}: "{title}", page {page}
Scene goal: {scene_goal}

Rules:
- Keep what works, fix what doesn't
- Stay within 280-320 words
- Maintain 3rd person limited Polish narrative
- Keep the scene goal and beats intact
- Do NOT add fantasy explanations

Write ONLY the final page text in Polish, no commentary."""


MEMORY_SYSTEM = """You are a continuity manager for a Polish novel. You maintain narrative consistency."""

MEMORY_USER = """Update the story memory after this completed page.

PREVIOUS MEMORY:
Summary (keep this under 800 tokens): {summary}
Facts ledger: {facts}
Open threads: {threads}
Character states: {chars}

COMPLETED PAGE (Chapter {num}: "{title}", page {page}):
{final_page}

CONTINUITY UPDATES FROM CRITIQUE:
{continuity_updates}

Return a JSON object:
{{
  "new_summary": "updated rolling summary — must capture all key events, revelations, and emotional shifts. Max 700 words.",
  "new_facts": {{"key": "value — new canonical facts only, merge with existing"}},
  "closed_threads": ["thread resolved on this page"],
  "new_threads": ["new unresolved question or foreshadowed element introduced"],
  "char_updates": {{"Zosia": "emotional state / goal progress update"}}
}}

Return ONLY the JSON, no markdown."""


CHAPTER_VERIFY_USER = """Verify that Chapter {num}: "{title}" has been completed properly.

CHAPTER CONTRACT:
{contract}

BEATS COMPLETED:
{beats_done}

CHAPTER SUMMARY:
{chapter_summary}

FINAL PAGE TEXT:
{last_page}

Return a JSON object:
{{
  "all_beats_met": true/false,
  "missing_beats": ["any beats not covered"],
  "hook_present": true/false,
  "hook_description": "describe the ending hook",
  "verdict": "pass|fail",
  "notes": "any important notes for the next chapter"
}}

Return ONLY the JSON, no markdown."""


COMPRESS_SUMMARY_USER = """The rolling summary has grown too long. Compress it while preserving all critical information.

CURRENT SUMMARY:
{summary}

FACTS LEDGER (do NOT duplicate these — they are separately stored):
{facts}

Create a compressed summary that:
- Captures ALL key plot events and emotional arcs
- Preserves character state changes
- Keeps unresolved threads visible
- Maximum 600 words

Return ONLY the compressed summary text in Polish, no JSON."""
