"""
Evaluation script — measure accuracy of all NLP pipeline components.

Usage:
    python -m spb_nlp.evaluate              # uses hardcoded ground truth
    python -m spb_nlp.evaluate --dataset     # uses data/Resume/Resume.csv (Kaggle dataset)
    python -m spb_nlp.evaluate --dataset --jobs   # also loads monster_com jobs dataset
"""

import sys, os, math
import csv, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spb_nlp.cv_parser import CVParser, SpacyNerParser
from spb_nlp.semantic_matcher import SemanticMatcher
from spb_nlp.shortlister import Shortlister
from spb_nlp.recommender import JobRecommender
from spb_nlp.models import CVParseResult, Job, Student, MatchResult


# ═══════════════════════════════════════════════════════════════════
#  Ground-truth dataset (manually annotated CVs)
# ═══════════════════════════════════════════════════════════════════

GROUND_TRUTH_CVS = [
    {
        "raw": """John Doe
john.doe@email.com
+1-555-123-4567

SUMMARY
Software engineer with 5+ years experience.

SKILLS
Python, Java, JavaScript, React, Django, PostgreSQL, Docker, AWS

EXPERIENCE
Senior Engineer | TechCorp | 2020-2024
- Built microservices with Python/Django
- Managed AWS infrastructure

EDUCATION
Bachelor of Science in Computer Science
University of Technology | GPA: 3.6/4.0 | 2014-2018

CERTIFICATIONS
AWS Certified Solutions Architect

PROJECTS
E-commerce Platform - React/Django/PostgreSQL""",
        "gt": {
            "name": "John Doe",
            "email": "john.doe@email.com",
            "phone": "+1-555-123-4567",
            "skills": {"python", "java", "javascript", "react", "django", "postgresql", "docker", "aws"},
            "education": "bachelor",
            "gpa": (3.6, 0.1),
            "years_exp": (5.0, 1.0),
            "certifications": {"aws certified solutions architect"},
        }
    },
    {
        "raw": """Jane Smith
jane.smith@example.com
+92-300-1234567

SUMMARY
Data scientist with 3+ years of experience.

SKILLS
Python, R, Machine Learning, SQL, TensorFlow, NLP, Tableau, AWS

EXPERIENCE
Data Scientist | AnalyticsPro | 2021-2024
- Built ML models for churn prediction
- NLP pipeline for sentiment analysis

EDUCATION
Master of Science in Data Science
Stanford University | GPA: 3.8/4.0 | 2018-2020

CERTIFICATIONS
AWS Certified Machine Learning Specialty""",
        "gt": {
            "name": "Jane Smith",
            "email": "jane.smith@example.com",
            "phone": "+92-300-1234567",
            "skills": {"python", "r", "machine learning", "sql", "tensorflow", "nlp", "tableau", "aws"},
            "education": "master",
            "gpa": (3.8, 0.1),
            "years_exp": (3.0, 1.0),
            "certifications": {"aws certified machine learning specialty"},
        }
    },
    {
        "raw": """Ali Khan
ali.khan@email.com
+1-212-555-7890

SUMMARY
Fresh graduate with Android development skills.

SKILLS
Kotlin, Android, Jetpack Compose, Firebase, Git, REST APIs

EXPERIENCE
Intern | AppDev Studio | 2023-2024
- Developed Android UI with Jetpack Compose
- Integrated Firebase Firestore

EDUCATION
B.Tech in Computer Science
NED University | GPA: 3.2/4.0 | 2020-2024

PROJECTS
Weather App - Kotlin/Jetpack Compose
Chat App - Firebase/Android""",
        "gt": {
            "name": "Ali Khan",
            "email": "ali.khan@email.com",
            "phone": "+1-212-555-7890",
            "skills": {"kotlin", "android", "jetpack compose", "firebase", "git", "rest api"},
            "education": "b.tech",
            "gpa": (3.2, 0.1),
            "years_exp": (1.0, 1.0),
            "certifications": set(),
        }
    },
]

