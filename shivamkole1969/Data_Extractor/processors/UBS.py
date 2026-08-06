import pandas as pd
import numpy as np
from datetime import datetime
from processors.base import BaseProcessor

class UBSProcessor(BaseProcessor):
    PROCESSOR_NAME = "UBS Global Broker Report"
    SUPPORTED_EXTENSIONS = [".xlsx", ".xls"]

    def process(self, input_file: str, job) -> str:
        job.message = "Initializing UBS extraction..."
        job.progress = 10
        
        try:
            # Read the report
            try:
                df = pd.read_excel(input_file)
            except Exception as e:
                print(f"Standard pandas read failed, falling back to xlrd: {str(e)}")
                df = pd.read_excel(input_file, engine='xlrd')
            job.progress = 30
            job.message = "Transforming data..."
            
            # 1. CAPEX absolute value
            for col in ["CAPEXFY1", "CAPEXFY2", "CAPEXFY3"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').abs()
            
            # 2. NETDEBT signs flip
            for col in ["NETDEBTFY1", "NETDEBTFY2", "NETDEBTFY3"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce') * -1
            
            # Columns to keep (from user's script)
            tokeep = [
                "COMPANY_NAME", "Company Code", "Coverage as Market", "Data point", 
                "REUTERS", "TARGET_PRICE", "RECOMMENDATION", "1YE-MM/YY",
                "CPSFY1", "CPSFY2", "CPSFY3", 
                "NDPSFY1", "NDPSFY2", "NDPSFY3", 
                "NETFY1", "NETFY2", "NETFY3", 
                "PREFY1", "PREFY2", "PREFY3", 
                "SALESFY1", "SALESFY2", "SALESFY3", 
                "BVPSFY1", "BVPSFY2", "BVPSFY3", 
                "EDITDAFY1", "EDITDAFY2", "EDITDAFY3", 
                "EBITFY1", "EBITFY2", "EBITFY3", 
                "NETDEBTFY1", "NETDEBTFY2", "NETDEBTFY3", 
                "EPS_DIL_ADJQ1Y1", "EPS_DIL_ADJQ2Y1", "EPS_DIL_ADJQ3Y1", "EPS_DIL_ADJQ4Y1", "EPS_DIL_ADJFY1",
                "EPS_DIL_ADJQ1Y2", "EPS_DIL_ADJQ2Y2", "EPS_DIL_ADJQ3Y2", "EPS_DIL_ADJQ4Y2", "EPS_DIL_ADJFY2",
                "EPS_DIL_ADJQ1Y3", "EPS_DIL_ADJQ2Y3", "EPS_DIL_ADJQ3Y3", "EPS_DIL_ADJQ4Y3", "EPS_DIL_ADJFY3",
                "EPS_DIL_REPQ1Y1", "EPS_DIL_REPQ2Y1", "EPS_DIL_REPQ3Y1", "EPS_DIL_REPQ4Y1", "EPS_DIL_REPFY1",
                "EPS_DIL_REPQ1Y2", "EPS_DIL_REPQ2Y2", "EPS_DIL_REPQ3Y2", "EPS_DIL_REPQ4Y2", "EPS_DIL_REPFY2",
                "EPS_DIL_REPQ1Y3", "EPS_DIL_REPQ2Y3", "EPS_DIL_REPQ3Y3", "EPS_DIL_REPQ4Y3", "EPS_DIL_REPFY3",
                "CAPEXFY1", "CAPEXFY2", "CAPEXFY3", 
                "ANALYST_NAME", "EPS_CURRENCY", "REPORTING_CURRENCY", "EMAIL_ADDRESS",
                "FFOPSFY1", "FFOPSFY2", "FFOPSFY3"
            ]
            
            # Filter available columns
            available_cols = [c for c in tokeep if c in df.columns]
            out = df[available_cols]
            
            job.progress = 80
            job.companies_found = len(out)
            
            # Fill NaNs
            for col in out.columns:
                out[col] = out[col].astype(object).fillna("-")
            
            # Generate Output
            output_name = f"UBS_Extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            output_path = self.output_folder / output_name
            out.to_excel(output_path, index=False)
            
            job.progress = 100
            job.message = "Successfully generated Excel report."
            job.output_file = output_name
            return output_name
            
        except Exception as e:
            job.status = "error"
            job.message = f"UBS Processing failed: {str(e)}"
            raise e
