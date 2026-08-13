from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


PRODUCTION_ENABLED = False
CLINICAL_VALIDITY_CLAIM_ALLOWED = False
LEVEL_ORDER = {"S0": 0, "N1": 1, "U1": 2, "E1": 3, "E0": 4}
ALL_LEVELS = set(LEVEL_ORDER) | {"NEEDS_CLARIFICATION"}

E0_SIGNALS = {
    "breathing_difficulty",
    "swallowing_difficulty",
    "speech_or_voice_change",
    "eye_or_neck_involvement",
    "severe_systemic_state",
    "severe_facial_trauma",
    "possible_cardiac_pattern",
    "possible_analgesic_overuse",
}
E1_SIGNALS = {"adult_permanent_tooth_avulsion", "uncontrolled_oral_bleeding"}
U1_SIGNALS = {
    "any_face_or_neck_swelling",
    "expanding_persistent_or_recurrent_oral_swelling",
    "severe_uncontrolled_pain_affecting_function",
    "swelling_with_infection_features",
    "trismus_with_pain_or_swelling",
    "fracture_or_displacement_affecting_function",
    "recurrent_or_marked_oral_bleeding",
    "dental_pain_with_systemic_features",
    "post_treatment_infection_not_improving",
}
N1_SIGNALS = {
    "mild_or_moderate_pain_without_upgrade_signal",
    "pain_over_two_days",
    "recurrent_short_cold_or_heat_sensitivity",
    "current_or_progressive_oral_health_concern",
}
S0_REQUIRED = {
    "mild_short_and_self_resolving",
    "all_upgrade_signals_denied",
    "understands_escalation_conditions",
}

QUESTIONS = {
    "breathing_difficulty": "请只确认一件事：现在是否有呼吸费力、喘不上气或吸气时发出异常尖锐声音？",
    "swallowing_difficulty": "请只确认一件事：现在是吞咽疼痛，还是连水或唾液也难以咽下？",
    "speech_or_voice_change": "请只确认一件事：现在是否说话明显困难、声音明显含糊或嘶哑，或吸气时有异常尖锐声音？",
    "eye_or_neck_involvement": "请只确认一件事：现在是否有明显颈部肿胀，或眼周肿胀伴眼痛、睁眼困难或视力突然变化？",
    "severe_systemic_state": "请只确认一件事：现在是否有意识异常、异常嗜睡、严重全身不适，或连水也无法正常喝下？",
    "severe_facial_trauma": "请只确认一件事：这次是否为严重颌面外伤，或怀疑骨折？",
    "possible_cardiac_pattern": "请只确认一件事：下颌或口腔疼痛是否同时伴胸部紧缩、呼吸困难、出汗或恶心？",
    "possible_analgesic_overuse": "请只确认一件事：是否可能超过说明书剂量，或重复服用了含相同成分的止痛药？",
    "adult_permanent_tooth_avulsion": "请只确认一件事：脱落的是成人恒牙，且整颗牙已经完全脱出吗？",
    "uncontrolled_oral_bleeding": "请只确认一件事：持续局部压迫后，口内出血是否仍无法控制？",
}

DESTINATIONS = {
    "E0": ["附近综合医院急诊科", "具备口腔颌面外科急诊能力的医院"],
    "E1": ["医院口腔急诊", "口腔颌面外科", "能够处理牙外伤或口腔急症的专业牙科机构"],
    "U1": ["口腔急诊", "综合医院口腔科", "口腔颌面外科"],
    "N1": ["具备资质的口腔科医生或牙科机构"],
    "S0": ["出现持续、反复或升级信号时联系具备资质的口腔专业人员"],
}
TIME_TO_CARE = {
    "E0": "立即",
    "E1": "立即联系并尽快到达",
    "U1": "目标24小时内，能更早时不要等待",
    "N1": "2至7天内",
    "S0": "有限观察；持续、反复或加重时升级",
}


class M00ContractError(ValueError):
    pass


def _more_urgent(left: str | None, right: str | None) -> str | None:
    levels = [item for item in (left, right) if item in LEVEL_ORDER]
    return max(levels, key=LEVEL_ORDER.__getitem__) if levels else None


