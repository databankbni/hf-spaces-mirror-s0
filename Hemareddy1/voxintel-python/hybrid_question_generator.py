"""
hybrid_question_generator.py
------------------------------
Phase 1 — Hybrid Personalized Interview Generation

Produces interview question lists that combine:
  50% Resume-Based Questions  — from skills, projects, experience, certifications
  50% Dataset-Based Questions — from the Node.js Question DB (passed in as JSON)

The Python service does NOT have direct DB access.
The Node.js caller passes the dataset questions as part of the request payload.

Distribution rules:
  10 questions → 5 resume + 5 dataset
  20 questions → 10 resume + 10 dataset
  Any N        → ceil(N * 0.5) resume + floor(N * 0.5) dataset

Source tracking:
  Every returned question has a "source" field: "resume" | "dataset"

Anti-duplication:
  Tracks used concepts to avoid semantic overlap.
"""

import math
import random
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


# ── Question templates for each skill ─────────────────────────
# Extended from question_generator.py with more coverage

SKILL_QUESTION_POOL: Dict[str, List[Dict]] = {
    "react": [
        {"q": "Explain how the Virtual DOM works in React and why it improves rendering performance.", "concepts": ["virtual dom", "reconciliation"]},
        {"q": "What is the difference between useEffect with an empty dependency array vs. with dependencies vs. no array?", "concepts": ["useEffect", "lifecycle"]},
        {"q": "How do you optimize a React component tree that re-renders too frequently?", "concepts": ["memoization", "useMemo", "useCallback", "re-render"]},
        {"q": "What is React's Context API and when would you choose it over a state management library?", "concepts": ["context", "state management"]},
        {"q": "How does React's reconciliation algorithm (Fiber) decide what to re-render?", "concepts": ["fiber", "reconciliation", "key prop"]},
        {"q": "Explain the difference between controlled and uncontrolled components in React.", "concepts": ["controlled", "uncontrolled", "refs"]},
    ],
    "node.js": [
        {"q": "How does Node.js handle thousands of concurrent connections with a single thread?", "concepts": ["event loop", "non-blocking", "libuv"]},
        {"q": "What is the purpose of the cluster module in Node.js and when would you use it?", "concepts": ["cluster", "worker", "cpu"]},
        {"q": "How do you handle memory leaks in a long-running Node.js process?", "concepts": ["memory leak", "heap", "gc"]},
        {"q": "Explain readable and writable streams in Node.js. When would you use them over loading data into memory?", "concepts": ["streams", "pipe", "buffer"]},
        {"q": "What is the difference between process.nextTick(), setImmediate(), and setTimeout() in Node.js?", "concepts": ["event loop", "microtask", "macrotask"]},
    ],
    "python": [
        {"q": "What is the difference between multiprocessing, multithreading, and asyncio in Python? When would you use each?", "concepts": ["GIL", "concurrency", "async"]},
        {"q": "Explain Python's garbage collector and how it handles reference cycles.", "concepts": ["gc", "reference counting", "cyclic"]},
        {"q": "How do you write a thread-safe Python class that can be safely used from multiple threads?", "concepts": ["threading", "lock", "thread safety"]},
        {"q": "What are Python decorators and how would you implement one that caches function results?", "concepts": ["decorator", "functools", "caching"]},
        {"q": "How would you profile a slow Python script to find performance bottlenecks?", "concepts": ["profiling", "cProfile", "performance"]},
    ],
    "mongodb": [
        {"q": "When would you use embedding vs. referencing (normalization) for related documents in MongoDB?", "concepts": ["embedding", "referencing", "denormalization"]},
        {"q": "How does MongoDB's aggregation pipeline work? Describe a real use-case with at least two stages.", "concepts": ["aggregation", "pipeline", "stages"]},
        {"q": "What indexing strategies do you use to speed up MongoDB queries?", "concepts": ["index", "compound index", "explain"]},
        {"q": "How do you handle multi-document transactions in MongoDB and what are the limitations?", "concepts": ["transaction", "acid", "session"]},
    ],
    "postgresql": [
        {"q": "What is the difference between a clustered index and a non-clustered index in PostgreSQL?", "concepts": ["index", "heap", "B-tree"]},
        {"q": "How do you use EXPLAIN ANALYZE to debug a slow query in PostgreSQL?", "concepts": ["explain", "query plan", "sequential scan"]},
        {"q": "What are Common Table Expressions (CTEs) and recursive CTEs? Give an example use case.", "concepts": ["CTE", "recursive", "WITH clause"]},
        {"q": "How does PostgreSQL implement MVCC (Multi-Version Concurrency Control)?", "concepts": ["MVCC", "transaction isolation", "visibility"]},
    ],
    "docker": [
        {"q": "What is the difference between a Docker image and a container? How does the layered filesystem work?", "concepts": ["image", "container", "layer"]},
        {"q": "How do you reduce a Docker image size for production without sacrificing functionality?", "concepts": ["multi-stage build", "alpine", "layer optimization"]},
        {"q": "Explain Docker networking modes. How do containers in the same network communicate?", "concepts": ["bridge network", "host network", "overlay"]},
    ],
    "aws": [
        {"q": "Which AWS services have you worked with and what did you specifically use each for?", "concepts": ["ec2", "s3", "lambda", "rds"]},
        {"q": "What is the difference between EC2, ECS (Fargate), and Lambda? When would you choose each?", "concepts": ["serverless", "containers", "vms"]},
        {"q": "How do you manage IAM roles and policies securely — what is the principle of least privilege?", "concepts": ["IAM", "roles", "least privilege"]},
    ],
    "typescript": [
        {"q": "What are generics in TypeScript? Give an example of a generic function or class you've written.", "concepts": ["generics", "type safety", "reusability"]},
        {"q": "What is the difference between interface and type alias in TypeScript? When do you prefer one over the other?", "concepts": ["interface", "type alias", "structural typing"]},
        {"q": "How does TypeScript's structural typing work and how is it different from nominal typing?", "concepts": ["structural typing", "duck typing", "compatibility"]},
    ],
    "machine learning": [
        {"q": "Walk me through how you approach a new machine learning classification problem end-to-end.", "concepts": ["classification", "pipeline", "evaluation"]},
        {"q": "How do you handle class imbalance in a training dataset?", "concepts": ["class imbalance", "SMOTE", "class weight"]},
        {"q": "Explain the bias-variance tradeoff and how it affects model selection.", "concepts": ["bias", "variance", "overfitting", "underfitting"]},
        {"q": "What cross-validation strategy do you use and why is it important to avoid data leakage?", "concepts": ["cross-validation", "k-fold", "data leakage"]},
    ],
    "redis": [
        {"q": "What data structures does Redis support and what is each used for in practice?", "concepts": ["string", "hash", "list", "set", "sorted set"]},
        {"q": "How would you implement a distributed rate limiter using Redis?", "concepts": ["rate limiting", "sliding window", "lua script"]},
        {"q": "How do you use Redis as a distributed lock? What problems can arise?", "concepts": ["distributed lock", "SETNX", "expiry", "deadlock"]},
    ],
    "kubernetes": [
        {"q": "Explain the relationship between a Pod, Deployment, and Service in Kubernetes.", "concepts": ["pod", "deployment", "service", "selector"]},
        {"q": "How does Kubernetes handle rolling updates and rollbacks?", "concepts": ["rolling update", "rollback", "replicaset"]},
        {"q": "What is a Kubernetes Ingress and how does it differ from a Service?", "concepts": ["ingress", "load balancing", "HTTP routing"]},
    ],
    "django": [
        {"q": "Explain Django's ORM and how you'd optimize a query that performs N+1 database hits.", "concepts": ["ORM", "select_related", "prefetch_related", "N+1"]},
        {"q": "How does Django's middleware pipeline work and how would you write a custom middleware?", "concepts": ["middleware", "request", "response", "pipeline"]},
    ],
    "flask": [
        {"q": "What is Flask's application context vs. request context? When does each exist?", "concepts": ["application context", "request context", "g"]},
        {"q": "How do you structure a large Flask application using Blueprints and Factories?", "concepts": ["Blueprint", "application factory", "modularity"]},
    ],
    "fastapi": [
        {"q": "How does FastAPI use Python type hints and Pydantic to provide automatic validation?", "concepts": ["Pydantic", "type hints", "validation", "openapi"]},
        {"q": "How do you handle background tasks and async endpoints in FastAPI?", "concepts": ["BackgroundTasks", "async", "await", "dependency injection"]},
    ],
    "tensorflow": [
        {"q": "What is the difference between eager execution and graph execution in TensorFlow?", "concepts": ["eager", "graph", "tf.function"]},
        {"q": "How do you save and load a TensorFlow model for production serving?", "concepts": ["SavedModel", "TF Serving", "checkpoints"]},
    ],
    "pytorch": [
        {"q": "How does PyTorch's autograd mechanism work for computing gradients?", "concepts": ["autograd", "backward", "computational graph"]},
        {"q": "What is the difference between DataLoader, Dataset, and IterableDataset in PyTorch?", "concepts": ["DataLoader", "Dataset", "batching"]},
    ],
    "git": [
        {"q": "What is the difference between git merge and git rebase? When do you prefer each?", "concepts": ["merge", "rebase", "history"]},
        {"q": "How do you recover from a bad git rebase that has been pushed to a remote?", "concepts": ["force push", "reflog", "reset"]},
    ],
    "microservices": [
        {"q": "What are the main challenges of a microservices architecture compared to a monolith?", "concepts": ["network latency", "distributed tracing", "service discovery"]},
        {"q": "How do microservices communicate — synchronous (REST/gRPC) vs. asynchronous (message queue)? When do you prefer each?", "concepts": ["REST", "gRPC", "Kafka", "RabbitMQ"]},
    ],
}

