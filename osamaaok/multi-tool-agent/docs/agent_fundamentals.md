# AI Agent Fundamentals

## What is an AI Agent?

An AI agent is a system built around a core AI model (almost always a large language model, or LLM) that does more than just generate text in response to a prompt. An agent can reason about a problem, make a plan, take actions in the world using tools, and adjust based on what it observes — rather than simply producing a single text response and stopping.

A useful way to picture this: a plain LLM chatbot is like someone who can only talk. An agent is like someone who can talk, decide what needs doing, then actually go do it — checking a calendar, running a calculation, looking something up — before replying.

## The Thought → Action → Observation Cycle

This is the core loop almost every agent runs on:

- **Thought**: the LLM reasons about what the next step should be, given the user's request and everything that has happened so far.
- **Action**: the agent acts on that thought, usually by calling a tool with specific arguments.
- **Observation**: the agent looks at what the tool returned, and feeds that result back into its reasoning for the next step.

This cycle repeats until the agent decides it has enough information to give a final answer. It behaves like a loop in programming: it keeps going until some stopping condition (the task being complete) is met.

## Why Agents Need Tools

LLMs only take in text and only produce text. By themselves, they cannot check today's weather, run precise arithmetic, browse the internet, or query a database — they can only generate plausible-sounding text about those things, which is not the same as actually doing them.

A **tool** is a function made available to the LLM, with a clear, well-described purpose. The model doesn't call the tool directly itself — instead, it generates a structured request (in text) saying "call this tool with these arguments." The agent (the surrounding system, not the LLM) reads that request, actually executes the function, and feeds the result back to the LLM as an observation.

Two reasons tools matter so much:
1. **Reliability** — LLMs are often inaccurate at precise tasks like arithmetic, since they are predicting plausible text rather than computing an exact answer. A calculator tool guarantees a correct result instead of a guess.
2. **Freshness** — an LLM's knowledge is frozen at whatever point its training data ended. A search tool lets it retrieve real, current information instead of relying on outdated or absent internal knowledge.

## Designing Good Tools

A good tool description matters as much as the tool's actual code. The LLM decides which tool to use based on matching the user's question against each tool's description — so descriptions need to be specific and clearly differentiated from each other. Vague or overlapping descriptions lead the model to pick the wrong tool, or hesitate between similar-sounding options.

## Multi-Agent Systems

More advanced agentic systems can use multiple specialized agents coordinated by a manager agent, rather than one single agent trying to do everything. Each specialized agent can focus on a narrower kind of task, and the manager decides which specialist to route a given problem to — the same underlying idea as tool-routing, just applied at the level of whole agents instead of individual functions.
