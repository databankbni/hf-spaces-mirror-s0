"""
question_generator.py
----------------------
Generates interview questions dynamically based on:
  - User's resume skills
  - Their listed projects
  - Selected company
  - Selected role
  - Interview type
  - Difficulty level

This module is used by the Flask app's /generate-questions endpoint.
The Node.js backend can also call it when starting a session to
supplement the database questions with resume-specific ones.

Design:
  - Deterministic templates for project-based questions (no AI model needed)
  - Skill-matching logic using extracted resume data
  - Company-specific question injection from a local lookup table
"""

import random
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


# ── Company-Specific Interview Style Notes ────────────────────
# These describe what each company focuses on in interviews.
# Used to add contextual hints to generated questions.

COMPANY_STYLES = {
    "Google": {
        "focus": ["algorithms", "system design", "scalability", "coding"],
        "notes": "Google interviews heavily emphasize data structures, algorithm efficiency, and system design at scale.",
        "question_tags": ["complexity", "optimize", "scale", "Big-O"],
    },
    "Amazon": {
        "focus": ["leadership principles", "behavioral", "coding", "system design"],
        "notes": "Amazon uses the STAR method for behavioral questions tied to their 16 Leadership Principles.",
        "question_tags": ["ownership", "customer obsession", "trade-offs", "distributed"],
    },
    "Microsoft": {
        "focus": ["problem solving", "design patterns", "coding", "behavioral"],
        "notes": "Microsoft values problem-solving approach and explains thought process as much as the final answer.",
        "question_tags": ["design pattern", "OOP", "thought process", "collaboration"],
    },
    "Flipkart": {
        "focus": ["DSA", "system design", "MERN", "scalability"],
        "notes": "Flipkart focuses on scalable e-commerce systems and strong DSA fundamentals.",
        "question_tags": ["e-commerce", "catalog", "inventory", "search", "scale"],
    },
    "TCS": {
        "focus": ["fundamentals", "DBMS", "OS", "networking", "HR"],
        "notes": "TCS focuses on core CS fundamentals, aptitude, and communication skills.",
        "question_tags": ["fundamentals", "basic", "communication"],
    },
    "Infosys": {
        "focus": ["programming", "DBMS", "aptitude", "communication"],
        "notes": "Infosys tests programming basics, DBMS, aptitude, and situational HR questions.",
        "question_tags": ["basics", "SQL", "aptitude"],
    },
    "Wipro": {
        "focus": ["technical basics", "aptitude", "English", "HR"],
        "notes": "Wipro's process includes aptitude, verbal, technical basics, and an HR round.",
        "question_tags": ["basic", "verbal", "problem solving"],
    },
    "Zoho": {
        "focus": ["coding", "problem solving", "product thinking"],
        "notes": "Zoho has multiple coding rounds — they value raw problem-solving ability over rote knowledge.",
        "question_tags": ["problem solving", "implementation", "logic"],
    },
    "Deloitte": {
        "focus": ["case study", "behavioral", "technical", "communication"],
        "notes": "Deloitte values structured thinking, case analysis, and professional communication.",
        "question_tags": ["case study", "analysis", "stakeholder", "consulting"],
    },
}

# ── Project-Based Question Templates ─────────────────────────
# These templates are filled with the project name and technologies
# to generate realistic project-discussion questions.

