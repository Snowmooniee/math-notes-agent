"""Run a two-point topology example through CoreCoder with scripted tool requests."""

import json
from pathlib import Path

from corecoder import Agent
from corecoder.demo import ScriptedLLM
from corecoder.llm import LLMResponse, ToolCall
from math_notes.topology import ContinuityTool, TopologyTool


def main():
    example = Path(__file__).resolve().parent.parent / "examples/math-notes/continuity-claim.json"
    forward = json.loads(example.read_text(encoding="utf-8"))
    inverse = {
        "domain": forward["codomain"], "codomain": forward["domain"],
        "mapping": [[target, source] for source, target in forward["mapping"]],
    }
    agent = Agent(
        llm=ScriptedLLM([
            LLMResponse(tool_calls=[
                ToolCall("topology", "check_topology", forward["domain"]),
                ToolCall("forward", "check_continuity", forward),
                ToolCall("inverse", "check_continuity", inverse),
            ]),
            LLMResponse(content="Checks complete; inspect the tool results for the forward and inverse maps."),
        ]),
        tools=[TopologyTool(), ContinuityTool()],
        max_rounds=2,
    )
    agent.chat("Check the finite topology and continuity of this bijection and its inverse.")
    results = {message["tool_call_id"]: json.loads(message["content"]) for message in agent.messages if message["role"] == "tool"}
    print(json.dumps({
        "controller": "ScriptedLLM", "api_calls": 0,
        "model_calls": sum(message["role"] == "assistant" for message in agent.messages),
        "tool_calls": len(results), "results": results, "messages": agent.messages,
    }, indent=2))


if __name__ == "__main__":
    main()