# Human-judged match scores (0-100) for semantic matching evaluation
HUMAN_MATCH_SCORES = [
    # (cv_index, job_skills, job_title, human_score)
    (0, ["python", "django", "postgresql", "docker", "aws"], "Senior Python Developer", 85),
    (0, ["javascript", "react", "css", "html", "typescript"], "Frontend Developer", 65),
    (0, ["python", "machine learning", "tensorflow", "sql"], "Data Scientist", 50),
    (1, ["python", "machine learning", "tensorflow", "sql"], "Data Scientist", 90),
    (1, ["python", "django", "postgresql", "docker", "aws"], "Backend Developer", 40),
    (1, ["r", "statistics", "tableau", "sql"], "Data Analyst", 70),
    (2, ["kotlin", "android", "jetpack compose", "firebase", "git"], "Android Developer", 88),
    (2, ["python", "django", "postgresql", "docker", "aws"], "Python Backend Developer", 20),
    (2, ["javascript", "react", "css", "html"], "Frontend Developer", 25),
]


# ═══════════════════════════════════════════════════════════════════
#  Evaluation helpers
# ═══════════════════════════════════════════════════════════════════

def precision_recall_f1(pred_set, gt_set):
    if not gt_set:
        return 1.0, 1.0, 1.0 if not pred_set else (0.0, 0.0, 0.0)
    tp = len(pred_set & gt_set)
    fp = len(pred_set - gt_set)
    fn = len(gt_set - pred_set)
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return round(p, 4), round(r, 4), round(f1, 4)


def float_match(pred, expected_range):
    """Check if pred is within tolerance of expected value."""
    return abs(pred - expected_range[0]) <= expected_range[1]


def str_similar(a: str, b: str) -> float:
    """Simple substring/startswith matching for strings."""
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.8
    if a.startswith(b) or b.startswith(a):
        return 0.6
    return 0.0


# ═══════════════════════════════════════════════════════════════════
#  1. CV Parsing Accuracy
# ═══════════════════════════════════════════════════════════════════

def evaluate_cv_parsing():
    print("\n" + "=" * 60)
    print("  CV PARSING ACCURACY")
    print("=" * 60)

    regex_parser = CVParser()
    spacy_parser = SpacyNerParser()

    for parser_name, parser in [("Regex    ", regex_parser), ("spaCy NER", spacy_parser)]:
        print(f"\n  ── {parser_name} ──")
        all_skills_p, all_skills_r, all_skills_f1 = [], [], []
        name_acc, email_acc, gpa_acc, exp_acc = 0, 0, 0, 0
        total = len(GROUND_TRUTH_CVS)

        for i, item in enumerate(GROUND_TRUTH_CVS):
            gt = item["gt"]
            pred = parser.parse_text(item["raw"])

            # Name
            ns = str_similar(pred.candidate_name, gt["name"])
            if ns >= 0.8:
                name_acc += 1

            # Email
            if pred.email == gt["email"]:
                email_acc += 1

            # Skills
            p, r, f1 = precision_recall_f1(
                {s.lower() for s in pred.skills}, gt["skills"]
            )
            all_skills_p.append(p)
            all_skills_r.append(r)
            all_skills_f1.append(f1)

            # GPA
            if gt["gpa"][0] > 0:
                if float_match(pred.gpa, gt["gpa"]):
                    gpa_acc += 1

            # Experience
            if gt["years_exp"][0] > 0:
                if float_match(pred.years_of_experience, gt["years_exp"]):
                    exp_acc += 1

            print(f"    CV #{i+1}: skills P={p:.3f} R={r:.3f} F1={f1:.3f}"
                  f" | name={'✓' if ns >= 0.8 else '✗'}"
                  f" email={'✓' if pred.email == gt['email'] else '✗'}"
                  f" gpa={'✓' if gt['gpa'][0]==0 or float_match(pred.gpa, gt['gpa']) else '✗'}"
                  f" exp={'✓' if gt['years_exp'][0]==0 or float_match(pred.years_of_experience, gt['years_exp']) else '✗'}")

        avg_p = sum(all_skills_p) / len(all_skills_p)
        avg_r = sum(all_skills_r) / len(all_skills_r)
        avg_f1 = sum(all_skills_f1) / len(all_skills_f1)
        print(f"\n    ──────────────────────────────────────")
        print(f"    Skills  → Precision: {avg_p:.3f}  Recall: {avg_r:.3f}  F1: {avg_f1:.3f}")
        print(f"    Name    → Accuracy:  {name_acc}/{total} ({100*name_acc/total:.0f}%)")
        print(f"    Email   → Accuracy:  {email_acc}/{total} ({100*email_acc/total:.0f}%)")
        print(f"    GPA     → Accuracy:  {gpa_acc}/{total} ({100*gpa_acc/total:.0f}%)")
        print(f"    Exp yrs → Accuracy:  {exp_acc}/{total} ({100*exp_acc/total:.0f}%)")