PROJECT_QUESTION_TEMPLATES = [
    # Architecture & Design
    "Walk me through the overall architecture of your {project} project.",
    "What design decisions did you make when building {project}, and why?",
    "How did you structure the database schema for {project}?",
    "If you were rebuilding {project} from scratch today, what would you do differently?",

    # Tech stack
    "Why did you choose {tech} for {project} instead of alternatives?",
    "What challenges did you face integrating {tech} into {project}?",
    "How does {tech} contribute to {project}'s performance?",

    # Implementation
    "What was the most technically challenging part of building {project}?",
    "How did you handle authentication and authorization in {project}?",
    "How did you handle errors and edge cases in {project}?",
    "Describe how data flows through {project} from the user's action to the database.",

    # Debugging & Problem Solving
    "Tell me about a bug you encountered in {project} and how you fixed it.",
    "How did you debug performance issues in {project}?",
    "What was the hardest bug you faced in {project} and what was the root cause?",

    # Scalability & Future
    "How would you scale {project} to handle 10x more users?",
    "What features would you add to {project} in the next version?",
    "What are the current limitations of {project} and how would you address them?",
    "How would you add real-time features to {project}?",

    # AI/ML specific (used when AI/ML tech detected)
    "How did you train and evaluate the model used in {project}?",
    "What dataset did you use for {project} and how did you handle data quality?",
    "How do you serve the ML model in {project} — batch or real-time inference?",
    "What accuracy did your model achieve in {project} and how did you improve it?",
]

# ── Skill-Based Question Starters ─────────────────────────────
# For each skill, a list of probing questions that can be asked.

SKILL_QUESTIONS = {
    "react": [
        "Explain the React component lifecycle and when each phase runs.",
        "How do you optimize a React app that's re-rendering too frequently?",
        "What is the difference between useEffect with an empty array vs no array?",
        "How would you implement infinite scrolling in React?",
    ],
    "node.js": [
        "How does Node.js handle thousands of concurrent connections with a single thread?",
        "What is the purpose of the cluster module in Node.js?",
        "How do you handle memory leaks in a long-running Node.js process?",
        "Explain streams in Node.js and when you'd use them.",
    ],
    "mongodb": [
        "When would you use embedding vs referencing documents in MongoDB?",
        "How does MongoDB's aggregation pipeline work? Give an example.",
        "What indexing strategies do you use to speed up MongoDB queries?",
        "How do you handle transactions in MongoDB?",
    ],
    "python": [
        "How would you profile a slow Python script?",
        "What is the difference between multiprocessing and asyncio in Python?",
        "Explain how Python's garbage collector handles reference cycles.",
        "How do you write a thread-safe Python class?",
    ],
    "machine learning": [
        "Walk me through how you would approach a new ML classification problem.",
        "How do you handle class imbalance in a training dataset?",
        "What is the bias-variance tradeoff and how does it affect your model choice?",
        "Explain cross-validation and why it's important.",
    ],
    "nlp": [
        "How would you build a text classification pipeline from scratch?",
        "What is the difference between TF-IDF and word embeddings?",
        "How do you evaluate the quality of a language model?",
        "What preprocessing steps do you apply to raw text before modeling?",
    ],
    "docker": [
        "What is the difference between a Docker image and a container?",
        "How do you reduce Docker image size for production?",
        "Explain Docker networking — how do containers talk to each other?",
        "What is a multi-stage Docker build and why would you use it?",
    ],
    "aws": [
        "Which AWS services have you used and what did you use each for?",
        "What is the difference between EC2, ECS, and Lambda?",
        "How do you manage IAM roles and permissions securely?",
        "What is the difference between SQS and SNS?",
    ],
    "postgresql": [
        "What is the difference between a clustered index and a non-clustered index in PostgreSQL?",
        "How do you use EXPLAIN ANALYZE to debug a slow query?",
        "What are CTEs (Common Table Expressions) and when would you use them?",
        "How does PostgreSQL implement MVCC (Multi-Version Concurrency Control)?",
    ],
    "redis": [
        "What data structures does Redis support and what is each used for?",
        "How would you implement a rate limiter using Redis?",
        "What is Redis persistence — RDB vs AOF?",
        "How do you use Redis as a distributed lock?",
    ],
    "typescript": [
        "What are generics in TypeScript and why are they useful?",
        "What is the difference between interface and type alias in TypeScript?",
        "How does TypeScript's structural typing differ from nominal typing?",
        "How do you handle external JS libraries that don't have TypeScript types?",
    ],
    "git": [
        "What is the difference between git merge and git rebase?",
        "How do you recover from a bad git rebase?",
        "Explain the Git feature branch workflow.",
        "What is a git cherry-pick and when would you use it?",
    ],
}



