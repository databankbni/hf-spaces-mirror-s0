from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ingestion.domain.models import SectionBlock


SECTION_LEVEL_KEY = "section_level"
LOGICAL_SECTION_ID_KEY = "logical_section_id"
IS_NETWORK_NODE_KEY = "is_network_node"
PARENT_SECTION_ID_KEY = "parent_section_id"
PREVIOUS_SIBLING_SECTION_ID_KEY = "previous_sibling_section_id"
CONTINUATION_OF_SECTION_ID_KEY = "continuation_of_section_id"
SECTION_PATH_IDS_KEY = "section_path_ids"
SECTION_PATH_TITLES_KEY = "section_path_titles"
NETWORK_DEPTH_KEY = "section_network_depth"

_SECTION_ID_REFERENCE_KEYS = (
    PARENT_SECTION_ID_KEY,
    PREVIOUS_SIBLING_SECTION_ID_KEY,
    CONTINUATION_OF_SECTION_ID_KEY,
)


@dataclass(frozen=True)
class SectionNetworkStats:
    """Summary diagnostics for the derived section hierarchy."""

    sections: int
    logical_sections: int
    root_sections: int
    parented_sections: int
    edge_count: int
    max_depth: int
    continuation_sections: int

    @property
    def parented_pct(self) -> float:
        return self.parented_sections / self.logical_sections if self.logical_sections else 0.0


def annotate_section_network(sections: list[SectionBlock]) -> SectionNetworkStats:
    """Annotate section metadata with a deterministic parent/sibling/path network.

    The graph is derived from section heading levels. Synthetic segmentation-floor
    continuations are kept as persisted sections for chunk/page granularity, but
    they are marked as non-network nodes and linked back to the first logical
    section part so they do not create fake hierarchy depth.
    """

    stack: list[tuple[int, SectionBlock]] = []
    first_by_logical_id: dict[str, SectionBlock] = {}
    last_sibling_by_parent_and_level: dict[tuple[str | None, int], str] = {}

    logical_sections = 0
    root_sections = 0
    parented_sections = 0
    max_depth = 0
    continuation_sections = 0

    for section in sections:
        section_id = _section_id(section)
        logical_id = str(section.metadata.get(LOGICAL_SECTION_ID_KEY) or section_id)
        section.metadata[LOGICAL_SECTION_ID_KEY] = logical_id

        first_logical_section = first_by_logical_id.get(logical_id)
        if section.metadata.get("synthetic_continuation") is True and first_logical_section is not None:
            continuation_sections += 1
            _copy_continuation_network(section, first_logical_section)
            continue

        first_by_logical_id.setdefault(logical_id, section)
        logical_sections += 1

        level = _section_level(section)
        while stack and stack[-1][0] >= level:
            stack.pop()

        parent = stack[-1][1] if stack else None
        parent_id = _section_id(parent) if parent is not None else None
        previous_sibling_id = last_sibling_by_parent_and_level.get((parent_id, level))

        parent_path_ids = list(parent.metadata.get(SECTION_PATH_IDS_KEY, [])) if parent else []
        parent_path_titles = list(parent.metadata.get(SECTION_PATH_TITLES_KEY, [])) if parent else []
        path_ids = [*parent_path_ids, section_id]
        path_titles = [*parent_path_titles, _path_title(section)]
        depth = len(path_ids)

        _set_or_remove(section.metadata, PARENT_SECTION_ID_KEY, parent_id)
        _set_or_remove(section.metadata, PREVIOUS_SIBLING_SECTION_ID_KEY, previous_sibling_id)
        section.metadata[SECTION_LEVEL_KEY] = level
        section.metadata[IS_NETWORK_NODE_KEY] = True
        section.metadata[SECTION_PATH_IDS_KEY] = path_ids
        section.metadata[SECTION_PATH_TITLES_KEY] = path_titles
        section.metadata[NETWORK_DEPTH_KEY] = depth

        if parent_id is None:
            root_sections += 1
        else:
            parented_sections += 1
        max_depth = max(max_depth, depth)

        last_sibling_by_parent_and_level[(parent_id, level)] = section_id
        stack.append((level, section))

    return SectionNetworkStats(
        sections=len(sections),
        logical_sections=logical_sections,
        root_sections=root_sections,
        parented_sections=parented_sections,
        edge_count=parented_sections,
        max_depth=max_depth,
        continuation_sections=continuation_sections,
    )


def summarize_section_network(sections: list[SectionBlock]) -> SectionNetworkStats:
    """Read hierarchy diagnostics from already-annotated section metadata."""

    logical_sections = 0
    root_sections = 0
    parented_sections = 0
    max_depth = 0
    continuation_sections = 0

    for section in sections:
        if section.metadata.get("synthetic_continuation") is True:
            continuation_sections += 1
        if section.metadata.get(IS_NETWORK_NODE_KEY) is False:
            continue

        logical_sections += 1
        parent_id = section.metadata.get(PARENT_SECTION_ID_KEY)
        if parent_id:
            parented_sections += 1
        else:
            root_sections += 1
        max_depth = max(max_depth, _int_value(section.metadata.get(NETWORK_DEPTH_KEY), default=1))

    if logical_sections == 0 and sections:
        # Backward-compatible diagnostic for legacy/unannotated SectionBlocks.
        logical_sections = len(sections)
        root_sections = len(sections)
        max_depth = 1

    return SectionNetworkStats(
        sections=len(sections),
        logical_sections=logical_sections,
        root_sections=root_sections,
        parented_sections=parented_sections,
        edge_count=parented_sections,
        max_depth=max_depth,
        continuation_sections=continuation_sections,
    )


def remap_section_network_ids(metadata: dict[str, object], section_id_map: dict[str, str]) -> None:
    """Rewrite network ID references after section rows receive DB UUIDs."""
    if not section_id_map:
        return

    for key in _SECTION_ID_REFERENCE_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and value in section_id_map:
            metadata[key] = section_id_map[value]

    path_ids = metadata.get(SECTION_PATH_IDS_KEY)
    if isinstance(path_ids, list):
        metadata[SECTION_PATH_IDS_KEY] = [
            section_id_map.get(value, value) if isinstance(value, str) else value
            for value in path_ids
        ]


def _copy_continuation_network(section: SectionBlock, original: SectionBlock) -> None:
    original_id = _section_id(original)
    section.metadata[IS_NETWORK_NODE_KEY] = False
    section.metadata[CONTINUATION_OF_SECTION_ID_KEY] = original_id

    for key in (
        SECTION_LEVEL_KEY,
        PARENT_SECTION_ID_KEY,
        SECTION_PATH_IDS_KEY,
        SECTION_PATH_TITLES_KEY,
        NETWORK_DEPTH_KEY,
    ):
        if key in original.metadata:
            section.metadata[key] = original.metadata[key]


def _section_level(section: SectionBlock) -> int:
    return max(1, min(_int_value(section.metadata.get(SECTION_LEVEL_KEY), default=1), 6))


def _int_value(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _section_id(section: SectionBlock) -> str:
    return section.id or section.content_hash[:16]


def _path_title(section: SectionBlock) -> str:
    return section.section_title or f"Section {section.ordinal}"


def _set_or_remove(metadata: dict[str, object], key: str, value: object | None) -> None:
    if value is None:
        metadata.pop(key, None)
    else:
        metadata[key] = value
