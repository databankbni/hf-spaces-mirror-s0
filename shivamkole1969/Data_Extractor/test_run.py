import sys
import os
from pathlib import Path

# Add local lib to path
_LIB_DIR = str(Path(r'c:\Users\skole\MORNINGSTAR INC\Morningstar Mumbai - India-Earning-Estimates\Shivam\Estimates Data Extractor\lib'))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from processors.EGR import EGRProcessor

class DummyJob:
    def __init__(self):
        self.message = ""
        self.status = ""
        self.progress = 0
        self.output_file = ""

if __name__ == "__main__":
    job = DummyJob()
    processor = EGRProcessor(api_keys=[], output_folder=Path("output"))
    processor.run("EGR/EGR.pdf", job)
    
    print(f"Status: {job.status}")
    print(f"Output: {job.output_file}")
