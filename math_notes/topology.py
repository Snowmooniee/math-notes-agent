"""Check finite topologies and continuous maps with explicit witnesses."""

import json
from itertools import combinations
from typing import ClassVar

from corecoder.tools.base import Tool


def _point_set(values):
    if not isinstance(values, list) or any(type(value) not in (int, str) for value in values):
        raise ValueError("Represent sets as lists of integer or string point labels.")
    return frozenset(values)


def _as_list(points):
    return sorted(points, key=lambda point: (isinstance(point, str), point))


def _check_opens(points, opens):
    if not isinstance(opens, list):
        raise TypeError("opens must be a list of sets.")
    family = tuple(dict.fromkeys(_point_set(opened) for opened in opens))
    members = set(family)
    for opened in family:
        if not opened <= points:
            return family, {"axiom": "subsets", "set": _as_list(opened), "outside_points": _as_list(opened - points)}
    for required, axiom in ((frozenset(), "empty_set"), (points, "whole_space")):
        if required not in members:
            return family, {"axiom": axiom, "missing_set": _as_list(required)}
    # The family is finite: binary union closure implies arbitrary union closure.
    for left, right in combinations(family, 2):
        for axiom, result in (("unions", left | right), ("intersections", left & right)):
            if result not in members:
                return family, {
                    "axiom": axiom, "left": _as_list(left), "right": _as_list(right), "missing_set": _as_list(result),
                }
    return family, None


def check_topology(points: list, opens: list[list]) -> dict:
    """Check a finite open-set family against the topology axioms."""
    points = _point_set(points)
    family, witness = _check_opens(points, opens)
    return {"valid": witness is None, "point_count": len(points), "open_set_count": len(family), "witness": witness}


def check_continuity(domain: dict, codomain: dict, mapping: list[list]) -> dict:
    """Check a finite map by the preimages of all codomain open sets."""
    if not isinstance(domain, dict) or not isinstance(codomain, dict):
        raise TypeError("domain and codomain must be objects containing points and opens.")
    domain_points = _point_set(domain["points"])
    codomain_points = _point_set(codomain["points"])
    image = dict(mapping)
    if (
        len(image) != len(mapping)
        or _point_set(list(image)) != domain_points
        or not _point_set(list(image.values())) <= codomain_points
    ):
        raise ValueError("mapping must give exactly one codomain image for every domain point.")

    families = {}
    missing = []
    for name, space, points in (("domain", domain, domain_points), ("codomain", codomain, codomain_points)):
        if space.get("opens") is None:
            missing.append(f"{name}.opens")
            continue
        family, witness = _check_opens(points, space["opens"])
        if witness is not None:
            return {"status": "invalid_topology", "continuous": None, "space": name, "witness": witness}
        families[name] = family
    if missing:
        return {"status": "undetermined", "continuous": None, "missing": missing}

    preimages = []
    domain_opens = set(families["domain"])
    for opened in families["codomain"]:
        preimage = frozenset(point for point in domain_points if image[point] in opened)
        preimages.append({
            "open_set": _as_list(opened), "preimage": _as_list(preimage), "open_in_domain": preimage in domain_opens,
        })
    witness = next((item for item in preimages if not item["open_in_domain"]), None)
    return {"status": "checked", "continuous": witness is None, "preimages": preimages, "witness": witness}


_POINTS = {"type": "array", "items": {"type": ["integer", "string"]}}
_OPENS = {"type": "array", "items": _POINTS}
_SPACE = {
    "type": "object",
    "properties": {"points": _POINTS, "opens": {**_OPENS, "type": ["array", "null"]}},
    "required": ["points"],
}


class TopologyTool(Tool):
    name = "check_topology"
    description = "Check whether an explicit finite open-set family is a topology. Returns a failed axiom and witness if invalid."
    parameters: ClassVar[dict] = {
        "type": "object", "properties": {"points": _POINTS, "opens": _OPENS}, "required": ["points", "opens"],
    }

    def execute(self, points: list, opens: list[list]) -> str:
        return json.dumps(check_topology(points, opens))


class ContinuityTool(Tool):
    name = "check_continuity"
    description = (
        "Check a finite map using all codomain open-set preimages. Supply domain and codomain with points and opens, "
        "and mapping as [source, image] pairs. Omit opens or use null when a topology is unknown: the result is undetermined. "
        "An invalid topology is reported separately from a discontinuous map."
    )
    parameters: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "domain": _SPACE, "codomain": _SPACE,
            "mapping": {"type": "array", "items": {**_POINTS, "minItems": 2, "maxItems": 2}},
        },
        "required": ["domain", "codomain", "mapping"],
    }

    def execute(self, domain: dict, codomain: dict, mapping: list[list]) -> str:
        return json.dumps(check_continuity(domain, codomain, mapping))
