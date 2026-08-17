from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


BLOCK_SOURCE_USE_MODES = {"verify_before_use"}
BLOCK_LATEST_CLAIM_MODES = {"verify_before_latest_claim", "verify_before_use"}
BLOCK_FORMAL_LITERATURE_MODES = {"live_verification_with_cache"}


def default_skill_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    if (script_dir.parent / "SKILL.md").is_file():
        return script_dir.parent
    return script_dir.parent / "skills" / "yayi-dazi"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _date(value: Any, *, field: str, record_id: str, errors: list[str]) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        errors.append(f"{record_id}:{field}:invalid_date")
        return None


def _impact_modules(m10: Mapping[str, Any]) -> dict[str, list[str]]:
    impacts: dict[str, set[str]] = defaultdict(set)
    for chunk in m10.get("evidence_chunks", []):
        if not isinstance(chunk, Mapping):
            continue
        module = str(chunk.get("module", "")).strip()
        for source_ref in chunk.get("source_refs", []):
            if isinstance(source_ref, Mapping) and source_ref.get("source_id") and module:
                impacts[str(source_ref["source_id"])].add(module)
    return {source_id: sorted(modules) for source_id, modules in impacts.items()}


def _normalize_m10_sources(m10: Mapping[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    impacts = _impact_modules(m10)
    sources = m10.get("source_registry", [])
    if not isinstance(sources, list):
        errors.append("m10:source_registry:not_list")
        return []
    normalized: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, Mapping):
            errors.append("m10:source_registry:invalid_record")
            continue
        source_id = str(source.get("source_id", "")).strip()
        source_type = str(source.get("source_type", "")).strip()
        normalized.append(
            {
                **dict(source),
                "source_id": source_id,
                "impact_modules": impacts.get(source_id, ["M10"]),
                "review_interval_days": 365 if source_type == "textbook" else 90,
                "overdue_action": {
                    "edition_locked": "require_new_edition_check_before_latest_claim",
                    "edition_locked_with_terminology_note": "require_new_edition_and_terminology_check_before_latest_claim",
                    "verify_before_latest_claim": "block_latest_claim_and_affected_release",
                    "verify_before_use": "block_source_use_and_affected_release",
                    "live_verification_with_cache": "block_formal_literature_recommendation",
                }.get(str(source.get("freshness_mode", "")), "manual_review_required"),
                "registry_origin": "m10_catalog",
            }
        )
    return normalized


def _validate_source(
    source: Mapping[str, Any],
    *,
    as_of: date,
    errors: list[str],
) -> dict[str, Any]:
    source_id = str(source.get("source_id", "")).strip() or "UNNAMED_SOURCE"
    for field in ("title", "source_type", "rights", "redistribution", "review_status", "overdue_action"):
        if not str(source.get(field, "")).strip():
            errors.append(f"{source_id}:{field}:missing")
    impacts = source.get("impact_modules")
    if not isinstance(impacts, list) or not impacts or not all(str(item).strip() for item in impacts):
        errors.append(f"{source_id}:impact_modules:invalid")
    interval = source.get("review_interval_days")
    if isinstance(interval, bool) or not isinstance(interval, int) or interval <= 0:
        errors.append(f"{source_id}:review_interval_days:invalid")
        interval = None
    last_reviewed = _date(source.get("last_reviewed_on"), field="last_reviewed_on", record_id=source_id, errors=errors)
    next_review = _date(source.get("next_review_on"), field="next_review_on", record_id=source_id, errors=errors)
    if last_reviewed and next_review:
        actual_interval = (next_review - last_reviewed).days
        if actual_interval <= 0:
            errors.append(f"{source_id}:review_schedule:not_forward")
        if interval is not None and actual_interval != interval:
            errors.append(f"{source_id}:review_schedule:expected_{interval}_days_got_{actual_interval}")
    if next_review is None:
        review_state = "invalid"
    elif next_review < as_of:
        review_state = "overdue"
    elif next_review == as_of:
        review_state = "due_today"
    else:
        review_state = "current"
    return {
        "source_id": source_id,
        "title": source.get("title"),
        "source_type": source.get("source_type"),
        "registry_origin": source.get("registry_origin", "additional_register"),
        "impact_modules": list(impacts) if isinstance(impacts, list) else [],
        "last_reviewed_on": str(source.get("last_reviewed_on", "")) or None,
        "next_review_on": str(source.get("next_review_on", "")) or None,
        "review_state": review_state,
        "freshness_mode": source.get("freshness_mode"),
        "overdue_action": source.get("overdue_action"),
    }


def evaluate(*, skill_root: Path | None = None, as_of: date | None = None) -> dict[str, Any]:
    root = (skill_root or default_skill_root()).resolve()
    as_of_date = as_of or date.today()
    register_path = root / "references" / "knowledge-maintenance-register.json"
    m10_path = root / "references" / "runtime-data" / "m10_catalog.json"
    register = _load_json(register_path)
    m10 = _load_json(m10_path)
    errors: list[str] = []

    additional = register.get("additional_sources", [])
    if not isinstance(additional, list):
        errors.append("maintenance_register:additional_sources:not_list")
        additional = []
    additional_sources = [
        {**dict(item), "registry_origin": "knowledge_maintenance_register"}
        for item in additional
        if isinstance(item, Mapping)
    ]
    if len(additional_sources) != len(additional):
        errors.append("maintenance_register:additional_sources:invalid_record")

    all_sources = _normalize_m10_sources(m10, errors) + additional_sources
    source_ids = [str(item.get("source_id", "")).strip() for item in all_sources]
    duplicates = sorted(source_id for source_id, count in Counter(source_ids).items() if not source_id or count > 1)
    if duplicates:
        errors.extend(f"source_id:{source_id or 'EMPTY'}:duplicate_or_empty" for source_id in duplicates)

    source_sets = register.get("source_sets", {})
    expected_m10 = int(source_sets.get("baseline_m10_source_count", -1))
    expected_additional = int(source_sets.get("additional_source_count", -1))
    expected_total = int(source_sets.get("expected_total_source_count", -1))
    actual_m10 = len(m10.get("source_registry", [])) if isinstance(m10.get("source_registry"), list) else 0
    if actual_m10 != expected_m10:
        errors.append(f"source_count:m10:expected_{expected_m10}_got_{actual_m10}")
    if len(additional_sources) != expected_additional:
        errors.append(f"source_count:additional:expected_{expected_additional}_got_{len(additional_sources)}")
    if len(all_sources) != expected_total:
        errors.append(f"source_count:total:expected_{expected_total}_got_{len(all_sources)}")

    reviewed_sources = [_validate_source(source, as_of=as_of_date, errors=errors) for source in all_sources]

    snapshots = register.get("catalog_snapshots", [])
    if not isinstance(snapshots, list):
        errors.append("maintenance_register:catalog_snapshots:not_list")
        snapshots = []
    reviewed_snapshots: list[dict[str, Any]] = []
    for snapshot in snapshots:
        if not isinstance(snapshot, Mapping):
            errors.append("maintenance_register:catalog_snapshots:invalid_record")
            continue
        source_like = {
            "source_id": snapshot.get("snapshot_id"),
            "title": snapshot.get("title"),
            "source_type": "catalog_snapshot",
            "rights": "derived_catalog_metadata",
            "redistribution": "not_applicable",
            "review_status": "engineering_snapshot_reviewed",
            **dict(snapshot),
            "registry_origin": "catalog_snapshot",
        }
        reviewed_snapshots.append(_validate_source(source_like, as_of=as_of_date, errors=errors))

    due = [item for item in reviewed_sources + reviewed_snapshots if item["review_state"] == "due_today"]
    overdue = [item for item in reviewed_sources + reviewed_snapshots if item["review_state"] == "overdue"]
    stale = due + overdue
    source_use_blocked_ids = sorted(
        item["source_id"] for item in stale if item.get("freshness_mode") in BLOCK_SOURCE_USE_MODES
    )
    latest_claim_blocked_ids = sorted(
        item["source_id"] for item in stale if item.get("freshness_mode") in BLOCK_LATEST_CLAIM_MODES
    )
    formal_literature_blocked_ids = sorted(
        item["source_id"] for item in stale if item.get("freshness_mode") in BLOCK_FORMAL_LITERATURE_MODES
    )
    release_blocked = bool(errors or stale)
    state_counts = Counter(item["review_state"] for item in reviewed_sources + reviewed_snapshots)
    next_dates = sorted(
        str(item["next_review_on"])
        for item in reviewed_sources + reviewed_snapshots
        if item["review_state"] == "current" and item.get("next_review_on")
    )
    status = "invalid_register" if errors else "review_required" if stale else "current"
    return {
        "schema_version": "yayi-dazi.knowledge-lifecycle-audit.v1",
        "as_of": as_of_date.isoformat(),
        "status": status,
        "release_version": register.get("release_baseline", {}).get("skill_release_version"),
        "source_count": len(reviewed_sources),
        "catalog_snapshot_count": len(reviewed_snapshots),
        "review_state_counts": dict(sorted(state_counts.items())),
        "next_review_on": next_dates[0] if next_dates else None,
        "due_ids": sorted(item["source_id"] for item in due),
        "overdue_ids": sorted(item["source_id"] for item in overdue),
        "source_use_blocked_ids": source_use_blocked_ids,
        "latest_claim_blocked_ids": latest_claim_blocked_ids,
        "formal_literature_recommendation_blocked_ids": formal_literature_blocked_ids,
        "release_blocked_by_maintenance": release_blocked,
        "register_errors": sorted(errors),
        "minimum_incremental_cases": register.get("minimum_incremental_cases"),
        "professional_or_clinical_validation_completed": False,
        "production_enabled": False,
        "records": reviewed_sources,
        "catalog_snapshots": reviewed_snapshots,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit yayi-dazi knowledge review dates and release gates")
    parser.add_argument("--skill-root", type=Path, default=None)
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--include-records", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate(skill_root=args.skill_root, as_of=args.as_of)
    printable = result if args.include_records else {
        key: value for key, value in result.items() if key not in {"records", "catalog_snapshots"}
    }
    rendered = json.dumps(printable, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "current" else 1


if __name__ == "__main__":
    raise SystemExit(main())
