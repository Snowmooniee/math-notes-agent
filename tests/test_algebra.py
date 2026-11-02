"""Exact mathematical checks and their real CoreCoder tool integration."""

import json
from pathlib import Path

import pytest

from corecoder import Agent
from corecoder.demo import ScriptedLLM
from corecoder.llm import LLMResponse, ToolCall
from math_notes.__main__ import main
from math_notes.algebra import NullspaceTool, check_nullspace
from scripts.demo_nullspace import main as demo

MATRIX = [[1, 2, 3], [2, 4, 6]]
COMPLETE_BASIS = [[-2, 1, 0], [-3, 0, 1]]


@pytest.mark.parametrize("basis", [COMPLETE_BASIS, [[-5, 1, 1], [-2, 1, 0]]])
def test_accepts_equivalent_complete_bases(basis):
    result = check_nullspace(MATRIX, basis)
    assert result["valid"] is True
    assert result["matrix_rank"] == 1 and result["nullity"] == 2
    assert result["basis_rank"] == 2
    assert result["products"] == [["0", "0"], ["0", "0"]]
    assert all(result["checks"].values())


@pytest.mark.parametrize(
    ("basis", "checks", "rank"),
    [
        ([[-2, 1, 0]], (True, True, False), 1),
        ([[-2, 1, 0], [-4, 2, 0]], (True, False, True), 1),
        ([[-2, 1, 0], [1, 0, 0]], (False, True, True), 2),
    ],
)
def test_distinguishes_membership_independence_and_dimension(basis, checks, rank):
    result = check_nullspace(MATRIX, basis)
    assert result["valid"] is False
    assert result["checks"] == dict(zip(("vectors_in_nullspace", "independent", "dimension_matches"), checks))
    assert result["basis_rank"] == rank
    if not checks[0]:
        assert result["products"][1] == ["1", "2"]


def test_full_column_rank_has_empty_nullspace_basis():
    result = check_nullspace([[1, 0], [0, 1], [1, 1]], [])
    assert result["valid"] is True
    assert result["nullity"] == 0
    assert result["reference_basis"] == result["products"] == []


def test_zero_matrix_has_full_domain_as_nullspace():
    result = check_nullspace([[0, 0], [0, 0]], [[1, 0], [0, 1]])
    assert result["valid"] is True
    assert result["matrix_rank"] == 0 and result["nullity"] == 2


def test_rational_entries_are_checked_exactly():
    result = check_nullspace([["1/3", "2/3"]], [[-1, "1/2"]])
    assert result["valid"] is True
    assert result["products"] == [["0"]]
    assert result["basis"] == [["-1", "1/2"]]
    assert result["reference_basis"] == [["-2", "1"]]


@pytest.mark.parametrize(
    ("matrix", "basis"),
    [([], []), ([[1, 2], [3]], []), ([[1, 2]], [[1]]), ([[0.1, 1]], []), ([["1/0"]], [])],
)
def test_rejects_inputs_outside_the_rational_matrix_contract(matrix, basis):
    with pytest.raises(ValueError):
        check_nullspace(matrix, basis)


def test_cli_false_claim_is_a_completed_check(tmp_path, capsys):
    claim = tmp_path / "claim.json"
    claim.write_text(json.dumps({"matrix": MATRIX, "basis": [[-2, 1, 0]]}), encoding="utf-8")
    assert main(["check-nullspace", str(claim)]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["valid"] is False and result["nullity"] == 2
    assert not captured.err


@pytest.mark.parametrize("content", ['{"matrix": [[1]]}', '{"matrix": [["1/0"]], "basis": []}'])
def test_cli_reports_uncheckable_input(tmp_path, capsys, content):
    claim = tmp_path / "claim.json"
    claim.write_text(content, encoding="utf-8")
    assert main(["check-nullspace", str(claim)]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error"]
    assert not captured.out


def test_corecoder_returns_tool_error_and_calculation_to_the_next_turn():
    agent = Agent(
        llm=ScriptedLLM([
            LLMResponse(tool_calls=[ToolCall("bad-shape", "check_nullspace", {"matrix": MATRIX, "basis": [[1]]})]),
            LLMResponse(tool_calls=[ToolCall("corrected", "check_nullspace", {"matrix": MATRIX, "basis": COMPLETE_BASIS})]),
            LLMResponse(content="The calculation is complete."),
        ]),
        tools=[NullspaceTool()],
        max_rounds=3,
    )
    assert agent.chat("Check the proposed nullspace basis.") == "The calculation is complete."
    results = [message for message in agent.messages if message["role"] == "tool"]
    assert results[0]["tool_call_id"] == "bad-shape"
    assert "Each basis vector must have 3 coordinates" in results[0]["content"]
    assert results[1]["tool_call_id"] == "corrected"
    assert json.loads(results[1]["content"])["valid"] is True


def test_scripted_demo_exposes_the_actual_tool_trace(monkeypatch, capsys):
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)
    demo([])
    result = json.loads(capsys.readouterr().out)
    assert result["controller"] == "ScriptedLLM" and result["api_calls"] == 0
    assert result["model_calls"] == 2 and result["tool_calls"] == 1
    tool_result = next(message for message in result["messages"] if message["role"] == "tool")
    assert tool_result["tool_call_id"] == "nullspace-1"
    assert json.loads(tool_result["content"]) == result["check"]
    assert result["check"]["checks"] == {
        "vectors_in_nullspace": True, "independent": True, "dimension_matches": False,
    }
