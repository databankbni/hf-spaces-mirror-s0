from collections import Counter
from typing import Sequence

def detect_page_offset(page_numbers: Sequence[tuple[int, int | None]]) -> int:
    """
    Given a list of (pdf_index, printed_number) pairs, compute the page offset.
    printed = pdf_index - page_offset -> page_offset = pdf_index - printed
    Returns the mode of page_offset. Requires agreement on > 60% of non-null samples.
    If no agreement or no samples, returns 0.
    """
    deltas = []
    for pdf_index, printed in page_numbers:
        if printed is not None:
            deltas.append(pdf_index - printed)
            
    if not deltas:
        return 0
        
    counts = Counter(deltas)
    most_common, count = counts.most_common(1)[0]
    
    if count / len(deltas) >= 0.6:
        return most_common
    return 0
