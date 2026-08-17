from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from typing import Any, Mapping, Sequence

from .privacy import DataGovernanceContractError, evaluate_data_processing_gate
from .runtime_paths import data_path


M08_RULES_PATH = data_path("m08_rules.json")


@lru_cache(maxsize=1)
def load_m08_rules() -> dict[str, Any]:
    payload = json.loads(M08_RULES_PATH.read_text(encoding="utf-8"))
    if payload.get("module") != "M08" or not isinstance(payload.get("task_codes"), list):
        raise M08ContractError("bundled M08 rules are structurally invalid")
    return payload


ALLOWED_REQUESTING_MODULES = {f"M{index:02d}" for index in range(2, 8)}
ALLOWED_ROUTE_MODULES = {f"M{index:02d}" for index in range(2, 9)}
ALL_M00_LEVELS = {"E0", "E1", "U1", "N1", "S0", "NEEDS_CLARIFICATION"}
HALT_LEVELS = {"E0", "E1"}

ALLOWED_TASKS = {
    "single_tooth_or_area",
    "gingiva_region",
    "mucosal_region",
    "intraoral_visible_area",
    "intraoral_frontal",
    "intraoral_right",
    "intraoral_left",
    "upper_arch",
    "lower_arch",
    "face_frontal_rest",
    "face_frontal_smile",
    "face_profile",
    "local_external_swelling",
    "mouth_open_closed_comparison",
    "wound_or_device_area",
    "prosthesis_or_appliance_area",
    "report_page",
}

CAPTURE_VIEW_TIERS = {
    "frontal_rest": "core",
    "profile_rest": "core",
    "oblique_45_rest": "conditional",
    "frontal_smile": "core",
    "profile_smile": "conditional",
    "oblique_45_smile": "conditional",
    "intraoral_right": "core",
    "intraoral_frontal": "core",
    "intraoral_left": "core",
    "anterior_overbite_overjet": "conditional",
    "upper_arch": "core",
    "lower_arch": "core",
}

STANDARD_CAPTURE_VIEW_TASKS = {
    "intraoral_frontal": {"intraoral_frontal", "anterior_overbite_overjet"},
    "intraoral_right": {"intraoral_right", "anterior_overbite_overjet"},
    "intraoral_left": {"intraoral_left", "anterior_overbite_overjet"},
    "upper_arch": {"upper_arch"},
    "lower_arch": {"lower_arch"},
    "face_frontal_rest": {"frontal_rest", "oblique_45_rest"},
    "face_frontal_smile": {"frontal_smile", "profile_smile", "oblique_45_smile"},
    "face_profile": {"profile_rest", "profile_smile", "oblique_45_rest", "oblique_45_smile"},
}

QUALITY_WEIGHTS = {
    "file_integrity": 10,
    "target_coverage": 20,
    "focus_detail": 20,
    "exposure_color": 10,
    "view_pose": 15,
    "perspective": 10,
    "obstruction": 10,
    "comparability": 5,
}

COMPONENT_SCORE_VALUES = {0, 25, 50, 75, 100}
HARD_FAILURES = {
    "decode_failure",
    "target_absent",
    "critical_area_cropped",
    "critical_area_unreadable",
    "strong_filter_or_edit",
    "task_view_mismatch",
    "unsafe_manipulation_required",
    "incomplete_report_page",
    "frontal_face_key_area_cropped",
    "profile_contour_cropped",
    "profile_oblique_mismatch",
    "smile_key_area_cropped",
    "natural_bite_state_unconfirmed",
    "side_dental_range_incomplete",
    "arch_range_incomplete",
    "anterior_relation_unreadable",
}

ALLOWED_SOURCE_TYPES = {"user_upload", "user_current", "user_history", "clinician_record", "device_document"}
ALLOWED_VISIBILITY = {"clear", "partial", "not_visible"}
ALLOWED_TIME_RELATIONS = {"current", "historical", "unknown"}
ALLOWED_OBSERVATION_TYPES = {
    "count",
    "distribution",
    "side",
    "symmetry_in_frame",
    "shape",
    "boundary_visibility",
    "surface_appearance",
    "visible_covering",
    "color_category",
    "visible_elevation",
    "visible_depression",
    "surface_continuity_break",
    "visible_fissure",
    "visible_defect",
    "visible_blood_or_trace",
    "visible_fluid_or_covering",
    "tooth_alignment_appearance",
    "spacing_appearance",
    "crowding_appearance",
    "midline_relation_in_frame",
    "anterior_horizontal_relation_in_frame",
    "anterior_vertical_relation_in_frame",
    "posterior_transverse_relation_in_frame",
    "lip_posture_in_frame",
    "tooth_display_in_smile",
    "prosthesis_or_appliance_integrity_in_frame",
    "prosthesis_or_appliance_position_in_frame",
    "external_change_extent_in_frame",
    "report_text",
}

