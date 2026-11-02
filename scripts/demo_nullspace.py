"""Run the real nullspace checker through CoreCoder with scripted tool selection."""

import argparse
import json
from pathlib import Path

from corecoder import Agent
from corecoder.demo import ScriptedLLM
from corecoder.llm import LLMResponse, ToolCall
from math_notes.algebra import NullspaceTool


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("claim", type=Path, nargs="?", default=Path("examples/math-notes/nullspace-claim.json"))
    args = parser.parse_args(argv)
    claim = json.loads(args.claim.read_text(encoding="utf-8"))
    agent = Agent(
        llm=ScriptedLLM([
            LLMResponse(tool_calls=[ToolCall(id="nullspace-1", name="check_nullspace", arguments=claim)]),
            LLMResponse(content="Calculation complete; the tool result contains the check."),
        ]),
        tools=[NullspaceTool()],
        max_rounds=2,
    )
    agent.chat("Check whether the proposed vectors form a nullspace basis.")
    tool_results = [message for message in agent.messages if message["role"] == "tool"]
    print(json.dumps({
        "controller": "ScriptedLLM",
        "api_calls": 0,
        "model_calls": sum(message["role"] == "assistant" for message in agent.messages),
        "tool_calls": len(tool_results),
        "messages": agent.messages,
        "check": json.loads(tool_results[0]["content"]),
    }, indent=2))


if __name__ == "__main__":
    main()