# ── Difficulty-Based Timing Map ───────────────────────────────
# Returns (min_minutes, max_minutes) for each difficulty level.

DIFFICULTY_TIMING = {
    "easy":   (5,  10),
    "medium": (15, 25),
    "hard":   (30, 60),
}

def get_time_limit(difficulty: str) -> int:
    """Return the recommended time limit in minutes for a given difficulty."""
    lo, hi = DIFFICULTY_TIMING.get(difficulty.lower(), (15, 25))
    return (lo + hi) // 2  # midpoint as default


# ── Coding-Only Question Bank ─────────────────────────────────
# Used ONLY when interview_type is "Coding Interview" or "Coding Round".
# All questions require actual code to be written or analyzed.

CODING_QUESTIONS = {
    "easy": [
        {
            "question": "Write a function to reverse a string without using built-in reverse methods.",
            "concepts": ["loops", "string indexing", "two-pointer"],
            "eval": "Check for O(n) solution, no extra space bonus.",
        },
        {
            "question": "Write a function that checks whether a given string is a palindrome.",
            "concepts": ["string manipulation", "two-pointer"],
            "eval": "Handles edge cases: empty string, single char, case sensitivity.",
        },
        {
            "question": "Implement a function that returns the factorial of a number both iteratively and recursively.",
            "concepts": ["recursion", "iteration", "base case"],
            "eval": "Both approaches present, handles n=0.",
        },
        {
            "question": "Write a function to find the two numbers in an array that sum to a given target. Return their indices.",
            "concepts": ["hash map", "two-pointer", "O(n) lookup"],
            "eval": "O(n) hash map solution preferred over O(n²) brute force.",
        },
        {
            "question": "Write a function to remove duplicates from a sorted array in-place and return the new length.",
            "concepts": ["two-pointer", "in-place", "sorted arrays"],
            "eval": "In-place modification, correct pointer management.",
        },
        {
            "question": "Implement a basic stack using only arrays (push, pop, peek, isEmpty).",
            "concepts": ["stack ADT", "array operations"],
            "eval": "All four methods present and correct, handles empty stack.",
        },
        {
            "question": "Write a SQL query to find all employees whose salary is above the department average.",
            "concepts": ["SQL subquery", "GROUP BY", "correlated subquery"],
            "eval": "Correct use of correlated subquery or window function AVG.",
        },
        {
            "question": "Write a function to count the occurrences of each character in a string and return a dictionary.",
            "concepts": ["hash map", "string traversal"],
            "eval": "Single pass O(n), handles unicode/special chars.",
        },
    ],
    "medium": [
        {
            "question": "Implement an LRU (Least Recently Used) Cache with O(1) get and put operations.",
            "concepts": ["doubly linked list", "hash map", "cache design"],
            "eval": "Both get and put must be O(1). Eviction logic correct.",
        },
        {
            "question": "Write a function to validate if a given string of brackets (including {}, [], ()) is balanced.",
            "concepts": ["stack", "hash map", "string traversal"],
            "eval": "Uses stack correctly, handles all bracket types, empty string.",
        },
        {
            "question": "Given a binary tree, write a function to perform level-order (BFS) traversal and return nodes level by level.",
            "concepts": ["BFS", "queue", "binary tree", "level traversal"],
            "eval": "Uses queue, returns list-of-lists, handles null root.",
        },
        {
            "question": "Implement a function that merges two sorted linked lists into a single sorted linked list.",
            "concepts": ["linked list", "merge", "two pointers"],
            "eval": "Handles null inputs, no extra memory for values.",
        },
        {
            "question": "Write a REST API endpoint in your preferred language that accepts a JSON body with `name` and `age` fields, validates them, and stores them in a database.",
            "concepts": ["REST API", "input validation", "database insert", "error handling"],
            "eval": "Proper status codes (200/400/500), input validation, DB interaction.",
        },
        {
            "question": "Write a function to find the longest substring without repeating characters. Return its length.",
            "concepts": ["sliding window", "hash set", "two pointers"],
            "eval": "O(n) sliding window solution, handles empty/single-char inputs.",
        },
        {
            "question": "Write a SQL query to find the Nth highest salary from an Employee table.",
            "concepts": ["SQL ranking", "DENSE_RANK", "subquery", "LIMIT/OFFSET"],
            "eval": "Handles ties correctly, uses DENSE_RANK or equivalent.",
        },
        {
            "question": "Implement a function that detects if a linked list has a cycle. Return True/False.",
            "concepts": ["Floyd's cycle detection", "fast/slow pointer"],
            "eval": "O(1) space Floyd's algorithm, correct pointer advancement.",
        },
        {
            "question": "Design and implement a basic rate limiter class that allows at most N requests per second.",
            "concepts": ["sliding window", "timestamp queue", "rate limiting"],
            "eval": "Handles edge cases, O(1) or O(N) acceptable, thread-safety mention bonus.",
        },
    ],
    "hard": [
        {
            "question": "Implement a thread-safe Singleton pattern. Discuss why naive implementations fail in multithreaded environments.",
            "concepts": ["design patterns", "threading", "double-checked locking", "mutex"],
            "eval": "Thread-safe implementation with explanation of race condition, lazy initialization.",
        },
        {
            "question": "Given a stream of integers, design a data structure that supports: insert(x), findMedian() in O(log n) and O(1) respectively.",
            "concepts": ["two heaps", "max-heap", "min-heap", "streaming"],
            "eval": "Two-heap approach, correct balancing, O(log n) insert, O(1) median.",
        },
        {
            "question": "Implement a mini database query engine that parses a simple SQL-like string (SELECT col FROM table WHERE col > N) and filters a list of dictionaries.",
            "concepts": ["string parsing", "query evaluation", "filter logic", "tokenization"],
            "eval": "Parses SELECT/FROM/WHERE correctly, handles numeric and string comparisons.",
        },
        {
            "question": "Design and implement a URL shortener service. Write the key generation algorithm and the storage/retrieval logic.",
            "concepts": ["hashing", "base62 encoding", "collision handling", "key-value store"],
            "eval": "Collision-safe key gen, encode/decode functions, storage abstraction.",
        },
        {
            "question": "Implement a word search algorithm on a 2D board: given a board of characters and a word, determine if the word exists in the board using adjacent cells (no cell reused).",
            "concepts": ["DFS", "backtracking", "2D grid traversal", "visited set"],
            "eval": "DFS with backtracking, visited path tracking, correct boundary checks.",
        },
        {
            "question": "Write a concurrent task queue in Python (or Java) that runs tasks in parallel with a configurable max number of worker threads.",
            "concepts": ["threading", "thread pool", "queue", "synchronization"],
            "eval": "ThreadPoolExecutor or manual thread management, graceful shutdown, exception handling.",
        },
        {
            "question": "Implement a B+ Tree or a Skip List and explain the time complexity of insert, delete, and search operations.",
            "concepts": ["advanced data structures", "B+ Tree", "skip list", "complexity analysis"],
            "eval": "Core operations implemented, complexity correctly analyzed, trade-offs discussed.",
        },
        {
            "question": "Implement a distributed key-value store that supports consistent hashing to distribute keys across N nodes.",
            "concepts": ["consistent hashing", "virtual nodes", "distributed systems", "hash ring"],
            "eval": "Hash ring implementation, node add/remove rebalancing, virtual nodes for uniformity.",
        },
    ],
}