def _signals(value: Any, *, name: str, allowed: set[str]) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise M00ContractError(f"{name} must be an object")
    result: dict[str, str] = {}
    for key, status in value.items():
        if str(key) not in allowed:
            raise M00ContractError(f"{name}.{key} is not a registered signal")
        normalized = str(status).lower()
        if normalized not in {"yes", "no", "unknown"}:
            raise M00ContractError(f"{name}.{key} must be yes, no, or unknown")
        result[str(key)] = normalized
    return result


def _basis(keys: Sequence[str], spans: Mapping[str, Any], raw: str) -> list[str]:
    result = [str(spans[key]).strip() for key in keys if str(spans.get(key, "")).strip()]
    return list(dict.fromkeys(result)) or ([raw.strip()] if raw.strip() else [])


def pre_gate(payload: Mapping[str, Any]) -> dict[str, Any]:
    entry_mode = str(payload.get("entry_mode", "uncertain"))
    if entry_mode not in {"oral_health", "dentofacial_aesthetic", "mixed", "uncertain", "out_of_scope"}:
        raise M00ContractError(f"unsupported entry_mode: {entry_mode}")
    hard = payload.get("hard_signal_candidates", [])
    health = payload.get("health_or_function_features", [])
    if not isinstance(hard, list) or not isinstance(health, list):
        raise M00ContractError("hard_signal_candidates and health_or_function_features must be lists")
    if hard or health or entry_mode in {"oral_health", "mixed"}:
        decision, state = "full_triage", "PRE_GATE"
    elif entry_mode == "dentofacial_aesthetic":
        decision, state = "aesthetic_mini_screen", "AESTHETIC_MINI_SCREEN"
    elif entry_mode == "out_of_scope":
        decision, state = "out_of_scope", "END"
    else:
        decision, state = "clarify_once", "CLARIFY_ONCE"
    return {
        "schema_version": "cn-dental-triage.pre-gate.v1",
        "operation": "pre_gate",
        "gate_decision": decision,
        "next_state": state,
        "entry_mode": entry_mode,
        "hard_signal_candidates": list(hard),
        "health_or_function_features": list(health),
        "production_enabled": False,
    }