# ── Project-Based Question Templates ─────────────────────────

PROJECT_TEMPLATES = [
    "Walk me through the overall architecture of your {project} project — what problem does it solve and how is it structured?",
    "What was the most technically challenging aspect of building {project}?",
    "Why did you choose {tech} for {project} over other alternatives?",
    "How does data flow through {project} — from the user's action all the way to the database and back?",
    "If you were rebuilding {project} from scratch today, what decisions would you make differently?",
    "How would you scale {project} to handle 10x more concurrent users?",
    "How did you handle authentication and authorization in {project}?",
    "Tell me about a bug or performance issue you encountered in {project} and how you resolved it.",
    "What are the current limitations of {project} and how would you address them in the next version?",
    "How did you ensure data consistency and handle edge cases in {project}?",
]

PROJECT_TEMPLATES_AI = [
    "How did you train and evaluate the ML/AI model used in {project}? What metrics did you optimize?",
    "What dataset did you use for {project} and how did you handle data quality and bias?",
    "How do you serve the model in {project} — batch inference or real-time? Why?",
]

PROJECT_TEMPLATES_CLOUD = [
    "What cloud infrastructure did you use for {project} and how is it deployed?",
    "How do you handle logging, monitoring, and alerting for {project} in production?",
]

# ── Experience-based question templates ──────────────────────

