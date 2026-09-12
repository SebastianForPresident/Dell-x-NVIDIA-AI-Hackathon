# GB10 runtime handoff — verified 2026-09-12

## Current carrier-registry flow

The current intake resolves insured fields through
`data/carrier_registry/insured_fields.json`. Carrier and policy records are
fictional. `FIELD-17` uses a carrier-defined DeWitt field polygon with locally
cached real NOAA NCEI, USDA NASS CDL, and Copernicus Sentinel-2 evidence.
`FIELD-KS-04` has different carrier geometry and no matching local public
evidence, so its checks return unavailable and the agent requests follow-up.
Claimed crop, cause, and narrative do not select or change either package.

The sections below preserve the chronological runtime proof, including earlier
synthetic fixture runs. They describe artifacts retained on this machine and
must not be read as the current field-resolution design. The active model route
remains OpenClaw → local Ollama → `gpt-oss:20b`, with no fallbacks or runtime
public-data downloads.

The actual React → FastAPI → OpenClaw → local Ollama → gpt-oss:20b →
validated Python tools → InvestigationService → MongoDB chain passed on this
machine. A fresh browser-driven DeWitt investigation reached
`READY_FOR_ADJUSTER_REVIEW`. All four findings are **synthetic demo measurements**;
this is evidence preparation, never a claim approval or coverage decision.

## Start and use

Ollama and MongoDB must already be running (as they are on this machine).
From the repository:

```bash
# Already installed and built on this GB10; needed for a fresh checkout only:
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci --prefix frontend
npm run build --prefix frontend

# Start the API and built React UI:
./scripts/start_demo.sh
```

Open http://127.0.0.1:8000, choose **Open demo claim**, then **Run investigation**
or **Run fresh investigation**. The browser polls persisted state every five
seconds while its POST `/api/cases/{id}/investigate` waits for the local agent.
The completed demo is already visible; the server was left running on port 8000.
Do not start a second server on that port.

CLI equivalents (each invocation without `--case` preserves history and creates
a fresh synthetic case):

```bash
.venv/bin/python -m runtime.run --first
.venv/bin/python -m runtime.run
.venv/bin/python -m runtime.run --case INVESTIGATION_ID
```

`--first` limits the task to determining whether the claimed crop is present.
All eight tools remain available; the model selects the tool. The full mode
specifies investigation goals and business gates, not a fixed tool sequence.

Canonical database defaults in the launcher:

```text
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DATABASE=crop_forensics
```

## Verified OpenClaw mechanism

Installed binary: `/home/dell/.npm-global/bin/openclaw`, version
`2026.9.4 (3a9d69d)`. Verified using `--help`, `agent --help`, installed package
documentation and actual successful execution. Documentation under
`/home/dell/.npm-global/lib/node_modules/openclaw/docs/`:

- `plugins/building-plugins.md`: manifest `contracts.tools`,
  `plugins.load.paths`, `api.registerTool({name, parameters, execute(id,args)})`.
- `providers/ollama/configuration.md`: `api: "ollama"`, native local base URL,
  no `/v1`.
- `tools/tool-search.md`: `tools.toolSearch: false` exposes the eight schemas
  directly and avoids the default deferred tool wrapper.
- `tools/plugin.md`: explicit plugin and tool allowlists.

The installed loader accepts the small ESM plugin in `runtime/openclaw`.
Registration reads schemas directly from Python's existing `TOOL_SCHEMAS`.
The fixed callback starts `.venv/bin/python -m runtime.bridge` with JSON stdin;
it never executes model-supplied commands or paths. Case/run binding comes from
trusted environment variables. `bound_tools(...).invoke(name,args,call_id)`
remains the validation, computation and audit boundary. The runtime ID prefixes
the OpenClaw call ID for case-safe retry keys. Tool results return as OpenClaw
`content` and `details`, and the model continues in the same agent turn.

The runner uses `openclaw agent --local --agent main --session-id ... --json`.
Each run has isolated configuration, workspace, SQLite state and output under
`.runtime/<run_id>/`; the operator's existing OpenClaw configuration is untouched.
No gateway daemon or adapter HTTP listener is required.

