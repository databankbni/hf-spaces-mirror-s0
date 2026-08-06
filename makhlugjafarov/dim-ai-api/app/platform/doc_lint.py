import sys
import re
from pathlib import Path

def lint_doc(content: str) -> list[str]:
    errors = []
    # Fail if doc claims "uses sparsevec" without a migration
    # Use negative lookbehinds/lookaheads to ignore quoted string from the doc's own instructions
    if re.search(r'(?<!["`])\buses?\s+sparsevec\b(?!["`])', content, re.IGNORECASE):
        errors.append("Claimed 'uses sparsevec' but it is not deployed.")
    return errors

def main():
    # Adjusting for path: apps/api/app/platform/doc_lint.py
    # repo root: ../../../../../
    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    target_doc = repo_root / "docs" / "SUBJECT_PIPELINE_REDESIGN.md"
    
    if not target_doc.exists():
        print(f"doc-lint: OK (target doc not found at {target_doc})")
        return 0
        
    content = target_doc.read_text(encoding='utf-8')
    errors = lint_doc(content)
    if errors:
        for err in errors:
            print(f"doc-lint error: {err}")
        return 1
        
    print("doc-lint: OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
