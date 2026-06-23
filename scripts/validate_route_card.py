#!/usr/bin/env python3
"""Validate one Rethlas route_card.json against the route-card schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route_card", type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "agents"
        / "generation"
        / "schemas"
        / "route_card.schema.json",
    )
    parser.add_argument("--write-report", type=Path, default=None)
    return parser.parse_args()


def load_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # noqa: BLE001 - command-line diagnostic.
        return None, str(exc)


def validate_with_jsonschema(card: Any, schema: dict[str, Any]) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
    except Exception as exc:  # noqa: BLE001 - fall back below if unavailable.
        return [f"jsonschema_unavailable: {exc}"]

    validator = Draft202012Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(card), key=lambda item: list(item.path)):
        loc = ".".join(str(part) for part in err.path) or "<root>"
        errors.append(f"{loc}: {err.message}")
    return errors


def fallback_validate(card: Any) -> list[str]:
    if not isinstance(card, dict):
        return ["<root>: route card must be a JSON object"]
    try:
        from triage_route_cards import validate_card
    except Exception as exc:  # noqa: BLE001 - no better local fallback.
        return [f"fallback_validator_unavailable: {exc}"]
    return validate_card(card)


def main() -> int:
    args = parse_args()
    card, card_err = load_json(args.route_card)
    schema, schema_err = load_json(args.schema)

    errors: list[str] = []
    if card_err:
        errors.append(f"card_parse_error: {card_err}")
    if schema_err:
        errors.append(f"schema_parse_error: {schema_err}")

    if not errors:
        assert card is not None
        if isinstance(schema, dict):
            errors = validate_with_jsonschema(card, schema)
            if errors and errors[0].startswith("jsonschema_unavailable:"):
                errors = fallback_validate(card)
        else:
            errors = ["schema must be a JSON object"]

    report = {
        "route_card": str(args.route_card),
        "schema": str(args.schema),
        "valid": not errors,
        "errors": errors,
    }
    if args.write_report is not None:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if errors:
        print(f"invalid route card: {args.route_card}")
        for err in errors:
            print(f"- {err}")
        return 1

    print(f"valid route card: {args.route_card}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