PROHIBITED_OBSERVATION_TYPES = {
    "diagnosis",
    "disease_probability",
    "severity_stage",
    "benign_or_malignant",
    "pathogen",
    "tissue_origin",
    "texture",
    "tenderness",
    "fluctuation",
    "depth",
    "mobility",
    "probing_bleeding",
    "periodontal_pocket",
    "attachment_loss",
    "skeletal_classification",
    "fracture",
    "deep_infection",
    "joint_disc",
    "nerve_localization",
    "radiology_interpretation",
    "treatment_indication",
    "personal_treatment_plan",
    "malocclusion_classification",
    "overjet_measurement_or_grade",
    "overbite_measurement_or_grade",
    "crossbite_or_scissors_bite_classification",
    "appliance_failure_cause",
    "periodontal_inflammation_diagnosis",
    "enamel_demineralization_or_caries_diagnosis",
    "orthodontic_relapse_diagnosis",
    "treatment_compliance_judgment",
}

ORTHODONTIC_OBSERVATION_PROFILES = {
    "M08-ORTHO-PAT-001": {
        "allowed_tasks": {"intraoral_frontal", "upper_arch", "lower_arch"},
        "allowed_observation_types": {"crowding_appearance", "tooth_alignment_appearance"},
    },
    "M08-ORTHO-PAT-002": {
        "allowed_tasks": {"intraoral_frontal", "upper_arch", "lower_arch"},
        "allowed_observation_types": {"spacing_appearance"},
    },
    "M08-ORTHO-PAT-003": {
        "allowed_tasks": {"face_frontal_rest", "face_profile", "intraoral_frontal"},
        "allowed_observation_types": {"lip_posture_in_frame", "tooth_alignment_appearance"},
    },
    "M08-ORTHO-PAT-004": {
        "allowed_tasks": {"intraoral_frontal", "intraoral_right", "intraoral_left"},
        "allowed_observation_types": {"anterior_horizontal_relation_in_frame"},
    },
    "M08-ORTHO-PAT-005": {
        "allowed_tasks": {"intraoral_frontal", "intraoral_right", "intraoral_left"},
        "allowed_observation_types": {"anterior_horizontal_relation_in_frame"},
    },
    "M08-ORTHO-PAT-006": {
        "allowed_tasks": {"intraoral_right", "intraoral_left"},
        "allowed_observation_types": {"posterior_transverse_relation_in_frame"},
    },
    "M08-ORTHO-PAT-007": {
        "allowed_tasks": {"intraoral_right", "intraoral_left"},
        "allowed_observation_types": {"posterior_transverse_relation_in_frame"},
    },
    "M08-ORTHO-PAT-008": {
        "allowed_tasks": {"intraoral_frontal"},
        "allowed_observation_types": {"anterior_vertical_relation_in_frame"},
    },
    "M08-ORTHO-PAT-009": {
        "allowed_tasks": {"intraoral_frontal", "intraoral_right", "intraoral_left"},
        "allowed_observation_types": {"anterior_vertical_relation_in_frame"},
    },
    "M08-ORTHO-DEV-001": {
        "allowed_tasks": {"prosthesis_or_appliance_area", "wound_or_device_area"},
        "allowed_observation_types": {"prosthesis_or_appliance_integrity_in_frame", "prosthesis_or_appliance_position_in_frame"},
    },
    "M08-ORTHO-DEV-002": {
        "allowed_tasks": {"prosthesis_or_appliance_area", "wound_or_device_area"},
        "allowed_observation_types": {"prosthesis_or_appliance_integrity_in_frame", "prosthesis_or_appliance_position_in_frame"},
    },
    "M08-ORTHO-DEV-003": {
        "allowed_tasks": {"prosthesis_or_appliance_area", "wound_or_device_area"},
        "allowed_observation_types": {"prosthesis_or_appliance_integrity_in_frame", "prosthesis_or_appliance_position_in_frame"},
    },
    "M08-ORTHO-DEV-004": {
        "allowed_tasks": {"prosthesis_or_appliance_area", "wound_or_device_area"},
        "allowed_observation_types": {"prosthesis_or_appliance_integrity_in_frame", "prosthesis_or_appliance_position_in_frame"},
    },
    "M08-ORTHO-DEV-005": {
        "allowed_tasks": {"gingiva_region", "mucosal_region", "wound_or_device_area"},
        "allowed_observation_types": {"color_category", "visible_elevation", "surface_continuity_break", "visible_blood_or_trace"},
    },
    "M08-ORTHO-DEV-006": {
        "allowed_tasks": {"gingiva_region", "single_tooth_or_area", "prosthesis_or_appliance_area"},
        "allowed_observation_types": {"visible_covering", "visible_fluid_or_covering", "surface_appearance", "color_category"},
    },
    "M08-ORTHO-DEV-007": {
        "allowed_tasks": {"intraoral_frontal", "upper_arch", "lower_arch"},
        "allowed_observation_types": {"tooth_alignment_appearance", "spacing_appearance", "crowding_appearance", "midline_relation_in_frame"},
    },
}

