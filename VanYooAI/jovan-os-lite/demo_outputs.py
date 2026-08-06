def demo_plan_output():
    return """# Daily Plan

## Summary
This demo plan balances focused study, project progress, light training, and a small optional visibility task. It is synthetic sample content for hosted portfolio preview.

## Priority Tasks

### Formal Education
- Complete one 75-minute study block on a clearly defined topic.
- Write a short closure note with what was finished and the next step.

### Projects / Skill Building
- Complete one 60-minute project work block.
- Fix or improve one small, visible part of the project.

### Health / Training
- Complete 20 minutes of training, mobility, or recovery work.

### Career Visibility
- Optional: write one short public-safe progress note or update a project README.

## Time Allocation

| Activity | Duration |
|---|---:|
| Study block | 75 min |
| Project work | 60 min |
| Training or mobility | 20 min |
| Closure notes | 10 min |

## Success Criteria
- One study block completed.
- One project improvement completed.
- Training or mobility is either completed or explicitly rescheduled.
- The day ends with a clear next step.
"""


def demo_evaluation_output():
    return """# Daily Evaluation

## Overall Score
7.2/10

_Python weighted score. LLM initial estimate: 7.0/10._

## Plan Execution

### Completed
- Completed one focused study block.
- Fixed one small project issue and documented the result.

### Missed
- Training was explicitly skipped due to time constraints.

### Unknown
- Career visibility task was not mentioned.

### Plan Completion Score
7/10

## Domain Scores

### Formal Education: 8/10
The study block was completed with useful focus and clear progress.

### Projects / Skill Building: 8/10
The project task produced a concrete improvement.

### Health / Training: 4/10
Training was missed, but the reason was explicit and can be corrected tomorrow.

### Career Visibility: 5/10
No visibility output was mentioned, so this remains neutral rather than failed.

## What Went Well
- Two core execution blocks were completed.
- The project work had a visible output.

## What Was Missing
- Training needs a smaller fallback option on busy days.
- The final closure note could be more explicit.

## Main Bottleneck
The day had enough focus for cognitive work, but not enough protected time for health maintenance.

## Next Actions
1. Schedule training earlier or reduce it to a 10-minute minimum fallback.
2. Keep the next study block narrow and outcome-based.
3. End the next project block with one visible artifact or note.
"""


def demo_weekly_review_output():
    return """# Weekly Review

## Overall Score
7.4/10

_Python weighted score. LLM initial estimate: 7.3/10._

## Weekly Pattern
The week shows consistent progress in study and project work, with weaker consistency around training and public visibility.

## Strongest Momentum
- Study blocks were completed on multiple days.
- Project work produced practical improvements.
- The system maintained a useful plan/evaluate/review loop.

## Main Bottlenecks
- Training was too easy to skip when the day became crowded.
- Some work ended without a clear closure note or next action.
- Visibility tasks were useful but treated as optional too often.

## Recommended Operating Rule
Every focused work block should end with one short note: what changed, what remains, and the next action.

## Next Week Targets
- Complete three focused study blocks.
- Complete two concrete project improvements.
- Complete three short training or mobility sessions.
- Publish or prepare one small public-safe project update.
"""


def demo_optimizer_output():
    return """# Optimizer Report

## System Diagnosis
Execution is strongest when the plan is small, concrete, and tied to a visible output. The main improvement area is consistency across health and visibility tasks.

## Recommended Weight Changes

| Domain | Current | Proposed | Reason |
|---|---:|---:|---|
| Formal Education | 30 | 30 | Keep stable because study remains a core priority. |
| Projects / Skill Building | 30 | 30 | Keep stable because project output is the strongest portfolio signal. |
| Health / Training | 20 | 20 | Keep stable, but use smaller fallback sessions. |
| Career Visibility | 20 | 20 | Keep stable and attach it to project completion. |

## Concrete Targets
- Finish one study block with a written next step.
- Ship one project improvement that can be shown or explained.
- Complete one minimum viable training or mobility session.
- Add one public-safe visibility artifact when project work is finished.

## Main Risk
The user may complete useful work without leaving enough evidence or closure, making progress harder to evaluate later.

## Apply Decision
Review only. Human approval is required before applying any weight changes.
"""


def demo_apply_weights_output():
    return """## Apply

Demo Mode: no database weights were changed.

Hosted demo mode uses static sample outputs and synthetic data. In local live mode, this button applies the latest human-approved optimizer weight recommendations to SQLite.
"""