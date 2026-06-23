#!/usr/bin/env python3
"""Validate and triage Rethlas discovery route cards."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


STAGES = {
    "planar_lattice_baseline",
    "planar_incidence_or_product",
    "equal_length_source_bottleneck",
    "hidden_coordinate_needed",
    "hidden_coordinate_projection",
    "hidden_coordinate_framework_found",
    "source_entropy_needed",
    "sparse_source_failed",
    "fixed_degree_source_failed",
    "denominator_cost_obstruction",
    "growing_degree_arithmetic_needed",
    "number_field_source_needed",
    "number_field_source_candidate",
    "number_field_source_identified",
    "relative_norm_one_source",
    "host_sign_bottleneck",
    "regulator_shape_needed",
    "product_window_needed",
    "projection_collision_needed",
    "parameter_assembly_ready",
    "complete_candidate",
    "no_progress",
}

DISCOVERY_MODES = {
    "general",
    "unit_distance_transition",
    "hidden_coordinate_bridge",
    "source_family",
    "number_field_focus",
    "parameter_assembly",
}

REQUIRED_TOP = {
    "problem_id",
    "attempt_id",
    "discovery_mode",
    "stage",
    "construction_family",
    "positive_reduction",
    "missing_object",
    "cost_formula",
    "failed_because",
    "next_stage",
    "next_source_families",
    "confidence",
}

REQUIRED_COST = {
    "point_count",
    "displacement_count",
    "edge_count",
    "height_or_denominator_cost",
    "projection_or_collision_cost",
    "exponent_gap",
}

STAGE_SCORE = {
    "complete_candidate": 100,
    "parameter_assembly_ready": 85,
    "projection_collision_needed": 84,
    "product_window_needed": 83,
    "regulator_shape_needed": 82,
    "host_sign_bottleneck": 81,
    "relative_norm_one_source": 80,
    "number_field_source_identified": 78,
    "number_field_source_needed": 70,
    "number_field_source_candidate": 66,
    "growing_degree_arithmetic_needed": 56,
    "denominator_cost_obstruction": 54,
    "fixed_degree_source_failed": 52,
    "source_entropy_needed": 48,
    "hidden_coordinate_framework_found": 42,
    "hidden_coordinate_projection": 38,
    "hidden_coordinate_needed": 34,
    "equal_length_source_bottleneck": 32,
    "sparse_source_failed": 28,
    "planar_incidence_or_product": 22,
    "planar_lattice_baseline": 10,
    "no_progress": 0,
}

NUMBER_FIELD_WORDS = {
    "number field",
    "number-field",
    "cm",
    "minkowski",
    "ideal",
    "fractional ideal",
    "class group",
    "split prime",
    "prime ideal",
    "norm-one",
    "norm one",
    "relative norm",
    "s-unit",
    "s unit",
    "torus",
    "unit group",
    "minkowski embedding",
    "dirichlet unit",
    "regulator",
    "conjugation",
    "root discriminant",
}

TRANSITION_WORDS = {
    "same-length",
    "same length",
    "equal-length",
    "equal length",
    "unit-modulus",
    "unit modulus",
    "hidden coordinate",
    "hidden-coordinate",
    "product window",
    "source entropy",
    "fixed rank",
    "fixed-rank",
    "fixed degree",
    "fixed-degree",
    "denominator",
    "height cost",
    "covolume",
    "collision",
    "exponent gap",
}

SPARSE_FAILED_FAMILIES = {"rational", "fixed-rank", "fixed rank", "cyclotomic"}

NUMBER_THEORY_STAGES = {
    "growing_degree_arithmetic_needed",
    "number_field_source_needed",
    "number_field_source_candidate",
    "number_field_source_identified",
    "relative_norm_one_source",
    "host_sign_bottleneck",
    "regulator_shape_needed",
    "product_window_needed",
    "projection_collision_needed",
}

DEEP_NUMBER_FIELD_STAGES = {
    "number_field_source_identified",
    "relative_norm_one_source",
    "host_sign_bottleneck",
    "regulator_shape_needed",
    "product_window_needed",
    "projection_collision_needed",
}

SOURCE_TRANSITION_STAGES = {
    "equal_length_source_bottleneck",
    "source_entropy_needed",
    "sparse_source_failed",
    "fixed_degree_source_failed",
    "denominator_cost_obstruction",
    "growing_degree_arithmetic_needed",
    "number_field_source_needed",
    "number_field_source_candidate",
}

TRANSITION_SIGNAL_SCORE = {
    "planar_audit": 4,
    "equal_length_bottleneck": 8,
    "hidden_coordinate_bridge": 10,
    "source_entropy_bottleneck": 12,
    "fixed_degree_failed": 14,
    "growing_degree_arithmetic": 16,
    "number_field_source_needed": 20,
    "relative_norm_one_source": 24,
    "parameter_assembly": 28,
}

UNIT_DISTANCE_SIGNAL_WEIGHTS = {
    "planar_baseline_audited": 3,
    "equal_length_bottleneck": 6,
    "denominator_or_height_obstruction": 5,
    "hidden_coordinate_move": 6,
    "source_entropy_needed": 6,
    "fixed_degree_or_rank_failed": 7,
    "growing_degree_move": 8,
    "number_field_candidate": 9,
    "relative_norm_or_unit_source": 12,
    "quantitative_slots_filled": 8,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "batch_result_dir",
        type=Path,
        help="Directory containing sample_*/route_card.json files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for triage outputs. Defaults to batch_result_dir.",
    )
    parser.add_argument(
        "--fail-on-invalid",
        action="store_true",
        help="Exit nonzero if any route card is invalid.",
    )
    return parser.parse_args()


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report exact parse failure.
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "route card must be a JSON object"
    return data, None


def validate_card(card: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_TOP - set(card))
    if missing:
        errors.append(f"missing required top-level fields: {', '.join(missing)}")

    stage = card.get("stage")
    if stage not in STAGES:
        errors.append(f"invalid stage: {stage!r}")

    mode = card.get("discovery_mode")
    if mode not in DISCOVERY_MODES:
        errors.append(f"invalid discovery_mode: {mode!r}")

    cost = card.get("cost_formula")
    if not isinstance(cost, dict):
        errors.append("cost_formula must be an object")
    else:
        missing_cost = sorted(REQUIRED_COST - set(cost))
        if missing_cost:
            errors.append(f"missing cost_formula fields: {', '.join(missing_cost)}")

    families = card.get("next_source_families")
    if not isinstance(families, list) or not all(isinstance(x, str) for x in families):
        errors.append("next_source_families must be an array of strings")

    confidence = card.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        errors.append("confidence must be a number in [0, 1]")

    transition_signal = card.get("transition_signal")
    allowed_transition_signals = set(TRANSITION_SIGNAL_SCORE) | {"none"}
    if transition_signal is not None and transition_signal not in allowed_transition_signals:
        errors.append(f"invalid transition_signal: {transition_signal!r}")

    unit_distance_signals = card.get("unit_distance_signals")
    if unit_distance_signals is not None and not isinstance(unit_distance_signals, dict):
        errors.append("unit_distance_signals must be an object when present")

    stage_evidence = card.get("stage_evidence")
    if stage_evidence is not None and (
        not isinstance(stage_evidence, list)
        or not all(isinstance(item, str) for item in stage_evidence)
    ):
        errors.append("stage_evidence must be an array of strings when present")

    return errors


def card_text(card: dict[str, Any]) -> str:
    pieces = [
        str(card.get("stage", "")),
        str(card.get("construction_family", "")),
        str(card.get("missing_object", "")),
        str(card.get("failed_because", "")),
        str(card.get("next_stage", "")),
        " ".join(str(x) for x in card.get("next_source_families", []) if isinstance(x, str)),
    ]
    cost = card.get("cost_formula")
    if isinstance(cost, dict):
        pieces.extend(str(v) for v in cost.values())
    transition_signal = card.get("transition_signal")
    if transition_signal is not None:
        pieces.append(str(transition_signal))
    signals = card.get("unit_distance_signals")
    if isinstance(signals, dict):
        pieces.extend(f"{key}={value}" for key, value in signals.items())
    evidence = card.get("stage_evidence")
    if isinstance(evidence, list):
        pieces.extend(str(item) for item in evidence)
    return " ".join(pieces).lower()


def truthy_signal(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, (int, float)) and value > 0:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "present"}
    return False


def transition_evidence_score(card: dict[str, Any]) -> float:
    score = float(TRANSITION_SIGNAL_SCORE.get(str(card.get("transition_signal")), 0))
    signals = card.get("unit_distance_signals")
    if isinstance(signals, dict):
        for key, weight in UNIT_DISTANCE_SIGNAL_WEIGHTS.items():
            if truthy_signal(signals.get(key)):
                score += float(weight)

    evidence = card.get("stage_evidence")
    if isinstance(evidence, list):
        nonempty = [str(item).strip() for item in evidence if str(item).strip()]
        score += min(8.0, 2.0 * len(nonempty))

    text = card_text(card)
    if any(word in text for word in TRANSITION_WORDS):
        score += 4.0

    cost = card.get("cost_formula")
    if isinstance(cost, dict):
        for key in ("source_entropy", "realization_cost", "fixed_exponent_margin"):
            if str(cost.get(key, "")).strip():
                score += 2.0

    return score


def is_number_theory_card(card: dict[str, Any]) -> bool:
    stage = str(card.get("stage"))
    if stage in NUMBER_THEORY_STAGES:
        return True
    signals = card.get("unit_distance_signals")
    if isinstance(signals, dict) and (
        truthy_signal(signals.get("number_field_candidate"))
        or truthy_signal(signals.get("relative_norm_or_unit_source"))
        or truthy_signal(signals.get("growing_degree_move"))
    ):
        return True
    text = card_text(card)
    return any(word in text for word in NUMBER_FIELD_WORDS)


def is_evidence_backed_number_theory_card(card: dict[str, Any]) -> bool:
    stage = str(card.get("stage"))
    if stage in DEEP_NUMBER_FIELD_STAGES:
        return True
    if not is_number_theory_card(card):
        return False
    if transition_evidence_score(card) >= 24.0:
        return True
    signals = card.get("unit_distance_signals")
    if isinstance(signals, dict):
        return (
            truthy_signal(signals.get("equal_length_bottleneck"))
            and truthy_signal(signals.get("fixed_degree_or_rank_failed"))
            and (
                truthy_signal(signals.get("growing_degree_move"))
                or truthy_signal(signals.get("number_field_candidate"))
            )
        )
    return False


def score_card(card: dict[str, Any]) -> float:
    score = float(STAGE_SCORE.get(str(card.get("stage")), 0))
    confidence = card.get("confidence")
    if isinstance(confidence, (int, float)):
        score += 10.0 * float(confidence)
    score += transition_evidence_score(card)
    text = card_text(card)
    if any(word in text for word in NUMBER_FIELD_WORDS):
        score += 12.0
    scores = card.get("scores")
    if isinstance(scores, dict):
        for key in ("source_entropy_score", "exponent_surplus", "novelty_score"):
            value = scores.get(key)
            if isinstance(value, (int, float)):
                score += float(value)
    return score


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def promotion_decision(cards: list[dict[str, Any]]) -> dict[str, Any]:
    stage_counts = Counter(str(card.get("stage")) for card in cards)
    all_text = " ".join(card_text(card) for card in cards)
    number_field_cards = [card for card in cards if is_number_theory_card(card)]
    evidence_backed_number_field_cards = [
        card for card in number_field_cards if is_evidence_backed_number_theory_card(card)
    ]
    transition_cards = [
        card
        for card in cards
        if str(card.get("stage")) in SOURCE_TRANSITION_STAGES
        or transition_evidence_score(card) >= 18.0
    ]
    best_number_field_score = max((score_card(card) for card in number_field_cards), default=0.0)
    best_transition_score = max((transition_evidence_score(card) for card in cards), default=0.0)

    source_bottleneck_count = (
        stage_counts["equal_length_source_bottleneck"]
        + stage_counts["source_entropy_needed"]
        + stage_counts["sparse_source_failed"]
    )
    growing_degree_count = (
        stage_counts["fixed_degree_source_failed"]
        + stage_counts["denominator_cost_obstruction"]
        + stage_counts["growing_degree_arithmetic_needed"]
        + stage_counts["number_field_source_needed"]
    )

    reasons: list[str] = []
    action = "continue_general_discovery"

    if stage_counts["complete_candidate"] > 0:
        action = "launch_verification_and_repair"
        reasons.append("at least one route card claims a complete candidate")
    elif stage_counts["parameter_assembly_ready"] > 0:
        action = "launch_parameter_assembly_repair"
        reasons.append("at least one route card reached parameter assembly")
    elif any(stage_counts[stage] > 0 for stage in DEEP_NUMBER_FIELD_STAGES):
        action = "launch_number_field_source_repair"
        reasons.append("a card reached an explicit number-field/source-lemma bottleneck")
    elif len(evidence_backed_number_field_cards) >= 2:
        action = "launch_number_field_source_repair"
        reasons.append("multiple cards give evidence-backed arithmetic promotion signals")
    elif stage_counts["number_field_source_needed"] > 0 and best_transition_score >= 24.0:
        action = "launch_number_field_source_repair"
        reasons.append(
            "a card says a number-field source is needed and fills the transition evidence"
        )
    elif best_number_field_score >= 86.0 and evidence_backed_number_field_cards:
        action = "launch_number_field_source_repair"
        reasons.append(
            f"one evidence-backed arithmetic candidate reached score {best_number_field_score:.1f}"
        )
    elif growing_degree_count >= 2:
        action = "launch_growing_degree_arithmetic_discovery"
        reasons.append("multiple cards found fixed-rank/denominator obstructions requiring growing degree")
    elif stage_counts["source_entropy_needed"] >= 3:
        action = "launch_source_family_discovery"
        reasons.append("at least three cards reached source-entropy bottleneck")
    elif source_bottleneck_count >= 3:
        action = "launch_source_family_discovery"
        reasons.append("at least three cards expose an equal-length or source-entropy bottleneck")
    elif (
        stage_counts["sparse_source_failed"] >= 2
        and any(family in all_text for family in SPARSE_FAILED_FAMILIES)
    ):
        action = "launch_growing_degree_arithmetic_discovery"
        reasons.append("multiple sparse-source failures mention rational/fixed-rank/cyclotomic families")
    elif stage_counts["hidden_coordinate_needed"] >= 3:
        action = "launch_hidden_coordinate_bridge"
        reasons.append("at least three cards ask for a hidden-coordinate bridge")
    else:
        reasons.append("no promotion threshold met")

    return {
        "action": action,
        "reasons": reasons,
        "stage_counts": dict(sorted(stage_counts.items())),
        "number_field_card_count": len(number_field_cards),
        "evidence_backed_number_field_card_count": len(evidence_backed_number_field_cards),
        "transition_card_count": len(transition_cards),
        "best_number_field_score": best_number_field_score,
        "best_transition_evidence_score": best_transition_score,
    }


def write_report(
    output_dir: Path,
    batch_dir: Path,
    valid: list[tuple[Path, dict[str, Any], float]],
    invalid: list[tuple[Path, str]],
    decision: dict[str, Any],
) -> None:
    stage_counts = Counter(str(card.get("stage")) for _, card, _ in valid)
    transition_counts = Counter(
        str(card.get("transition_signal", "")).strip() for _, card, _ in valid
    )
    family_counts = Counter(str(card.get("construction_family", "")).strip() for _, card, _ in valid)
    missing_counts = Counter(str(card.get("missing_object", "")).strip() for _, card, _ in valid)
    top = sorted(valid, key=lambda item: item[2], reverse=True)[:10]

    lines: list[str] = [
        "# Route Card Triage Report",
        "",
        f"Batch result dir: `{batch_dir}`",
        f"Valid route cards: {len(valid)}",
        f"Invalid route cards: {len(invalid)}",
        "",
        "## Promotion Decision",
        "",
        f"Action: `{decision['action']}`",
        "",
    ]
    for reason in decision["reasons"]:
        lines.append(f"- {reason}")

    lines.extend(["", "## Stage Counts", ""])
    for stage, count in sorted(stage_counts.items()):
        lines.append(f"- `{stage}`: {count}")

    lines.extend(["", "## Top Route Cards", ""])
    for path, card, score in top:
        lines.append(
            f"- score={score:.1f} `{relative(path, batch_dir)}` "
            f"stage=`{card.get('stage')}` "
            f"transition_score={transition_evidence_score(card):.1f} "
            f"transition=`{card.get('transition_signal', '')}` "
            f"family={card.get('construction_family')!r}"
        )
        missing = str(card.get("missing_object", "")).strip()
        if missing:
            lines.append(f"  missing: {missing}")

    lines.extend(["", "## Transition Signals", ""])
    for item, count in transition_counts.most_common(10):
        if item:
            lines.append(f"- `{item}`: {count}")

    lines.extend(["", "## Common Missing Objects", ""])
    for item, count in missing_counts.most_common(10):
        if item:
            lines.append(f"- {count} x {item}")

    lines.extend(["", "## Construction Families", ""])
    for item, count in family_counts.most_common(10):
        if item:
            lines.append(f"- {count} x {item}")

    if invalid:
        lines.extend(["", "## Invalid Cards", ""])
        for path, error in invalid:
            lines.append(f"- `{relative(path, batch_dir)}`: {error}")

    (output_dir / "triage_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / "stage_counts.json").write_text(
        json.dumps(dict(sorted(stage_counts.items())), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "promotion_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    batch_dir = args.batch_result_dir.resolve()
    output_dir = (args.output_dir or args.batch_result_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    card_paths = sorted(batch_dir.glob("**/route_card.json"))
    valid: list[tuple[Path, dict[str, Any], float]] = []
    invalid: list[tuple[Path, str]] = []

    for path in card_paths:
        card, parse_error = load_json(path)
        if parse_error is not None or card is None:
            invalid.append((path, parse_error or "unknown parse error"))
            continue
        errors = validate_card(card)
        if errors:
            invalid.append((path, "; ".join(errors)))
            continue
        valid.append((path, card, score_card(card)))

    decision = promotion_decision([card for _, card, _ in valid])
    write_report(output_dir, batch_dir, valid, invalid, decision)

    print(f"valid_cards={len(valid)}")
    print(f"invalid_cards={len(invalid)}")
    print(f"promotion_action={decision['action']}")
    print(f"triage_report={output_dir / 'triage_report.md'}")

    if args.fail_on_invalid and invalid:
        return 1
    if not valid:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
