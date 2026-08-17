# 主Agent模块间数据契约

状态：M00基础契约已审核；M08-M10已内部封版；M11公共结构化入口已接入；作品集级文本前向工程验证已完成。专业参考标准、真实图像验证及发布门禁未完成，整体保持生产禁用。

## 0. 这里的“接口”到底是什么

这里的“接口”不是用户看到的页面，也暂时不是一个对外开放的网络API。它是**主Agent与口腔安全分流Skill之间的内部数据契约**：

```text
用户文字或照片
  → 主Agent整理已知事实
  → 按固定字段调用安全分流Skill
  → Skill返回等级、依据、下一状态和用户文案
  → 主Agent只能按状态机执行，不能自行降低等级
```

这份契约解决五个问题：何时调用、送入哪些事实、返回哪些结果、主Agent接下来允许做什么、模块失败时怎么办。它不负责诊断，也不决定具体治疗。

### 0.1 数据治理前置门禁

真实文字或照片进入M00至M12前，先调用`evaluate_data_processing_gate`。这是数据处理门禁，不是新增医疗模块，也不参与紧迫度或专业路由计算。

- `personal_local`：完成当前咨询告知与敏感信息授权后可处理真实文字；照片另行授权。Skill不新增持久化存储，但不能替宿主承诺保存或删除结果。
- `public_demo`：只允许`fictional`，收到`real_text`或`real_photo`时阻断。
- `public_or_institution`：除一般授权外，还要求处理者、处理地点、跨境状态、保存政策、删除能力、撤回途径和独立部署评估均明确；任一未知即阻断。

门禁只返回状态码、阻断原因、告知版本、处理目的和保存政策编号，不回显用户病情、照片或身份信息。详细字段与撤回逻辑见[隐私与数据治理契约](privacy-and-data-governance.md)。

## 1. 三种调用操作

同一个Skill提供三种内部操作，不需要建立三个独立Agent：

| `operation` | 调用时机 | 目的 |
|---|---|---|
| `pre_gate` | 每次新的口腔或颌面相关用户信息到达时 | 识别健康、美观、混合及硬危险信号 |
| `full_triage` | 前置识别命中健康、混合或危险线索时 | 计算E0至S0，并给出下一状态 |
| `final_guard` | 主Agent准备输出最终建议前 | 防止文案的紧迫度低于历史最高等级 |

若用户在第一条消息中直接上传照片，主Agent先处理随附文字并运行`pre_gate`；没有文字时先做最小安全筛查。完成前不得依据照片给出病因或低风险结论。

## 2. 前置识别阈值

### 2.1 硬规则优先，不能被分数覆盖

只要文本明确或语义上疑似出现下列任一线索，就直接调用`full_triage`：

- 呼吸、吞咽、说话或声音异常；
- 眼周、颈部或快速扩大的口腔颌面肿胀；
- 意识异常、明显嗜睡、严重全身不适或无法饮水；
- 严重颌面外伤、控制不住的口内出血或成人恒牙完全脱出；
- 下颌或口腔疼痛伴胸部不适、呼吸困难、出汗或恶心；
- 疑似镇痛药过量、重复成分或剂量无法确认。

硬规则既检查明确词语，也检查同义、口语和上下文表达。例如“口水都咽不下去”必须映射到吞咽危险信号，不能因为没有出现“吞咽困难”四个字而漏掉。

### 2.2 明确健康或混合意图

出现疼痛、敏感、肿胀、出血、黏膜破损、外伤、发热、异常分泌、牙齿松动或折裂、治疗后异常，或者张口、咀嚼、吞咽、说话功能异常时，直接调用`full_triage`，不依赖数值分数。

美观与上述任一线索并存时按`mixed`处理，先安全分流，再进入正畸或美观问诊。

### 2.3 纯美观意图

只有排列、拥挤、间隙、前突、中线、笑线、牙色、牙形或**长期稳定**的面部不对称，且没有健康与功能线索时，进入`AESTHETIC_MINI_SCREEN`。面部不对称若近期新出现、突然加重或伴肿胀，不得归为纯美观。

### 2.4 数值阈值只处理模糊意图

如果实现中使用意图分类器，第一版采用以下**工程初始值**：

