"""
Processors Package - Modular report processing system
Each report type has its own dedicated processor file.
"""

from processors.base import BaseProcessor
from processors.registry import get_processor, get_available_processors

__all__ = ["BaseProcessor", "get_processor", "get_available_processors"]