Exact model configuration:

```json
{
  "provider": "ollama",
  "baseUrl": "http://127.0.0.1:11434",
  "api": "ollama",
  "apiKey": "ollama-local",
  "model": "gpt-oss:20b",
  "contextWindow": 32768,
  "maxTokens": 4096,
  "thinking": "low",
  "fallbacks": []
}
```

The key is the documented local marker, not a cloud credential. The terminal
receipt verifies the effective model and no reroute. Only the eight application
tools are exposed; shell, Python, filesystem, web, database and decision tools
are absent. Memory search and bundled skills are disabled. A per-case file lock
prevents concurrent CLI/API agent writers. The old manual `demo-step` route is
retained for explicit deterministic debugging; React no longer calls it.
The old Qwen `ai-review` endpoint/import is inactive; historical modules remain.

## Empirical proof

See `docs/GB10_RUNTIME_PROOF.json` for the actual model request, matching tool
result, visible model continuation, Mongo evidence/action IDs, and full-run
receipt. This is exported runtime evidence, not a mocked test.

First crop milestone:

- Investigation: `a1915a6d5dcbb0f071a7dc2a25855f777df43e6e9a573a199c69478947382141`
- Run: `8a944bcff66d46f6a3488d76b2a8d0a3`
- Model call: `call_xja00otr`, `check_crop_classification`, `{}`
- Mongo evidence: `06a5fdb7f9a74bd8f25b7a6ea1fee1b2e166bf5b1b4086b9e9803ad0c78f2848`
- Mongo action: `e9c1e247b6edbfb1ef29f8c73a9eb7ef8241b118442cc50d5a61c90d3e1cc34d`
- Deterministic result: corn, CDL code 1, 25 pixels, share 1.0.
- The returned model answer explicitly used the measured 100% corn result.

Fresh **browser-initiated** full run:

- Investigation: `e3cbaee439497a44ce5b6afeb02811edd0f3595cebaa0fdc50bd075b2a5f6ef7`
- Run: `7131fe725efa45999fcb53cf7435c3fb`
- Four evidence records; seven executed tool actions plus the saved runtime receipt.
- Crop: corn, 100% of 25 sampled pixels.
- Rainfall: 30 mm vs 90 mm normal, 33.3% of normal.
- NDVI: 0.750 → 0.429 (−0.321).
- Other supplied fields: 1/1 with NDVI decline, −0.321.
- Report saved; `NEW → INVESTIGATING → READY_FOR_ADJUSTER_REVIEW`.
- Chromium clicked the actual UI button and verified the API response, four
  visible supported checks, report/audit display and no JavaScript page errors.
- Screenshot: `.runtime/browser/claim.png`; browser response and rendered text:
  `.runtime/browser/result.json`, `.runtime/browser/visible.txt`.

The model initially supplied an extra `claim_id` to `get_claim`. OpenClaw rejected
it before dispatch; the model corrected itself and completed the run. That
rejection is preserved separately from executed application audits. An earlier
full run stopped after saving the report; the final instructions explicitly
require the model to request the status transition too. No hardcoded tool calls
were added to compensate.

Read the running MongoDB and correlate OpenClaw's stored requests/results again:

```bash
.venv/bin/python -m runtime.proof 8a944bcff66d46f6a3488d76b2a8d0a3
.venv/bin/python -m runtime.proof 7131fe725efa45999fcb53cf7435c3fb
curl -s http://127.0.0.1:8000/api/cases/e3cbaee439497a44ce5b6afeb02811edd0f3595cebaa0fdc50bd075b2a5f6ef7
```

The proof exporter opens OpenClaw's installed SQLite transcript schema read-only,
checks each executed model call against its stable Mongo audit ID and returned
result, and omits reasoning blocks. `.runtime` is intentionally ignored by Git;
retain it on this demo machine if you want to re-export these specific runs.

## Validation and limits

- Linux aarch64, Python 3.12.3.
- ARM64 wheels installed without native compilation or system package changes:
  Rasterio 1.5.1 / GDAL 3.12.4, NumPy 2.5.3, PyMongo 4.18.1, FastAPI 0.141.1.
