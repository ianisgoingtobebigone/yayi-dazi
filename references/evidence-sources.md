# 证据来源与规则映射

检索日期：2026-08-07。以下境外来源仅作为内部临床紧迫度依据，不将其电话号码或服务入口展示给中国用户。

## 主框架

1. [NHS England: Clinical guidance: unscheduled urgent and non-urgent dental care](https://www.england.nhs.uk/long-read/clinical-guidance-unscheduled-urgent-and-non-urgent-dental-care/)，发布于2025-05-01，更新于2025-10-03，出版编号PRN01927_ii。
   - 第3.1-3.4节：紧急、24小时内和7天内的照护分类。
   - 第7.2节：严重全身感染、气道或吞咽受累、眼部闭合、脱水、显著张口受限及既往治疗失败等升级因素。

2. [SDCEP: Management of Acute Dental Problems](https://www.acutedentalproblems.sdcep.org.uk/)，第2版，2026年3月。
   - [Timescales for treatment](https://www.acutedentalproblems.sdcep.org.uk/guidance/overarching-principles/timescales-for-treatment/)：立即医疗急诊、紧急牙科、24小时内、7天内和自我照护的时间定义。
   - [Pain pathway](https://www.acutedentalproblems.sdcep.org.uk/guidance/pathways-to-providers-of-care/pain-pathway/)：口腔或下颌痛开始时考虑少见心肌梗死表现和镇痛药过量。
   - [Acute apical abscess](https://www.acutedentalproblems.sdcep.org.uk/guidance/management-of-oral-conditions/common-oral-conditions/acute-apical-abscess/)：气道评估、肿胀、发热和紧急牙科照护。
   - [Acute pericoronitis](https://www.acutedentalproblems.sdcep.org.uk/guidance/management-of-oral-conditions/common-oral-conditions/acute-pericoronitis-including-erupting-teeth-in-children/)：吞咽不适、张口受限、面部肿胀和感染扩散。
   - [Pulpitis](https://www.acutedentalproblems.sdcep.org.uk/guidance/management-of-oral-conditions/common-oral-conditions/pulpitis/)：疼痛对常规缓解措施的反应可影响24小时或非紧急路径，但不能用于线上确诊。

## 患者表述交叉验证

3. [NHS: Toothache](https://www.nhs.uk/symptoms/toothache/)，最近审核2024-07-01，下次审核2027-07-01。
   - 疼痛持续超过2天应看牙医。
   - 眼周或颈部肿胀，以及影响呼吸、吞咽或说话的肿胀，应进入急诊评估。

4. [NHS: Dental abscess](https://www.nhs.uk/conditions/dental-abscess/)，2026-08-07访问。
   - 口腔大量肿胀、眼部疼痛或肿胀、视力变化、呼吸或吞咽困难及明显张口困难为立即升级线索。

5. [NHS: Heart attack](https://www.nhs.uk/conditions/heart-attack/)，2026-08-07访问。
   - 胸部紧缩或压榨感可向颈部和下颌扩散，并可伴呼吸困难、出汗、恶心等。

## 治疗边界交叉验证

6. [ADA: Antibiotics for Dental Pain and Swelling Guideline](https://www.ada.org/resources/research/science/evidence-based-dental-research/antibiotics-for-dental-pain-and-swelling)，2019年。
   - 多数牙髓及根尖周相关疼痛或局限肿胀不应仅靠抗生素处理。
   - 发热或乏力等全身受累表现需要提高警惕并由专业人员评估。
   - 本来源不用于中国就诊时效或处方建议。

## 规则对应

| 规则 | 主来源 |
|---|---|
| E0 气道、眼周、严重全身状态、严重外伤 | NHS England 3.2、7.2；SDCEP时效及感染章节 |
| E1 恒牙完全脱出、无法控制的口内出血 | NHS England 3.2 |
| U1 24小时内 | NHS England 3.3；SDCEP时效章节 |
| N1 2至7天内 | NHS England 3.4；NHS牙痛页面 |
| S0 有限观察 | SDCEP时效章节 |
| 下颌痛伴心脏相关表现 | SDCEP疼痛路径；NHS心肌梗死页面 |
| 镇痛药可能过量 | SDCEP疼痛路径；药物具体阈值尚未纳入本技能 |
| 抗生素禁限 | NHS England 7.1-7.2；ADA 2019 |

## M10来源与文献核验入口

核验日期：2026-08-12。M10最终审核完成前，以下入口仅用于内部实现和审计。

- [国家卫生健康委口腔相关病种诊疗指南（2022年版）发布页](https://www.nhc.gov.cn/wjw/c100378/202210/db6de17358944c8b9b270d1412d9bf62.shtml)：中国诊疗指南原始发布入口。
- [中华口腔医学会团体标准目录](https://hym.cndent.com/fg5a6m/)：中国口腔专业学会标准和共识入口。
- [NCBI APIs](https://www.ncbi.nlm.nih.gov/home/develop/api/)：PubMed检索和PMID元数据核验。
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)：DOI、题名、作者、年份、出版类型和更新关系核验。
- [Europe PMC Articles RESTful API](https://dev.europepmc.org/RestfulWebService)：出版元数据、版本及撤稿状态补充核验。

不得保存或分发无许可全文。接口失败、撤稿状态不明或元数据冲突时，不生成正式文献推荐。
