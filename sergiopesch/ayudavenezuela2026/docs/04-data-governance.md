# Data Governance And Safety

## Governance Stance

AyudaVenezuela2026 should adopt humanitarian data responsibility from the first line of code. The platform will handle personal, location, health, protection, and possibly politically sensitive data during a chaotic emergency. The default posture is minimization, verification, redaction, and time-limited use.

## Data Classes

| Class | Examples | Handling |
| --- | --- | --- |
| Public operational info | approved service points, donation guidance, public instructions | publish only after partner approval |
| Aggregate needs | WASH gaps by parish, shelter demand by municipality | publish when risk assessed |
| Partner operational data | road access, facility capacity, supply routes | role-gated |
| Personal data | names, phones, household details | encrypted, access-limited, retention-limited |
| Sensitive personal data | health, children, disability, GBV, migration status | strict role gating; no public output |
| Raw evidence | screenshots, voice notes, photos | encrypted; redact; delete when no longer needed |
| AI outputs | extracted entities, classifications, geocodes, summaries | advisory; store provenance and confidence |

## Verification Model

Every report must include:

- source type;
- received timestamp;
- observed timestamp if available;
- verification status;
- last reviewer;
- last reviewed timestamp;
- confidence and reason, if AI-assisted;
- publication safety status.

Verification states:

- `unverified`
- `plausible`
- `duplicate_candidate`
- `contacted`
- `confirmed_by_partner`
- `confirmed_by_field_team`
- `contradicted`
- `stale`
- `unsafe_to_publish`
- `resolved`

## Access Model

Suggested roles:

- public viewer;
- community submitter;
- volunteer validator;
- partner responder;
- cluster coordinator;
- protection focal point;
- admin;
- auditor.

Role design rules:

- protection, health, missing-person, and child-related data need specialized access;
- public viewers never see exact personal locations;
- validators see only records assigned to their scope unless explicitly elevated;
- every sensitive record read/write is logged;
- exports respect the same redaction rules as the UI.

## Retention Rules

Starter policy:

- raw screenshots/audio/photos: delete or anonymize within 30 days unless required for active casework;
- contact details: delete or tokenize within 90 days after case closure;
- missing-person cases: retain only under partner-approved family tracing policy;
- aggregate operational data: retain for analysis where disclosure risk is low;
- audit logs: retain under legal and partner agreement requirements.

## AI Safety Rules

- AI suggestions must be editable and rejectable.
- AI confidence must be visible.
- Low-confidence geocodes should stop at admin area, not exact point.
- No AI-only publication.
- No automated denial of aid, rescue, medical support, or family tracing.
- No model training on sensitive personal, Indigenous language, or child/protection data without explicit governance approval and consent.
- Maintain model cards, data sheets, evaluation sets, and incident reviews.

## Indigenous And Community Data

For Indigenous-language or community-owned data:

- collect only with community consent;
- involve community reviewers in message design and translation;
- do not assume Spanish literacy;
- support voice, icons, and assisted reporting;
- avoid extracting or publishing ethnicity unless required for a specific protection or inclusion purpose;
- apply CARE principles: collective benefit, authority to control, responsibility, and ethics.

## Fraud And Misinformation

The platform should include:

- vetted donation registry;
- scam/fraud report intake;
- rumor clustering;
- validation queue for repeated claims;
- public correction templates;
- source provenance on all public claims.

Do not assign opaque "truth scores" to people or communities. Track claims, evidence, validation status, and public response.