- Real MongoDB 8.0.30: admin ping `{ok: 1.0}`, evidence/report/audit queries passed.
  Docker CLI inspection required sudo credentials, but direct database validation
  succeeded and no container changes were necessary.
- `python -m unittest discover -s tests -v`: 35 tests, 33 passed, 2 obsolete
  Streamlit tests skipped. Existing GIS, business gates and persistence tests pass.
- `npm run build --prefix frontend`: passed.
- Actual Chromium ARM64 browser workflow: passed, zero page errors.
- No demo blocker. Model ordering and latency can vary; inspect persisted status
  and tool errors rather than treating a natural-language completion as a decision.
  One writer per investigation remains the supported business-service mode.
- Final upstream fetch still reports `ba8370c improved website`; no teammate
  changes were discarded. Changes are uncommitted and unpushed.

Changed files: `.gitignore`, `frontend/src/App.jsx`, `server/main.py`,
`server/integration.py`, `tests/test_ai_review.py`; added `runtime/` adapter,
runner and proof exporter, `tests/test_openclaw_runtime.py`,
`scripts/start_demo.sh`, this handoff, and the exported proof JSON.

## Live GPT-OSS briefing

The claim screen now includes an investigation briefing under GPT-OSS. The
plugin subscribes to the installed, documented
`api.runtime.events.onAgentEvent` API and forwards only public `assistant`
text events (`event.data.text`), never thinking events. Atomic, case-bound
snapshots in `.runtime/streams` feed the API's SSE endpoint
`GET /api/cases/{id}/agent-stream`. The React EventSource displays real output
increments and actual tool results; there is no simulated typing. Snapshots are
transient display data; final summaries and evidence remain persisted in MongoDB.

Verified in Chromium with fresh run `1d8982b0eb854ff6aadbbb3066274e1e`:
13 distinct partial model-text updates arrived while the run was active,
then all four evidence checks, a saved report and READY_FOR_ADJUSTER_REVIEW.
Browser errors: zero. Captured updates: `.runtime/browser/stream-updates.json`.
Updated test suite: 37 tests, 35 passed, 2 obsolete tests skipped; React build passed.

## Claim-first intake and smoother live briefing

The default flow is now New claim: farmer/name, a user-written statement,
field selection, loss date, reported cause and crop. Claim references can be
generated. `POST /api/claims` saves a NEW investigation without executing tools;
the Run investigation button starts the local model. The DeWitt field binds to
its existing local synthetic evidence bundle. An unregistered field gets no
measurements, with missing evidence handled by the existing tools/workflow gates.
`GET /api/local-fields` exposes the limited supported coverage. No arbitrary
county matching or real-data acquisition is implied.

The page no longer calls POST /api/demo on load. Existing example history is
hidden by default, preserved behind Show synthetic example history, and a new
example is created only through Try a synthetic example. Own evidence uploads
remain available under Advanced in the claim dialog.

Streaming snapshots now arrive up to every 40ms. The browser smoothly reveals
only already-received text, formats paragraphs/bold text, and keeps tool details
collapsed. The briefing is above the full action timeline. Follow-up tasks are
visible in What is still needed.

Live browser validation:
- Covered user-written claim `1ddaedee6d9ee0881fe6774359d3633b675e67516a00b3971dc1f55e94b929d0`:
  149 distinct partial text updates, four evidence checks, saved report,
  READY_FOR_ADJUSTER_REVIEW, zero browser errors.
- Unregistered-field claim `bf570639c19ba76a85aff4b8dd923a8d169841d8f015f12e15f9b53338b2647e`:
  four unavailable checks, one follow-up task, NEEDS_EVIDENCE, zero browser errors.
- Read-only page navigation did not POST/create a claim.
- 41 Python tests: 39 passed, 2 skipped. React production build passed.

Screenshots and browser results remain under `.runtime/browser/`:
`new-claim.png`, `intake-briefing.png`, `intake-result.json`, `missing-result.json`.
These explicitly named rehearsal claims are preserved as verification history.
