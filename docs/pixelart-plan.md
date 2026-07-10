# Pixel-art waiting animation — design & production plan

*Drafted 2026-07-09. Expands PLAN.md §9 (pixel art) and §12 Ch. 11 for Phase 4 (Aug 24–Sep 4).
Feasibility numbers below were measured with a spike in this repo, not estimated.*

## 1. Goal & spec

A waiting animation shown while the model generates, **clearly visible at 90×30 pixels**,
with one art set per persona and honest state signalling:

| Persona (registry)   | Scene (PLAN.md §9)                                            |
|----------------------|---------------------------------------------------------------|
| neutral (qwen/gemma) | Non-persona scene — e.g. desk with CRT terminal, blinking cursor, steaming mug |
| `british`            | Royal figure waving + speech bubble echoing a salient prompt word |
| `scottish`           | Angry bagpiper outside a pub + grumpy speech bubble           |

States: **generating** (looping), **stopped** (frozen + red/desaturated tint on Esc,
matching today's spinner contract), **hidden** (idle). The widget replaces
`WaitingIndicator` behind the same `start()` / `stop(cancelled=)` API; the current 2×2
spinner stays as the small-terminal fallback.

## 2. How 90×30 "pixels" fit in a terminal

Half-block `▀` renders **2 pixels per character cell** — foreground colour = top pixel,
background = bottom pixel, both independent. So 90×30 px = **90 columns × 15 rows** of text.

| Technique   | Px/cell | Colours              | Verdict |
|-------------|---------|----------------------|---------|
| Half-block ▀| 1×2     | 2 independent/cell   | **Locked (PLAN.md §9)** — only lossless-colour option |
| Quadrants ▖▞| 2×2     | 2 per 4 px → bleeding| Rejected: muddy colour |
| Braille ⣿   | 2×4     | 1 per 8 px           | Rejected: effectively monochrome |
| Sextants    | 2×3     | 2 per 6 px           | Rejected: patchy font support |

Implication: **90 columns exceeds the 80-col default terminal.** See §7.

## 3. Measured feasibility (spike, this repo)

8 frames of 90×15 cells with worst-case colouring (every pixel a unique random truecolour —
zero style-run merging, the most expensive possible frame):

- Frame pre-render: **4.9 ms/frame** (done once at startup)
- `Static.update()` + refresh per frame swap: **46.5 ms** against a 100–150 ms frame budget (8–10 fps)
- Real sprites use ≤16-colour palettes → long same-style runs → far cheaper than measured
- 80×24 terminal: content crops safely, **no crash** (fallback still wanted for looks)

**Conclusion: comfortably feasible with pre-rendered frames swapped on a `set_interval` timer** —
the exact architecture the current `WaitingIndicator` already uses.

## 4. Getting the artistic style — three options

### A. Hand-pixel everything (LibreSprite / Piskel / Aseprite)
Full stylistic control; the classic route. **Cost:** slowest, and the quality ceiling is my
pixel-art skill. 3 scenes × 90×30 × frames is many hours of unfamiliar work. Editors:
Piskel (free, browser), LibreSprite (free, desktop), Aseprite (~€20, the industry favourite).

### B. AI-assisted, then clean up by hand
Generate concept art at high resolution, downscale to 90×30 with nearest-neighbour, quantize
to a fixed palette (Pillow), then repair by hand in the editor. **Pros:** fast path to a
composition that looks designed. **Cons:** AI output rarely respects a pixel grid or a small
palette (cleanup is real work); frame-to-frame consistency for animation is poor, so AI is
best for the **static background only**. Provenance documented (see §8).

### C. Compose from CC0 game assets
Build scenes by compositing existing CC0 sprites (Kenney, OpenGameArt), recoloured to our
palettes. **Pros:** fastest, professional-looking base. **Cons:** style dictated by what
exists; 16×16/32×32 game sprites need scaling/adaptation into a 90×30 banner; the specific
characters (royal, bagpiper) almost certainly don't exist ready-made.

### → Recommended: hybrid, per layer
- **Backgrounds** (pub exterior, palace/flag, desk): option **C** (CC0 tiles/props) with
  option-B AI drafts as fallback, hand-adjusted.
- **Focal characters** (royal, bagpiper): option **A**, hand-pixeled — they're small
  (~20×28 px within the banner), unique, and carry the persona identity.
- **Style anchor:** one fixed ≤16-colour palette per persona (Lospec palettes are free to
  use; palettes aren't copyrightable): neutral = cool greys/teal, british = navy/red/cream/gold
  (Union-Jack range), scottish = tartan greens/navy + warm pub browns. All art is quantized to
  its palette — this is what makes mixed-source art read as one style.

## 5. Animation design — frame economy

Full-frame animation at 90×30 is wasteful; **static background + 2–4 small animated regions**
is how real games do idle animations and cuts effort by ~10×:

- **Neutral:** cursor blink (2 fr) · mug steam drift (3 fr) · CRT scanline shimmer (2 fr)
- **British:** waving hand (3 fr) · flag flutter (3 fr) · bubble text types in
- **Scottish:** cheeks/bag inflate (3 fr) · pub sign swings (2 fr) · chimney smoke (3 fr)

Loop of 4–8 composed frames at ~8 fps (`set_interval(0.12)`), like today's spinner.
**Stopped state:** same current frame re-mapped through a desaturated/red palette (cheap,
no extra art) + "Stopped (Esc)" caption.
**Speech bubble:** a reserved flat-colour region in the art; the word is rendered as real
text glyphs on top (crisp at any size), max ~12 chars, ellipsized. Source: the router's
matched trigger keyword (Phase 2 gives us this for free), else the longest content word.

## 6. Pipeline & architecture

```
editor/AI/CC0 assets ──► PNG sprite sheet per persona (art/ source files, committed)
        │ tools/png2frames.py   (standalone uv script, PEP 723 inline deps: pillow —
        ▼                        Pillow never enters the app's runtime dependencies)
src/bpx/widgets/frames_<persona>.py   (generated, committed: palette + frame data)
        ▼
PixelArtWidget(Static)  — pre-builds Rich Text frames once, swaps on set_interval,
                          same start()/stop(cancelled=) contract as WaitingIndicator,
                          persona setter, bubble_text setter, fallback to 2×2 spinner
```

Keeping generated frame modules in the repo means: zero runtime deps, instant startup, and
the converter only reruns when art changes. (`rich-pixels` (MIT) can PNG→half-block at
runtime — useful for prototyping in week 1, but it drags Pillow into runtime deps, so the
offline converter is the shipping path.)

## 7. Bottlenecks & risks — with mitigations

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | **Terminal width**: 90 cols > 80-col default; banner + padding needs ~94 | Design art with an **80-col safe zone** (nothing essential in outer margins); if `app.size.width < 94` or height < 24, fall back to the 2×2 spinner. Crop is safe (measured), just ugly. |
| 2 | **Height cost**: 15 rows squeezes the chat log on small terminals | Same fallback rule; optionally a half-height 90×16 px "strip" variant later. |
| 3 | **Colour fidelity**: macOS Terminal.app has no truecolour (256 max) | Rich auto-downgrades; palettes chosen near xterm-256 anchors so quantization doesn't mud the art. Test in Terminal.app, iTerm2, Windows Terminal. |
| 4 | **Font seams**: some fonts leave gaps between ▀ rows (line-height ≠ 1) | Cosmetic only; note recommended fonts in README (SF Mono, JetBrains Mono OK). |
| 5 | **Art time blowout** (the biggest risk — solo, unfamiliar craft) | Frame economy (§5); timebox one set/day; neutral first (simplest, always shippable); Scottish before British (demo order). A static scene + one animated region is an acceptable minimum per set. |
| 6 | **Licensing** of sourced art | Commit only CC0 (+ CC-BY with attribution at most); never CC-BY-SA (share-alike friction with MIT repo); log every asset in `art/ASSETS.md` (source, URL, licence). AI-assisted pieces documented as such. Matches the CLAUDE.md "nothing you can't redistribute" rule. |
| 7 | **Flicker/perf** | Pre-rendered `Text` objects, one `Static.update()` per tick — measured 46.5 ms worst-case, real art much less. No per-frame markup parsing. |
| 8 | **Dynamic bubble text vs pixel grid** | Bubble region uses real glyphs, not pixels — always crisp, no per-word art. |

## 8. Safe sources of artistic material

| Source | Licence | Use for |
|---|---|---|
| **Kenney.nl** (all packs) | CC0 | Props, tiles, UI bits, background elements |
| **OpenGameArt.org** (licence-filtered) | CC0 / CC-BY | Buildings, nature, character reference |
| **Lospec palette list** | palettes not copyrightable | The three persona palettes |
| **Public-domain references** (royal portraits, tartan patterns, pub photos) | PD | Drawing reference only |
| **Piskel / LibreSprite** | free tools | Authoring |
| **rich-pixels** (Textualize) | MIT | Runtime prototyping only |
| itch.io free packs | ⚠ per-pack | Only if explicitly CC0/redistributable — most forbid redistribution, and we commit assets to a public repo |
| Lospec *gallery art*, game rips, "free wallpaper" sites | ✗ | Never — not redistributable |

## 9. Execution plan (Phase 4 window, ≈5 working days)

| Step | Deliverable | Time |
|---|---|---|
| 0 | ~~Feasibility spike~~ — **done** (numbers in §3) | — |
| 1 | `PixelArtWidget` skeleton: frame player, states, persona/bubble API, size fallback, headless tests | ½ d |
| 2 | `tools/png2frames.py` converter (PNG→palette-mapped frame module) + `art/ASSETS.md` | ½ d |
| 3 | **Neutral set** end-to-end (proves the whole pipeline) | 1 d |
| 4 | **Scottish set** (bagpiper, pub, smoke, bubble) | 1 d |
| 5 | **British set** (royal, flag, wave, bubble word wiring) | 1 d |
| 6 | Polish: stopped-tint palettes, terminal matrix test, handbook **Ch. 11** | ½ d |

Definition of done per set: loops at 8 fps in `uv run bpx`, stopped state renders, fallback
triggers below 94 cols, all sources logged in `art/ASSETS.md`.

## 10. Decisions to confirm (when reviewing this plan)

1. **Size trade-off** — full 90×30 with fallback (planned), or an 80-col-native 80×30 so the
   default terminal never crops?
2. **Style sign-off** — I'll produce one static mock frame per persona palette before
   animating anything; approve/adjust palettes then.
3. **Tooling** — free (Piskel/LibreSprite) vs Aseprite (~€20, nicer animation onion-skinning).