def generate_coding_questions(difficulty: str, skills: List[str], count: int = 10) -> List[Dict]:
    """
    Generate ONLY coding problems — used when interview_type is 'Coding Interview' or 'Coding Round'.

    Each question includes:
      - The coding problem statement
      - difficulty label
      - expected_concepts (what the candidate must know)
      - time_limit in minutes
      - evaluation_criteria
    """
    difficulty_key = difficulty.lower() if difficulty.lower() in CODING_QUESTIONS else "medium"
    pool = CODING_QUESTIONS[difficulty_key].copy()
    random.shuffle(pool)

    time_lo, time_hi = DIFFICULTY_TIMING.get(difficulty_key, (15, 25))
    time_limit = (time_lo + time_hi) // 2

    generated = []
    for item in pool[:count]:
        generated.append({
            "question": item["question"],
            "difficulty": difficulty_key,
            "expected_concepts": item["concepts"],
            "time_limit_minutes": time_limit,
            "ideal_answer": (
                f"Candidate should demonstrate: {', '.join(item['concepts'])}. "
                f"Evaluation: {item['eval']}"
            ),
            "keywords": item["concepts"],
            "evaluation_guidelines": item["eval"],
            "category": "Coding Challenge",
            "company_tags": [],
            "role_tags": [],
            "follow_up_questions": [
                "What is the time and space complexity of your solution?",
                "How would you optimize this further?",
                "Can you write unit tests for edge cases?",
            ],
            "is_generated": True,
            "is_coding": True,
        })

    return generated


