import asyncio
from agents import Runner, trace, gen_trace_id
from research_agents.planning_agent import WebSearchPlan, planner_agent, WebSearchItem
from research_agents.search_qna_agent import search_qna_agent, UserQueryPlan
from research_agents.search_agent import search_agent
from research_agents.writer_agent import writer_agent, ReportData
from research_agents.notification_agent import notification_agent


class ResearchManager:
    async def get_clarifying_questions(self, query: str) -> UserQueryPlan:
        """ Ask the Search QnA agent for clarifying questions about the query """
        result = await Runner.run(
            search_qna_agent,
            f"Query: {query}",
        )
        return result.final_output_as(UserQueryPlan)

    async def run(self, query: str, qna_pairs: list[tuple[str, str]]):
        """ Run the deep research process, yielding (status_log, plan_markdown, report_markdown,
        summary_markdown, followup_markdown) as it progresses. The report/summary/follow-ups are
        only populated once the report has been written; plan_markdown fills in as soon as the
        planner agent returns, so the UI can show *how* the report is being put together. """
        trace_id = gen_trace_id()
        log_lines: list[str] = []
        plan_md = ""

        def log(line: str) -> str:
            print(line)
            log_lines.append(line)
            return "\n".join(f"- {entry}" for entry in log_lines)

        with trace("Research trace", trace_id=trace_id):
            yield log(f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}"), plan_md, "", "", ""
            yield log("Planning searches based on your query and answers..."), plan_md, "", "", ""
            search_plan = await self.plan_searches(query, qna_pairs)
            plan_md = self._format_plan(search_plan)
            yield log(f"Planned {len(search_plan.searches)} searches. Searching the web..."), plan_md, "", "", ""
            search_results = await self.perform_searches(search_plan)
            yield log(f"Completed {len(search_results)} searches. Writing report..."), plan_md, "", "", ""
            report = await self.write_report(query, search_results)
            yield log("Report written. Sending notification..."), plan_md, "", "", ""
            await self.send_notification(report)
            followup_md = "\n".join(f"- {q}" for q in report.follow_up_questions) or "_No follow-up ideas suggested._"
            yield (
                log("Notification sent. Research complete."),
                plan_md,
                report.markdown_report,
                report.short_summary,
                followup_md,
            )

    @staticmethod
    def _format_plan(plan: WebSearchPlan) -> str:
        return "\n\n".join(
            f"**{i}. {item.query}**  \n_{item.reason}_" for i, item in enumerate(plan.searches, start=1)
        )

    async def plan_searches(self, query: str, qna_pairs: list[tuple[str, str]]) -> WebSearchPlan:
        """ Plan the searches to perform for the query """
        qna_text = "\n".join(f"Q: {question}\nA: {answer}" for question, answer in qna_pairs)
        result = await Runner.run(
            planner_agent,
            f"Query: {query}\nClarifying questions and answers:\n{qna_text}",
        )
        return result.final_output_as(WebSearchPlan)

    async def perform_searches(self, search_plan: WebSearchPlan) -> list[str]:
        """ Perform the web searches based on the search plan """
        results = []
        tasks = [asyncio.create_task(self.search(item)) for item in search_plan.searches]
        for task in asyncio.as_completed(tasks):
            search_result = await task
            if search_result is not None:
                results.append(search_result)
        return results

    async def search(self, item: WebSearchItem):
        """ Perform a search for the query """
        input = f"Search term: {item.query}\nReason for searching: {item.reason}"
        try:
            result = await Runner.run(
                search_agent,
                input,
            )
            return str(result.final_output)
        except Exception:
            return None

    async def write_report(self, query: str, search_results: list[str]) -> ReportData:
        """ Write the report for the query """
        input = f"Original query: {query}\nSummarized search results: {search_results}"
        result = await Runner.run(
            writer_agent,
            input,
        )
        return result.final_output_as(ReportData)

    async def send_notification(self, report: ReportData) -> None:
        """ Send the report to the user via email or Pushover """
        await Runner.run(
            notification_agent,
            report.markdown_report,
        )