EXPERIENCE_TEMPLATES = [
    "In your role as {role}, describe how you handled a technically difficult problem or architecture decision.",
    "As a {role}, how did you collaborate with other team members — what was your contribution to the overall system?",
    "Tell me about a performance optimization you made as a {role} and how you measured its impact.",
    "Describe a situation where you had to learn a new technology quickly in your {role} position. How did you approach it?",
]

# ── Difficulty normalization map ──────────────────────────────

LEVEL_TO_DB_DIFFICULTY = {
    "Beginner": "easy",
    "Intermediate": "medium",
    "Advanced": "hard",
    "Expert": "hard",
    "Junior": "easy",
    "Senior": "hard",
}


# ── Question source constants ─────────────────────────────────

SOURCE_RESUME = "resume"
SOURCE_DATASET = "dataset"


# ── Resume-based question generator ──────────────────────────

def generate_resume_questions(
    parsed: Dict,
    intelligence: Dict,
    count: int,
) -> List[Dict]:
    """
    Generate `count` resume-based questions from:
      1. Skill-specific probing questions
      2. Project architecture / implementation questions
      3. Experience-based situational questions
      4. Certification-derived questions
    """
    questions = []
    used_concepts: set = set()

    def _add_if_new(q_dict: Dict) -> bool:
        concepts = set(q_dict.get("_concepts", []))
        overlap = concepts & used_concepts
        if len(overlap) >= len(concepts) * 0.7 and overlap:
            return False
        used_concepts.update(concepts)
        q_dict.pop("_concepts", None)
        questions.append(q_dict)
        return True

    skills = [s.lower() for s in parsed.get("skills", []) + parsed.get("technologies", [])]
    projects = parsed.get("projects", [])
    experience = parsed.get("experience", [])
    certifications = parsed.get("certifications", [])
    candidate_level = intelligence.get("candidateLevel", "Intermediate")
    recommended_difficulty = intelligence.get("recommendedDifficulty", "Intermediate")

    # Map difficulty label → db difficulty string
    difficulty = LEVEL_TO_DB_DIFFICULTY.get(candidate_level, "medium")

    # 1. Skill-based questions — prioritize tier3 skills (advanced)
    from resume_intelligence import SKILL_TIERS

    tier3_skills = [s for s in skills if s in SKILL_TIERS["tier3_advanced"]]
    tier2_skills = [s for s in skills if s in SKILL_TIERS["tier2_mid"]]
    ordered_skills = tier3_skills + tier2_skills

    random.shuffle(ordered_skills)

    for skill in ordered_skills:
        if len(questions) >= count:
            break
        pool = SKILL_QUESTION_POOL.get(skill, [])
        if not pool:
            # Normalize: try partial match
            for key in SKILL_QUESTION_POOL:
                if key in skill or skill in key:
                    pool = SKILL_QUESTION_POOL[key]
                    break

        if pool:
            random.shuffle(pool)
            for item in pool:
                if len(questions) >= count:
                    break
                _add_if_new({
                    "question": item["q"],
                    "difficulty": difficulty,
                    "category": _skill_to_category(skill),
                    "source": SOURCE_RESUME,
                    "ideal_answer": f"Candidate should demonstrate hands-on experience with {skill}.",
                    "keywords": item["concepts"],
                    "evaluation_guidelines": f"Verify depth of {skill} knowledge. Look for practical examples.",
                    "follow_up_questions": [],
                    "is_generated": True,
                    "_concepts": item["concepts"],
                })

    # 2. Project-based questions
    for proj in projects[:3]:
        if len(questions) >= count:
            break
        name = proj.get("name", "your project")
        techs = proj.get("technologies", [])
        primary_tech = techs[0] if techs else "your tech stack"
        desc = (proj.get("description", "") + " " + name).lower()

        # Choose templates based on project signals
        templates = PROJECT_TEMPLATES[:]

        is_ai_project = any(kw in desc for kw in ["ml", "ai", "model", "neural", "nlp", "predict"])
        is_cloud_project = any(kw in desc for kw in ["aws", "gcp", "azure", "docker", "kubernetes", "deploy"])

        if is_ai_project:
            templates += PROJECT_TEMPLATES_AI
        if is_cloud_project:
            templates += PROJECT_TEMPLATES_CLOUD

        random.shuffle(templates)

        for tmpl in templates[:3]:
            if len(questions) >= count:
                break
            q_text = tmpl.format(project=name, tech=primary_tech)
            concepts = [name.lower(), primary_tech.lower(), "architecture"]
            _add_if_new({
                "question": q_text,
                "difficulty": difficulty,
                "category": "Backend Development",
                "source": SOURCE_RESUME,
                "ideal_answer": (
                    f"Should show personal knowledge of {name}: problem solved, "
                    f"design decisions, {primary_tech} usage, challenges, and lessons."
                ),
                "keywords": techs + ["architecture", "design"],
                "evaluation_guidelines": "Must show first-hand project knowledge.",
                "follow_up_questions": [f"How would you test {name}?", f"What would you change in {name}?"],
                "is_generated": True,
                "_concepts": concepts,
            })

    # 3. Experience-based questions
    for exp in experience[:2]:
        if len(questions) >= count:
            break
        role = exp.get("role", "developer")
        tmpl = random.choice(EXPERIENCE_TEMPLATES)
        _add_if_new({
            "question": tmpl.format(role=role),
            "difficulty": difficulty,
            "category": "HR & Behavioral",
            "source": SOURCE_RESUME,
            "ideal_answer": f"Should reference real experiences from their {role} role with specific outcomes.",
            "keywords": ["problem solving", "collaboration", "impact"],
            "evaluation_guidelines": "Look for STAR-format answer: Situation, Task, Action, Result.",
            "follow_up_questions": ["What was the outcome?", "What did you learn?"],
            "is_generated": True,
            "_concepts": [role.lower(), "experience"],
        })

    # 4. Certification-based questions
    for cert in certifications[:1]:
        if len(questions) >= count:
            break
        _add_if_new({
            "question": f"You hold a certification in {cert[:80]}. Describe a practical scenario where you applied that knowledge.",
            "difficulty": difficulty,
            "category": "Backend Development",
            "source": SOURCE_RESUME,
            "ideal_answer": f"Should demonstrate practical application of {cert} domain knowledge.",
            "keywords": [cert[:30].lower()],
            "evaluation_guidelines": "Verify the certification is backed by real usage.",
            "follow_up_questions": [],
            "is_generated": True,
            "_concepts": [cert[:30].lower()],
        })

    return questions[:count]


