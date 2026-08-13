# M08 image observation module

Use M08 only after M00 has produced a non-halt result and M11 has identified the business route. Require one of the 17 approved image tasks, a specific user goal, an authorized-source record, current-consultation consent, and all eight quality components.

The 93 general rules, 12 capture views, and 16 orthodontic observation profiles are approved for internal integration. Keep every runtime item disabled and keep production disabled until independent real-image validation passes the release gates.

## Orthodontic capture views

Keep the image `task` separate from `capture_view`: the task states why the image is being inspected, while the capture view records which standardized photograph was supplied. For the eight standard orthodontic tasks, require a compatible view.

Use eight core views for a complete orthodontic/aesthetic record: `frontal_rest`, `profile_rest`, `frontal_smile`, `intraoral_right`, `intraoral_frontal`, `intraoral_left`, `upper_arch`, and `lower_arch`. Request only the minimum views needed for the user's current goal; never require all eight by default.

Use four conditional views only when a core view cannot answer the bounded visible question: `oblique_45_rest`, `profile_smile`, `oblique_45_smile`, and `anterior_overbite_overjet`. Do not derive millimetre measurements, malocclusion grades, formal classifications, or dental-versus-skeletal origin from ordinary phone photographs.

## Orthodontic observation profiles

The catalog contains 16 approved, source-linked orthodontic profiles: nine manifestation profiles and seven appliance, hygiene, retention, or post-treatment profiles. A profile constrains the image task and the allowed observation type; it does not authorize a diagnosis. Approval does not enable production use before independent real-image validation.

For crowding, spacing, anterior prominence, anterior reverse or increased horizontal relation, posterior transverse relation, deep anterior overlap, and vertical-gap concerns, use neutral in-frame descriptions only. Do not output the clinical anchor as a current-user diagnosis or grade. For fixed, removable, clear-aligner, and retention appliances, describe visible integrity, position, surrounding soft-tissue appearance, or surface covering only. Comparable historical and current photographs may preserve a visible difference but must not label it orthodontic relapse.

Reject a profile when its task or observation type is incompatible. The four additional allowed observation types are `anterior_horizontal_relation_in_frame`, `anterior_vertical_relation_in_frame`, `posterior_transverse_relation_in_frame`, and `lip_posture_in_frame`.

## Numeric scoring

Score each quality component with exactly one value from `0, 25, 50, 75, 100`. Calculate the weighted score with:

```text
file_integrity 10%
target_coverage 20%
focus_detail 20%
exposure_color 10%
view_pose 15%
perspective 10%
obstruction 10%
comparability 5%
```

Classify `85.0–100.0` as `suitable`, `60.0–84.9` as `partially_suitable`, and below `60.0` as `not_suitable`. A hard failure always produces `not_suitable`. Permit color descriptions only when the exposure/color component is at least `75` and no strong filter or edit is present.

For every candidate observation, provide numeric `location_confidence_score` and `observation_confidence_score` from 0 to 100. Set the effective score to the minimum of both scores and the image-task quality score.

- `85.0–100.0`: write a neutral visible fact.
- `70.0–84.9`: write only a bounded visible possibility with limitations.
- `50.0–69.9`: withhold the fact and request one clarification or safe recapture.
- below `50.0`: discard the observation.

Before real-image calibration, mark every score `engineering_score_unvalidated`. Never present it as a disease, diagnosis, malignancy, or treatment probability.

## Observation boundaries

Describe only count, distribution, side, symmetry in the image, shape, boundary visibility, surface appearance, visible covering, color under valid color conditions, elevation, depression, surface discontinuity, fissure, defect, visible blood or trace, alignment, spacing, crowding, midline relation in the image, and visible prosthesis or appliance condition.

Do not infer diagnosis, severity stage, benign or malignant nature, pathogen, tissue origin, texture, tenderness, fluctuation, depth, mobility, probing bleeding, periodontal pockets, attachment loss, skeletal classification, fracture, deep infection, joint-disc status, nerve localization, radiology findings, treatment indication, or an individual treatment plan.

Treat X-rays, panoramic radiographs, CBCT, CT, MRI, ultrasound, and pathology slides as outside the ordinary-photo interpretation scope. A report-page task may extract visible report text but must preserve it as a clinician-record source and must not interpret the medical image itself.

## Safety and fusion

Preserve text and image facts separately. Photo nonvisibility never negates a user-reported symptom. Preserve historical and current sources separately. Transfer a safety-relevant image candidate to M00 at an effective score of `50.0` or above; M08 never assigns or lowers urgency. Return every image result to M00 before M11 or the requesting specialist module continues.

For U1, do not request recapture. In ordinary states, return at most one safe recapture instruction. Never ask a user to probe, squeeze, scrape, puncture, forcibly open, reposition, remove, or adjust tissue, a restoration, or an appliance.

## Privacy

Current-consultation consent does not imply evaluation or training consent. Keep `secondary_use_consent` and `training_use_consent` false by default. Minimize views, avoid collecting a full face when unnecessary, remove location metadata unless required, provide a concrete retention period, and support audited withdrawal and deletion.

Keep production disabled until the locked independent test set passes every release threshold in `evidence/54-m08-image-annotation-and-evaluation.md`.
