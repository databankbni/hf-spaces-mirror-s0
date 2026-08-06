# Model Context Protocol (MCP)

## What Problem Does MCP Solve?

Before MCP, if a developer wanted an AI model to connect to ten different external systems (a database, Slack, Google Drive, a calendar, etc.), they typically had to write ten separate, custom integrations — one per system, often per AI application. If a company had three different AI tools that each needed access to the same ten systems, that became up to thirty separate integrations. This is sometimes called the "N × M integration problem" — N applications times M data sources, each needing its own glue code.

MCP is an open standard, introduced by Anthropic in November 2024, that replaces this fragmented approach with one common protocol. Instead of custom one-off integrations, any AI application that supports MCP can connect to any system that exposes itself as an MCP server, using the same standardized method every time.

A common analogy: MCP is like a USB-C port for AI applications. Just as USB-C lets many different devices plug into many different cables and chargers without needing a unique connector for each combination, MCP lets AI applications plug into many different external systems through one shared interface.

## The Three Main Roles in MCP

- **Host**: the AI application itself — for example, an AI-powered IDE or a chat assistant. The host contains the LLM and decides when external help is needed.
- **Client**: a component inside the host that manages communication with one specific MCP server. If a host connects to three different servers, it typically runs three separate clients, one per server.
- **Server**: an external program that exposes specific capabilities — tools, resources (read-only data, like files or database records), and prompts (reusable templates) — that the host's LLM can use.

## What an MCP Server Can Expose

- **Tools**: actions the LLM can trigger, such as querying a database, running a calculation, or sending a message.
- **Resources**: read-only data the LLM can pull in as context, such as the contents of a specific file or a FAQ document.
- **Prompts**: reusable templates that structure how certain tasks should be approached.

When a host connects to a server, the client asks the server what it offers. The server replies with natural-language descriptions of each tool/resource and the format needed to use it. This description is what the LLM actually reads in order to decide whether and how to use that capability — which is why clear, well-written descriptions matter just as much in MCP as they do for any other agent tool.

## Why This Matters for Reducing Hallucination

LLMs generate text based on patterns learned during training, not by checking real-time facts. When asked something outside their training data — recent events, private company data, or anything that has changed since training ended — they can produce confident-sounding but incorrect answers. MCP helps address this by giving the LLM a standardized way to pull in real, current, externally verified information instead of relying purely on what it "remembers" from training.

## Security Considerations

Because MCP gives AI systems the ability to actually act on external systems, not just talk about them, security matters a great deal. The protocol includes concepts like "roots" — boundaries that limit which files or directories a server is allowed to access — and supports authentication standards to control who can connect to what. Security researchers have also pointed out real risks in practice, including prompt injection (where malicious instructions are hidden inside content the model processes) and the possibility of a compromised or malicious server returning manipulated data. These are active, ongoing concerns in the field, not solved problems — anyone building or connecting MCP servers needs to treat trust boundaries carefully, rather than assuming every connected tool is automatically safe to use.
