from __future__ import annotations
from .generic_adapter import GenericAdapter

class Adapter(GenericAdapter):
    adapter_name = __name__.split('.')[-1]
