from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


DEPLOYMENT_MODES = {"personal_local", "public_demo", "public_or_institution"}
DATA_MODES = {"fictional", "real_text", "real_photo"}
KNOWN_PROCESSING_LOCATIONS = {"known_domestic", "known_cross_border"}
KNOWN_CROSS_BORDER_STATES = {"not_involved", "involved_assessment_complete"}
KNOWN_DELETION_CAPABILITIES = {"host_managed", "deployer_available"}


class DataGovernanceContractError(ValueError):
    """Raised when a data-governance gate receives an unsupported value."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _append_once(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _valid_consent_timestamp(value: Any) -> bool:
    text = _text(value)
    if not text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def evaluate_data_processing_gate(
    record: Mapping[str, Any] | None,
    *,
    deployment_mode: str | None = None,
    data_mode: str | None = None,
) -> dict[str, Any]:
    """Return a minimal, non-identifying gate decision before processing user data.

    The result records engineering preconditions only. It does not determine whether a
    consent record is legally valid or whether a deployment is legally compliant.
    """

    payload = dict(record or {})
    deployment = _text(deployment_mode or payload.get("deployment_mode") or "personal_local")
    data_kind = _text(data_mode or payload.get("data_mode") or "fictional")
    if deployment not in DEPLOYMENT_MODES:
        raise DataGovernanceContractError(f"unsupported deployment_mode: {deployment}")
    if data_kind not in DATA_MODES:
        raise DataGovernanceContractError(f"unsupported data_mode: {data_kind}")

    blockers: list[str] = []
    warnings: list[str] = []
    is_real = data_kind != "fictional"
    is_photo = data_kind == "real_photo"

    if not is_real:
        return {
            "schema_version": "cn-oral-data-governance.gate.v1",
            "status": "allowed",
            "processing_allowed": True,
            "deployment_mode": deployment,
            "data_mode": data_kind,
            "blockers": [],
            "warnings": [],
            "consent_status": "not_required_for_fictional_case",
            "skill_persistent_storage_enabled": False,
            "host_storage_controlled_by_skill": False,
            "public_production_enabled": False,
        }

    if deployment == "public_demo":
        _append_once(blockers, "public_demo_real_data_forbidden")

    age_scope = _text(payload.get("age_scope"))
    if age_scope == "minor":
        _append_once(blockers, "minor_out_of_scope")
    elif age_scope != "adult_confirmed":
        _append_once(blockers, "age_scope_unconfirmed")

    if not _text(payload.get("notice_version")):
        _append_once(blockers, "privacy_notice_missing")
    if not _text(payload.get("controller_identity")):
        _append_once(blockers, "controller_unknown")
    if not _text(payload.get("purpose_code")):
        _append_once(blockers, "purpose_undefined")
    categories = payload.get("data_categories")
    if not isinstance(categories, list) or not categories or not all(_text(item) for item in categories):
        _append_once(blockers, "data_categories_incomplete")
    if payload.get("sensitive_processing_consent") is not True:
        _append_once(blockers, "sensitive_consent_missing")
    if payload.get("host_or_third_party_disclosure_acknowledged") is not True:
        _append_once(blockers, "processor_disclosure_missing")
    if not _valid_consent_timestamp(payload.get("consent_timestamp")):
        _append_once(blockers, "consent_timestamp_invalid")
    if not _text(payload.get("retention_policy_id")):
        _append_once(blockers, "retention_undefined")
    if is_photo and payload.get("photo_processing_consent") is not True:
        _append_once(blockers, "photo_consent_missing")
    if is_photo and isinstance(categories, list) and not {
        "intraoral_photo",
        "facial_photo",
    }.intersection({_text(item) for item in categories}):
        _append_once(blockers, "photo_data_category_missing")
    if payload.get("withdrawal_requested") is True:
        _append_once(blockers, "consent_withdrawn")

    processing_location = _text(payload.get("processing_location_status") or "unknown")
    cross_border = _text(payload.get("cross_border_status") or "unknown")
    deletion_capability = _text(payload.get("deletion_capability") or "unknown")
    processor_identity = _text(payload.get("processor_identity"))
    if deployment == "public_or_institution":
        if not processor_identity:
            _append_once(blockers, "processor_unknown")
        if processing_location not in KNOWN_PROCESSING_LOCATIONS:
            _append_once(blockers, "processing_location_unknown")
        if cross_border not in KNOWN_CROSS_BORDER_STATES:
            _append_once(blockers, "cross_border_unknown")
        if deletion_capability not in KNOWN_DELETION_CAPABILITIES:
            _append_once(blockers, "deletion_capability_unknown")
        if not _text(payload.get("withdrawal_route")):
            _append_once(blockers, "withdrawal_route_missing")
        if payload.get("deployment_review_completed") is not True:
            _append_once(blockers, "deployment_review_incomplete")
    else:
        if not processor_identity:
            _append_once(warnings, "host_processor_identity_not_recorded")
        if processing_location == "unknown":
            _append_once(warnings, "host_processing_location_unknown")
        if cross_border == "unknown":
            _append_once(warnings, "host_cross_border_status_unknown")
        if deletion_capability == "unknown":
            _append_once(warnings, "host_deletion_capability_unknown")

    if payload.get("secondary_use_consent") is True:
        _append_once(warnings, "secondary_use_not_implemented")
    if payload.get("training_use_consent") is True:
        _append_once(warnings, "training_use_not_implemented")

    allowed = not blockers
    return {
        "schema_version": "cn-oral-data-governance.gate.v1",
        "status": "allowed" if allowed else "blocked",
        "processing_allowed": allowed,
        "deployment_mode": deployment,
        "data_mode": data_kind,
        "blockers": blockers,
        "warnings": warnings,
        "consent_status": "recorded_not_legal_determination",
        "notice_version": _text(payload.get("notice_version")) or None,
        "purpose_code": _text(payload.get("purpose_code")) or None,
        "retention_policy_id": _text(payload.get("retention_policy_id")) or None,
        "secondary_use_enabled": False,
        "training_use_enabled": False,
        "skill_persistent_storage_enabled": False,
        "host_storage_controlled_by_skill": False,
        "public_production_enabled": False,
        "withdrawal_action": (
            "stop_processing_and_clear_skill_controlled_temporary_state"
            if "consent_withdrawn" in blockers
            else None
        ),
    }