def select_dataset_questions(
    dataset_questions: List[Dict],
    intelligence: Dict,
    count: int,
    already_used_concepts: Optional[set] = None,
) -> List[Dict]:
    """
    Select `count` questions from the dataset (DB questions passed in from Node.js).
    Selection is filtered by difficulty and randomized.
    Adds source='dataset' to each.
    """
    if not dataset_questions:
        return []

    used = already_used_concepts or set()
    candidate_level = intelligence.get("candidateLevel", "Intermediate")
    difficulty = LEVEL_TO_DB_DIFFICULTY.get(candidate_level, "medium")

    # Prefer questions matching the recommended difficulty
    preferred = [q for q in dataset_questions if q.get("difficulty") == difficulty]
    fallback = [q for q in dataset_questions if q.get("difficulty") != difficulty]

    random.shuffle(preferred)
    random.shuffle(fallback)

    pool = preferred + fallback
    selected = []

    for q in pool:
        if len(selected) >= count:
            break

        # Avoid semantic overlap with already-used concepts
        q_keywords = set(str(kw).lower() for kw in q.get("keywords", []))
        q_text = q.get("question", "").lower()
        q_concepts = q_keywords | set(q_text.split()[:5])

        if used and q_concepts & used:
            # Some overlap is ok, but don't skip entirely — only skip if too much overlap
            overlap_ratio = len(q_concepts & used) / max(len(q_concepts), 1)
            if overlap_ratio > 0.6:
                continue

        used.update(q_keywords)

        q_out = {
            "question": q.get("question", ""),
            "difficulty": q.get("difficulty", difficulty),
            "category": q.get("category", "Backend Development"),
            "source": SOURCE_DATASET,
            "ideal_answer": q.get("ideal_answer", ""),
            "keywords": q.get("keywords", []),
            "evaluation_guidelines": q.get("evaluation_guidelines", ""),
            "follow_up_questions": q.get("follow_up_questions", []),
            "is_generated": False,
            # Preserve original DB identifier for analytics
            "questionId": str(q.get("_id", q.get("questionId", ""))),
        }
        selected.append(q_out)

    return selected