- `P(health_or_mixed) >= 0.35`：调用`full_triage`；
- `P(pure_aesthetic) >= 0.85`，同时`P(health_or_mixed) < 0.35`且没有任何硬规则或健康词义命中：进入美观简筛；
- 其余落入不确定区：问一个入口澄清问题；仍不确定时保守调用`full_triage`。

`0.35`和`0.85`是为了开始制作评测集而设置的工程阈值，不是医学指南阈值，也不宣称已经校准。后续必须以危险病例召回率、美观病例误触发率和不同表达方式的一致性进行调参。任何硬危险信号都能越过数值阈值直接触发。

## 3. 最小输入结构

主Agent不必等字段齐全才调用；缺失值统一使用`unknown`，不得把`unknown`当成`no`。

```json
{
  "schema_version": "cn-dental-triage.input.v0.2",
  "operation": "pre_gate | full_triage | final_guard",
  "locale": "zh-CN",
  "episode_id": "本次问题的临时非身份编号",
  "turn_id": "本轮临时编号",
  "age_group": "adult | unknown",
  "data_governance_gate": {
    "status": "allowed | blocked",
    "deployment_mode": "personal_local | public_demo | public_or_institution",
    "data_mode": "fictional | real_text | real_photo",
    "blockers": []
  },
  "raw_user_text": "用户最近一次原始表述",
  "routing_context": {
    "entry_mode": "oral_health | dentofacial_aesthetic | mixed | uncertain",
    "health_or_mixed_score": null,
    "pure_aesthetic_score": null,
    "hard_signal_candidates": [],
    "gate_decision": "full_triage | aesthetic_mini_screen | clarify_once | out_of_scope"
  },
  "prior_state": {
    "current_state": "START",
    "risk_floor_level": null,
    "clarification_used": false
  },
  "known_history": {
    "chief_complaint": null,
    "onset_and_duration": null,
    "site_and_localizability": null,
    "radiation": null,
    "pain_features": null,
    "evolution": null,
    "local_associated_features": null,
    "systemic_features": null,
    "recent_event_or_trauma": null,
    "prior_care_and_response": null,
    "medicines_taken": null,
    "relevant_medical_context": null
  },
  "critical_signals": {
    "breathing_difficulty": "yes | no | unknown",
    "swallowing_difficulty": "yes | no | unknown",
    "speech_or_voice_change": "yes | no | unknown",
    "eye_or_neck_involvement": "yes | no | unknown",
    "severe_systemic_state": "yes | no | unknown",
    "severe_facial_trauma": "yes | no | unknown",
    "uncontrolled_oral_bleeding": "yes | no | unknown",
    "adult_permanent_tooth_avulsion": "yes | no | unknown",
    "possible_cardiac_pattern": "yes | no | unknown",
    "possible_analgesic_overuse": "yes | no | unknown"
  },
  "photo_context": {
    "provided": false,
    "image_rule_version": null,
    "assessment_status": "not_provided | awaiting_text_screen | not_assessed | assessed",
    "technical_quality": {
      "target_present": "yes | no | unknown",
      "focus": "pass | fail | unknown",
      "exposure": "pass | fail | unknown",
      "framing": "pass | fail | unknown",
      "occlusion": "pass | fail | unknown"
    },
    "visible_observations_only": [],
    "unassessable_reasons": []
  }
}
```

输入约束：

- 不采集姓名、身份证号、电话号码或精确住址。
- `episode_id`和`turn_id`由系统临时生成，不使用用户个人信息。
- 保留`raw_user_text`；结构化字段只能摘要，不得改写成病名。
- `possible_cardiac_pattern`和`possible_analgesic_overuse`只能来自明确用户信息。
- 主Agent传入的分数不能覆盖Skill对`raw_user_text`进行的硬规则复核。
- 图像规则未审核前，`image_rule_version`保持为空，图像结果不得自动改变等级。
- 真实数据的`data_governance_gate.status`不是`allowed`时，不得继续把数据交给M00至M12；安全紧急提示只能基于调用方已经具备处理依据的信息生成。

## 4. 最小输出结构

