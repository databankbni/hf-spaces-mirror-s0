# data/static/

Static identity files for ArunCore. These define who Arun is and how the agent is allowed to behave. They are the foundation layer of the knowledge base — loaded on every query regardless of what is retrieved.

---

## Files

### `public_profile.md`
Arun's public-facing professional identity. Contains:
- Name, title, and one-line positioning
- Core engineering stack
- Key projects (names + one-line descriptions)
- Professional values and working style
- What he's currently building and looking for

This file is injected as baseline context for every agent response. It ensures the agent always has a minimum accurate representation of Arun even for questions that don't match any specific project document.

### `rules_of_engagement.md`
The agent's answer policy. Defines:
- Truth-only rule: never speculate or fill gaps with plausible-sounding information
- Source citation requirement: every factual claim must be traceable
- Fallback behavior: what the agent says when it doesn't have the information
- Tone guidelines: professional, direct, first-person

---

## How These Files Are Used
When a query arrives, both files are included in the LLM context window as fixed system-level context. Retrieved chunks from the vector DB are appended on top. The agent synthesises an answer grounded in both layers.

---

## Update Frequency
These files should be updated whenever Arun's professional positioning, stack, or answer policy changes. They do not need to be re-embedded — they are injected directly as text, not retrieved via vector search.