def generate_hybrid_questions(
    parsed: Dict,
    intelligence: Dict,
    dataset_questions: List[Dict],
    count: int = 10,
    interview_type: str = "Technical Interview",
) -> List[Dict]:
    """
    Main entry point for Hybrid Question Generation.

    Distribution:
      resume_count  = ceil(count * 0.5)
      dataset_count = count - resume_count

    Returns a shuffled list with source tracking.
    """
    resume_count = math.ceil(count * 0.5)
    dataset_count = count - resume_count

    logger.info(
        f"Hybrid generation: total={count}, "
        f"resume={resume_count}, dataset={dataset_count}"
    )

    # Generate resume questions
    resume_questions = generate_resume_questions(parsed, intelligence, resume_count)

    # Collect concepts already used so dataset questions don't overlap
    used_concepts = set()
    for q in resume_questions:
        used_concepts.update(str(kw).lower() for kw in q.get("keywords", []))

    # Select dataset questions
    dataset_qs = select_dataset_questions(
        dataset_questions, intelligence, dataset_count, used_concepts
    )

    # Combine and shuffle
    all_questions = resume_questions + dataset_qs
    random.shuffle(all_questions)

    logger.info(
        f"Hybrid output: {len(resume_questions)} resume + {len(dataset_qs)} dataset "
        f"= {len(all_questions)} total"
    )

    return all_questions[:count]


# ── Helper ────────────────────────────────────────────────────

def _skill_to_category(skill: str) -> str:
    """Map a skill name to the appropriate VoxIntel question category."""
    s = skill.lower()
    if any(k in s for k in ["react", "angular", "vue", "html", "css", "javascript", "typescript", "nextjs", "frontend"]):
        return "Frontend Development"
    if any(k in s for k in ["machine learning", "deep learning", "nlp", "pytorch", "tensorflow", "sklearn", "spacy", "ai", "computer vision"]):
        return "NLP / AI / ML"
    if any(k in s for k in ["python", "pandas", "numpy", "asyncio"]):
        return "Python Development"
    if any(k in s for k in ["mongodb", "postgresql", "mysql", "redis", "sqlite", "database", "sql", "dynamodb"]):
        return "DBMS"
    if any(k in s for k in ["system design", "distributed", "microservice", "scalab", "architecture"]):
        return "System Design Basics"
    if any(k in s for k in ["algorithm", "data structure", "leetcode"]):
        return "Data Structures & Algorithms"
    if any(k in s for k in ["behavioral", "hr", "soft skills", "communication", "teamwork"]):
        return "HR & Behavioral"
    return "Backend Development"