```json
{
  "schema_version": "cn-dental-triage.output.v0.2",
  "rule_version": "cn-dental-triage.rules.v0.1",
  "candidate_level": "E0 | E1 | U1 | N1 | S0 | NEEDS_CLARIFICATION",
  "risk_floor_level": "E0 | E1 | U1 | N1 | S0 | null",
  "effective_level": "E0 | E1 | U1 | N1 | S0 | NEEDS_CLARIFICATION",
  "next_state": "CLARIFY_ONCE | AESTHETIC_MINI_SCREEN | E0_HALT | E1_ROUTE | U1_LIMITED | N1_INTAKE | S0_OBSERVE | FINAL_GUARD | END",
  "dialogue_action": "interrupt_and_route | route_now | continue_minimal | continue | return_to_aesthetic",
  "time_to_care": {
    "kind": "immediate_medical | immediate_dental_contact | within_24_hours | within_2_to_7_days | observe",
    "contact_target_minutes": null,
    "outer_limit_hours": null,
    "note_zh": "时间含义说明"
  },
  "destination_types_zh": [],
  "matched_rule_ids": [],
  "basis_from_user": [],
  "uncertainties": [],
  "clarification_question_zh": null,
  "escalation_signs_zh": [],
  "user_message_zh": "可直接展示的中国化安全分流文案",
  "capability_boundary_zh": "本结果只用于安全分流，不是诊断或个人治疗方案"
}
```

三个等级字段不能混用：

- `candidate_level`回答“只看本轮新信息会得到什么等级”；
- `risk_floor_level`保存“此前已经确认过的最高等级”；
- `effective_level`决定主Agent当前真正执行什么，永远不得低于`risk_floor_level`。

其他约束：

- `basis_from_user`只能包含用户已经表达的事实。
- `matched_rule_ids`只用于内部审计，不默认展示。
- `contact_target_minutes`只表示E1获得专业接触或分诊的目标，不代表完成治疗。
- `outer_limit_hours`不是“可以等待到最后一刻”。
- `user_message_zh`必须可以直接展示，不含境外服务入口或境外电话号码。

## 5. 等级对应动作

| 结果 | 下一状态 | 主Agent必须执行 | 主Agent不得执行 |
|---|---|---|---|
| E0 | `E0_HALT` | 原样展示急诊文案并结束普通问诊 | 索要照片、继续诊断、用低风险建议稀释提示 |
| E1 | `E1_ROUTE` | 先展示紧急牙科去向 | 为填满字段继续完整问诊 |
| U1 | `U1_LIMITED` | 立即给出24小时内建议；最多补问一个改变去向的问题 | 等问完全部病史才告知紧迫度 |
| N1 | `N1_INTAKE` | 完成压缩问诊并给出2至7天内面诊建议 | 确认病因或表示无需面诊 |
| S0 | `S0_OBSERVE` | 给有限观察和升级条件 | 表达为“没有问题”或“无需牙医” |
| NEEDS_CLARIFICATION | `CLARIFY_ONCE` | 只问一个能改变E0/E1/U1去向的问题 | 一次追问多个低价值细节 |

完整状态转移和禁止降级规则见[主Agent安全状态机](state-machine.md)。

## 6. 一次澄清规则

只有当用户提到呼吸、吞咽、眼周、严重全身状态、失控出血或用药过量，但表达含糊，且一个问题能够改变E0/E1/U1去向时，才返回`NEEDS_CLARIFICATION`。

例如：

> 你现在是否真的出现了吞咽困难，例如连水或自己的唾液都难以下咽？请只回答“是、否或不确定”。

若一次澄清后仍无法确认，而原始信息提示可信高风险，采用更保守等级，不得默认N1或S0。

## 7. M08图像接口

图像部分已完成独立规则和运行契约，详细要求见[M08图像模块](m08-module.md)。主Agent接入时必须：

- 先取得M00结果和M11业务路由，再由M02至M07提出17类具体任务之一；
- 八项质量分数均使用0、25、50、75或100，并按固定权重得到0—100总分；
- 每条候选观察同时提供0—100的位置分数和属性分数；
- 85.0以上写明确可见事实，70.0—84.9只写受限可能，50.0—69.9补拍或澄清，低于50.0丢弃；
- 校准前所有分数标记`engineering_score_unvalidated`，不得解释为疾病或诊断概率；
- 所有新增图像事实返回M00，照片不能降低紧迫度；
- 普通照片不判断深度、触感、骨折、深部感染、骨性类型、病理性质或个人治疗方案；
- 专业医学影像不判读，报告页面只提取既有报告文字；
- 当前咨询、评测和训练分别授权；真实图像独立评测未通过前保持生产禁用。
- 授权结构使用具名保存政策，不再接受任意`1—3650天`作为充分保存依据；公众或机构部署的处理地点、跨境状态、删除能力或撤回途径未知时，M08阻断。