# ═══════════════════════════════════════════════════════════════════
#  2. Semantic Matching Accuracy
# ═══════════════════════════════════════════════════════════════════

def evaluate_semantic_matching():
    print("\n" + "=" * 60)
    print("  SEMANTIC MATCHING ACCURACY")
    print("=" * 60)

    matcher = SemanticMatcher()
    cv_parser = CVParser()

    print(f"\n  Model: {'BERT (all-MiniLM-L6-v2)' if matcher.using_bert else 'n-gram fallback'}")
    print(f"\n  {'CV':20s} {'Job':25s} {'Model':>7s} {'Human':>7s} {'Error':>7s}")
    print(f"  {'─'*20} {'─'*25} {'─'*7} {'─'*7} {'─'*7}")

    errors = []
    for cv_idx, job_skills, job_title, human_score in HUMAN_MATCH_SCORES:
        gt_cv = GROUND_TRUTH_CVS[cv_idx]
        cv = cv_parser.parse_text(gt_cv["raw"])
        job = Job(
            job_id=f"j{cv_idx}",
            title=job_title,
            company_name="TestCo",
            description=" ".join(job_skills),
            required_skills=job_skills,
            matching_threshold=0,
        )
        match = matcher.match_cv_to_job(cv, job)
        err = abs(match.match_score - human_score)
        errors.append(err)

        cv_name = gt_cv["gt"]["name"].split()[0]
        print(f"  {cv_name + ',':20s} {job_title:25s} {match.match_score:6.1f}  {human_score:6d}  {err:6.1f}")

    mae = sum(errors) / len(errors)
    print(f"\n  ─────────────────────────────────────────────")
    print(f"  Mean Absolute Error (MAE): {mae:.2f} / 100")
    print(f"  Accuracy (within ±15):     {sum(1 for e in errors if e <= 15)}/{len(errors)}"
          f" ({100*sum(1 for e in errors if e <= 15)/len(errors):.0f}%)")

    if matcher.using_bert:
        print(f"  BERT model:  {matcher._model_name}")
    else:
        print(f"  ⚠ Install sentence-transformers for BERT-based matching")


# ═══════════════════════════════════════════════════════════════════
#  3. Shortlisting Accuracy
# ═══════════════════════════════════════════════════════════════════

