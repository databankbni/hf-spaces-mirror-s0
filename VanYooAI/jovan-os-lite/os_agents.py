from agents import Agent, Runner
from prompts import evaluator_instructions, planner_instructions, optimizer_instructions
from schemas import EvaluationOutput, PlanOutput, OptimizationOutput
from dotenv import load_dotenv

load_dotenv(override=True)

def build_context(goals, weights, recent_logs, recent_evaluations=None):
    return f"""
CURRENT GOALS:
{goals}

CURRENT DOMAIN WEIGHTS:
{weights}

RECENT LOGS:
{recent_logs}

RECENT EVALUATIONS:
{recent_evaluations or []}
"""


async def evaluate_day(day_log, latest_plan, goals, weights, recent_logs, recent_evaluations=None):
    agent = Agent(
        name="Jovan OS Evaluator",
        instructions=evaluator_instructions(),
        model="gpt-5.4",
        output_type=EvaluationOutput,
    )

    context = build_context(goals, weights, recent_logs, recent_evaluations)

    message = f"""
    Evaluate this day.

    Return structured output according to the EvaluationOutput schema.

    The markdown field should contain a clean markdown version of the evaluation.

    LATEST PLAN:
    {latest_plan}

    USER EXECUTION LOG:
    {day_log}

    CONTEXT:
    {context}

    Compare the user's execution log against the latest plan.

    Identify:
    - completed plan items
    - missed plan items
    - unknown plan items
    - plan completion score
    - domain scores
    - overall execution quality
    """

    result = await Runner.run(agent, message)
    return result.final_output


async def plan_day(request, goals, weights, recent_logs, recent_evaluations=None):
    agent = Agent(
        name="Jovan OS Planner",
        instructions=planner_instructions(),
        model="gpt-5.4",
        output_type=PlanOutput,
    )

    context = build_context(goals, weights, recent_logs, recent_evaluations)

    message = f"""
Create a realistic daily plan.

Return the answer in markdown.

Format:

# Daily Plan

## Summary
...

## Priority Tasks

### Formal Education
- ...

### Informal Education
- ...

### Sport
- ...

### Career
- ...

## Time Allocation
| Activity | Duration |
|----------|----------|
| ... | ... |

## Success Criteria
- ...
- ...
- ...

USER REQUEST:
{request}

CONTEXT:
{context}

"""

    result = await Runner.run(agent, message)
    return result.final_output



async def optimize_goals(
    goals,
    weights,
    recent_logs,
    recent_evaluations
):
    agent = Agent(
        name="Goal Optimizer",
        instructions=optimizer_instructions(),
        model="gpt-5.4",
        output_type=OptimizationOutput,
    )

    context = build_context(
        goals,
        weights,
        recent_logs,
        recent_evaluations
    )

    message = f"""
Review the current system.

Suggest:

- goal changes
- goal completions
- goal additions
- weight adjustments

Return structured output according to OptimizationOutput.

CONTEXT:

{context}
"""

    result = await Runner.run(agent, message)

    return result.final_output

async def evaluate_week(goals, weights, recent_logs, recent_evaluations, recent_plans):
    agent = Agent(
        name="Jovan OS Weekly Evaluator",
        instructions=evaluator_instructions(),
        model="gpt-5.4",
        output_type=EvaluationOutput,
    )

    context = build_context(goals, weights, recent_logs, recent_evaluations)

    plans_text = "\n\n---\n\n".join(
        [plan[2] for plan in recent_plans]
    ) if recent_plans else "No recent plans available."

    message = f"""
Evaluate this week.

Return structured output according to the EvaluationOutput schema.

This is a WEEKLY REVIEW, not a daily review.

IMPORTANT:
The markdown field must start with:

# Weekly Review

Do not use "# Daily Evaluation" for weekly reviews.

Be stricter about:
- consistency
- repeated patterns
- domains that are repeatedly skipped
- whether execution matches current goals
- whether the current domain weights still make sense
- concrete progress toward goals

RECENT PLANS:
{plans_text}

CONTEXT:
{context}

Analyze:
- what improved this week
- what kept repeating as a bottleneck
- which domains were strong
- which domains were weak
- what should be the focus next week

The markdown field should contain a clean Serbian Latin markdown weekly review.
"""
    result = await Runner.run(agent, message)
    return result.final_output

async def optimize_goals(goals, domain_weights, recent_logs, recent_evaluations):
    optimizer_agent = Agent(
        name="Jovan OS Optimizer",
        instructions=optimizer_instructions(),
        output_type=OptimizationOutput,
    )

    message = f"""
Optimize the user's personal operating system.

Return structured output according to the OptimizationOutput schema.

CURRENT GOALS:
{goals}

CURRENT DOMAIN WEIGHTS:
{domain_weights}

RECENT LOGS:
{recent_logs}

RECENT EVALUATIONS:
{recent_evaluations}

Analyze:
- whether current goals still make sense
- whether domain weights are balanced
- repeated bottlenecks
- weak domains
- strong momentum
- what should stay unchanged
- what small changes should be recommended

Do not apply any changes.
Only recommend changes.
"""

    result = await Runner.run(
        optimizer_agent,
        message,
    )

    return result.final_output