## 8. M09治疗类别参考接口

M09只响应明确的`treatment_background`、`category_comparison`或`maintenance_background`任务。调用前必须已有M00结果、M11业务路由和M02至M07之一的专业模块所有权。

- E0、E1直接停止M09；U1只保留M00就诊行动，不展开治疗背景；
- N1或S0且用户明确需要治疗背景时，单次最多返回三个紧密相关类别；
- 类别命中只提供一般目的、线下决定前提、其他方向和维护要求，不表示当前用户适合该类别；
- 未审核类别、请求模块不匹配、成人范围不匹配或来源缺失时必须阻断；
- M09不得修改M00等级、生成处方药决定、输出剂量疗程、器械参数、操作步骤、疗效保证或价格排序；
- 基础大模型只能依据M09返回的结构化背景组织语言，随后必须经过M11输出复核和M00发送前最终复核；
- M09最终人工审核、M11公共接入及作品集级文本前向工程验证已完成；外部专业验证完成前保持`production_enabled=false`。

## 9. M10证据检索与文献核验接口

M10只接收`clinical_evidence`、`diagnostic_method_background`、`treatment_background`、`maintenance_background`或`literature_recommendation`任务。调用前必须已有M00结果、M11业务路由、用户原话依据跨度和M01至M08事实字段编号。

- E0、E1停止普通检索；U1只返回M00行动；`NEEDS_CLARIFICATION`等待M00完成一次澄清。
- M11只能提供业务路由和允许检索模块，不得在路由中修改M00的等级、时效或去向。
- 查询必须按模块、知识类型、审核状态、运行范围和版权范围过滤。
- 关键词候选20、语义候选20，经RRF `k=60`融合前20，每类知识最多返回5项；语义服务缺失时明确标记词面检索降级。
- 排序分仅为工程检索分，不是医学置信度或疾病概率。
- `supports/conflicts/missing_clinician_evidence/context_only/retrieval_gap`由M11基于用户事实显式确定，相似度不得自动确定。
- M02/M03新增68项知识已于2026-08-13批准，可进入内部检索；M10整体仍受生产门禁约束。
- 文献正式推荐必须核验题名、作者、年份、出版类型、DOI或PMID、HTTPS落地页、适读人群、推荐理由、局限、30天内核验日期和未撤稿状态；单次最多3篇核心加2篇深入阅读。
- 接口失败或撤稿状态不明时不返回正式推荐，不允许基础模型补造引用。
- 检索内容固定为`reference_only`；提示注入内容、内部编号、本地文件路径、教材页面、境外服务入口和未核验引用不得进入用户输出。
- 草稿必须先经M11事实、来源和边界复核，再经M00发送前复核。
- M10最终人工审核、M11接入及作品集级文本前向工程验证已完成；当前22例未观察到相对Skill组的额外RAG增益，外部专业验证完成前仍保持`production_enabled=false`。

## 10. M11公共编排接口

公共入口为`MainAgent.orchestrate_dental_turn(...)`，由`M11Orchestrator.process_turn(...)`实现。每次调用必须提交当前轮M00结果、用户原文、事实记录、基础模型提出的路由候选及入口类型。

