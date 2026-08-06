import re

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from app.ingestion.domain.models import Block

# GOT-OCR transcribes DİM STEM books in LaTeX, not Markdown: section titles arrive
# as \title{...}/\section{...}, never as "# ...". MarkdownIt then sees them as plain
# paragraphs, so the whole book collapses into one section (GRO-123). Normalise the
# LaTeX sectioning commands into Markdown headings before parsing so the existing
# heading→section machinery (chunking.py) works unchanged.
_LATEX_HEADINGS = (
    (re.compile(r"\\chapter\*?\{([^{}]+)\}"), "# "),
    (re.compile(r"\\section\*?\{([^{}]+)\}"), "# "),
    (re.compile(r"\\title\{([^{}]+)\}"), "# "),
    (re.compile(r"\\subsection\*?\{([^{}]+)\}"), "## "),
)


def _latex_headings_to_markdown(text: str) -> str:
    """Rewrite LaTeX sectioning commands as Markdown ATX headings.

    A \\title{...} whose body contains LaTeX line breaks (``\\\\``) is front-matter —
    the anthem, the author list, a dedication — not a topic title, so it is left as
    prose. Single-line titles ("Funksiyanın ekstremumları") become headings.
    """
    for pattern, prefix in _LATEX_HEADINGS:
        def _repl(m: re.Match[str], _prefix: str = prefix) -> str:
            body = m.group(1).strip()
            if "\\\\" in body:  # multi-line ⇒ front-matter/author block, keep as text
                return body
            return f"\n{_prefix}{body}\n"

        text = pattern.sub(_repl, text)
    return text


def extract_markdown_blocks(markdown_text: str, page_number: int, method: str) -> list[Block]:
    """Extracts blocks from Markdown text (usually emitted by GOT-OCR or Docling)."""
    markdown_text = _latex_headings_to_markdown(markdown_text)
    md = MarkdownIt()
    tokens = md.parse(markdown_text)
    node = SyntaxTreeNode(tokens)
    
    lines = markdown_text.splitlines()
    blocks = []
    reading_order = 1
    
    for child in node.children:
        # We can extract the raw text using the source map
        if child.map:
            raw_text = "\n".join(lines[child.map[0]:child.map[1]]).strip()
        else:
            # Fallback to inline content
            if child.children and child.children[0].type == "inline":
                raw_text = child.children[0].content.strip()
            else:
                raw_text = "".join(t.content for t in child.children).strip()
                
        if not raw_text:
            continue
            
        if child.type == "heading":
            level = int(child.tag[1:])
            # For heading we only want the actual text, not the '#' prefix
            if child.children and child.children[0].type == "inline":
                clean_text = child.children[0].content.strip()
            else:
                clean_text = raw_text.lstrip("#").strip()
                
            # Defer heading classification to HeadingDetector
            blocks.append(Block(
                type="text",
                text=clean_text,
                page=page_number,
                reading_order=reading_order,
                confidence=0.9,
                method=method,
                metadata={"is_markdown_heading": True, "markdown_level": level}
            ))
            reading_order += 1
            
        elif child.type == "paragraph":
            btype = "text"
            if raw_text.startswith("$$") and raw_text.endswith("$$"):
                btype = "formula"
            
            blocks.append(Block(
                type=btype,
                text=raw_text,
                page=page_number,
                reading_order=reading_order,
                confidence=0.8,
                method=method
            ))
            reading_order += 1
            
        elif child.type in ("table", "fence", "math_block"):
            btype = "table" if child.type == "table" else "formula" if child.type == "math_block" else "text"
            blocks.append(Block(
                type=btype,
                text=raw_text,
                page=page_number,
                reading_order=reading_order,
                confidence=0.8,
                method=method
            ))
            reading_order += 1
            
    return blocks
