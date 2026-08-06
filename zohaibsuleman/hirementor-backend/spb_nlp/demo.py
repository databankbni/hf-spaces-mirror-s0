"""
SPB NLP Backend - demo / example usage.
Shows all features: CV parsing (regex + spaCy NER), BERT-based
semantic matching, shortlisting, and job recommendations.

Run:  python -m spb_nlp.demo
"""

import sys
import os

# Add parent to path if running as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spb_nlp.cv_parser import CVParser, SpacyNerParser, _HAS_SPACY
from spb_nlp.semantic_matcher import SemanticMatcher, _HAS_EMBEDDINGS
from spb_nlp.shortlister import Shortlister
from spb_nlp.recommender import JobRecommender
from spb_nlp.models import Student, Job


SAMPLE_RESUME_TEXT = """
John Doe
john.doe@email.com
+1-555-123-4567

PROFESSIONAL SUMMARY
Experienced software engineer with 5+ years building full-stack web applications.

SKILLS
Python, Java, JavaScript, React, Django, PostgreSQL, Docker, AWS, Git, REST APIs

EXPERIENCE
Senior Software Engineer | TechCorp | 2020-2024
- Led development of microservices architecture serving 1M+ users
- Built RESTful APIs using Python/ Django
- Managed AWS infrastructure (EC2, S3, RDS)
- Mentored 3 junior developers

Software Developer | StartupX | 2018-2020
- Developed React-based dashboard for analytics platform
- Implemented CI/CD pipeline with Docker and GitHub Actions

EDUCATION
Bachelor of Science in Computer Science
University of Technology | GPA: 3.6/4.0 | 2014-2018

CERTIFICATIONS
AWS Certified Solutions Architect
Certified Scrum Master

PROJECTS
E-commerce Platform - Full-stack React/Django/PostgreSQL
Real-time Chat Application - WebSocket/Node.js/Redis
"""


