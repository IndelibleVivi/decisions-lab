# Decisions Lab

**Make bounded decisions inspectable.**

[中文](README.md) · [Research snapshot](research/2026-10-08/README.md) · [Project map](docs/projects.md) · [Experiment](experiments/next-action/README.md)

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
```

The next-action task recommends a reading or verification action for supplied evidence and a claim. It has 25 original synthetic cases in Chinese, English and mixed language, grouped by source across dev/test splits. The baseline is deterministic; the demo deliberately includes an error and an explicit unknown. Neither is model inference or a model-quality benchmark. Use a fresh output directory for each run.

The opt-in live collector has native profiles for TypeSafe Jev and OpenAI Decisions. It requires credentials via environment variables, an explicit network switch and a call limit. It does not execute the recommended action, retry implicitly, or fall back to another provider. See the [experiment contract and commands](experiments/next-action/README.md). Live availability, quality, billing and production integration remain unverified.

## Build and check the reader

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-site.txt
.venv/bin/python tools/check.py
.venv/bin/python tools/build_site.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory _site
```

Open `http://127.0.0.1:8765`. The reader uses the canonical Markdown/catalog and an explicit output allowlist. It has no external fonts, analytics or browser-side model requests. For the dependency-free CLI/data checks only, run `python3 tools/check.py --core-only`. CI uses the same entry point.

## Interpretation and boundaries

Results apply to the recorded tasks, routes and versions. Probability, provider confidence and correctness are distinct. Missing context, explicit unknown, refusal and transport failure need distinct treatment. See [evaluation method](docs/method.md), [integration design](docs/integration.md), [maintenance](docs/maintenance.md) and [current state](docs/current-state.md).

Public content uses public sources or original synthetic tasks. Private chats, account information, credentials and real run records stay outside Git. Live collection sends selected task inputs to the chosen provider and retains raw responses locally; protect those records according to the sensitivity of their inputs. The experiment never changes external systems or personal memory.

Original code is under [SUL-1.0](LICENSE); original documentation, diagrams and synthetic cases are under [CC BY-NC-SA 4.0](LICENSE-DOCUMENTATION.md). Third-party rights remain separate. See [LICENSING.md](LICENSING.md). These are source-available terms, not an OSI open-source claim.