# ── Coding interview type detector ────────────────────────────

CODING_INTERVIEW_TYPES = {
    "coding round", "coding interview", "coding", "dsa round",
    "algorithmic", "data structures", "competitive coding",
}

def is_coding_interview(interview_type: str) -> bool:
    """Return True if the interview type should generate coding-only questions."""
    return interview_type.lower().strip() in CODING_INTERVIEW_TYPES


# ── Project-Based Question Generator ─────────────────────────

def generate_project_questions(projects: List[Dict], count: int = 3) -> List[Dict]:
    """
    Generate interview questions based on the user's specific projects.

    Each project dict should have: name, description, technologies.
    Returns a list of question dicts in the standard format.
    """
    generated = []

    for project in projects[:3]:  # use first 3 projects max
        name = project.get("name", "your project")
        technologies = project.get("technologies", [])
        primary_tech = technologies[0] if technologies else "your tech stack"

        # Pick a mix of templates
        templates = random.sample(PROJECT_QUESTION_TEMPLATES, min(count, len(PROJECT_QUESTION_TEMPLATES)))

        for template in templates:
            question_text = template.format(project=name, tech=primary_tech)

            generated.append({
                "question": question_text,
                "difficulty": "medium",
                "ideal_answer": (
                    f"A strong answer about {name} should cover: the problem it solves, "
                    f"the architecture and tech choices made, key implementation challenges, "
                    f"and lessons learned. Be specific about {primary_tech} usage."
                ),
                "keywords": technologies + ["architecture", "design", "implementation", "challenges"],
                "company_tags": [],
                "role_tags": [],
                "category": "Backend Development",  # default — will be overridden by context
                "evaluation_guidelines": "Should show deep personal knowledge of their own project.",
                "follow_up_questions": [
                    f"What would you change about {name} if you rebuilt it?",
                    f"How did you test {name}?",
                ],
                "is_generated": True,  # flag to distinguish from database questions
            })

    return generated


# ── Skill-Based Question Generator ───────────────────────────

def generate_skill_questions(skills: List[str], count: int = 5) -> List[Dict]:
    """
    Generate targeted questions based on skills extracted from the resume.
    Returns a list of question dicts.
    """
    generated = []
    used_questions = set()  # avoid duplicates

    # Shuffle skills so we don't always use the same ones first
    shuffled_skills = skills.copy()
    random.shuffle(shuffled_skills)

    for skill in shuffled_skills:
        skill_lower = skill.lower()

        # Find matching skill template (exact or partial match)
        matched_key = None
        for key in SKILL_QUESTIONS:
            if key in skill_lower or skill_lower in key:
                matched_key = key
                break

        if matched_key:
            questions_for_skill = SKILL_QUESTIONS[matched_key]
            for q_text in questions_for_skill:
                if q_text not in used_questions and len(generated) < count:
                    used_questions.add(q_text)
                    generated.append({
                        "question": q_text,
                        "difficulty": "medium",
                        "ideal_answer": f"Answer should demonstrate practical experience with {skill}.",
                        "keywords": [skill, matched_key],
                        "company_tags": [],
                        "role_tags": [],
                        "category": _skill_to_category(skill),
                        "evaluation_guidelines": f"Candidate claims {skill} experience — verify depth.",
                        "follow_up_questions": [],
                        "is_generated": True,
                    })

        if len(generated) >= count:
            break

    return generated


