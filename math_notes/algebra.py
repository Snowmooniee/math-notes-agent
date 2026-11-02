"""Check nullspace basis claims with exact rational arithmetic."""

import json
from fractions import Fraction
from typing import ClassVar

from sympy import Matrix, Rational, zeros

from corecoder.tools.base import Tool


def _rational(value):
    if type(value) not in (int, str):
        raise ValueError("Use integers or rational strings such as '1/2'.")
    try:
        number = Fraction(value)
    except ZeroDivisionError as error:
        raise ValueError("A rational number cannot have a zero denominator.") from error
    return Rational(number.numerator, number.denominator)


def check_nullspace(matrix: list[list], basis: list[list]) -> dict:
    """Check Av=0, independence and basis size; each supplied vector is a column."""
    if not isinstance(matrix, list) or not matrix or any(not isinstance(row, list) or not row for row in matrix):
        raise ValueError("matrix must be a non-empty list of non-empty rows.")
    a = Matrix([[_rational(value) for value in row] for row in matrix])
    if not isinstance(basis, list) or any(not isinstance(vector, list) or len(vector) != a.cols for vector in basis):
        raise ValueError(f"Each basis vector must have {a.cols} coordinates.")
    vectors = [Matrix([_rational(value) for value in vector]) for vector in basis]
    products = [a * vector for vector in vectors]
    candidates = Matrix.hstack(*vectors) if vectors else zeros(a.cols, 0)
    matrix_rank = a.rank()
    nullity = a.cols - matrix_rank
    basis_rank = candidates.rank()
    checks = {
        "vectors_in_nullspace": all(product == zeros(a.rows, 1) for product in products),
        "independent": basis_rank == len(vectors),
        "dimension_matches": len(vectors) == nullity,
    }
    return {
        "valid": all(checks.values()),
        "matrix": [[str(value) for value in row] for row in a.tolist()],
        "basis": [[str(value) for value in vector] for vector in vectors],
        "matrix_rank": matrix_rank,
        "nullity": nullity,
        "basis_rank": basis_rank,
        "products": [[str(value) for value in product] for product in products],
        "checks": checks,
        "reference_basis": [[str(value) for value in vector] for vector in a.nullspace()],
    }


_VECTORS = {"type": "array", "items": {"type": "array", "items": {"type": ["integer", "string"]}}}


class NullspaceTool(Tool):
    name = "check_nullspace"
    description = (
        "Check whether supplied vectors form a basis of a rational matrix's nullspace. "
        "Returns matrix-vector products, independence, nullity and a reference basis. "
        "Use integer entries or rational strings such as '1/2'; each basis vector is one list."
    )
    parameters: ClassVar[dict] = {
        "type": "object",
        "properties": {"matrix": _VECTORS, "basis": _VECTORS},
        "required": ["matrix", "basis"],
    }

    def execute(self, matrix: list[list], basis: list[list]) -> str:
        return json.dumps(check_nullspace(matrix, basis))
