#!/usr/bin/env python3
"""Certified lattice residual normalization for squared affine factors."""

from __future__ import annotations

import copy
import math
from collections import defaultdict
from typing import Any


def primitive_residual(residual: dict[str, Any]) -> dict[str, Any]:
    coefficients = {
        str(name): int(value)
        for name, value in residual["coefficients"].items()
        if int(value)
    }
    if not coefficients:
        raise ValueError("a residual must contain a nonzero direction")
    weight = int(residual.get("weight", 1))
    if weight <= 0:
        raise ValueError("residual weights must be positive")

    divisor = math.gcd(*(abs(value) for value in coefficients.values()))
    first_name = min(coefficients)
    sign = -1 if coefficients[first_name] < 0 else 1
    primitive = {
        name: sign * value // divisor for name, value in coefficients.items()
    }
    return {
        "primitive": primitive,
        "scale": divisor,
        "constant": sign * int(residual.get("constant", 0)),
        "weight": weight,
    }


def moment_certificate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot normalize an empty group")
    direction = tuple(sorted(rows[0]["primitive"].items()))
    if any(tuple(sorted(row["primitive"].items())) != direction for row in rows):
        raise ValueError("all rows must share one primitive direction")

    moment_a = sum(row["weight"] * row["scale"] ** 2 for row in rows)
    moment_b = sum(row["weight"] * row["scale"] * row["constant"] for row in rows)
    moment_d = sum(row["weight"] * row["constant"] ** 2 for row in rows)
    common = math.gcd(moment_a, abs(moment_b))
    reduced_denominator = moment_a // common
    one_square_possible = moment_a % (reduced_denominator**2) == 0
    if one_square_possible:
        scale = reduced_denominator
        weight = moment_a // (scale**2)
        center = moment_b // common
        outputs = [{
            "primitive": dict(direction),
            "scale": scale,
            "constant": center,
            "weight": weight,
        }]
    else:
        lower_center, upper_weight = divmod(moment_b, moment_a)
        lower_weight = moment_a - upper_weight
        outputs = [{
            "primitive": dict(direction),
            "scale": 1,
            "constant": lower_center,
            "weight": lower_weight,
        }]
        if upper_weight:
            outputs.append({
                "primitive": dict(direction),
                "scale": 1,
                "constant": lower_center + 1,
                "weight": upper_weight,
            })
    output_second_moment = sum(
        row["weight"] * row["constant"] ** 2 for row in outputs
    )
    constant_shift = moment_d - output_second_moment
    return {
        "primitive_direction": dict(direction),
        "source": copy.deepcopy(rows),
        "A": moment_a,
        "B": moment_b,
        "D": moment_d,
        "gcd_AB": common,
        "reduced_denominator": reduced_denominator,
        "K": constant_shift,
        "outputs": outputs,
        "one_square_possible": one_square_possible,
    }


def materialize_output(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "coefficients": {
            name: row["scale"] * value for name, value in row["primitive"].items()
        },
        "constant": row["constant"],
        "weight": row["weight"],
    }


def check_certificate(certificate: dict[str, Any]) -> tuple[bool, list[str]]:
    errors = []
    source = certificate["source"]
    recomputed_a = sum(row["weight"] * row["scale"] ** 2 for row in source)
    recomputed_b = sum(row["weight"] * row["scale"] * row["constant"] for row in source)
    recomputed_d = sum(row["weight"] * row["constant"] ** 2 for row in source)
    if recomputed_a != certificate["A"]:
        errors.append("source A mismatch")
    if recomputed_b != certificate["B"]:
        errors.append("source B mismatch")
    if recomputed_d != certificate["D"]:
        errors.append("source D mismatch")

    output_a = sum(row["weight"] * row["scale"] ** 2 for row in certificate["outputs"])
    output_b = sum(
        row["weight"] * row["scale"] * row["constant"]
        for row in certificate["outputs"]
    )
    output_d = sum(row["weight"] * row["constant"] ** 2 for row in certificate["outputs"])
    if output_a != certificate["A"]:
        errors.append("output A mismatch")
    if output_b != certificate["B"]:
        errors.append("output B mismatch")
    if output_d + certificate["K"] != certificate["D"]:
        errors.append("output D+K mismatch")
    expected_denominator = certificate["A"] // math.gcd(certificate["A"], abs(certificate["B"]))
    if certificate["reduced_denominator"] != expected_denominator:
        errors.append("reduced denominator mismatch")
    expected_one = certificate["A"] % (expected_denominator**2) == 0
    if certificate["one_square_possible"] != expected_one:
        errors.append("one-square condition mismatch")
    if len(certificate["outputs"]) != (1 if expected_one else 2):
        errors.append("non-minimal output count")
    return not errors, errors


def normalize_problem(problem: dict[str, Any], mode: str = "compress") -> tuple[dict[str, Any], dict[str, Any]]:
    if mode not in {"canonical", "compress"}:
        raise ValueError(f"unknown LRN mode: {mode}")
    result = copy.deepcopy(problem)
    objective = result.setdefault("objective", {})
    objective.setdefault("terms", [])
    metadata: dict[str, Any] = {
        "mode": mode,
        "original_residuals": 0,
        "output_residuals": 0,
        "direction_groups": 0,
        "applied_groups": 0,
        "integer_center_groups": 0,
        "fractional_center_groups": 0,
        "proportional_groups": 0,
        "removed_residuals": 0,
        "negative_constant_groups": 0,
        "zero_constant_groups": 0,
        "positive_constant_groups": 0,
        "certificates": [],
    }

    for block in objective.get("factor_blocks", []) or []:
        groups: dict[tuple[tuple[str, int], ...], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
        for raw in block.get("residuals", []) or []:
            normalized = primitive_residual(raw)
            key = tuple(sorted(normalized["primitive"].items()))
            groups[key].append((copy.deepcopy(raw), normalized))
            metadata["original_residuals"] += 1

        rewritten = []
        for pairs in groups.values():
            raw_group = [pair[0] for pair in pairs]
            rows = [pair[1] for pair in pairs]
            certificate = moment_certificate(rows)
            candidate = [materialize_output(row) for row in certificate["outputs"]]
            apply = mode == "canonical" or len(candidate) < len(raw_group)
            metadata["direction_groups"] += 1
            metadata["proportional_groups"] += int(len({row["scale"] for row in rows}) > 1)
            integral_mean = certificate["B"] % certificate["A"] == 0
            metadata["integer_center_groups"] += int(integral_mean)
            metadata["fractional_center_groups"] += int(not integral_mean)
            if apply:
                rewritten.extend(copy.deepcopy(candidate))
                metadata["applied_groups"] += 1
                metadata["removed_residuals"] += len(raw_group) - len(candidate)
                metadata["certificates"].append(certificate)
                shift = certificate["K"]
                metadata["negative_constant_groups"] += int(shift < 0)
                metadata["zero_constant_groups"] += int(shift == 0)
                metadata["positive_constant_groups"] += int(shift > 0)
                if shift:
                    objective["terms"].append({"c": shift, "vars": {}})
            else:
                rewritten.extend(raw_group)
        block["residuals"] = rewritten
        metadata["output_residuals"] += len(rewritten)
    return result, metadata
