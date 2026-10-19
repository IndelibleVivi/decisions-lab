# Decisions Lab

**Make bounded decisions inspectable.**

[中文](README.md) · [October 15 update](research/2026-10-15/README.md) · [Playbook](docs/playbook.md) · [Project map](docs/projects.md) · [Experiment](experiments/next-action/README.md)

Decisions Lab studies decision models and typed decision APIs: their contracts, failure modes, and place in workflows that remain accountable to people and code. Chinese is the primary documentation language; this entry covers setup, supported behavior and limitations in English.

Stable methods, dated research, and replayable experiments have different lifetimes. The initial snapshot indexes 23 model/service entities, 21 repositories, 6 studies and 171 sources. The supplied historical dataset was recomputed: 1,000 cases, 4,000 probability records and 14 matching author aggregates. Historical predictions are not redistributed. See the [snapshot guide](research/2026-10-08/README.md) for reproduction using an independently supplied bundle.

## Run offline

Python 3.11+; no third-party dependencies for the experiment CLI. From the repository root:

```bash
python3 -m decision_lab validate experiments/next-action/cases.json
python3 -m decision_lab baseline-run experiments/next-action/cases.json --run-dir runs/baseline-001
python3 -m decision_lab demo experiments/next-action/cases.json --run-dir runs/demo-001
python3 -m decision_lab replay runs/demo-001 experiments/next-action/cases.json
python3 -m decision_lab prepare experiments/next-action/cases.json --route jev --limit 1
python3 -m decision_lab prepare experiments/next-action/cases.json --route decisions --limit 1
python3 tools/catalog.py projects --query calibration
python3 tools/catalog.py updates --query jev
python3 tools/catalog.py recipes --query NPC --json
```

The next-action task recommends a reading or verification action for supplied evidence and a claim. It has 25 original synthetic cases in Chinese, English and mixed language, grouped by source across dev/test splits. The baseline is deterministic; the demo deliberately includes an error and an explicit unknown. Neither is model inference or a model-quality benchmark. Use a fresh output directory for each run.

The opt-in live collector has native profiles for TypeSafe Jev and OpenAI Decisions. It requires credentials via environment variables, an explicit network switch and a call limit. It does not execute the recommended action, retry implicitly, or fall back to another provider. See the [experiment contract and commands](experiments/next-action/README.md). Live availability, quality, billing and production integration remain unverified.

## Build and check the reader

The home page opens with full-screen typography and an original WebGL particle sculpture: morph between a woven knot, branching ribbons and an orbit; pointer movement changes the whole pose, dragging rotates it with inertial release, and tapping scatters it. Arrow keys rotate; Home or Reset restores the initial viewpoint of the selected shape. The large title letters respond to pointer proximity and dragging, spring back into place, and leave sliced echoes. Below the cover, recipes lead into experiments, then tools and reading. The playbook offers 20 recipes with category and keyword filtering and pixel cartridges for switching the active recipe and updating a shareable fragment. An original low-resolution signal field uses the same catalog options, with an explicit cue that square nodes are clickable. Ordinary options follow forward branches, requests for context or human review loop back, and unknown has a separate × outlet and an unnumbered control. The drawing, selection and readable result stay in sync. The result rail distinguishes ok, unknown, refusal and error: manual choices preview the first two, while clearly labeled offline examples of API refusal and call failure clear every selected option. Reset returns to the unanswered state. The readout separates choice from probabilities / confidence and never invents probability values. This workbench demonstrates a Choice profile; see the [result contract](docs/method.md#结果状态与输出类型) for the distinction between output primitives and normalized record states. Each recipe retains expandable steps, mechanisms and failure modes, project references and copyable provider-neutral task JSON. Two have existing offline experiments; the others are integration proposals. Complete recipes link to native API examples. Five project categories retain access to the 21 historical catalog projects.

Further down are an illustrative probability landscape with presets, a bias slider, maxP and entropy, and a historical pixel matrix with task and high-maxP subset controls. Cells settle with a finite stepped animation while the actual counts update immediately. Three original synthetic cases let you choose a next action and compare it with editorial labels and rationale. Particle geometry and color are visual treatments, not model relationships or performance; the probability landscape is also illustrative. The PLAY dot-matrix sign cycles through six group marks, displaying at most two per frame. Entry glyphs, the probability landscape and the historical matrix have controlled motion. Space Grotesk display text and Silkscreen labels are self-hosted. Articles have section navigation, reading progress, code copying and scrollable tables. Project search offers direct links to matching rows while retaining limitations and source notes.

Building requires Python 3.11+ and `requirements-site.txt`; full verification also requires Node.js 22+, with no npm packages. Answers are not stored. Only a manually selected day/night appearance is saved locally; the initial theme follows the system and applies throughout the reader. Motion can be paused, respects reduced-motion preferences, and stops while offscreen or in a background tab. Shape changes, dragging and keyboard rotation work as static updates when paused or under reduced motion; hovering does not restart animation. Title motion follows the cover pause control; the shared lower-page pause control also stops the signal field, sign, glyphs, probability landscape and historical matrix. Static route choices, offline outcome examples and distribution controls remain available while paused, with immediate readouts. Reduced motion suppresses these animations. Static images remain when WebGL or Canvas 2D is unavailable. All recipes, historical aggregates, articles and case material remain readable without JavaScript.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-site.txt
.venv/bin/python tools/check.py
.venv/bin/python tools/build_site.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory _site
```

Open `http://127.0.0.1:8765`. The reader uses the canonical Markdown/catalog and an explicit output allowlist. It makes no requests to external font services, analytics or browser-side model APIs. For the dependency-free CLI/data checks only, run `python3 tools/check.py --core-only`. CI uses the same entry point.

## Interpretation and boundaries

The separate [2026-10-15 targeted update](research/2026-10-15/README.md) records 30 sources and 12 changes across Jev 1.14, OpenAI Decisions contract/SDK differences, Cloudflare, Fastino and Upstage. It does not refresh the entire initial census or overwrite historical evidence. Recipes carry their own project-source dates. Public documentation and advertised prices are not evidence of live calls, billing or task quality.

Results apply to the recorded tasks, routes and versions. Probability, provider confidence and correctness are distinct. Missing context, explicit unknown, refusal and transport failure need distinct treatment. See [evaluation method](docs/method.md), [integration design](docs/integration.md), [maintenance](docs/maintenance.md) and [current state](docs/current-state.md).

Public content uses public sources or original synthetic tasks. Private chats, account information, credentials and real run records stay outside Git. Live collection sends selected task inputs to the chosen provider and retains raw responses locally; protect those records according to the sensitivity of their inputs. The experiment never changes external systems or personal memory.

Original code is under [SUL-1.0](LICENSE); original documentation, diagrams and synthetic cases are under [CC BY-NC-SA 4.0](LICENSE-DOCUMENTATION.md). Third-party rights remain separate. See [LICENSING.md](LICENSING.md). These are source-available terms, not an OSI open-source claim.
