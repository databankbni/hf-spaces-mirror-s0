from __future__ import annotations
from typing import Any, Protocol

class SiteAdapter(Protocol):
    adapter_name: str
    def extract(self, *, target: dict[str, Any], search_row: dict[str, Any], extract_row: dict[str, Any], classification: dict[str, Any]) -> dict[str, Any]: ...
