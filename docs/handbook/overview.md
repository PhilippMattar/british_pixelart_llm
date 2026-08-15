# The Story So Far — bpx in Plain Terms

*A quick, jargon-light tour of what we've built. Assumes you're technical-curious, not a
software engineer. The numbered chapters (00–07) are the detailed versions.*

## What we're building

`bpx` is a chat app that lives in your terminal — a mini ChatGPT that talks to AI models
running **on your own computer** (via a tool called Ollama, so nothing goes to the cloud).
Normally it's a plain, helpful assistant. But say the right word and it slips into character: an
impossibly posh, dry-witted **British butler**, or a warm-but-grumbling **Scot** — with matching
pixel-art animations while it thinks.

## How we got here

**Phase 0–1 — the skeleton.** First we built the app itself: the chat window, a small local
database that saves your conversations (so you can close it and pick up where you left off), and
a "registry" that lets you swap between AI models. At this point it could chat, remember, and
switch models by hand.

**Phase 2 — teaching the AI to have a personality.** This was the big one. You can't just *tell*
a model "be British" and get a consistent character; you have to **train** it. The recipe:

- **The idea — distillation.** We used a big, clever AI (the "teacher") to answer thousands of
  ordinary questions *in character*. That gave us ~4,850 examples of "here's a normal question →
  here's how a posh Brit / grumpy Scot would answer it." Like a teacher writing out a textbook of
  worked examples. (Importantly, the questions came from a public dataset; the teacher only ever
  wrote the *style*.)

- **The training — a "personality patch."** We fed those examples to the base model to train a
  small clip-on patch (a *LoRA adapter*) — one for British, one for Scottish. Same model
  underneath, different voice on top, like an actor learning a role. This ran on a university
  **supercomputer**, because training needs a serious graphics card we don't have locally.

- **The gotcha — thinking out loud.** The first time we ran the trained Scot, it produced
  gibberish. The model was trying to "show its reasoning" first (a feature called *thinking
  mode*), but we'd trained it to answer *directly*. That mismatch = garbage. Once we told it to
  stop thinking out loud, it was flawless.

- **The report card — evaluation.** How do we *know* it worked? We had a **judge AI** grade 30
  answers from the plain model versus our trained personas, scoring "how in-character" and "how
  helpful." Character jumped from ~2/5 to a perfect **5/5** — and helpfulness didn't drop at all.

## Where we are now

Both personas are trained, wired into the app, and measured. Phase 2 is done. Next up: giving
the app a **memory**, and letting it **search your documents and the web**.
