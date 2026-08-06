import re
from dataclasses import dataclass, field
from app.ingestion.domain.models import Block

@dataclass
class HeadingPolicy:
    allow_font: bool = False
    # Trust markdown-heading metadata ('# ...'). GOT-OCR LaTeX sectioning
    # (\title/\section) is normalised to markdown upstream, so it lands here too.
    allow_markdown: bool = False
    deny_patterns: list[re.Pattern[str]] = field(default_factory=list)

HUM_POLICY = HeadingPolicy(
    allow_font=True,
    allow_markdown=False,
    # e.g. running headers/footers might not have specific patterns yet, but we can add them here
    deny_patterns=[],
)

STEM_FORMULA_POLICY = HeadingPolicy(
    allow_font=True,
    allow_markdown=True,
    deny_patterns=[
        re.compile(r"(?i)^mündəricat$"),          # TOC page
        re.compile(r"^\d+\.$"),                   # numbered exercise headers like "1."
        re.compile(r"^\d+$"),                     # bare page numbers
    ],
)

STEM_DESC_POLICY = HeadingPolicy(
    allow_font=True,
    allow_markdown=False,
    deny_patterns=[
        # figure captions typically start with Şəkil
        re.compile(r"(?i)^şəkil\s+\d+"),
    ],
)

def get_heading_policy(subject: str) -> HeadingPolicy:
    """Returns the HeadingPolicy for the given subject.
    Defaults to HUM if subject is unknown, pending full registry in Phase 5.
    """
    from app.ingestion.domain.category_policy import get_category_policy
    return get_category_policy(subject).heading_policy

class HeadingDetector:
    def __init__(self, policy: HeadingPolicy):
        self.policy = policy
        
    def _matches_text_pattern(self, text: str) -> tuple[bool, int | None]:
        """Fallback text-patterns for OCR with no layout."""
        text_lower = text.strip().lower()
        if text_lower.startswith("mövzu "):
            return True, 1
        if text_lower.startswith("§"):
            return True, 2
        return False, None

    def _is_heading(self, block: Block) -> tuple[bool, int | None]:
        """Evaluates whether a block is a heading based on signals, returning (is_heading, level)."""
        # 1. Markdown-heading signal (native '#' or normalised LaTeX sectioning)
        if self.policy.allow_markdown and block.metadata.get("is_markdown_heading"):
            level = block.metadata.get("markdown_level", 1)
            return True, level
            
        # 2. OCR layout signal (GRO-155/GRO-156). The layout-aware Tesseract TSV
        #    extractor flags lines visibly larger than the page's body text
        #    (height_ratio >= OCR_HEADING_HEIGHT_RATIO, few words). The absolute
        #    point-size thresholds below miss these because OCR-estimated font
        #    sizes run small (a 1.25x heading off ~10pt body is ~12.5pt, under the
        #    14pt gate), so trust the relative layout signal directly when present.
        if self.policy.allow_font and block.metadata.get("is_ocr_heading_candidate"):
            ratio = block.metadata.get("ocr_height_ratio") or 0
            level = 3
            if ratio >= 1.6:
                level = 1
            elif ratio >= 1.4:
                level = 2
            return True, level

        # 3. Font / Layout signal
        if self.policy.allow_font:
            max_size = block.metadata.get("max_size", 0)
            is_bold = block.metadata.get("is_bold", False)
            line_count = block.metadata.get("line_count", 1)

            if max_size > 14 or (max_size > 11 and is_bold and line_count == 1):
                level = 3
                if max_size >= 18:
                    level = 1
                elif max_size >= 14:
                    level = 2
                return True, level

        # 4. Text-pattern fallback
        matched, level = self._matches_text_pattern(block.text)
        if matched:
            return True, level

        return False, None

    def detect(self, blocks: list[Block]) -> list[Block]:
        """Applies heading detection rules to a list of blocks in-place."""
        for block in blocks:
            # We only evaluate blocks that are currently considered text (or markdown headings which we reset to text during extraction)
            if block.type != "text" and block.type != "heading":
                continue

            is_heading, level = self._is_heading(block)
            
            if is_heading:
                # Check deny lists
                denied = False
                for pattern in self.policy.deny_patterns:
                    if pattern.search(block.text.strip()):
                        denied = True
                        break
                
                if not denied:
                    block.type = "heading"
                    block.level = level
                else:
                    block.type = "text"
                    block.level = None
                    
        return blocks
