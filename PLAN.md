# british_pixelart_llm — Project Plan

*v1.0 (finalized draft) — 2026-07-09. Solo project for "Intelligent Agents, Retrieval, Reasoning and Action" (40% of grade).*

**Repo:** https://github.com/PhilippMattar/british_pixelart_llm
**Deadlines:** Presentation **Mon 2026-09-07** · Hand-in (ZIP) **Mon 2026-09-14**

---

## 1. Concept

A Claude-Code-style terminal chat app (Python **Textual**) talking to **locally served** LLMs via **Ollama**. The assistant is helpful by default but can slip into a British or Scottish persona — via fine-tuned LoRA adapters, triggered by keywords in the user's message or switched manually. A pixel-art waiting animation reflects which persona is generating.

## 2. Requirements mapping (project prompt PDF, version 2026-07-06)

### Required (all mandatory; R7+R8 sit *above* the "Elective Features" heading → required)

| # | Requirement | Satisfied by |
|---|---|---|
| R1 | Runnable with `uv`/`uvx` | `pyproject.toml` entry point `bpx`; `uvx --from git+https://github.com/PhilippMattar/british_pixelart_llm bpx` |
| R2 | Cross-platform UI | Textual TUI (Windows/macOS/Linux) |
| R3 | Chat: send text, visible history, scroll/page anywhere | Streaming message log in `VerticalScroll` |
| R4 | Start/stop/resume; switch/create/continue/remove conversations | Sidebar + SQLite persistence; Esc cancels mid-stream, partials saved |
| R5 | Switch underlying LLM; **≥2 different models loadable** | Model registry (§4): Qwen3-8B **and** Gemma — two genuinely different families — plus 2 persona adapters and optional cloud models |
| R6 | Simple memory over groups of chats ("Project Folder" style) | Projects grouping conversations; auto-extracted per-project memories injected into system prompt |
| R7 | **≥2 fine-tuned models** (LoRA/QLoRA) | British LoRA + Scottish LoRA on Qwen3-8B, QLoRA-trained on HPC cluster |
| R8 | **Video demo** (all features + ≥1 real-world use case) | Scripted screen recording, §16 |

### Electives (solo → 2)

| # | Elective | Satisfied by |
|---|---|---|
| E1 | Adaptive RAG (judge, rewriter, multiturn retrieval, summarization; user txt+pdf) | §10 |
| E2 | Self-controlled iterative web search (find + *visit* pages) | §11 |

*Stretch (optional, decide end of Phase 3): preference optimisation — A/B choice UI + DPO LoRA, reusing the Phase-2 training infra.*

## 3. Decisions locked now — and what is hard to change later

Decisions with real switching costs, settled 2026-07-09:

| Decision | Choice | Why it's hard to change later |
|---|---|---|
| **Persona base model** | **Qwen3-8B** (Ollama `qwen3:8b`, Q4_K_M local) | LoRA adapters are mathematically tied to the exact base weights — a new base means regenerating nothing but **retraining both adapters** and re-running eval. Gate **G1** (§7.1) validates the pipeline in week 1 of Phase 2; fallback = Qwen2.5-7B-Instruct. |
| **Chat template & thinking mode** | Qwen3 non-thinking chat template everywhere (training data, eval, serving) | Template mismatch between training and serving silently degrades the adapters. Qwen3's thinking mode stays **off** for personas (no `<think>` blocks in training data). |
| **Second model family (R5)** | Latest **Gemma** in the 4–12B class (pull whatever is current in Ollama at build time) | Low cost to swap (no fine-tuning), but pick early so the demo script and README stay stable. |
| **Serving & provider abstraction** | Local-first via Ollama; every model behind an OpenAI-compatible client; optional remote endpoints via config (§4.3) | The client abstraction must exist from the first line of `llm.py` — retrofitting streaming + cancellation across providers is painful. |
| **Teacher model** | **Qwen2.5-72B/Qwen3-32B-class Qwen** on the cluster via vLLM | Llama's license requires derivatives trained on its outputs to carry "Llama" in the name + attribution; Qwen (Apache-2.0) avoids this. Switching teachers later means regenerating all data. |
| **Persistence** | SQLite, stdlib `sqlite3`, `schema_version` table + tiny migration runner from day 1 | Schema changes without migrations = broken saved chats mid-project. |
| **Package identity** | src layout, package `bpx`, Python ≥3.11, entry point `bpx` | Renames ripple through docs, README, demo, Modelfiles. |
| **Repo license & data policy** | MIT for code; generated datasets shipped in repo; raw seed corpora **never** committed (only collection scripts) | Hand-in link must stay public until semester end — don't commit anything you can't redistribute. |

