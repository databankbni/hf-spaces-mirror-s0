from pydantic import BaseModel


class DomainScore(BaseModel):
    domain: str
    score: float
    reason: str


class EvaluationOutput(BaseModel):
    overall_score: float
    domain_scores: list[DomainScore]

    plan_completion_score: float
    completed_plan_items: list[str]
    missed_plan_items: list[str]
    unknown_plan_items: list[str]

    what_went_well: list[str]
    what_was_missing: list[str]

    main_bottleneck: str
    next_actions: list[str]

    markdown: str


class PlanBlock(BaseModel):
    activity: str
    duration_minutes: int
    domain: str
    reason: str


class PlanOutput(BaseModel):
    summary: str
    blocks: list[PlanBlock]
    success_criteria: list[str]
    warnings: list[str]
    markdown: str


class GoalRecommendation(BaseModel):
    goal_id: int
    action: str
    reason: str


class WeightRecommendation(BaseModel):
    domain: str
    current_weight: int
    proposed_weight: int
    reason: str


class OptimizationOutput(BaseModel):
    summary: str
    goal_recommendations: list[GoalRecommendation]
    weight_recommendations: list[WeightRecommendation]
    markdown: str