- M11保存同一`episode_id`内的`risk_floor_level`、事实账本和路由历史。
- M11返回`state_machine.current_state`、`phase`、`awaiting`和中文转移原因；该字段是主Agent执行的统一状态，M00的`next_state`只表示安全子状态。
- M11追加保存事实历史和纠正事件；用户纠正不覆盖原始事实，且要求M00纠错重算。
- 路由只允许M02-M07作为主模块；一次一个主模块和最多一个交叉模块。
- 路由分数为0至100工程相关度；差值不超过5.0时进入一次路由澄清，交叉模块最低60.0。
- `module_calls`只允许命中已确认路由及M08-M10；E0、E1、U1和`NEEDS_CLARIFICATION`禁止普通模块调用。
- 分道澄清每个`episode_id`最多一次，并且只在问题真正发出后消耗；仍不确定时保留`route_unresolved`并转通用口腔专业评估。
- M08产生新候选图像事实时，后续模块和基础模型草稿暂停，必须先取得新的M00复核结果；调用顺序固定为专业模块、M08、M10、M09。
- 用户纠正进入`M00_CORRECTION_RECHECK_WAIT`；调用方只有在M00完成纠错重算后才能提交`correction_recalculation_confirmed=true`恢复流程。
- 基础模型返回`text + claims + presentation`；M11按来源、事实字段、证据关系、能力边界、自适应栏目和中国化要求审核。
- M11另外保存已问问题及其目标事实。普通问诊每轮最多一个问题块、每块最多三个紧密相关的信息点，最多两轮且不得重复；紧急状态不得因追问延迟行动。
- 用户输出不再固定堆叠五段。普通流程生成包含四个核心栏目和最多两个条件栏目的“智慧口腔记录”；紧急行动、安全澄清、路由澄清和U1紧迫简版不展开完整记录。
- 输出计划提供移动端单列、电脑端八列记录加四列行动区、纯文字单列回退三种渲染配置；布局只能重排同一组审核后栏目，不得另行生成医学内容。
- 空栏目不得展示；治疗类别背景和文献推荐只在用户明确提出时放在记录之外。
- M11审核通过后必须取得M00的`final_guard`结果；在专业参考标准、真实图像验证与发布门禁完成前，不产生公共生产可发布的`user_output`。

完整说明见[M11主Agent编排契约](m11-orchestration.md)和[用户问询与智慧口腔记录契约](user-experience-and-output.md)。

### 10.1 M02与M03运行适配器

- M02、M03独立运行适配器已接入M11，分别只接受已审核的16个和17个专科事实字段及M01共享字段。
- 两个适配器均先读取M00，再验证M11路由；E0/E1停止、U1受限、照片交M08，新照片事实仍必须回M00。
- 每轮最多一个问题块，每块最多三个紧密相关的信息点。
- `offline_assessment`只表达线上不能确认的具体事项和线下评估方向，不设置风险等级、时效、诊断或必做检查。
- M02、M03均不直接读取未审核知识，不输出病名、病因、分期分级、预后、患牙确认或个人治疗方案。

## 11. 异常与失败

- Skill调用失败或结构无效时不得默认S0；主Agent运行最短安全筛查，并保守提示需要专业评估。
- 结构校验最多重试一次；E0/E1线索明确时不得等待重试。
- 无法确认精确科室时，使用附近综合医院急诊科、口腔急诊、口腔颌面外科或具备资质的口腔专业人员等中国化目的地。
- 错误信息、日志和用户文案均不输出姓名、电话号码、身份证号或精确住址。

## 12. M12评测门禁

- 规则衍生文本参考标签、专家裁决参考标准、模型评分器结果、三版本输出和真实图像结果分别存储，不互相冒充。
- 当前已生成120例开发文本、360例锁定文本、120例组合场景和200例图像试运行清单；另已完成22例、11组最小对照的三组独立前向工程验证。全部规则衍生参考标签仍待外部专业审核，图像资产尚待合法取得。
- 模型评分器只能辅助评估清晰度、相关性、结构、事实一致性和证据克制；未与人工标签校准前不得参与批量统计，且永远不能单独决定专家裁决参考标准。
- 任何发布阻断错误不得被总体平均分抵消。作品集级三组输出不能替代M08真实图像评测、专业双盲审核和发布验证；这些门禁未完成前，`production_enabled=false`。

## 13. 已确认契约

1. 是否接受`pre_gate / full_triage / final_guard`三种内部调用操作。
2. 是否接受硬规则优先，数值阈值只处理模糊意图；`0.35/0.85`作为待评测校准的工程初始值。
3. 是否接受输入和输出新增状态字段，并由`effective_level`约束主Agent动作。
4. 是否接受图像规则未审核前只保留技术质量字段，不允许自动生成临床程度或降低分流等级。
