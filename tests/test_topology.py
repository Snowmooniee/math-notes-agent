"""Check finite mathematics, CLI results and the actual CoreCoder tool loop."""

import json
from itertools import chain, combinations

import pytest

from math_notes.__main__ import main
from math_notes.topology import check_continuity, check_topology
from scripts.demo_topology import main as demo

POINTS = [1, 2, 3, 4]
T1 = {"points": POINTS, "opens": [[], [1], POINTS]}
T2 = {"points": POINTS, "opens": [[], [1], [1, 2], [1, 3], [1, 2, 3], POINTS]}
IDENTITY = [[point, point] for point in POINTS]


def test_course_topologies_and_union_counterexample():
    for space in (T1, T2):
        assert check_topology(**space)["valid"] is True
    result = check_topology(POINTS, [[], [1], [1, 2], [1, 3], POINTS])
    assert result["valid"] is False
    assert result["witness"] == {"axiom": "unions", "left": [1, 2], "right": [1, 3], "missing_set": [1, 2, 3]}


def test_intersection_counterexample():
    result = check_topology([1, 2, 3], [[], [1, 2], [2, 3], [1, 2, 3]])
    assert result["witness"] == {"axiom": "intersections", "left": [1, 2], "right": [2, 3], "missing_set": [2]}


@pytest.mark.parametrize(
    ("opens", "axiom", "missing"),
    [([[1, 2]], "empty_set", []), ([[]], "whole_space", [1, 2])],
)
def test_required_open_sets(opens, axiom, missing):
    assert check_topology([1, 2], opens)["witness"] == {"axiom": axiom, "missing_set": missing}


def test_open_sets_must_be_subsets_of_the_space():
    result = check_topology([1], [[], [1], [2]])
    assert result["valid"] is False
    assert result["witness"] == {"axiom": "subsets", "set": [2], "outside_points": [2]}


def test_pairwise_algorithm_agrees_with_all_subfamily_unions_and_intersections():
    points = frozenset([1, 2, 3])
    subsets = [frozenset(group) for size in range(4) for group in combinations(points, size)]
    optional = [part for part in subsets if part not in (frozenset(), points)]
    for mask in range(1 << len(optional)):
        family = [frozenset(), points] + [part for index, part in enumerate(optional) if mask & (1 << index)]
        selections = chain.from_iterable(combinations(family, size) for size in range(len(family) + 1))
        # Direct definition: examine every subfamily, including the empty one.
        expected = all(
            frozenset().union(*chosen) in family and points.intersection(*chosen) in family
            for chosen in selections
        )
        assert check_topology(list(points), [list(part) for part in family])["valid"] is expected


def test_identity_is_continuous_from_finer_to_coarser_topology():
    result = check_continuity(T2, T1, IDENTITY)
    assert result["status"] == "checked" and result["continuous"] is True
    assert result["preimages"] == [
        {"open_set": opened, "preimage": opened, "open_in_domain": True} for opened in T1["opens"]
    ]


def test_reverse_identity_exposes_noncontinuous_inverse():
    result = check_continuity(T1, T2, IDENTITY)
    assert result["status"] == "checked" and result["continuous"] is False
    assert result["witness"] == {"open_set": [1, 2], "preimage": [1, 2], "open_in_domain": False}


def test_many_to_one_map_uses_preimages_rather_than_images():
    domain = {"points": [1, 2, 3], "opens": [[], [1, 2, 3]]}
    codomain = {"points": ["a", "b"], "opens": [[], ["a"], ["b"], ["a", "b"]]}
    result = check_continuity(domain, codomain, [[1, "a"], [2, "a"], [3, "a"]])
    assert result["continuous"] is True
    assert result["preimages"][1]["preimage"] == [1, 2, 3]
    assert result["preimages"][2]["preimage"] == []


@pytest.mark.parametrize("codomain", [{"points": POINTS}, {"points": POINTS, "opens": None}])
def test_missing_topology_is_undetermined(codomain):
    assert check_continuity(T1, codomain, IDENTITY) == {
        "status": "undetermined", "continuous": None, "missing": ["codomain.opens"],
    }


def test_invalid_topology_is_not_a_discontinuous_map():
    invalid = {"points": POINTS, "opens": [[], [1], [1, 2], [1, 3], POINTS]}
    result = check_continuity(invalid, T1, IDENTITY)
    assert result["status"] == "invalid_topology" and result["continuous"] is None
    assert result["space"] == "domain" and result["witness"]["axiom"] == "unions"


@pytest.mark.parametrize("mapping", [IDENTITY[:-1], [[1, 1], [1, 2], [3, 3], [4, 4]], [[1, 1], [2, 2], [3, 3], [4, 5]]])
def test_mapping_must_be_a_total_function_into_the_codomain(mapping):
    with pytest.raises(ValueError, match="exactly one codomain image"):
        check_continuity(T1, T2, mapping)


def test_point_labels_can_mix_integers_and_strings():
    result = check_topology(["a", 1], [[], ["a"]])
    assert result["witness"] == {"axiom": "whole_space", "missing_set": [1, "a"]}


@pytest.mark.parametrize(
    ("command", "claim", "field", "expected"),
    [
        ("check-topology", {"points": [1, 2, 3], "opens": [[], [1], [2], [1, 2, 3]]}, "valid", False),
        ("check-continuity", {"domain": T1, "codomain": T2, "mapping": IDENTITY}, "continuous", False),
        ("check-continuity", {"domain": T1, "codomain": {"points": POINTS}, "mapping": IDENTITY}, "status", "undetermined"),
    ],
)
def test_cli_reports_mathematical_results_with_exit_zero(tmp_path, capsys, command, claim, field, expected):
    path = tmp_path / "claim.json"
    path.write_text(json.dumps(claim), encoding="utf-8")
    assert main([command, str(path)]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)[field] == expected and not output.err


def test_cli_reports_incomplete_function_input(tmp_path, capsys):
    path = tmp_path / "claim.json"
    path.write_text(json.dumps({"domain": T1, "codomain": T2, "mapping": IDENTITY[:-1]}), encoding="utf-8")
    assert main(["check-continuity", str(path)]) == 1
    output = capsys.readouterr()
    assert "exactly one codomain image" in json.loads(output.err)["error"] and not output.out


def test_scripted_corecoder_loop_executes_both_topology_tools(capsys):
    demo()
    result = json.loads(capsys.readouterr().out)
    assert result["controller"] == "ScriptedLLM" and result["api_calls"] == 0
    assert result["model_calls"] == 2 and result["tool_calls"] == 3
    assert result["results"]["topology"]["valid"] is True
    assert result["results"]["forward"]["continuous"] is True
    assert result["results"]["inverse"]["continuous"] is False
    assert result["results"]["inverse"]["witness"] == {"open_set": ["a"], "preimage": ["a"], "open_in_domain": False}
    messages = [message for message in result["messages"] if message["role"] == "tool"]
    assert [message["tool_call_id"] for message in messages] == ["topology", "forward", "inverse"]
    assert all(json.loads(message["content"]) == result["results"][message["tool_call_id"]] for message in messages)
