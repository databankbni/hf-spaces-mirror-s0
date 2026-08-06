from agents import Agent
from pydantic import BaseModel, Field
from lib.env_var import MODEL, NO_OF_SEARCHES

PLANNING_AGENT_INSTRUCTIONS = f"""You are a research agent planner. You will be given the original query asked by the
user together with clarifying questions and the user's answers to them.
Combine the query and the question/answer pairs and come up with a set of web searches to best answer the query.
You should output exactly {NO_OF_SEARCHES} search terms.
You should also provide reasoning for why each search is important to the query."""


class WebSearchItem(BaseModel):
    reason: str = Field(description="Your reasoning for why this search is important to the query.")
    query: str = Field(description="The search term to use for the web search.")


class WebSearchPlan(BaseModel):
    searches: list[WebSearchItem] = Field(description="A list of web searches to perform to best answer the query.")


planner_agent = Agent(
    name="Planner Agent",
    instructions=PLANNING_AGENT_INSTRUCTIONS,
    model=MODEL,
    output_type=WebSearchPlan,
)
