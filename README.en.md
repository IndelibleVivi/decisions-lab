# Decisions Lab

**Make decisions and typed values inspectable.**

[中文](README.md) · [October 22 update](research/2026-10-22/README.md) · [Research infrastructure](docs/research-infrastructure.md) · [API experiments](experiments/api-capabilities/README.md) · [Typed values](docs/typed-values.md) · [Playbook](docs/playbook.md)

Decisions Lab studies decision models and typed value extraction: selecting actions, extracting fields, computing values, and estimating unknown outcomes. It examines their contracts, failure modes, and place in workflows that remain accountable to people and code. Chinese is the primary documentation language; this entry covers setup, supported behavior and limitations in English.

Stable methods, dated research, and replayable experiments have different lifetimes. The initial snapshot indexes 23 model/service entities, 21 repositories, 6 studies and 171 sources. The supplied historical dataset was recomputed: 1,000 cases, 4,000 probability records and 14 matching author aggregates. Historical predictions are not redistributed. See the [snapshot guide](research/2026-10-08/README.md) for reproduction using an independently supplied bundle.

## Research infrastructure

The [research guide](docs/research-infrastructure.md) separates numeric event probabilities from modal-menu option mass, adds perfect/uniform/wrong oracle controls and explicit trial repetitions, and provides a read-only common ledger over the native contracts. Four deterministic generators retain exact truth, source families and grouped splits. The offline rule workflow connects compilation, exhaustive verification, minimal counterexamples, repair controls, version changes and replay. Paired comparisons retain failures in the workflow-loss denominator, aggregate units and bootstrap source families; small cluster counts remain descriptive.

```bash
python3 -m decision_lab research generate --kind rules --seed 17 --units 20 --output runs/rule-worlds.json
python3 -m decision_lab research rule-workflow --dataset runs/rule-worlds.json --output runs/rule-repair.json
python3 -m decision_lab research rule-replay runs/rule-repair.json
```

The opt-in `research collect` requires explicit network permission, credentials and call/question/estimated-input-token budgets. Sequential attempts retain raw bytes, elapsed time, failures, cancellation and uncertain delivery across checkpoints and resume. The byte-based input estimate is not an output-token or billing cap. Live calls still require a separately selected model, input boundary and budget; none were made in this upgrade. Synthetic controls demonstrate the research machinery, not model performance.

## New content: API capabilities and experiments

The [October 22 investigation](research/2026-10-22/README.md) connects documented capabilities to falsifiable experiments: compiling Boolean rules with Choice, testing probability composition, and defining Jev criteria with reference images. A separate `api-lab` CLI prepares native multi-question requests, imports raw responses, replays per-question scoring and reports counterexamples. Ground truth comes from enumeration, known synthetic worlds and geometry. Synthetic demos are not model measurements; provider status remains `NOT_RUN`.

The [capability guide](docs/api-capabilities.md) covers seven research directions with controls and implementation limits. The [queryable index](catalog/capabilities.json) connects each hypothesis to dated sources, metrics and request coverage. Semantic features, semantic addressing, Clairic list/forecast transformations, and temporal/multimodal evaluation remain research designs. The current reference documents 400 questions while the inspected Python SDK docstring says 200; the service boundary is untested. Experimental Jev image criteria use their own assets/header contract.

The [October 20 investigation](research/2026-10-20/README.md) adds Cloudflare Clairic with eight official sources and seven change records. A [field guide](docs/typed-values.md) distinguishes extraction, computation and prediction. [Three experiment dossiers](experiments/typed-values/README.md) provide original synthetic inputs, native requests, editorial oracles, controls and scoring plans for missing values, context loss after extraction, and prediction intervals.

The provider experiments remain NOT_RUN, with no collected model results. A separate `typed-values` CLI now prepares requests, runs explicitly synthetic baselines/demos, imports local responses and replays field, arithmetic and interval scoring. It uses its own result contract alongside next-action; an opt-in bounded collector now covers Clairic and api-lab; no live provider collection has been performed. The October 8 census and October 15 investigation retain their original dates.

## Run offline

Python 3.11+; no third-party dependencies for the experiment CLI. From the repository root:

```bash
python3 -m decision_lab api-lab list
python3 -m decision_lab api-lab validate
python3 -m decision_lab api-lab prepare --experiment rule-compile --route decisions --limit 1
python3 tools/catalog.py capabilities --query probability --json
```

See the [experiment guide](experiments/api-capabilities/README.md) for synthetic demos, import format, replay and comparison. These commands do not read credentials or make provider calls. Imported responses are not described as Lab live collection. Numeric event answers, native option probabilities and confidence retain separate meanings. Legacy next-action and typed-values records remain supported under their own contracts:

```bash
python3 -m decision_lab validate experiments/next-action/cases.json
python3 -m decision_lab baseline-run experiments/next-action/cases.json --run-dir runs/baseline-001
python3 -m decision_lab demo experiments/next-action/cases.json --run-dir runs/demo-001
python3 -m decision_lab replay runs/demo-001 experiments/next-action/cases.json
python3 -m decision_lab prepare experiments/next-action/cases.json --route jev --limit 1
python3 -m decision_lab prepare experiments/next-action/cases.json --route decisions --limit 1
python3 tools/catalog.py projects --query calibration
python3 tools/catalog.py updates --query clairic
python3 tools/catalog.py updates --date 2026-10-15 --query jev
python3 tools/catalog.py recipes --query NPC --json
```

The next-action task recommends a reading or verification action for supplied evidence and a claim. It has 25 original synthetic cases in Chinese, English and mixed language, grouped by source across dev/test splits. The baseline is deterministic; the demo deliberately includes an error and an explicit unknown. Neither is model inference or a model-quality benchmark. Use a fresh output directory for each run.

Typed values use a separate subcommand under the same entry point:

```bash
python3 -m decision_lab typed-values validate
python3 -m decision_lab typed-values prepare --case-id source-missing
python3 -m decision_lab typed-values baseline-run --run-dir runs/typed-baseline-001
python3 -m decision_lab typed-values demo --run-dir runs/typed-demo-001
python3 -m decision_lab typed-values replay runs/typed-demo-001
```

`prepare` only prints requests; the baseline and demo are synthetic. Import existing local responses with `typed-values import --responses <responses.json> --run-dir <new-directory>`, then recompute scoring with `replay`. The [typed-values guide](experiments/typed-values/README.md) defines the import format, three decision paths and explicit span conventions. These commands read no credentials, make no provider calls and do not change the authored suite's NOT_RUN status.

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
