from pathlib import Path
from datetime import datetime
import pandas as pd
import importlib.util
from processors.base import BaseProcessor

class CADailyGoldProcessor(BaseProcessor):
    PROCESSOR_NAME = "CA Daily Gold"
    SUPPORTED_EXTENSIONS = [".pdf"]

    def process(self, input_file: str, job) -> str:
        job.message = "Initializing CA Daily Gold extraction..."
        job.progress = 10
        
        # Dynamically import the script due to spaces and special characters in path
        script_path = Path(__file__).parent.parent / "CA" / "Daily Gold" / "DG automation.py"
        spec = importlib.util.spec_from_file_location("dg_automation", str(script_path))
        dg_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dg_module)
        
        job.progress = 30
        job.message = "Extracting data from PDF..."
        
        df_targets, df_eps, df_cfps, df_commodity = dg_module.extract_financial_data(str(input_file))
        job.companies_found = len(df_targets) if not df_targets.empty else 0
        
        job.progress = 70
        job.message = "Writing output to Excel..."
        
        output_name = f"CA_Daily_Gold_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        output_path = self.output_folder / output_name
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            if not df_targets.empty:
                df_targets.to_excel(writer, sheet_name='Recs and Targets', index=False)
            if not df_eps.empty:
                df_eps.to_excel(writer, sheet_name='EPS', index=False)
            if not df_cfps.empty:
                df_cfps.to_excel(writer, sheet_name='CFPS', index=False)
            if not df_commodity.empty:
                df_commodity.to_excel(writer, sheet_name='Commodity', index=False)
        
        job.progress = 100
        job.message = "Successfully generated Excel report."
        job.output_file = output_name
        return output_name