def evaluate_shortlisting():
    print("\n" + "=" * 60)
    print("  SHORTLISTING ACCURACY")
    print("=" * 60)

    # Ground truth: which candidates SHOULD be shortlisted for each job
    #   (job_skills, [indices of CVs that should pass])
    shortlist_gt = [
        (["python", "django", "postgresql", "docker", "aws"], [0]),      # back-end job → only CV0
        (["python", "machine learning", "tensorflow", "sql"], [1]),       # ML job → only CV1
        (["kotlin", "android", "firebase", "git"], [2]),                  # Android job → only CV2
        (["javascript", "react", "css", "html"], [0]),                    # frontend job → CV0 (has JS/React)
    ]

    parser = CVParser()
    matcher = SemanticMatcher()
    shortlister = Shortlister()

    all_precisions = []
    all_recalls = []

    for job_skills, correct_indices in shortlist_gt:
        job = Job(
            job_id="j1", title="Test Job", company_name="X",
            description=" ".join(job_skills),
            required_skills=job_skills,
            matching_threshold=55.0,
        )

        match_results = []
        for i, item in enumerate(GROUND_TRUTH_CVS):
            cv = parser.parse_text(item["raw"])
            mr = matcher.match_cv_to_job(cv, job)
            mr.job_id = str(i)  # tag MR with CV index for tracking
            match_results.append(mr)

        result = shortlister.shortlist_for_job(match_results, job)

        pred_shortlisted = set()
        for mr in result.shortlisted:
            if mr.job_id and mr.job_id.isdigit():
                pred_shortlisted.add(int(mr.job_id))

        tp = len(pred_shortlisted & set(correct_indices))
        fp = len(pred_shortlisted - set(correct_indices))
        fn = len(set(correct_indices) - pred_shortlisted)

        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        all_precisions.append(p)
        all_recalls.append(r)

        skills_str = ", ".join(job_skills[:3])
        print(f"  Job [{skills_str:30s}]  P={p:.3f}  R={r:.3f}  "
              f"shortlisted={len(result.shortlisted)}  correct={tp}/{len(correct_indices)}")

    avg_p = sum(all_precisions) / len(all_precisions)
    avg_r = sum(all_recalls) / len(all_recalls)
    avg_f1 = 2 * avg_p * avg_r / (avg_p + avg_r) if (avg_p + avg_r) > 0 else 0.0
    print(f"\n  ─────────────────────────────────────────────")
    print(f"  Avg Precision: {avg_p:.3f}")
    print(f"  Avg Recall:    {avg_r:.3f}")
    print(f"  Avg F1:        {avg_f1:.3f}")


# ═══════════════════════════════════════════════════════════════════
#  4. Summary Report
# ═══════════════════════════════════════════════════════════════════

def print_summary():
    print("\n\n" + "█" * 60)
    print("  ACCURACY EVALUATION SUMMARY")
    print("█" * 60)

    print("""
  ┌─────────────────────┬──────────────────────────────────┐
  │ Component           │ Metric                           │
  ├─────────────────────┼──────────────────────────────────┤
  │ CV Parsing (Skills) │ Precision / Recall / F1          │
  │ CV Parsing (Fields) │ Accuracy (% correct)             │
  │ Semantic Matching   │ MAE (Mean Absolute Error)        │
  │ Shortlisting        │ Precision@K / Recall@K           │
  └─────────────────────┴──────────────────────────────────┘

  How to improve accuracy:
  • Add more annotated CVs to GROUND_TRUTH_CVS (more data = better eval)
  • Install sentence-transformers:  pip install sentence-transformers
  • Install spaCy:                  pip install spacy && python -m spacy download en_core_web_lg
  • Tune matching_threshold in shortlisting
  """)


# ═══════════════════════════════════════════════════════════════════
#  Dataset Evaluation (reads data/Resume/Resume.csv)
# ═══════════════════════════════════════════════════════════════════