SAFETY_RELEVANT_TYPES = {
    "visible_blood_or_trace",
    "external_change_extent_in_frame",
    "surface_continuity_break",
    "prosthesis_or_appliance_integrity_in_frame",
}

ANATOMY_REGIONS = {
    "tooth_or_dental_region",
    "gingiva",
    "lip_or_commissure",
    "buccal_mucosa",
    "tongue",
    "floor_of_mouth",
    "palate",
    "visible_oropharyngeal_region",
    "prosthesis_or_appliance",
    "face_left",
    "face_right",
    "face_midline",
    "maxillofacial_local_region",
    "report_page",
}

SCORE_STATUS_ENGINEERING = "engineering_score_unvalidated"
SCORE_STATUS_CALIBRATED = "calibrated_probability"
OBSERVATION_FACT_PATTERN = re.compile(r"^FACT-M08-[A-Za-z0-9_-]+$")


class M08ContractError(ValueError):
    """Raised when M08 is used outside its approved image-observation contract."""


def _number(value: Any, *, name: str, allowed_discrete: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise M08ContractError(f"{name} must be a finite numeric score from 0 to 100")
    score = float(value)
    if not 0 <= score <= 100:
        raise M08ContractError(f"{name} must be between 0 and 100")
    if allowed_discrete and score not in COMPONENT_SCORE_VALUES:
        raise M08ContractError(f"{name} must be one of {sorted(COMPONENT_SCORE_VALUES)}")
    return score


def _validate_safety_result(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        raise M08ContractError("M08_REQUIRES_M00_RESULT")
    level = str(value.get("effective_level", ""))
    if level not in ALL_M00_LEVELS:
        raise M08ContractError(f"unsupported M00 effective_level: {level}")
    basis = value.get("basis_from_user", [])
    if not isinstance(basis, list):
        raise M08ContractError("M00 basis_from_user must be a list")
    return {
        "effective_level": level,
        "risk_floor_level": value.get("risk_floor_level"),
        "next_state": value.get("next_state"),
        "basis_from_user": list(basis),
        "uncertainties": list(value.get("uncertainties", [])),
        "user_message_zh": value.get("user_message_zh"),
        "time_to_care": value.get("time_to_care"),
        "destination": value.get("destination"),
        "urgency_owned_by": "M00",
    }


def validate_m11_route(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value or value.get("assembled_by") != "M11":
        raise M08ContractError("M08_REQUIRES_M11_BUSINESS_ROUTE")
    forbidden = {"effective_level", "risk_floor_level", "time_to_care", "destination", "urgency"}
    overlap = set(value) & forbidden
    if overlap:
        raise M08ContractError(f"M11 route must not alter M00 safety fields: {sorted(overlap)}")
    primary = value.get("primary_module")
    secondary = value.get("secondary_module")
    if primary is not None and str(primary) not in ALLOWED_ROUTE_MODULES:
        raise M08ContractError(f"unsupported primary_module: {primary}")
    if isinstance(secondary, list):
        raise M08ContractError("M11 may return at most one secondary_module")
    if secondary is not None and str(secondary) not in ALLOWED_ROUTE_MODULES:
        raise M08ContractError(f"unsupported secondary_module: {secondary}")
    return {
        "primary_module": str(primary) if primary is not None else None,
        "secondary_module": str(secondary) if secondary is not None else None,
        "route_status": str(value.get("route_status", "")),
        "offline_required": bool(value.get("offline_required", False)),
        "assembled_by": "M11",
    }


def validate_consent(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        raise M08ContractError("M08_REQUIRES_IMAGE_CONSENT_RECORD")
    required_true = {"authorized_source", "current_consultation_consent", "purpose_notice_acknowledged"}
    missing = sorted(key for key in required_true if value.get(key) is not True)
    if missing:
        raise M08ContractError(f"image consent requirements not met: {missing}")
    try:
        governance = evaluate_data_processing_gate(value, data_mode="real_photo")
    except DataGovernanceContractError as exc:
        raise M08ContractError(str(exc)) from exc
    if not governance["processing_allowed"]:
        raise M08ContractError(f"IMAGE_DATA_GOVERNANCE_BLOCKED: {governance['blockers']}")
    return {
        "authorized_source": True,
        "current_consultation_consent": True,
        "purpose_notice_acknowledged": True,
        "secondary_use_consent": bool(value.get("secondary_use_consent", False)),
        "training_use_consent": bool(value.get("training_use_consent", False)),
        "photo_processing_consent": True,
        "notice_version": governance["notice_version"],
        "purpose_code": governance["purpose_code"],
        "retention_policy_id": governance["retention_policy_id"],
        "data_governance": governance,
    }


def validate_capture_view(*, task: str, capture_view: str | None) -> dict[str, Any]:
    value = str(capture_view or "").strip()
    compatible = STANDARD_CAPTURE_VIEW_TASKS.get(task)
    if compatible is not None and not value:
        raise M08ContractError(f"capture_view is required for standard image task: {task}")
    if not value:
        return {"capture_view": None, "capture_view_tier": None, "standard_view_required": False}
    if value not in CAPTURE_VIEW_TIERS:
        raise M08ContractError(f"unsupported capture_view: {value}")
    if compatible is not None and value not in compatible:
        raise M08ContractError(f"capture_view {value} is incompatible with image task {task}")
    return {
        "capture_view": value,
        "capture_view_tier": CAPTURE_VIEW_TIERS[value],
        "standard_view_required": compatible is not None,
    }


def score_quality(
    *,
    task: str,
    components: Mapping[str, Any],
    hard_failures: Sequence[str] | None = None,
) -> dict[str, Any]:
    if task not in ALLOWED_TASKS:
        raise M08ContractError(f"unsupported M08 image task: {task}")
    if set(components) != set(QUALITY_WEIGHTS):
        missing = sorted(set(QUALITY_WEIGHTS) - set(components))
        extra = sorted(set(components) - set(QUALITY_WEIGHTS))
        raise M08ContractError(f"quality components mismatch; missing={missing}, extra={extra}")
    validated = {name: _number(components[name], name=name, allowed_discrete=True) for name in QUALITY_WEIGHTS}
    failures = [str(item) for item in (hard_failures or [])]
    unknown = sorted(set(failures) - HARD_FAILURES)
    if unknown:
        raise M08ContractError(f"unsupported hard failures: {unknown}")
    weighted = sum(validated[name] * QUALITY_WEIGHTS[name] for name in QUALITY_WEIGHTS) / 100.0
    score = round(weighted, 1)
    if failures or score < 60.0:
        suitability = "not_suitable"
    elif score < 85.0:
        suitability = "partially_suitable"
    else:
        suitability = "suitable"
    color_valid = validated["exposure_color"] >= 75.0 and "strong_filter_or_edit" not in failures
    return {
        "task": task,
        "quality_score": score,
        "score_scale": "0-100",
        "score_status": SCORE_STATUS_ENGINEERING,
        "score_interpretation": "工程任务质量分数，不是诊断概率或医学正确率",
        "suitability": suitability,
        "thresholds": {"suitable_min": 85.0, "partially_suitable_min": 60.0, "not_suitable_max_exclusive": 60.0},
        "components": validated,
        "component_weights_percent": dict(QUALITY_WEIGHTS),
        "hard_failures": failures,
        "color_description_allowed": color_valid,
        "color_component_min": 75.0,
    }


def _confidence_band(score: float) -> str:
    if score >= 85.0:
        return "accepted_visible_fact"
    if score >= 70.0:
        return "bounded_visible_possibility"
    if score >= 50.0:
        return "needs_recapture_or_clarification"
    return "discarded"


def validate_observations(
    observations: Sequence[Mapping[str, Any]],
    *,
    quality: Mapping[str, Any],
    media_id: str,
    task: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    withheld: list[dict[str, Any]] = []
    safety_candidates: list[dict[str, Any]] = []
    for index, item in enumerate(observations):
        obs_type = str(item.get("observation_type", ""))
        if obs_type in PROHIBITED_OBSERVATION_TYPES:
            raise M08ContractError(f"observation {index} uses prohibited type: {obs_type}")
        if obs_type not in ALLOWED_OBSERVATION_TYPES:
            raise M08ContractError(f"observation {index} uses unsupported type: {obs_type}")
        profile_code = str(item.get("observation_profile_code", "")).strip() or None
        if profile_code is not None:
            profile = ORTHODONTIC_OBSERVATION_PROFILES.get(profile_code)
            if profile is None:
                raise M08ContractError(f"observation {index} uses unsupported orthodontic profile: {profile_code}")
            if task not in profile["allowed_tasks"]:
                raise M08ContractError(f"orthodontic profile {profile_code} is incompatible with image task {task}")
            if obs_type not in profile["allowed_observation_types"]:
                raise M08ContractError(f"orthodontic profile {profile_code} does not allow observation type {obs_type}")
        fact_id = str(item.get("fact_id", ""))
        if not OBSERVATION_FACT_PATTERN.fullmatch(fact_id):
            raise M08ContractError(f"observation {index} has invalid fact_id")
        region = str(item.get("anatomy_region", ""))
        if region not in ANATOMY_REGIONS:
            raise M08ContractError(f"observation {index} has unsupported anatomy_region: {region}")
        visibility = str(item.get("visibility", ""))
        if visibility not in ALLOWED_VISIBILITY:
            raise M08ContractError(f"observation {index} has unsupported visibility: {visibility}")
        time_relation = str(item.get("time_relation", ""))
        if time_relation not in ALLOWED_TIME_RELATIONS:
            raise M08ContractError(f"observation {index} has unsupported time_relation: {time_relation}")
        location_score = _number(item.get("location_confidence_score"), name="location_confidence_score")
        observation_score = _number(item.get("observation_confidence_score"), name="observation_confidence_score")
        if item.get("score_status", SCORE_STATUS_ENGINEERING) not in {SCORE_STATUS_ENGINEERING, SCORE_STATUS_CALIBRATED}:
            raise M08ContractError(f"observation {index} has unsupported score_status")
        if item.get("score_status") == SCORE_STATUS_CALIBRATED and not item.get("calibration_release_id"):
            raise M08ContractError("calibrated_probability requires calibration_release_id")
        effective_score = round(min(location_score, observation_score, float(quality["quality_score"])), 1)
        band = _confidence_band(effective_score)
        limitations = [str(value) for value in item.get("limitations", [])]
        if quality["suitability"] == "not_suitable" or visibility == "not_visible":
            band = "discarded"
        if obs_type == "color_category" and not quality["color_description_allowed"]:
            band = "needs_recapture_or_clarification"
            limitations.append("exposure_color_score_below_75_or_filter_detected")
        record = {
            "fact_id": fact_id,
            "media_id": media_id,
            "observation_type": obs_type,
            "observation_profile_code": profile_code,
            "anatomy_region": region,
            "value_zh": str(item.get("value_zh", "")).strip(),
            "visibility": visibility,
            "time_relation": time_relation,
            "location_confidence_score": location_score,
            "observation_confidence_score": observation_score,
            "effective_confidence_score": effective_score,
            "score_scale": "0-100",
            "score_status": str(item.get("score_status", SCORE_STATUS_ENGINEERING)),
            "confidence_band": band,
            "confidence_thresholds": {"accepted_min": 85.0, "bounded_min": 70.0, "clarify_min": 50.0, "discard_below": 50.0},
            "limitations": limitations,
            "source_type": "user_upload",
            "not_a_diagnosis": True,
            "linked_text_fact_id": item.get("linked_text_fact_id"),
        }
        if not record["value_zh"]:
            raise M08ContractError(f"observation {index} requires value_zh")
        if band in {"accepted_visible_fact", "bounded_visible_possibility"}:
            accepted.append(record)
        else:
            withheld.append(record)
        safety_relevant = bool(item.get("safety_relevant", False)) or obs_type in SAFETY_RELEVANT_TYPES
        if safety_relevant and effective_score >= 50.0:
            safety_candidates.append({
                "fact_id": fact_id,
                "media_id": media_id,
                "candidate_visible_fact_zh": record["value_zh"],
                "effective_confidence_score": effective_score,
                "score_status": record["score_status"],
                "certainty_for_m00": "visible_candidate" if effective_score >= 70.0 else "uncertain_visible_candidate",
                "m00_recheck_required": True,
                "m08_does_not_assign_urgency": True,
            })
    return accepted, withheld, safety_candidates


def fuse_text_and_image(
    text_facts: Sequence[Mapping[str, Any]] | None,
    image_facts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    preserved_text = [dict(item) for item in (text_facts or [])]
    differences: list[dict[str, Any]] = []
    for image_fact in image_facts:
        linked = image_fact.get("linked_text_fact_id")
        if not linked:
            continue
        text_match = next((item for item in preserved_text if item.get("fact_id") == linked), None)
        if text_match and str(text_match.get("value_status")) == "denied":
            differences.append({
                "text_fact_id": linked,
                "image_fact_id": image_fact["fact_id"],
                "difference_type": "cross_source_difference",
                "image_confidence_score": image_fact["effective_confidence_score"],
                "clarification_priority_score": 100.0 if image_fact["effective_confidence_score"] >= 85.0 else 80.0,
                "maximum_clarification_questions": 1,
                "both_sources_preserved": True,
            })
    return {
        "text_facts": preserved_text,
        "image_facts": [dict(item) for item in image_facts],
        "cross_source_differences": differences,
        "photo_nonvisibility_never_equals_user_denial": True,
        "historical_and_current_kept_separate": True,
        "image_never_lowers_m00": True,
    }


def run_m08(
    *,
    task: str,
    requested_by_module: str,
    media: Mapping[str, Any],
    quality_components: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    safety_result: Mapping[str, Any] | None,
    route_result: Mapping[str, Any] | None,
    consent_record: Mapping[str, Any] | None,
    capture_view: str | None = None,
    hard_failures: Sequence[str] | None = None,
    text_facts: Sequence[Mapping[str, Any]] | None = None,
    age_group: str = "adult",
) -> dict[str, Any]:
    bundled_rules = load_m08_rules()
    safety = _validate_safety_result(safety_result)
    if safety["effective_level"] in HALT_LEVELS:
        return {
            "schema_version": "cn-dental-m08.output.v1.3",
            "module": "M08",
            "status": "halted_by_m00",
            "safety": safety,
            "observations": [],
            "m00_candidate_facts": [],
            "production_enabled": False,
        }
    if safety["effective_level"] == "NEEDS_CLARIFICATION":
        return {
            "schema_version": "cn-dental-m08.output.v1.3",
            "module": "M08",
            "status": "waiting_for_m00_clarification",
            "safety": safety,
            "observations": [],
            "m00_candidate_facts": [],
            "production_enabled": False,
        }
    if age_group != "adult":
        return {
            "schema_version": "cn-dental-m08.output.v1.3",
            "module": "M08",
            "status": "out_of_adult_scope",
            "safety": safety,
            "observations": [],
            "m00_candidate_facts": [],
            "production_enabled": False,
        }
    if requested_by_module not in ALLOWED_REQUESTING_MODULES:
        raise M08ContractError(f"unsupported M08 requesting module: {requested_by_module}")
    route = validate_m11_route(route_result)
    consent = validate_consent(consent_record)
    if task not in ALLOWED_TASKS:
        raise M08ContractError(f"unsupported M08 image task: {task}")
    if task not in set(bundled_rules["task_codes"]):
        raise M08ContractError(f"image task is absent from the bundled M08 rule catalog: {task}")
    view = validate_capture_view(task=task, capture_view=capture_view)
    media_id = str(media.get("media_id", "")).strip()
    if not re.fullmatch(r"MEDIA-[A-Za-z0-9_-]+", media_id):
        raise M08ContractError("media_id must use MEDIA-* format")
    source_type = str(media.get("source_type", ""))
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise M08ContractError(f"unsupported media source_type: {source_type}")
    if not str(media.get("user_goal", "")).strip():
        raise M08ContractError("M08 requires a specific user_goal")
    quality = score_quality(task=task, components=quality_components, hard_failures=hard_failures)
    accepted, withheld, safety_candidates = validate_observations(observations, quality=quality, media_id=media_id, task=task)
    fusion = fuse_text_and_image(text_facts, accepted)
    status = "limited_by_m00" if safety["effective_level"] == "U1" else "ready_for_m00_recheck"
    recapture_allowed = safety["effective_level"] not in {"E0", "E1", "U1"}
    return {
        "schema_version": "cn-dental-m08.output.v1.3",
        "module": "M08",
        "status": status,
        "requested_by_module": requested_by_module,
        "task": task,
        "media": {
            "media_id": media_id,
            "source_type": source_type,
            "captured_at": media.get("captured_at"),
            "user_goal": str(media["user_goal"]),
            "capture_view": view["capture_view"],
            "capture_view_tier": view["capture_view_tier"],
            "exif_removed_unless_needed": True,
        },
        "safety": safety,
        "m11_route": route,
        "consent": consent,
        "quality": quality,
        "observations": accepted,
        "withheld_observations": withheld,
        "fusion": fusion,
        "m00_candidate_facts": safety_candidates,
        "m00_recheck_required": bool(accepted or withheld or safety_candidates),
        "m08_may_lower_urgency": False,
        "recapture_allowed": recapture_allowed,
        "maximum_recapture_instruction_count": 1 if recapture_allowed else 0,
        "capability_boundary_zh": "只记录普通照片中的中性可见事实；不是诊断、专业影像判读、严重程度分期或个人治疗方案",
        "score_policy": {
            "all_confidence_scores_are_numeric": True,
            "scale": "0-100",
            "default_status": SCORE_STATUS_ENGINEERING,
            "probability_claim_allowed_before_calibration": False,
        },
        "rules_schema_version": bundled_rules.get("schema_version"),
        "production_enabled": False,
    }


FORBIDDEN_OUTPUT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?:确诊|可以排除|基本排除|肯定是|大概率是|最像)", "诊断或排除性结论"),
    (r"(?:良性|恶性|癌变概率|感染概率|疾病概率).{0,8}\d+(?:\.\d+)?%", "把置信分数解释为疾病概率"),
    (r"(?:照片|图片).{0,14}(?:证明|确定|看出).{0,18}(?:骨折|深部感染|关节盘|骨性|良性|恶性|神经损伤)", "用普通照片判断深部、骨性或病理性质"),
    (r"(?:照片|图片).{0,14}(?:证明|确定|看出|就是).{0,18}(?:双颌前突|前牙反𬌗|深覆𬌗|开𬌗|后牙反𬌗|锁𬌗|错𬌗)", "用普通照片完成正畸诊断或正式分类"),
    (r"(?:自己|自行).{0,16}(?:探|挤|压|刮|挑破|穿刺|复位|拆|调整)", "危险自行操作"),
    (r"M08-(?:IMG-[A-Z]+|ORTHO-(?:PAT|DEV))-\d{3}", "向用户暴露内部规则编号"),
    (r"(?<!\d)(?:911|999|111)(?!\d)|NHS|urgent care", "境外医疗服务入口"),
)


def guard_user_output(text: str, *, safety_level: str) -> dict[str, Any]:
    violations = [{"reason": reason, "matched_text": match.group(0)} for pattern, reason in FORBIDDEN_OUTPUT_PATTERNS if (match := re.search(pattern, text, re.I))]
    if safety_level in HALT_LEVELS and not re.search(r"立即|尽快前往|综合医院急诊|口腔急诊", text):
        violations.append({"reason": "紧急输出缺少M00行动", "matched_text": ""})
    return {"passed": not violations, "violations": violations}