# ── Company Context Generator ─────────────────────────────────

def get_company_context(company: str) -> Dict:
    """
    Return interview style notes and focus areas for a specific company.
    Used to add context to the interview session start screen.
    """
    if company in COMPANY_STYLES:
        return COMPANY_STYLES[company]
    return {
        "focus": ["technical fundamentals", "problem solving", "communication"],
        "notes": "Focus on demonstrating solid fundamentals and clear communication.",
        "question_tags": [],
    }


# ── Main Generator Function ───────────────────────────────────

def generate_interview_questions(
    skills: List[str],
    projects: List[Dict],
    company: str,
    role: str,
    interview_type: str,
    difficulty: str,
    count: int = 10,
) -> List[Dict]:
    """
    Main entry point: generate a personalized set of interview questions.

    Combines:
      1. Project-based questions (from user's resume projects)
      2. Skill-based questions (from extracted skills)
      3. Company context (style notes)

    Returns a list of question dicts.
    """
    questions = []

    # ── Coding interview: use dedicated coding question bank ──
    if is_coding_interview(interview_type):
        logger.info(f"Coding interview detected — using coding-only question bank (difficulty={difficulty})")
        coding_qs = generate_coding_questions(difficulty=difficulty, skills=skills, count=count)
        questions.extend(coding_qs)
        logger.info(f"Generated {len(coding_qs)} coding questions")
        return questions[:count]

    # ── Standard interview: mix of project + skill questions ──

    # Reserve 30% of slots for project questions (if projects exist)
    project_count = min(3, max(1, count // 3)) if projects else 0

    # Reserve 70% for skill-based questions
    skill_count = count - project_count

    # Generate project questions
    if projects and project_count > 0:
        project_qs = generate_project_questions(projects, count=project_count)
        questions.extend(project_qs)
        logger.info(f"Generated {len(project_qs)} project-based questions")

    # Generate skill questions
    if skills and skill_count > 0:
        skill_qs = generate_skill_questions(skills, count=skill_count)
        questions.extend(skill_qs)
        logger.info(f"Generated {len(skill_qs)} skill-based questions")

    # Get company context (for logging/metadata only — not added as questions here)
    company_ctx = get_company_context(company)
    logger.info(f"Company style for {company}: {company_ctx['focus']}")

    # Shuffle final list
    random.shuffle(questions)

    logger.info(f"Total generated questions: {len(questions)} for {role} @ {company}")
    return questions[:count]


# ── Helper: Map skill to question category ─────────────────────

def _skill_to_category(skill: str) -> str:
    """Map a skill name to the appropriate question category."""
    skill_lower = skill.lower()

    frontend_skills = ["react", "angular", "vue", "html", "css", "javascript", "typescript", "sass", "nextjs"]
    backend_skills = ["node", "express", "django", "flask", "fastapi", "spring", "rails", "rest api"]
    ml_skills = ["machine learning", "deep learning", "nlp", "pytorch", "tensorflow", "sklearn", "spacy"]
    python_skills = ["python", "pandas", "numpy", "asyncio"]
    db_skills = ["mongodb", "postgresql", "mysql", "redis", "sqlite", "database"]
    cloud_skills = ["aws", "gcp", "azure", "docker", "kubernetes"]
    algo_skills = ["algorithm", "data structure", "leetcode", "competitive"]

    if any(s in skill_lower for s in frontend_skills):
        return "Frontend Development"
    elif any(s in skill_lower for s in ml_skills):
        return "NLP / AI / ML"
    elif any(s in skill_lower for s in python_skills):
        return "Python Development"
    elif any(s in skill_lower for s in db_skills):
        return "DBMS"
    elif any(s in skill_lower for s in backend_skills + cloud_skills):
        return "Backend Development"
    elif any(s in skill_lower for s in algo_skills):
        return "Data Structures & Algorithms"
    else:
        return "Backend Development"  # safe default
