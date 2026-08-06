# Generative AI and RAG Fundamentals

## What "Generative AI" Means

Generative AI refers to models that produce new content — text, images, audio, code — rather than only classifying or scoring existing input. Large language models (LLMs) are the most common form of generative AI used in agent systems: they take text in and produce new text out, predicting what should come next based on patterns learned from enormous amounts of training data.

It's important to understand what this actually means underneath: an LLM does not "look up" facts the way a database does. It generates the statistically most plausible continuation of the text it has seen so far. This is exactly why LLMs can sometimes state incorrect information confidently — they are not retrieving a stored fact, they are generating plausible-sounding text, and "plausible" and "true" are not always the same thing.

## Why Prompt Engineering Matters

Because an LLM's output is shaped entirely by the text it receives as input, the way a request is phrased has a large effect on the quality and reliability of the response. Being specific, providing examples, specifying the exact output format needed, and separating instructions (system messages) from the actual task (user messages) all measurably change how well a model performs — this isn't a minor stylistic detail, it is often the difference between a usable and unusable response.

## What Retrieval-Augmented Generation (RAG) Is

RAG is a technique that combines an LLM's generative ability with a retrieval step over a specific set of documents. Instead of relying purely on what the model learned during training, the system first searches a document collection for the most relevant pieces of text related to the question, and then includes those retrieved pieces directly in the prompt sent to the LLM. The LLM then generates its answer grounded in that retrieved content, rather than purely from its own internal training-based memory.

This matters for two related reasons:
1. It lets the model answer questions about content it was never trained on — private documents, recent material, or anything specific to one organization or person.
2. It reduces hallucination, since the model has real source text in front of it to work from, rather than needing to recall or guess.

## How Retrieval Actually Works, at a High Level

1. Documents are broken into smaller chunks (paragraphs or sections, not whole documents at once, since whole documents are usually too long to be useful as a single retrieval unit).
2. Each chunk is converted into an **embedding** — a list of numbers that represents the meaning of that chunk in a high-dimensional mathematical space. Chunks with similar meaning end up with embeddings that are mathematically close to each other.
3. When a question comes in, the question itself is converted into an embedding using the same method.
4. The system searches for the stored chunk embeddings that are mathematically closest to the question's embedding — this is a similarity search, commonly implemented using a vector index such as FAISS.
5. The closest-matching chunks are retrieved and inserted into the prompt sent to the LLM, alongside the original question.

## RAG as a Tool, Inside an Agent

In an agentic system, RAG retrieval can be wrapped as one tool among several. The agent doesn't always need to search a specific document set — only when the question is actually about that document set's specific content. This is different from a general web search tool (which looks at the open internet) and different from just asking the LLM directly (which only uses what it learned during training). Choosing correctly between "answer from general knowledge," "search the web," and "search my own documents" is itself a meaningful reasoning step the agent has to get right.