def main():
    print("=" * 60)
    print("HireMentor NLP Backend Demo")
    print("Models: Regex + spaCy NER (CV parsing) | BERT (semantic matching)")
    print("=" * 60)

    # ------------------------------------------------------------------ #
    # 0. Model Status
    # ------------------------------------------------------------------ #
    print("\n---------- 0. Model Status ----------")
    print(f"  spaCy NER:         {'AVAILABLE' if _HAS_SPACY else 'NOT INSTALLED (using regex)'}")
    print(f"  BERT embeddings:   {'AVAILABLE' if _HAS_EMBEDDINGS else 'NOT INSTALLED (using n-gram fallback)'}")

    # ------------------------------------------------------------------ #
    # 1. CV Parsing (Regex + spaCy NER)
    # ------------------------------------------------------------------ #
    print("\n---------- 1. CV Parsing ----------")

    # Regex-based parser
    parser = CVParser()
    cv_result = parser.parse_text(SAMPLE_RESUME_TEXT)
    print("  [Regex Parser]")
    print(f"    Name:       {cv_result.candidate_name}")
    print(f"    Email:      {cv_result.email}")
    print(f"    Phone:      {cv_result.phone}")
    print(f"    Skills:     {', '.join(cv_result.skills[:8])}")
    print(f"    Education:  {cv_result.education[:80]}")
    print(f"    Exp (yrs):  {cv_result.years_of_experience}")
    print(f"    GPA:        {cv_result.gpa}")
    print(f"    Certs:      {', '.join(cv_result.certifications)}")
    print(f"    Projects:   {', '.join(cv_result.projects)}")

    # SpaCy NER parser
    spacy_parser = SpacyNerParser()
    spacy_result = spacy_parser.parse_text(SAMPLE_RESUME_TEXT)
    print(f"  [SpaCy NER Parser{' (active)' if spacy_parser.is_using_spacy else ' (fallback)'}]")
    print(f"    Name:       {spacy_result.candidate_name}")
    print(f"    Skills:     {', '.join(spacy_result.skills[:8])}")
    print(f"    Education:  {spacy_result.education[:80]}")
    if spacy_parser.is_using_spacy:
        print(f"    (spaCy NER model loaded: {spacy_parser._model_name})")

    # ------------------------------------------------------------------ #
    # 2. Semantic Matching (BERT / n-gram)
    # ------------------------------------------------------------------ #
    print("\n---------- 2. Semantic Matching ----------")

    sample_jobs = [
        Job(
            job_id="job_001",
            title="Senior Python Developer",
            company_name="TechCorp",
            description="Build and maintain Python microservices on AWS. "
                        "Experience with Django, PostgreSQL, and Docker required.",
            required_skills=["python", "django", "postgresql", "docker", "aws"],
            requirements=["5+ years Python experience", "AWS experience"],
            qualifications=["BS in CS or related"],
            location="Remote",
            salary="$120k-150k",
            matching_threshold=50.0,
        ),
        Job(
            job_id="job_002",
            title="Frontend React Developer",
            company_name="WebStudio",
            description="Develop modern React-based web applications.",
            required_skills=["javascript", "react", "css", "html", "typescript"],
            requirements=["3+ years React experience"],
            qualifications=["BS in CS or related"],
            location="New York, NY",
            salary="$100k-130k",
            matching_threshold=40.0,
        ),
        Job(
            job_id="job_003",
            title="Data Scientist",
            company_name="DataAI Inc.",
            description="Apply ML techniques to business problems.",
            required_skills=["python", "machine learning", "tensorflow",
                             "sql", "data analysis"],
            requirements=["2+ years data science experience"],
            qualifications=["MS/PhD in CS, Stats, or related"],
            location="San Francisco, CA",
            salary="$130k-160k",
            matching_threshold=55.0,
        ),
    ]

    matcher = SemanticMatcher()
    model_name = matcher._model_name if matcher.using_bert else "n-gram fallback"
    print(f"\n  Model: {model_name}")
    print(f"  Matching CV against {len(sample_jobs)} jobs...\n")

    for job in sample_jobs:
        match = matcher.match_cv_to_job(cv_result, job)
        print(f"  -> {job.title:35s}  Score: {match.match_score:5.1f}  "
              f"Threshold: {job.matching_threshold:4.0f}  "
              f"{'SHORTLISTED' if match.meets_threshold else 'REJECTED'}")
        print(f"     Cosine sim: {match.cosine_similarity:.3f}  "
              f"Matching: {len(match.matching_skills)}  "
              f"Missing: {len(match.missing_skills)}")

    # ------------------------------------------------------------------ #
    # 3. Shortlisting
    # ------------------------------------------------------------------ #
    print("\n---------- 3. Shortlisting ----------")
    shortlister = Shortlister()

    all_matches = [matcher.match_cv_to_job(cv_result, j) for j in sample_jobs]
    shortlist_result = shortlister.shortlist_for_job(
        match_results=all_matches,
        job=sample_jobs[0],
        threshold=50.0,
    )

    summary = shortlister.get_shortlist_summary(shortlist_result)
    print(f"  Job:                {summary['job_title']}")
    print(f"  Total Applicants:   {summary['total_applicants']}")
    print(f"  Shortlisted:        {summary['shortlisted_count']}")
    print(f"  Rejected:           {summary['rejected_count']}")
    print(f"  Threshold used:     {summary['threshold_used']}")

    # ------------------------------------------------------------------ #
    # 4. Job Recommendations
    # ------------------------------------------------------------------ #
    print("\n---------- 4. Job Recommendations ----------")
    student = Student(
        student_id="stu_001",
        full_name="John Doe",
        email="john.doe@email.com",
        university="University of Technology",
        degree="BS in Computer Science",
        major="Computer Science",
        cgpa=3.6,
        skills=["python", "java", "javascript", "react", "django",
                "postgresql", "docker", "aws", "git"],
        certifications=["AWS Certified Solutions Architect"],
    )

    recommender = JobRecommender(matcher)
    recommendations = recommender.recommend_for_student(student, sample_jobs, top_k=3)

    print()
    for rec in recommendations:
        print(f"  Rank {recommendations.index(rec) + 1}: {rec.job_title:30s}  "
              f"Score: {rec.match_score:5.1f}")
        print(f"       {rec.company_name:30s}  Reason: {rec.reason}")
        print(f"       Matching: {', '.join(rec.matching_skills[:3])}  "
              f"Missing: {', '.join(rec.missing_skills[:3])}")
        print()

    print("=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
