from __future__ import annotations

from typing import Any, Mapping, Sequence

from .specialist_intake import SpecialistContractError, guard_output, run_specialist


class M02ContractError(SpecialistContractError):
    """M02牙体牙髓入口违反已审核运行契约。"""


ALLOWED_TASKS = {"intake_support", "problem_education", "assessment_explanation", "record_explanation", "photo_observation"}

OFFLINE_MAPPING = {
    "M02-FLD-006": ("M02-RUL-016", "clinical_source_localization", ["affected_tooth", "diagnosis"]),
    "M02-FLD-010": ("M02-RUL-017", "structural_clinical_assessment", ["diagnosis", "lesion_depth"]),
    "M02-FLD-011": ("M02-RUL-017", "structural_clinical_assessment", ["diagnosis", "lesion_depth"]),
    "M02-FLD-001": ("M02-RUL-018", "tooth_response_assessment", ["pulp_status", "diagnosis"]),
    "M02-FLD-003": ("M02-RUL-018", "tooth_response_assessment", ["pulp_status", "diagnosis"]),
    "M02-FLD-007": ("M02-RUL-019", "occlusion_mobility_and_support_assessment", ["diagnosis", "mobility_grade"]),
    "M02-FLD-008": ("M02-RUL-019", "occlusion_mobility_and_support_assessment", ["diagnosis", "mobility_grade"]),
    "M02-FLD-013": ("M02-RUL-020", "local_soft_tissue_and_dental_assessment", ["abscess", "sinus_tract", "infection_extent"]),
    "M02-FLD-015": ("M02-RUL-021", "post_procedure_clinical_review", ["treatment_failure", "personal_treatment"]),
    "M02-FLD-016": ("M02-RUL-022", "record_to_current_clinical_correlation", ["current_diagnosis", "independent_image_interpretation"]),
}


def run_m02(
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
            module="M02", field_count=16, output_last=24, task=task, allowed_tasks=ALLOWED_TASKS,
            user_task=user_task, facts=facts, safety_result=safety_result, route_result=route_result,
            photo_context=photo_context, question_blocks=question_blocks, safety_recheck_fact_ids=safety_recheck_fact_ids,
            offline_mapping=OFFLINE_MAPPING,
            safety_recheck_fields={"M02-FLD-005", "M02-FLD-011", "M02-FLD-013", "M02-FLD-015"},
            capability_boundary_zh="本输出用于安全分流和信息整理，不是诊断、患牙确认或个人治疗方案",
            prohibitions=["不得确定病名、患牙、牙髓状态或结构深度", "不得独立判读牙片或专业医学影像", "不得选择治疗、药物、器械或操作方案", "不得让用户自行冷热刺激、敲牙、咬硬物、探洞或摇牙"],
        )
    except SpecialistContractError as exc:
        raise M02ContractError(str(exc)) from exc


def guard_user_output(text: str, *, safety_level: str) -> dict[str, Any]:
    return guard_output(
        text, safety_level=safety_level,
        internal_pattern=r"(?<![A-Za-z0-9])M02-(?:FLD|RUL|OUT)-\d{3}(?![A-Za-z0-9])",
        extra_patterns=[
            (r"(?:你|您).{0,20}(?:牙髓炎|根尖周炎|龋病|隐裂牙|脓肿|瘘管)", "把牙体牙髓表现写成当前诊断"),
            (r"(?:建议|应该|必须).{0,18}(?:根管|补牙|拔牙|服药|抗生素)", "替当前用户选择治疗或用药"),
        ],
    )
