import pdfplumber
from app.ingestion.domain.models import Block

def extract_native_blocks(pdf_path: str, page_number: int, method: str = "pdfplumber_native") -> list[Block]:
    """Extracts blocks (headings, text) from a native PDF page using pdfplumber."""
    blocks = []
    
    with pdfplumber.open(pdf_path) as pdf:
        if page_number > len(pdf.pages):
            return blocks
            
        page = pdf.pages[page_number - 1]
        # extract_words returns dicts: {text, x0, x1, top, bottom, upright, fontname, size}
        words = page.extract_words(
            x_tolerance=3, 
            y_tolerance=3, 
            keep_blank_chars=False, 
            use_text_flow=False, 
            extra_attrs=["size", "fontname"]
        )
        
        if not words:
            return blocks
            
        # 1. Sort words spatially (top-down, left-right)
        words.sort(key=lambda w: (round(w["top"], 1), w["x0"]))
        
        # 2. Group into lines
        lines = []
        current_line = []
        last_top = None
        for w in words:
            if last_top is None:
                current_line.append(w)
                last_top = w["top"]
            else:
                # Same line if vertical difference is small
                if abs(w["top"] - last_top) < w["size"] * 0.5:
                    current_line.append(w)
                else:
                    lines.append(current_line)
                    current_line = [w]
                    last_top = w["top"]
        if current_line:
            lines.append(current_line)
            
        # 3. Group lines into blocks
        current_block_lines = []
        last_line_bottom = None
        order_idx = 1
        
        def commit_block(blk_lines, order):
            if not blk_lines:
                return None
            
            text = "\n".join(" ".join(w["text"] for w in line) for line in blk_lines)
            x0 = min(w["x0"] for line in blk_lines for w in line)
            top = min(w["top"] for line in blk_lines for w in line)
            x1 = max(w["x1"] for line in blk_lines for w in line)
            bottom = max(w["bottom"] for line in blk_lines for w in line)
            
            first_line = blk_lines[0]
            max_size = max((w["size"] for w in first_line), default=0)
            is_bold = any("bold" in str(w.get("fontname", "")).lower() for w in first_line)
            
            # Defer heading classification to HeadingDetector.
            return Block(
                type="text",
                text=text,
                page=page_number,
                bbox=[x0, top, x1, bottom],
                reading_order=order,
                confidence=1.0,  # Native text is highly confident
                method=method,
                metadata={"max_size": max_size, "is_bold": is_bold, "line_count": len(blk_lines)}
            )

        for line in lines:
            line_top = min(w["top"] for w in line)
            line_size = max((w["size"] for w in line), default=12)
            
            if last_line_bottom is not None:
                # Start new block if vertical gap is large enough
                if (line_top - last_line_bottom) > line_size * 0.5:
                    blk = commit_block(current_block_lines, order_idx)
                    if blk:
                        blocks.append(blk)
                        order_idx += 1
                    current_block_lines = []
                    
            current_block_lines.append(line)
            last_line_bottom = max(w["bottom"] for w in line)
            
        blk = commit_block(current_block_lines, order_idx)
        if blk:
            blocks.append(blk)
            
    return blocks
