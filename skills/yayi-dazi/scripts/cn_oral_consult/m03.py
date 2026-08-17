from __future__ import annotations

from typing import Any, Mapping, Sequence

from .specialist_intake import SpecialistContractError, guard_output, run_specialist


class M03ContractError(SpecialistContractError):
    """M03牙周入口违反已审核运行契约。"""


ALLOWED_TASKS = {"intake_support", "problem_education", "assessment_explanation", "record_explanation", "maintenance", "photo_observation"}

OFFLINE_MAPPING = {
    "M03-FLD-001": ("M03-RUL-016", "gingival_and_bleeding_source_assessment", ["diagnosis", "bleeding_source"]),
    "M03-FLD-002": ("M03-RUL-016", "gingival_and_bleeding_source_assessment", ["diagnosis", "blood_loss"]),
    "M03-FLD-008": ("M03-RUL-018", "mobility_occlusion_and_support_assessment", ["mobility_grade", "bone_support", "prognosis"]),
    "M03-FLD-009": ("M03-RUL-018", "mobility_occlusion_and_support_assessment", ["etiology", "stage", "grade"]),
    "M03-FLD-006": ("M03-RUL-022", "local_lesion_source_differentiation", ["periodontal_abscess", "sinus_tract", "infection_extent"]),
    "M03-FLD-004": ("M03-RUL-023", "gingival_enlargement_and_surface_lesion_assessment", ["etiology", "tumor_nature", "medication_change"]),
    "M03-FLD-005": ("M03-RUL-023", "gingival_enlargement_and_surface_lesion_assessment", ["diagnosis", "tumor_nature"]),
    "M03-FLD-007": ("M03-RUL-024", "recession_mucogingival_and_aesthetic_assessment", ["attachment_loss", "bone_state", "etiology"]),
    "M03-FLD-011": ("M03-RUL-025", "halitosis_or_record_to_current_correlation", ["halitosis_source", "diagnosis"]),
    "M03-FLD-017": ("M03-RUL-025", "halitosis_or_record_to_current_correlation", ["current_stage", "current_grade", "prognosis"]),
}


def run_m03(
    *,
    task: str,
    user_task: str,
    facts: Sequence[Mapping[str, Any]],
    safety_result: Mapping[str, Any] | None,
    route_result: Mapping[str, Any] | None = None,
    photo_context: Mapping[str, Any] | None = None,
    question_blocks: Sequence[Mapping[str, Any]] | None = None,
    safety_recheck_fact_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    try:
        return run_specialist(
            module="M03", field_count=17, output_last=26, task=task, allowed_tasks=ALLOWED_TASKS,
            user_task=user_task, facts=facts, safety_result=safety_result, route_result=route_result,
            photo_context=photo_context, question_blocks=question_blocks, safety_recheck_fact_ids=safety_recheck_fact_ids,
            offline_mapping=OFFLINE_MAPPING,
            safety_recheck_fields={"M03-FLD-001", "M03-FLD-002", "M03-FLD-003", "M03-FLD-004", "M03-FLD-005", "M03-FLD-006", "M03-FLD-008", "M03-FLD-009", "M03-FLD-014"},
            capability_boundary_zh="本输出用于安全分流、信息整理和就诊方向参考，不是诊断、分期分级、预后判断或个人治疗方案",
            prohibitions=["不得诊断牙龈炎、牙周炎或局部病损", "不得给出袋深、附着、骨水平、松动度、分期、分级或预后", "不得把吸烟、糖尿病、用药或旧记录写成个人病因", "不得指导探龈沟、摇牙、挤压、刺破或停换药"],
        )
    except SpecialistContractError as exc:
        raise M03ContractError(str(exc)) from exc


def guard_user_output(text: str, *, safety_level: str) -> dict[str, Any]:
    return guard_output(
        text, safety_level=safety_level,
        internal_pattern=r"(?<![A-Za-z0-9])M03-(?:FLD|RUL|OUT)-\d{3}(?![A-Za-z0-9])",
        extra_patterns=[
            (r"(?:你|您).{0,20}(?:牙龈炎|牙周炎|牙周脓肿|龈瘤)", "把牙周表现写成当前诊断"),
            (r"(?:属于|确定为|判断为).{0,12}(?:[一二三四IV]+期|[ABC]级|松动[一二三IV]+度)", "远程分期、分级或松动度"),
            (r"(?:建议|应该|必须).{0,18}(?:刮治|翻瓣|拔牙|停药|换药|抗生素)", "替当前用户选择治疗或用药"),
        ],
    )
