# CoreCoder baseline

Before adding tools for course notes, this records what runs in the original engine and where the evidence stops.

Starting point: [he-yufeng/CoreCoder](https://github.com/he-yufeng/CoreCoder), commit [`bd64cfe`](https://github.com/he-yufeng/CoreCoder/commit/bd64cfe7ad2789fa0ab1b3a689ad160567b5cdb0), version 0.8.0. The engine, upstream tests, project configuration and MIT license are unchanged.

## Run record

| Check | Recorded on | Result |
| --- | --- | --- |
| Upstream test suite | 2026-10-26 | 227 passed, 1 skipped, 19.56 seconds |
| Scripted tool and validation check | 2026-10-29 | Both expected outcomes confirmed |
| Directory with spaces and a single quote | 2026-10-29 | Read, edit and shell test completed |

Environment: Windows, Python 3.11.9, Git Bash. The skipped upstream test needs a real model endpoint and is opt-in. It has not been run.

[Results](../benchmarks/upstream-baseline/results.json), [upstream test output](../benchmarks/upstream-baseline/pytest.log) and the [dependency snapshot](../benchmarks/upstream-baseline/requirements.txt) are included. The full suite result is the October 26 run; the October 29 check repeats only the scripted tool path after fixing shell quoting in the helper. Neither run changed the engine.

The published text files use LF line endings. Their hashes and the original run-file hashes are recorded separately; test output and dependency versions are otherwise unchanged.

## Follow one turn

`Agent.chat` sends the conversation and tool descriptions to the model interface. Tool requests go through permission checks and then the registered Python tool. The result is added to the conversation before the next request. A text-only response ends the turn.

The [local check](../scripts/offline_baseline.py) uses the upstream `Agent`, `ReadFileTool`, `EditFileTool` and `BashTool` with `ScriptedLLM`. The responses are fixed in advance. The file operations, shell command and external assertions run for real.

The fixture starts with an intentionally incorrect `mean` function. It checks two paths:

| Path | Tool calls | External result |
| --- | --- | --- |
| Return a completion message without changing the file | 0 | Fails, as expected |
| Read the file, apply the prescribed edit, run pytest, then return a completion message | 3 | Passes five behavior checks; the shell test also passes |

Both paths end with the same completion message. The external result distinguishes them. This checks the tool wiring and validation path; it does not measure whether a model can find or fix the bug.

## Repeat locally

From a fresh checkout with Python 3.11 active and Git Bash installed, use PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r benchmarks\upstream-baseline\requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
$env:CORECODER_LIVE_SMOKE = ''
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe scripts\offline_baseline.py --out .tmp\corecoder-baseline
```

The last command should exit with code 0 and write `summary.json`, tool traces, fixture diffs and individual results. The text-only case should fail its external assertions; the tool-repair case should pass. The output directory must be new, so an existing run is never overwritten.

The dependency file records the tested Windows environment. It is not a cross-platform lockfile, and installation on a second machine has not yet been checked.

## What went wrong

In a restricted Windows process environment, Git Bash stopped at `NtCreateDirectoryObject` with exit code `3221225794`. The fixture file had been edited, so its external assertions passed, but the shell test never started. The helper correctly marked the overall run as failed. Repeating it with ordinary host permissions passed; the engine needed no patch. The failed attempt is recorded alongside the successful result.

The helper also quotes shell paths with `shlex.quote`, including directories containing spaces or apostrophes.

## Scope

No model API was called. The prescribed edits are a deterministic fixture, not a task-success benchmark. There is no measured model success rate, speedup or mathematical accuracy here. This is the local baseline for the course-note work that follows.