def full_triage(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = str(payload.get("raw_user_text", ""))
    prior = payload.get("prior_risk_floor_level")
    if prior is not None and str(prior) not in LEVEL_ORDER:
        raise M00ContractError("invalid prior_risk_floor_level")
    prior = str(prior) if prior is not None else None
    critical = _signals(payload.get("critical_signals"), name="critical_signals", allowed=E0_SIGNALS | E1_SIGNALS)
    urgent = _signals(payload.get("urgent_signals"), name="urgent_signals", allowed=U1_SIGNALS)
    ordinary = _signals(payload.get("ordinary_signals"), name="ordinary_signals", allowed=N1_SIGNALS | S0_REQUIRED)
    spans = payload.get("basis_by_signal", {})
    if not isinstance(spans, Mapping):
        raise M00ContractError("basis_by_signal must be an object")
    ambiguity = payload.get("credible_ambiguity_signals", [])
    if not isinstance(ambiguity, list):
        raise M00ContractError("credible_ambiguity_signals must be a list")
    clarification_used = bool(payload.get("clarification_used", False))
    unknown = [key for key in ambiguity if key in E0_SIGNALS | E1_SIGNALS and critical.get(key) == "unknown"]
    if unknown and not clarification_used and prior not in {"E0", "E1"}:
        key = unknown[0]
        return {
            "schema_version": "cn-dental-triage.output.v2",
            "operation": "full_triage",
            "candidate_level": "NEEDS_CLARIFICATION",
            "risk_floor_level": prior,
            "effective_level": "NEEDS_CLARIFICATION",
            "next_state": "CLARIFY_ONCE",
            "dialogue_action": "ask_one_safety_changing_question",
            "basis_from_user": _basis([key], spans, raw),
            "uncertainties": [key],
            "clarification_question_zh": QUESTIONS.get(key, "请只确认这一项危险信号现在是否确实存在？"),
            "time_to_care": None,
            "destination_types_zh": [],
            "reviewed_by": "M00",
            "production_enabled": False,
        }
    e0 = sorted(key for key in E0_SIGNALS if critical.get(key) == "yes" or (clarification_used and key in unknown))
    e1 = sorted(key for key in E1_SIGNALS if critical.get(key) == "yes" or (clarification_used and key in unknown))
    u1 = sorted(key for key in U1_SIGNALS if urgent.get(key) == "yes")
    n1 = sorted(key for key in N1_SIGNALS if ordinary.get(key) == "yes")
    if e0:
        candidate, matched = "E0", e0
    elif e1:
        candidate, matched = "E1", e1
    elif u1:
        candidate, matched = "U1", u1
    elif n1:
        candidate, matched = "N1", n1
    elif all(ordinary.get(key) == "yes" for key in S0_REQUIRED):
        candidate, matched = "S0", sorted(S0_REQUIRED)
    else:
        candidate, matched = "N1", ["insufficient_facts_for_limited_self_care"]
    effective = _more_urgent(prior, candidate)
    assert effective is not None
    floor = _more_urgent(prior, candidate)
    return {
        "schema_version": "cn-dental-triage.output.v2",
        "operation": "full_triage",
        "candidate_level": candidate,
        "risk_floor_level": floor,
        "effective_level": effective,
        "next_state": {"E0": "E0_HALT", "E1": "E1_ROUTE", "U1": "U1_LIMITED", "N1": "N1_INTAKE", "S0": "S0_OBSERVE"}[effective],
        "dialogue_action": "halt_ordinary_flow" if effective in {"E0", "E1"} else "continue_with_level_limits",
        "basis_from_user": _basis(matched, spans, raw),
        "uncertainties": unknown if clarification_used else [],
        "time_to_care": TIME_TO_CARE[effective],
        "destination_types_zh": DESTINATIONS[effective],
        "risk_floor_preserved": prior is not None and effective != candidate,
        "reviewed_by": "M00",
        "production_enabled": False,
        "clinical_validity_claim_allowed": False,
    }


def final_guard(payload: Mapping[str, Any]) -> dict[str, Any]:
    draft = str(payload.get("draft_text", "")).strip()
    effective = str(payload.get("effective_level", ""))
    floor = payload.get("risk_floor_level")
    if not draft or effective not in LEVEL_ORDER or (floor is not None and str(floor) not in LEVEL_ORDER):
        raise M00ContractError("final_guard requires draft_text and valid effective/risk-floor levels")
    floor = str(floor) if floor is not None else None
    violations: list[str] = []
    if floor and LEVEL_ORDER[effective] < LEVEL_ORDER[floor]:
        violations.append("effective_level_lower_than_risk_floor")
    if effective == "E0" and not re.search(r"立即|马上|综合医院急诊", draft):
        violations.append("e0_action_missing")
    if effective == "E1" and not re.search(r"立即|紧急|口腔急诊|口腔颌面外科", draft):
        violations.append("e1_action_missing")
    if effective == "U1" and not re.search(r"24\s*小时|当天|尽快", draft):
        violations.append("u1_action_missing")
    if re.search(r"(?:已经|可以|基本|能够)?确诊|肯定是|就是.{0,10}(?:病|炎|癌)", draft):
        violations.append("diagnosis_claim")
    passed = not violations
    return {
        "schema_version": "cn-dental-triage.final-guard.v1",
        "operation": "final_guard",
        "passed": passed,
        "effective_level": effective,
        "risk_floor_level": floor,
        "violations": violations,
        "reviewed_by": "M00",
        "production_enabled": False,
    }


def run_m00(payload: Mapping[str, Any]) -> dict[str, Any]:
    operation = str(payload.get("operation", "full_triage"))
    if operation == "pre_gate":
        return pre_gate(payload)
    if operation == "full_triage":
        return full_triage(payload)
    if operation == "final_guard":
        return final_guard(payload)
    raise M00ContractError(f"unsupported M00 operation: {operation}")
