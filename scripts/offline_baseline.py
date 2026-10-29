"""Check the evaluation path with upstream tools and scripted responses, never an API.

Run from the repository root: .venv/Scripts/python scripts/offline_baseline.py --out <new-directory>
This is a synthetic development fixture, not an LLM benchmark or a security sandbox.
"""

import argparse
import difflib
import json
import platform
import shlex
import subprocess
import sys
import time
from pathlib import Path

from corecoder import Agent, checkpoints
from corecoder.demo import ScriptedLLM
from corecoder.llm import LLMResponse, ToolCall
from corecoder.permissions import Permission
from corecoder.tools.bash import BashTool, set_tracked_cwd
from corecoder.tools.edit import EditFileTool
from corecoder.tools.read import ReadFileTool

BEFORE = "def mean(values):\n    return sum(values) / (len(values) + 1)\n"
AFTER = (
    "def mean(values):\n"
    "    if not values:\n"
    "        raise ValueError('empty input')\n"
    "    return sum(values) / len(values)\n"
)
GRADER = """
import runpy, sys
mean = runpy.run_path(sys.argv[1])['mean']
for values, expected in [([2, 4], 3), ([7], 7), ([-2, 2], 0), ([0, 0], 0)]:
    assert mean(values) == expected, (values, mean(values), expected)
try:
    mean([])
except ValueError:
    pass
else:
    raise AssertionError('empty input must raise ValueError')
print('external validation: 5 checks passed')
"""


def run_case(out: Path, repair: bool) -> dict:
    out.mkdir()
    workspace = out / "workspace"
    workspace.mkdir()
    source = workspace / "stats.py"
    source.write_text(BEFORE, encoding="utf-8")
    (workspace / "test_stats.py").write_text(
        "from stats import mean\ndef test_mean():\n    assert mean([2, 4]) == 3\n",
        encoding="utf-8",
    )
    command = (
        f"cd {shlex.quote(workspace.as_posix())} && "
        f"{shlex.quote(Path(sys.executable).as_posix())} -m pytest test_stats.py -q"
    )
    turns = []
    if repair:
        for index, (name, arguments) in enumerate([
            ("read_file", {"file_path": str(source)}),
            ("edit_file", {"file_path": str(source), "old_string": BEFORE, "new_string": AFTER}),
            ("bash", {"command": command, "timeout": 15}),
        ]):
            turns.append(LLMResponse(tool_calls=[ToolCall(id=f"c{index}", name=name, arguments=arguments)]))
    turns.append(LLMResponse(content="The task is complete."))
    # Do not load user config, keys, hooks, MCP servers, permissions, or checkpoints.
    checkpoints.CHECKPOINTS_FILE = out / "checkpoints.json"
    checkpoints.clear()
    set_tracked_cwd(None)
    agent = Agent(
        llm=ScriptedLLM(turns), tools=[ReadFileTool(), EditFileTool(), BashTool()],
        permission=Permission(allow_all=True), max_rounds=6,
    )
    started = time.perf_counter()
    reply = agent.chat("Fix mean for non-empty numeric lists; empty input must raise ValueError. Run the visible test.")
    # The external grader is not supplied in the model's prompt or tool schema.
    # It lives outside the task workspace. This location alone is not isolation.
    grade = subprocess.run(
        [sys.executable, "-I", "-c", GRADER, str(source)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    observations = [m["content"] for m in agent.messages if m["role"] == "tool"]
    tool_chain_ok = (
        len(observations) == 3 and observations[0].startswith("1\tdef mean")
        and observations[1].startswith("Edited ") and "1 passed" in observations[2]
        and "[exit code:" not in observations[2] and not observations[2].startswith("Error")
    )
    result = {
        "case": out.name, "scripted": True, "reply": reply,
        "validation_exit_code": grade.returncode, "validated_success": grade.returncode == 0,
        "validation_stdout": grade.stdout, "validation_stderr": grade.stderr,
        "elapsed_seconds_including_validation": time.perf_counter() - started,
        "tool_calls": len(observations), "tool_chain_ok": tool_chain_ok,
        "tokens": None, "api_calls": 0, "api_cost_usd": 0,
    }
    (out / "trace.json").write_text(json.dumps(agent.messages, indent=2), encoding="utf-8")
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (out / "change.diff").write_text("".join(difflib.unified_diff(
        BEFORE.splitlines(True), source.read_text(encoding="utf-8").splitlines(True),
        fromfile="before/stats.py", tofile="after/stats.py",
    )), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New directory; existing evidence is never overwritten")
    out = parser.parse_args().out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cases = [run_case(out / "text_only", False), run_case(out / "tool_repair", True)]
    checks_passed = (
        not cases[0]["validated_success"] and cases[0]["tool_calls"] == 0
        and cases[1]["validated_success"] and cases[1]["tool_calls"] == 3
        and cases[1]["tool_chain_ok"]
    )
    summary = {
        "scope": "scripted development smoke only; no measured LLM success rate or improvement",
        "python": sys.version, "platform": platform.platform(), "cases": cases,
        "checks_passed": checks_passed,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if checks_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
