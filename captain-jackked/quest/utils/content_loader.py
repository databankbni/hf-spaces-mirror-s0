import re
from pathlib import Path
import markdown2

BASE_DIR = Path(__file__).parent.parent
CONTENT_DIR = BASE_DIR / 'content'

def _beautify(snake: str) -> str:
    return snake.replace('_com_', ',').replace('_', ' ').title()

def _split_numbered_name(name: str) -> tuple[int, str]:
    parts = name.split('_', 1)
    if len(parts) == 2 and parts[0].isdigit():
        return int(parts[0]), _beautify(parts[1])
    return 0, _beautify(name)

def _generate_slug(category_dir: str, filename: str) -> str:
    parts = category_dir.split('_', 1)
    n = parts[0] if parts[0].isdigit() else '0'
    
    parts = filename.split('_', 1)
    m = parts[0] if parts[0].isdigit() else '0'
    rest = parts[1] if len(parts) > 1 else filename
    
    return f"{n}_{m}_{rest}"


def _load_markdown_file(file_path: Path) -> dict | None:
    if not file_path.exists():
        return None
    try:
        text = file_path.read_text(encoding='utf-8')
    except Exception:
        return None
    
    # Parse direction metadata (<!-- direction: ... -->)
    directions = []
    direction_match = re.search(r'<!-- direction: (.*?) -->', text)
    if direction_match:
        raw_dirs = direction_match.group(1)
        directions = [d.strip() for d in raw_dirs.split(',') if d.strip()]

    html = markdown2.markdown(
        text,
        extras=['tables', 'fenced-code-blocks', 'header-ids', 'metadata', 'footnotes']
    )
    
    category_dir = file_path.parent.name
    filename = file_path.stem
    section = file_path.parent.parent.name
    
    part_num, title = _split_numbered_name(filename)
    _, clean_cat = _split_numbered_name(category_dir)
    
    subtitle = f"{clean_cat} — Part {part_num}" if part_num else clean_cat
    slug = _generate_slug(category_dir, filename)
    
    theme = html.metadata.get('theme', None)
    if not theme:
        # Default themes based on section
        if section == 'archive':
            theme = 'jackked'
        else:
            theme = 'generic'

    return {
        'slug': slug,
        'title': title,
        'subtitle': subtitle,
        'group_category': category_dir,
        'display_category': clean_cat,
        'content': html,
        'metadata': html.metadata,
        'directions': directions,
        'theme': theme,
        'path': file_path,
        'url': f"/{section}/{slug}",
        'snippet': html.metadata.get('snippet', '')
    }

def load_content(section: str) -> list[dict]:
    root_path = CONTENT_DIR / section
    if not root_path.exists():
        return []
    
    items = []
    for category_path in sorted(root_path.iterdir()):
        if category_path.is_dir():
            category_name = category_path.name
            _, clean_cat = _split_numbered_name(category_name)
            
            markdown_files = sorted(category_path.glob('*.md'))
            if not markdown_files:
                items.append({
                    'slug': None,
                    'title': 'Coming Soon...',
                    'subtitle': clean_cat,
                    'group_category': category_name,
                    'display_category': clean_cat,
                    'content': '',
                    'url': '#',
                    'is_placeholder': True
                })
            else:
                for file_path in markdown_files:
                    data = _load_markdown_file(file_path)
                    if data:
                        items.append(data)
    return items

def get_grouped_content(section: str, view_mode: str = 'series') -> list[tuple[str, list[dict]]]:
    """
    Returns content grouped by Series (physical folder) or Topic (logic tag).
    """
    items = load_content(section)
    
    groups = {}
    
    if view_mode == 'topic':
        # Group by extracted 'directions' tags
        for item in items:
            # If no tags, maybe group under "Uncategorized" or skip? 
            # For now, put in 'Misc' if empty, or just skip.
            # Actually, let's use the 'display_category' as a fallback if no tags? 
            # No, 'Series' is the fallback view. Topic view should be strict.
            tags = item.get('directions', [])
            if not tags:
                # Optional: Handle untagged items
                pass
            for tag in tags:
                # Tag format might be "1_math". Clean it up for display?
                # _split_numbered_name handles "1_math" -> (1, "Math")
                _, display_name = _split_numbered_name(tag)
                
                if display_name not in groups:
                    groups[display_name] = []
                # Check for duplicates? No, list is fine.
                if item not in groups[display_name]:
                    groups[display_name].append(item)

    else: # Default: 'series'
        # Group by physical folder (group_category)
        for item in items:
            cat = item['group_category'] # e.g. "1_the_story"
            _, display_name = _split_numbered_name(cat)
            
            if display_name not in groups:
                groups[display_name] = []
            groups[display_name].append(item)

    # Sort groups by Key (Alphabetical? Or Numbered?)
    # Since keys are now "The Story", "Math", we lost the number prefix in the key.
    # To preserve order, we might need to keep the raw key (e.g. "1_the_story") as the sort key.
    
    # Let's Refine: groups should be keyed by SortKey, but we return DisplayName.
    # But wait, 'directions' might be just "math" or "1_math". 
    # Current instruction: "1_math" is the tag.
    
    # Re-doing the grouping to preserve sort order:
    raw_groups = {}
    
    if view_mode == 'topic':
         for item in items:
            tags = item.get('directions', [])
            for tag in tags:
                if tag not in raw_groups:
                    raw_groups[tag] = []
                if item not in raw_groups[tag]:
                    raw_groups[tag].append(item)
    else:
        for item in items:
            cat = item['group_category']
            if cat not in raw_groups:
                raw_groups[cat] = []
            raw_groups[cat].append(item)
            
    # Sort by raw key (which handles "1_math" vs "2_anatomy")
    sorted_result = []
    for key in sorted(raw_groups.keys()):
        # Convert key to display name
        _, display_name = _split_numbered_name(key)
        sorted_result.append((display_name, raw_groups[key]))
        
    return sorted_result

def get_content(section: str, slug: str) -> dict | None:
    root_path = CONTENT_DIR / section
    if not root_path.exists():
        return None
    
    for category_path in root_path.iterdir():
        if category_path.is_dir():
            for file_path in category_path.glob('*.md'):
                if _generate_slug(category_path.name, file_path.stem) == slug:
                    data = _load_markdown_file(file_path)
                    if data:
                        data['section'] = section
                        # Find prev/next within same category (series)
                        siblings = sorted(category_path.glob('*.md'))
                        idx = next((i for i, f in enumerate(siblings) if f == file_path), None)
                        if idx is not None:
                            if idx > 0:
                                prev_data = _load_markdown_file(siblings[idx - 1])
                                if prev_data:
                                    data['prev'] = {'url': prev_data['url'], 'title': prev_data['title']}
                            if idx < len(siblings) - 1:
                                next_data = _load_markdown_file(siblings[idx + 1])
                                if next_data:
                                    data['next'] = {'url': next_data['url'], 'title': next_data['title']}
                    return data
    return None
