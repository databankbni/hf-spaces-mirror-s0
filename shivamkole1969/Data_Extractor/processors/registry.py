"""
Processor Registry - Maps report type names to their processor classes.

To register a new processor:
1. Import the processor class
2. Add it to the PROCESSORS dict below

The key must match the subfolder name (case-insensitive matching is done in get_processor).
"""

from pathlib import Path
from processors.EGR import EGRProcessor
from processors.TAS import TASProcessor
from processors.TAS_Monthly import TASMonthlyProcessor
from processors.HAY import HAYProcessor
from processors.RJ import RJProcessor
from processors.UBS import UBSProcessor
from processors.RBC_Monthly import RBCMonthlyProcessor
from processors.RBC_Weekly import RBCWeeklyProcessor
from processors.RBC_Global_Weekly import RBCGlobalWeeklyProcessor
from processors.RBC_Perlins_Ponderings import RBCPerlinsPonderingsProcessor
from processors.MNCS import MNCSProcessor
from processors.TD_CDN_Weekly import TDCDNWeeklyProcessor
from processors.CA_Daily_Gold import CADailyGoldProcessor
from processors.RBC_News_Nashville import RBCNewsNashvilleProcessor
from processors.PET_Weekly import PETWeeklyProcessor

PROCESSORS = {
    "EGR": EGRProcessor,
    "TAS Daily Brief": TASProcessor,
    "TAS Monthly Report": TASMonthlyProcessor,
    "HAY": HAYProcessor,
    "RJ Monthly": RJProcessor,
    "UBS Global": UBSProcessor,
    "RBC Monthly Software": RBCMonthlyProcessor,
    "RBC Weekly Software": RBCWeeklyProcessor,
    "RBC Global Financial Weekly": RBCGlobalWeeklyProcessor,
    "RBC Perlin's Ponderings": RBCPerlinsPonderingsProcessor,
    "MNCS": MNCSProcessor,
    "TD CDN Weekly Metals & Mining": TDCDNWeeklyProcessor,
    "CA Daily Gold": CADailyGoldProcessor,
    "RBC News from Nashville": RBCNewsNashvilleProcessor,
    "PET Weekly": PETWeeklyProcessor,
}

def get_report_folder(report_type: str) -> Path:
    """Get the relative path to a report's storage folder."""
    # The user has specific nested folders for RBC
    folder_map = {
        "TAS Daily Brief": "TAS",
        "TAS Monthly Report": "TAS monthly",
        "RBC Monthly Software": "RBC/RBC Software/RBC Monthly Software",
        "RBC Weekly Software": "RBC/RBC Software/RBC Weekly software",
        "RBC Global Financial Weekly": "RBC/Global Financial Weekly",
        "RBC Perlin's Ponderings": "RBC/Perlin’s Ponderings",
        "RJ Monthly": "RJ",
        "UBS Global": "UBS Global",
        "TD CDN Weekly Metals & Mining": "TD/CDN Weekly Metals & Mining",
        "CA Daily Gold": "CA/Daily Gold",
        "RBC News from Nashville": "RBC/News from nashville",
        "PET Weekly": "PET",
    }
    rel_path = folder_map.get(report_type, report_type)
    return Path(rel_path)

def get_processor(report_type: str, api_keys: list, output_folder: Path):
    """
    Get the appropriate processor for a report type.
    """
    processor_class = PROCESSORS.get(report_type)
    if processor_class is None:
        # Try case-insensitive match
        for key, cls in PROCESSORS.items():
            if key.upper() == report_type.upper():
                processor_class = cls
                break
    
    if processor_class:
        return processor_class(api_keys=api_keys, output_folder=output_folder)
    
    return None

def get_available_processors() -> list:
    """Return list of registered processor names with grouping info and available files."""
    import os
    processors = []
    # Base directory of the project (parent of processors/)
    base_path = Path(__file__).parent.parent
    
    for name, cls in PROCESSORS.items():
        group = None
        if name.startswith("TAS"):
            group = "TAS"
        elif name.startswith("RBC"):
            group = "RBC"
        elif name.startswith("TD"):
            group = "TD"
        elif name.startswith("CA"):
            group = "CA"
        elif name.startswith("PET"):
            group = "PET"
            
        # Determine folder to scan for existing files
        folder_rel = get_report_folder(name)
        folder_path = base_path / folder_rel
        
        files = []
        if folder_path.exists() and folder_path.is_dir():
            # Include supported extensions + common spreadsheet formats
            valid_exts = tuple(cls.SUPPORTED_EXTENSIONS) + ('.xlsx', '.xls')
            files = [f for f in os.listdir(folder_path) if f.lower().endswith(valid_exts)]
            
        processors.append({
            "name": name,
            "description": cls.PROCESSOR_NAME,
            "extensions": cls.SUPPORTED_EXTENSIONS,
            "group": group,
            "files": sorted(files)
        })
    return processors
