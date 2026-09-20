# RhinoCoder

> **An AI agent that executes, observes, verifies, and recovers inside Rhino 8—not just one that writes scripts.**

[Live read-only demo](https://rhinocoder-demo.xiongweiluo1.chatgpt.site) · [Real Rhino evidence clip](docs/assets/rhinocoder-real-rhino-demo.mov) · [中文](README.md) · [5-minute Replay](#quickstart-a-no-rhino-required) · [Real Rhino quickstart](#quickstart-b-real-rhino-8) · [Evidence index](docs/portfolio-evidence.md) · [Architecture](docs/architecture.md)

RhinoCoder is a verifiable, recoverable, privacy-aware spatial-design agent for Rhino 8. It translates natural-language tasks into 23 versioned MCP tool calls, executes geometry on Rhino's main thread, reads the resulting scene back, and checks it with programmatic assertions. Privacy decisions, model routing, tool calls, corrections, cost, and evidence share one auditable `run_id`. A sanitized synthetic Replay lets reviewers inspect the loop without Rhino or a model key.

![RhinoCoder synthetic self-correction Replay](docs/assets/replay-demo.gif)

## Results at a glance

| Verified result | Scope and evidence |
|---|---|
| **500/500 admitted golden traces across 46 tags** | Assertion, scene self-check, human approval, and privacy gates; [A7 report](docs/a7-500-marginal-value.md) |
| **All 8 measured coverage gaps filled** | 200 A7 tasks: 40 each for multi-round revision and Boolean-alternative recovery, 20 each for six other gaps; [A7 report](docs/a7-500-marginal-value.md) |
| **270/270 locked real-Rhino runs passed** | 30 tasks × 3 repeats × main/economy/rule-router; the saturated set is not an open-world claim; [A6 report](docs/a6-no-finetune-baseline.md) |
| **P2a external hard set: 18/30 valid baseline passes** | Five first-wave connection interruptions resumed the same slots with the frozen prompt and remain recorded; 60.0%, Wilson 95% CI 42.3%–75.4%; [P2a report](docs/p2-external-hard-set.md) |
| **Zero sensitive findings in the A4 audit** | 12 red-team cases, 1,609 traces, 7,016 SQLite rows, three Replays, and simulated log/request surfaces; [A4 report](docs/privacy-red-team-report.md) |
| **A1–A7, B1–B4, and C0–C2 completed** | The MornAI RTX 3090 completed C1 GPU smoke/resume and the single locked C2 QLoRA run; structured validation metrics were all zero, so no LoRA gain is claimed; [C2 report](docs/c2-qlora-training-report.md) |

Current release: [`v0.3.0`](https://github.com/xiongweiluo/RhinoCoder/releases/tag/v0.3.0). Recruiters can open the [live read-only demo](https://rhinocoder-demo.xiongweiluo1.chatgpt.site) without Rhino, a model key, or installation. Unreleased evidence now includes a [real-Rhino single-window clip](docs/assets/rhinocoder-real-rhino-demo.mov) and [result frame](docs/assets/rhinocoder-real-rhino-result.png). The clip is an explicitly labeled, privacy-reviewed before/after frame sequence—not continuous desktop footage—and contains no audio or real project data.

> **Honest boundary:** `local-mock` is a deterministic interface and safety test double. It proves forced private routing and no-cloud fallback, not real local-model quality. P2a contains tasks authored externally but executed by the Agent; it is not a study in which people used the UI. P2b is postponed. C0/C1/C2 have completed on a MornAI RTX 3090, but all four structured validation metrics—tool-call parse, name, arguments, and full sequence exactness—were zero. This is not evidence that LoRA beats the base model or can perform Rhino modeling. The A5 holdout has not been uploaded or read; the isolated C3 gate exists but has not been frozen or run, and there is no P2 LoRA result or C4 decision.

## Why this is more than an “LLM + tools” demo

- Success requires geometry evidence: RhinoCoder reads Rhino back and checks count, dimensions, color, and spatial relations.
- An enforceable privacy gate runs before routing, model initialization, and MCP. Critical input is blocked; high-risk input is forced local; medium-risk input is minimized.
- Mutations carry idempotency keys. Backend fallback occurs only at a planning boundary and never replays completed Rhino tool calls.
- A monotonic event envelope, Trace, and SQLite lineage tie decisions, tools, assertions, cost, feedback, and recovery to one run.
- Limitations sit beside metrics: Mock, GPU preparation, and 100% on a saturated 30-task set are never presented as local-model or open-world performance.

## Quickstart A: no Rhino required

Fastest path: open the **[RhinoCoder live read-only demo](https://rhinocoder-demo.xiongweiluo1.chatgpt.site)** and choose normal execution, self-correction, or privacy-aware routing. It plays frozen sanitized synthetic data in the browser, with no model, Rhino, WebSocket, or mutation capability.

To inspect the same experience locally, use:

Requirements: Python 3.11–3.13 and Node.js `^20.19.0` or `>=22.12.0`.

```bash
git clone https://github.com/xiongweiluo/RhinoCoder.git
cd RhinoCoder
RHINOCODER_PYTHON=python3 ./scripts/bootstrap.sh
./scripts/start-replay.sh
```

After local startup, open one of these read-only entry points:

- `http://127.0.0.1:7860/?demo=normal-loop&mode=replay` for a successful privacy → route → tool → scene → assertion loop;
- `http://127.0.0.1:7860/?demo=self-correction&mode=replay` for a failed first assertion, targeted correction, second scene read, and pass;
- `http://127.0.0.1:7860/?demo=privacy-route&mode=replay` for synthetic email minimization, rule-based routing, grouped-table geometry, and an audit summary.

Expected: `Read-only demo`, a filterable evidence timeline, a same-`run_id` dashboard, before/after Scene Summary, assertion detail, disabled mutation controls, and a browser-surface privacy summary. Replay is loaded only with GET: it opens no WebSocket, calls neither a model nor Rhino, and cannot mutate a scene. To rebuild a temporary public workspace and verify the first Replay:

```bash
python tools/verify_clean_install.py
```

The [P1 scenario catalog](docs/demo/p1-scenarios.json) locks each goal, input, expected result, assertion, Replay, and evidence link. See the [P1 recruiter demo report](docs/p1-recruiter-demo.md) for implementation boundaries and browser acceptance.

## Quickstart B: real Rhino 8

Requirements: macOS 14+, Rhino 8, supported Python/Node versions, and a DeepSeek-compatible model configuration. Start with a blank, disposable Rhino document.

```bash
git clone https://github.com/xiongweiluo/RhinoCoder.git
cd RhinoCoder
RHINOCODER_PYTHON=python3 ./scripts/bootstrap.sh
```

Fill the local `.env` placeholders; never commit a real key. In Rhino's Script Editor, start the Listener:

```text
_-ScriptEditor _Run "/absolute/path/to/RhinoCoder/plugin/start_rhinocoder_listener.py"
```

Then run a health check and a read-only first task:

```bash
.venv/bin/python tools/doctor.py
.venv/bin/python agent/main.py --prompt "Read the current Rhino scene summary and report the object count. Do not create, delete, move, or modify any object."
./scripts/start.sh
```

Open `http://127.0.0.1:7860` and try:

```text
Create a 20x20x2 base at the origin, then place a red sphere of radius 8 centered on its top face.
```

Expected: two Rhino objects plus privacy/route decisions, tool trace, Scene Summary, metrics, and a completed state in the UI. With a running Listener, the clean-room verifier can include the localhost read-only MCP path:

```bash
python tools/verify_clean_install.py --local-rhino
```

## Architecture and evidence

[Open the runtime architecture SVG](docs/assets/architecture.svg) · [Open the data-flow SVG](docs/assets/data-flow.svg) · [Detailed architecture](docs/architecture.md)

![RhinoCoder runtime architecture](docs/assets/architecture.svg)

The representative `self_correction.json` chain is:

```text
instruction → privacy decision → route decision → Rhino tool
→ scene read → failed assertion → targeted correction
→ second scene read → passing assertion → metrics + auditable result
```

The JSON, GIF, diagrams, and hashes are public and synthetic: [Replay](eval/replays/self_correction.json) · [GIF](docs/assets/replay-demo.gif) · [asset manifest](docs/demo/demo-assets-manifest.json). Full real traces, SQLite databases, screenshots, user identities, and project files stay in Git-ignored local storage.

Training data is grouped by task template and numeric variants before deterministic 70/15/15 splitting and view extraction. The A5 holdout and the frozen P2 hard set never enter training or iterative tuning; this run records `holdout_read=0`. Only the final locked candidate may consume A5 once through a separate audited entry point while training loaders continue to reject holdout. P2 is reported separately as a pre-training-frozen external hard regression set that has already informed earlier system-failure analysis, not as a pristine blind test.

## Verification

```bash
./scripts/check.sh
./scripts/release-verify.sh
# Add a local read-only Rhino check when the Listener is running:
./scripts/release-verify.sh --local-rhino
```

Release verification checks `git diff --check`, tests, task formats, P2 freeze/result recomputation, secret/privacy/Replay audits, training safety gates, version consistency, front-end build, P1 scenario audit, UI bundle budgets, real-browser end-to-end tests, demo hashes, and clean-room Replay. It never commits, tags, pushes, or creates a GitHub Release.

See the [evidence index](docs/portfolio-evidence.md), [v0.3.0 checklist](docs/release-checklist.md), and [release verification report](docs/v0.3.0-release-verification.md).

## Demo and interview kit

- [2:35 storyboard, bilingual narration, recording command, and privacy checklist](docs/demo/README.md)
- [Chinese subtitles](docs/demo/rhinocoder-demo.zh-CN.srt) · [English subtitles](docs/demo/rhinocoder-demo.en.srt)
- [Real Rhino single-window evidence clip](docs/assets/rhinocoder-real-rhino-demo.mov) · [result frame](docs/assets/rhinocoder-real-rhino-result.png)
- [One-page bilingual résumé description and interview outline](docs/career-one-pager.md)

The repository GIF remains an automated synthetic Replay. The real-Rhino clip is separately labeled as a sanitized single-window before/after frame sequence and was reviewed before publication.

## Known limitations

- Primary real-world validation is macOS 15.6 arm64 + Rhino 8. Windows, Intel Mac, multi-user concurrency, and a second physical Mac are not release-validated.
- The fixed 30-task suite is saturated. Its 100% Pass@1 establishes stability under that contract, not open-world, hard-set, or user-workflow success.
- `local-mock` does not perform local inference. GPU smoke/resume and the single formal QLoRA run completed on the RTX 3090, but structured validation scored zero and final A5/P2 pairing has not run, so no local-model quality gain is claimed.
- The first model experiment runs one preregistered QLoRA configuration and permits `GO / MORE-DATA / NO-GO`. Windows/macOS Agent and Rhino compatibility does not imply cross-platform local-model support; local inference is claimed only on platforms actually validated.
- P2a external-task automated evaluation is complete at 18/30 valid baseline passes; five resumed provider interruptions remain recorded. Supplemental real-Rhino topology evidence for 002/014 is complete but does not change the frozen failures or score. P2b real-user UI operation is postponed.
- The full live benchmark needs interactive Rhino and a model API; CI is offline.

More: [Architecture](docs/architecture.md) · [Training readiness](docs/training-readiness.md) · [C0 formal preregistration](docs/training-preregistration.md) · [Template](docs/training-preregistration-template.md) · [Troubleshooting](docs/troubleshooting.md) · [Roadmap](PROJECT_OPTIMIZATION_PLAN.md) · [Changelog](CHANGELOG.md)
