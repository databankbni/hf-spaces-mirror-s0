from pydantic import BaseModel


class OverviewResponse(BaseModel):
    session_id: str
    repo_name: str
    repo_url: str
    branch: str
    total_files: int
    total_lines: int
    total_functions: int
    total_classes: int
    languages: dict[str, float]          # lang → percentage
    top_modules: list[str]               # top-level dirs / key files
    complexity_score: float              # 0.0–10.0
    risk_score: float                    # 0.0–10.0 (from risk agent)
    contributors: int
    last_commit: str | None             # ISO-8601 datetime string
    entry_points: list[str]             # detected main / app entry files
    readme_summary: str | None         # first 300 chars of README
