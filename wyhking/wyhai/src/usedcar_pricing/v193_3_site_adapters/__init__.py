from __future__ import annotations
from typing import Any
from .generic_adapter import GenericAdapter
from .guazi_adapter import Adapter as GuaziAdapter
from .autohome_usedcar_adapter import Adapter as AutohomeUsedcarAdapter
from .dongchedi_adapter import Adapter as DongchediAdapter
from .certified_used_adapter import Adapter as CertifiedUsedAdapter


def adapter_for(classification: dict[str, Any]):
    family = str(classification.get('source_family') or '')
    if family == 'guazi':
        return GuaziAdapter()
    if family == 'autohome_usedcar':
        return AutohomeUsedcarAdapter()
    if 'certified' in family or family in {'bmw_certified_used','audi_certified_used'}:
        return CertifiedUsedAdapter()
    if family == 'dongchedi':
        return DongchediAdapter()
    return GenericAdapter()
