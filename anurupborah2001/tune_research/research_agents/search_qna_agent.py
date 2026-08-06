from agents import Agent
from pydantic import BaseModel, Field
from lib.env_var import MODEL, NO_OF_CLARIFYING_QUESTIONS

SEARCH_QNA_AGENT_INSTRUCTIONS = f"""You are a research clarification agent. Given a user's research query, come up
with exactly {NO_OF_CLARIFYING_QUESTIONS} clarifying questions to ask the user before researching the topic.
Each question should narrow down scope, audience, timeframe, or angle so the eventual web research is focused and
useful. For each question, explain your reasoning for why it matters to the query."""


class UserQuery(BaseModel):
    query: str = Field(description="A clarifying question to ask the user about their research query.")
    reason: str = Field(description="The reasoning for why this question is important to ask.")


class UserQueryPlan(BaseModel):
    queries: list[UserQuery] = Field(description=f"Exactly {NO_OF_CLARIFYING_QUESTIONS} clarifying questions to ask the user.")


search_qna_agent = Agent(
    name="Search QnA Agent",
    instructions=SEARCH_QNA_AGENT_INSTRUCTIONS,
    model=MODEL,
    output_type=UserQueryPlan,
)