def evaluate_with_dataset(use_jobs=False):
    dataset_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "Resume", "Resume.csv"
    )
    jobs_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "monster_com-job_sample.csv"
    )

    if not os.path.isfile(dataset_path):
        print(f"\n❌ Dataset not found: {dataset_path}")
        print("   Place Resume.csv in data/Resume/")
        return

    print("\n" + "=" * 70)
    print("  DATASET EVALUATION — Kaggle Resume Dataset")
    print("=" * 70)

    # Load resumes
    resumes = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            resumes.append(row)

    print(f"\n  Total resumes loaded: {len(resumes)}")
    categories = set(r["Category"] for r in resumes)
    print(f"  Categories ({len(categories)}): {', '.join(sorted(categories))}")

    # Parse a sample from each category
    parser = CVParser()
    spacy_parser = SpacyNerParser()
    matcher = SemanticMatcher(lazy_load=True)

    print(f"\n  Model: spaCy={'✓' if spacy_parser.is_using_spacy else '✗'}"
          f" | BERT={'✓' if matcher.using_bert else '✗ (lazy)'}")
    print(f"\n  {'Cat':15s} {'Name':20s} {'Skills':>7s} {'Email':>6s} {'Phone':>6s} {'GPA':>5s} {'Exp':>5s}")
    print(f"  {'─'*15} {'─'*20} {'─'*7} {'─'*6} {'─'*6} {'─'*5} {'─'*5}")

    stat_skills_found, stat_email_found, stat_phone_found = 0, 0, 0
    stat_exp_found, stat_name_found = 0, 0
    total_parsed = 0

    for cat in sorted(categories):
        cat_resumes = [r for r in resumes if r["Category"] == cat]
        sample = random.choice(cat_resumes)
        text = sample["Resume_str"]

        try:
            cv = parser.parse_text(text)
            total_parsed += 1
            n_skills = len(cv.skills)
            has_email = 1 if cv.email else 0
            has_phone = 1 if cv.phone else 0
            has_name = 1 if cv.candidate_name else 0
            has_exp = 1 if cv.years_of_experience > 0 else 0
            gpa_str = f"{cv.gpa:.1f}" if cv.gpa > 0 else "-"

            stat_skills_found += n_skills
            stat_email_found += has_email
            stat_phone_found += has_phone
            stat_name_found += has_name
            stat_exp_found += has_exp

            name_short = cv.candidate_name[:18] if cv.candidate_name else "❌"
            print(f"  {cat:15s} {name_short:20s} {n_skills:5d}   {'✓' if has_email else '✗'}"
                  f"     {'✓' if has_phone else '✗'}     {gpa_str:>4s}  {'✓' if has_exp else '✗'}")
        except Exception as e:
            print(f"  {cat:15s} {'ERROR':20s} {str(e)[:40]}")

    print(f"\n  ──────────────────────────────────────────────────────")
    print(f"  Parsed CVs:        {total_parsed}")
    print(f"  Name found:        {stat_name_found}/{total_parsed} ({100*stat_name_found//total_parsed if total_parsed else 0}%)")
    print(f"  Email found:       {stat_email_found}/{total_parsed} ({100*stat_email_found//total_parsed if total_parsed else 0}%)")
    print(f"  Phone found:       {stat_phone_found}/{total_parsed} ({100*stat_phone_found//total_parsed if total_parsed else 0}%)")
    print(f"  Experience found:  {stat_exp_found}/{total_parsed} ({100*stat_exp_found//total_parsed if total_parsed else 0}%)")
    print(f"  Avg skills/CV:     {stat_skills_found/total_parsed:.1f}" if total_parsed else "  N/A")

    # Optional: also run matcher with Monster.com jobs
    if use_jobs and os.path.isfile(jobs_path):
        print(f"\n  ── Matching against Monster.com Job Dataset ──")
        with open(jobs_path, "r", encoding="utf-8") as f:
            job_reader = csv.DictReader(f)
            sample_jobs = []
            for j, row in enumerate(job_reader):
                if j >= 5:
                    break
                sample_jobs.append(row)

        sample_cv = parser.parse_text(resumes[0]["Resume_str"])
        for j, job_row in enumerate(sample_jobs):
            title = (job_row.get("job_title", job_row.get("title", "Unknown")) or "Unknown")[:30]
            desc = (job_row.get("job_description", job_row.get("description", "")) or "")[:300]
            org = job_row.get("organization", job_row.get("Company", "Unknown")) or "Unknown"
            sector = job_row.get("sector", "")
            job_obj = Job(
                job_id=f"m{j}",
                title=title,
                company_name=org,
                description=desc,
                required_skills=[s.strip().lower() for s in
                                 (sector or "").replace("/", " ").split()] or ["python"],
            matching_threshold=55.0,
            )
            match = matcher.match_cv_to_job(sample_cv, job_obj)
            print(f"  {title:30s} Score: {match.match_score:5.1f}  ({org[:20]})")


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

def main():
    use_dataset = "--dataset" in sys.argv
    use_jobs = "--jobs" in sys.argv

    print("HireMentor NLP — Accuracy Evaluation")

    if use_dataset:
        evaluate_with_dataset(use_jobs)
    else:
        print(f"Ground truth CVs: {len(GROUND_TRUTH_CVS)}")
        print(f"Human-judged pairs: {len(HUMAN_MATCH_SCORES)}")
        evaluate_cv_parsing()
        evaluate_semantic_matching()
        evaluate_shortlisting()
        print_summary()

    print("\n✅ Evaluation complete!")


if __name__ == "__main__":
    main()