## 4. Model strategy

### 4.1 The lineup

| Registry name | Base | Role | Where |
|---|---|---|---|
| `base` | Qwen3-8B Q4_K_M | Default helpful assistant | Ollama, local |
| `gemma` | Gemma 4–12B class | Second family → R5 unambiguous | Ollama, local |
| `british` | Qwen3-8B + British LoRA | Persona (fine-tuned #1) | Ollama `ADAPTER`, local |
| `scottish` | Qwen3-8B + Scottish LoRA | Persona (fine-tuned #2) | Ollama `ADAPTER`, local |
| `remote-*` (optional) | anything | Big-model option for heavy generation | Any OpenAI-compatible endpoint |

### 4.2 Model registry & switching

- `models.toml` defines every model: `name`, `provider` (`ollama` \| `openai_compat`), `endpoint`, `model_id`, `api_key_env`, `is_persona`, `keywords[]`. Adding a cloud model = 4 lines of TOML, zero code.
- One `LLMClient` (OpenAI-compatible, streaming, cancellable) serves all providers — Ollama exposes the same API shape locally.
- Switching: `/model <name>` + picker widget; auto-switch when the keyword router (§8) fires; active model shown as a status-bar badge; per-conversation model choice persisted in SQLite; manual choice pins and always beats auto-switch.

### 4.3 Local vs cloud — the decision and the reasoning

**Local-first, with an optional cloud slot.** Two facts force the shape:

1. **Free cloud inference exists but cannot host your fine-tunes.** Groq, OpenRouter, Cerebras, and Google AI Studio all have real free tiers in 2026 (e.g. Groq ~30 req/min on Llama-class models; OpenRouter 50 free req/day, 1,000/day with a $10 balance; Cerebras ~1M tokens/day). But they serve *fixed* models — none load a custom LoRA. The personas, i.e. the graded R7 feature, therefore **must** run locally (or on your own cluster).
2. **The demo must not depend on wifi or rate limits.** Presentations punish flaky networks; local Ollama is deterministic.

So: all graded features run locally. The `openai_compat` provider additionally lets you register Groq/OpenRouter free tiers — or vLLM on your own cluster through an SSH tunnel — as extra models for playing with bigger compute. It costs ~30 lines because the client is OpenAI-compatible anyway, and it makes the R5 "switch models" story even stronger. Free-tier limits change frequently; treat them as toys, not infrastructure.

### 4.4 Fine-tune the same model we serve? — Yes, necessarily

A LoRA learns low-rank *deltas* (ΔW = BA) relative to one specific base's weights; applied to any other base — even a sibling like Qwen2.5 vs Qwen3, or the same model re-quantized differently at conversion time — the deltas point in meaningless directions. Consequences baked into this plan:

- Train on the **unquantized Qwen3-8B** checkpoint whose architecture matches the Ollama base tag; QLoRA quantizes the frozen base to 4-bit *during training* but the exported adapter targets the full-precision weight space.
- Serve as GGUF adapter over the same base (§7.3); identical chat template at train and serve time.
- The *teacher* (data generation) is deliberately a **different, bigger** model — that's fine and standard (distillation): teacher quality flows through the data, not through weight compatibility. Only student-base ↔ adapter must match.
- Gemma is never fine-tuned; it exists to make R5's "two different models" unambiguous.

## 5. Architecture

```
┌────────────────────────── Textual TUI (src/bpx/) ─────────────────────────┐
│ ChatScreen · Sidebar(projects→conversations) · PixelArtWidget · ModelPicker│
└──────────────┬─────────────────────────────────────────────────────────────┘
        ┌──────▼───────┐  keyword router (auto) + /model (manual, pins)
        │ Orchestrator │───────────────────────────────┐
        └──────┬───────┘                               │
   ┌───────────┼───────────────┐              ┌────────▼─────────┐
┌──▼─────┐ ┌───▼────────┐ ┌────▼────────┐    │ LLMClient        │
│ Store  │ │ RAG (E1)   │ │ WebSearch   │    │ (OpenAI-compat,  │
│ SQLite │ │ judge/     │ │ (E2) search │    │ streaming,       │
│ +vec   │ │ rewrite/   │ │ →fetch→read │    │ cancellable)     │
│ memory │ │ retrieve/  │ │ →traverse   │    └────┬────────┬────┘
└────────┘ │ summarize  │ └─────────────┘   ┌─────▼──┐ ┌───▼──────────┐
           └────────────┘                   │ Ollama │ │ remote       │
                                            │ base·  │ │ endpoints    │
                                            │ gemma· │ │ (optional:   │
                                            │ brit·  │ │ Groq/OR/vLLM)│
                                            │ scot   │ └──────────────┘
                                            └────────┘
```

The judge inside RAG doubles as the adaptive controller routing *no-retrieval / local-docs / web-search* — one architectural story covering both electives.

## 6. Fine-tuning data strategy (hybrid)

Goal per persona: **~3,000 chat-format pairs** (JSONL, Qwen3 non-thinking template) where responses are *helpful answers in persona* — correct content, dialect delivery.

### 6.1 Seed style corpora (style source only — never trained on directly, never committed)

500–1,000 authentic snippets per persona, used as few-shot exemplars for the teacher:

- **British:** Reddit dumps via Arctic Shift (r/CasualUK, r/britishproblems, r/AskUK); Project Gutenberg dry wit (Jerome K. Jerome, Saki, Wilde); curated lexicon (*innit, mate, cheeky, chuffed, gutted, knackered, taking the mickey, "I'm not being funny but…"*, understatement patterns).
- **Scottish (light Scots — readable):** r/Scotland, r/ScottishPeopleTwitter; SCOTS corpus (free for research); Scots Wikipedia + Burns *sparingly* (heavier register than target); lexicon (*aye, wee, ken, dinnae, cannae, bonnie, och, dreich, braw, numpty*).
- Cleaning: strip usernames/PII, profanity filter (mild swearing behind a config flag), dedupe, 10–60 words, manual skim.

### 6.2 Instruction prompt bank (~2,500, shared)

~70% sampled from openly licensed instruction sets (Dolly-15k, Alpaca-cleaned, OpenAssistant); ~20% hand-written prompts matching real app usage (including trigger-keyword prompts so autoswitching demos naturally); ~10% multi-turn seeds.

### 6.3 Teacher generation (cluster, SLURM + vLLM)

- Teacher: biggest current instruction-tuned **Qwen** that fits 1–2 A100/H100 (Qwen2.5-72B-Instruct or newer Qwen3-30B+ class).
- Per sample: persona system prompt + 3–5 random seed snippets as style exemplars + instruction → in-persona answer.
- Guardrails in the teacher prompt: answer correctly first; ≤3 dialect markers per paragraph; no stereotyped hostility; British = dry understatement, Scottish = warm grumpiness. Plus ~15% "plain competence" pairs (persona tone only in framing) to protect helpfulness.

### 6.4 Filtering

Exact + MinHash dedup → length/refusal filters → lexicon hit-rate banding (drop too-plain and caricature tails) → LLM-judge pass (helpfulness ≥4/5 AND persona-fit ≥4/5) → manual review of ~100/persona → 90/10 split. Output: `training/data/{british,scottish}_{train,val}.jsonl` (shippable).

## 7. Training & serving pipeline

### 7.1 Gate G1 — pipeline smoke test (first week of Phase 2, highest-risk item)

Train a **dummy adapter** (100 samples, 10 min) on Qwen3-8B → convert with llama.cpp `convert_lora_to_gguf.py` → `ollama create` with `ADAPTER` → verify coherent persona-tinged output locally. **Pass:** Qwen3-8B confirmed. **Fail after 2 days of debugging:** fall back to Qwen2.5-7B-Instruct (documented, boring, works). Everything downstream waits on G1, nothing upstream does.

### 7.2 QLoRA (per adapter, SLURM on A100/H100)

Unsloth (fallback PEFT+TRL SFTTrainer); 4-bit NF4 frozen base, bf16 compute; starting hyperparams r=16, α=32, dropout 0.05, lr 2e-4 cosine, 3 epochs, seq 2048, effective batch 16. ~30–60 min/run → iterate freely. Pre-download HF weights from the login node (compute nodes may lack internet).

### 7.3 Eval & export

- Fixed 30-prompt "vibe benchmark" (10 factual / 10 casual / 10 trigger-keyword); LLM-judge scores base vs adapter on persona-fit + helpfulness → results table for the presentation.
- Export: adapter → GGUF → `Modelfile` (`FROM qwen3:8b` + `ADAPTER ./british.gguf`) → `ollama create bpx-british`; same for Scottish. Fallback: merge LoRA into base and quantize the merged model (~5 GB/persona but bulletproof).

## 8. Keyword router

- `router/keywords.py`: two curated word-boundary regex lexicons (british: *innit, mate, cheers, telly, Manchester derby…*; scottish: *aye, wee, ken, bagpipe, whisky, William Wallace…*). Curate for false positives ("whisky" ≠ "whiskey"; "mate" in "checkmate").
- Auto-switch fires on match → toast notification ("Switching to Scottish mode, aye 🏴") + badge + animation change. Manual `/model` pins and disables auto-switch for that conversation. All switches logged to the conversation so the history is honest.

## 9. TUI, persistence, memory

- **Look:** Claude-Code-inspired dark theme, rounded borders, footer keybindings, command palette, slash commands (`/new /model /project /rag /search /memory /quit`).
- **Pixel art:** frame-based widget (multi-line strings + Rich color markup, half-block ▀▄ characters for 2× vertical resolution), timer-driven during generation. Three sets: neutral (base/gemma), royal figure + speech bubble echoing a salient prompt word (british), angry bagpiper by a pub + grumpy bubble (scottish).
- **Persistence:** SQLite tables `projects / conversations / messages / memories / schema_version`. Start/stop/resume: streaming cancellable, partials saved, reopening restores full scrollback (R3/R4).
- **Memory (R6):** background LLM call extracts durable facts every N messages into project-scoped `memories`; top-k injected into the system prompt of chats in that project; `/memory` lists and deletes. Simple, inspectable, demoable.

## 10. Elective 1 — Adaptive RAG

Lecture-diagram-faithful: **judge → rewriter → multiturn retrieval → summarization**.

- `/rag add <path>` ingests txt + pdf (pypdf), ~500-token chunks with overlap.
- Embeddings: `nomic-embed-text` via Ollama (local); store: **sqlite-vec** (lives inside the one SQLite file — no external service, uv-friendly).
- Judge classifies each query: no-retrieval / local-docs / web. Rewriter reformulates (with conversation context) into retrieval queries. If retrieved context is judged insufficient → rewrite + retrieve again (≤3 rounds). Summarizer compresses chunks into a source-tagged context block; answers cite sources.

## 11. Elective 2 — Agentic web search

Loop: model issues query → `ddgs` results → model picks URLs → fetch (`httpx`) + extract main text (`trafilatura`) → model reads and decides: answer / follow an in-page link / new query. Budget ~6 fetches/question. Traversing links *found within pages* is exactly the "further than direct results" requirement. Entry point is the same judge as §10.

## 12. Handbook (`docs/handbook/`)

One chapter per phase step, written as part of that step's definition-of-done — a phase isn't "complete" until its chapter exists. Every chapter follows one template:

```
# NN — <Topic>
## Goal              – what this step delivers
## Why it exists     – which requirement/idea forces this step
## What was built    – files touched, key classes/functions, how they interact
## Core concepts     – the 3–5 ideas you must understand (explained briefly)
## Resources         – curated links: official docs, one beginner tutorial, one deep dive
## Gotchas           – what went wrong / what to know before touching this again
```

Planned chapters (≈ one per phase deliverable):

| Ch. | Topic | Example resources to include |
|---|---|---|
| 00 | Project setup: uv, src layout, Claude Code workflow | uv docs, Claude Code docs |
| 01 | Textual TUI fundamentals | Textual tutorial + docs, `textual console` devtools |
| 02 | Persistence: SQLite schema + migrations | sqlite3 docs, schema-migration pattern |
| 03 | Serving LLMs: Ollama, OpenAI-compatible APIs, model registry | Ollama Modelfile docs, OpenAI API reference |
| 04 | Fine-tuning data: corpora, teacher generation, filtering | HF dataset guides, vLLM docs |
| 05 | QLoRA training on a SLURM cluster | Unsloth docs, HF PEFT LoRA conceptual guide, SLURM primer |
| 06 | GGUF export & adapter serving | llama.cpp conversion docs |
| 07 | Keyword routing & persona switching | — (design chapter) |
| 08 | Memory mechanism | — (design chapter) |
| 09 | Adaptive RAG | lecture slides, sqlite-vec, embedding model docs |
| 10 | Agentic web search | ddgs, trafilatura docs |
| 11 | Pixel-art animation in Textual | Rich markup docs, Aseprite→text conversion |
| 12 | Packaging with uv/uvx & the demo | uv packaging guide |

## 13. Working with Claude Code in VS Code

1. Install: `npm install -g @anthropic-ai/claude-code` (or `brew install claude-code`) + the **Claude Code VS Code extension**; open the cloned repo folder.
2. First session: run `/init` to generate **CLAUDE.md**, then edit it to state: uv-only workflow (`uv run bpx`, `uv run pytest`), src layout, "read PLAN.md §x before feature x", handbook-chapter-per-phase rule, and the G1 base-model constraint. CLAUDE.md is loaded every session — it's how the plan stays enforced.
3. Workflow per feature: new git branch → **plan mode** (Shift+Tab) to let Claude propose an approach against PLAN.md → implement → `uv run pytest` → small commits → merge. Keep commits scoped to one plan step so handbook chapters map cleanly.
4. Textual specifics: run the app in one terminal with `textual run --dev bpx.app`, `textual console` in another — Claude Code can read the console output for debugging.
5. Cluster work stays in `training/`; Claude Code writes/edits the SLURM + training scripts locally, you `rsync`/`git pull` them onto the cluster and paste job logs back for debugging.

## 14. Packaging & launch (R1)

- uv-managed, Python ≥3.11, console script `bpx`. One-liner: `uvx --from git+https://github.com/PhilippMattar/british_pixelart_llm bpx`.
- `bpx setup`: checks Ollama, pulls `qwen3:8b` + Gemma, creates persona models from bundled GGUF adapters + Modelfiles, initializes DB. TUI shows a first-run wizard if setup hasn't run.
- Hand-in ZIP: repo snapshot incl. adapters, training + data-generation code, generated datasets, handbook, README.

## 15. Timeline (9 weeks from 2026-07-09)

| Phase | Dates | Deliverables (each phase ends with its handbook chapter(s)) |
|---|---|---|
| 0 — Scaffold | Jul 9–13 | Repo init (PLAN.md = first commit), uv project, CLAUDE.md, Ollama + qwen3:8b + Gemma pulled, minimal streaming chat loop. *Ch. 00–01 started* |
| 1 — Required core | Jul 14–26 | Conversations CRUD + SQLite + migrations, resume/cancel, scrollback, model registry + manual switching (base↔gemma working = R5 done early). *Ch. 01–03* |
| 2 — Fine-tuning | Jul 27–Aug 16 | **G1 gate first.** Seeds + prompt bank; teacher generation + filtering; QLoRA ×2; eval table; GGUF → Ollama personas; keyword router. *Ch. 04–07* |
| 3 — Memory + electives | Aug 10–30 (overlaps 2) | Project memory; adaptive RAG; agentic web search. *Ch. 08–10* |
| 4 — Flair & polish | Aug 24–Sep 4 | Pixel-art animations, `bpx setup`, cross-platform check (macOS + Linux min.), README. *Ch. 11* |
| 5 — Demo & hand-in | Sep 1–14 | Video demo, presentation (Sep 7), ZIP (Sep 14). *Ch. 12* |

## 16. Video demo (R8) — outline

Screen recording (macOS + OBS/QuickTime): launch via `uvx` one-liner → new project + chat → scrollback → manual model switch base↔gemma → keyword auto-switch to British (pixel art changes, speech bubble) → Scottish trigger (bagpiper) → resume an old conversation → project memory recall across chats → RAG over a user PDF (real-world use case: e.g. querying a Digital Health course paper) → agentic web search question → wrap-up. Real-world use-case requirement is covered by the RAG-over-own-documents segment.

## 17. Risks

| Risk | Mitigation |
|---|---|
| GGUF LoRA conversion fails for Qwen3 | G1 gate week 1 of Phase 2; fallback Qwen2.5-7B; last resort merge+quantize |
| Cluster queues / no internet on compute nodes | Start Phase 2 early; pre-download weights via login node |
| Reddit data access | Arctic Shift dumps; fallback SCOTS + Gutenberg + hand-written seeds (teacher needs hundreds, not millions) |
| Caricature collapse ("Groundskeeper Willie mode") | Slang-density caps, 15% plain-competence data, judge-gated eval before accepting an adapter |
| Free-tier cloud instability | Cloud models are optional extras, never demoed as graded features |
| Solo time crunch | Electives share the judge/controller; stretch goal explicitly droppable; handbook written incrementally, not at the end |

## 18. Open questions (external — need answers from course staff or cluster docs)

1. Is a locally installed **Ollama** acceptable for "runnable with uv", or is a pure-Python fallback (llama-cpp-python) expected? *(Biggest architectural unknown — ask early.)*
2. Cluster specifics: partitions/GPU types actually available to students, max wall time, internet on compute nodes, shared HF cache?
3. Does the §10 pipeline match the lecture's adaptive-RAG diagram closely enough ("or an equivalently complex approach")?
4. Video demo: length limit, format, live demo expected at the presentation?
5. May generated datasets (teacher = Qwen, Apache-2.0) be committed to a public repo? (Plan assumes yes.)

## 19. Repo structure

```
british_pixelart_llm/
├── pyproject.toml            # uv project, entry point `bpx`
├── CLAUDE.md                 # Claude Code project instructions
├── PLAN.md
├── README.md
├── models.toml               # model registry (local + optional remote)
├── docs/handbook/            # 00-…12-…, chapter per phase step
├── src/bpx/
│   ├── app.py                # Textual app, screens
│   ├── widgets/pixelart.py   # animation frames + player
│   ├── orchestrator.py       # persona routing, RAG/web judge dispatch
│   ├── router/keywords.py    # trigger lexicons
│   ├── llm.py                # LLMClient (OpenAI-compat, streaming, cancel)
│   ├── registry.py           # models.toml loader
│   ├── store.py              # SQLite + migrations
│   ├── memory.py             # fact extraction + injection
│   ├── rag/                  # ingest, embed (sqlite-vec), judge, rewrite, summarize
│   └── websearch/            # search loop, fetch, extract
├── training/
│   ├── data/                 # generated JSONL (shippable)
│   ├── seeds/                # collection/cleaning scripts (raw data gitignored)
│   ├── generate.py           # teacher generation (vLLM)
│   ├── filter.py             # dedup, banding, judge filter
│   ├── train_qlora.py        # Unsloth/PEFT
│   ├── eval.py               # vibe benchmark, base-vs-LoRA
│   ├── export_gguf.sh        # llama.cpp conversion
│   └── slurm/                # sbatch scripts
├── models/
│   ├── Modelfile.british     # FROM qwen3:8b + ADAPTER
│   ├── Modelfile.scottish
│   └── adapters/             # GGUF LoRAs
├── tests/
└── demo/                     # video storyboard + script
```
