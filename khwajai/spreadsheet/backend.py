import os
import pickle
import pandas as pd
import numpy as np
import io
import json
import PyPDF2
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
from PIL import Image
import config

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

model = None
if config.GOOGLE_API_KEY:
    try:
        genai.configure(api_key=config.GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-3.5-flash')
    except: pass

class WorkspaceState:
    def __init__(self):
        self.sheets = {"Sheet 1": []}
        self.active_sheet = "Sheet 1"
        self.columns = {"Sheet 1": ["Date","Department","Revenue","Expenses","Status"]}
        self.load_from_disk()

    def get_active_data(self): return self.sheets.get(self.active_sheet, [])
    def set_active_data(self, data, columns=None):
        self.sheets[self.active_sheet] = data
        if columns: self.columns[self.active_sheet] = columns
        self.save_to_disk()

    def add_sheet(self, name, data, columns):
        base_name = name.replace(".csv", "").replace(".xlsx", "").replace(".pdf", "")
        counter = 1; unique_name = base_name
        while unique_name in self.sheets: unique_name = f"{base_name} ({counter})"; counter += 1
        self.sheets[unique_name] = data
        self.columns[unique_name] = columns
        self.active_sheet = unique_name
        self.save_to_disk()
        return unique_name

    def remove_sheet(self, name):
        if name in self.sheets:
            del self.sheets[name]; del self.columns[name]
            if self.active_sheet == name:
                self.active_sheet = list(self.sheets.keys())[0] if self.sheets else "Sheet 1"
                if not self.sheets: self.__init__()
            self.save_to_disk()

    def save_to_disk(self):
        try:
            with open(config.STATE_FILE, "wb") as f: pickle.dump((self.sheets, self.active_sheet, self.columns), f)
        except: pass

    def load_from_disk(self):
        if os.path.exists(config.STATE_FILE):
            try:
                with open(config.STATE_FILE, "rb") as f:
                    data = pickle.load(f)
                    if len(data) == 3: self.sheets, self.active_sheet, self.columns = data
                    else: self.sheets, self.active_sheet = data
            except: self.__init__()

workspace = WorkspaceState()

def find_header_row(df):
    max_non_nulls = 0; header_idx = 0
    for i, row in df.head(15).iterrows():
        non_null_count = row.dropna().astype(str).str.strip().replace('', np.nan).count()
        if non_null_count > max_non_nulls: max_non_nulls = non_null_count; header_idx = i
    if header_idx > 0:
        df.columns = df.iloc[header_idx].astype(str).str.strip()
        df = df.iloc[header_idx+1:].reset_index(drop=True)
    return df

def standardize_grid(df):
    df = df.dropna(how='all').fillna("")
    cols = []
    for c in df.columns:
        clean_c = str(c).strip()
        if clean_c.lower() in ["nan", "unnamed", "none", ""] or not clean_c: clean_c = "Data_Col"
        original = clean_c; count = 1
        while clean_c in cols: clean_c = f"{original} ({count})"; count += 1
        cols.append(clean_c)
    df.columns = cols
    if df.empty: return [], ["Col 1", "Col 2"]
    return df.to_dict(orient="records"), list(df.columns)

@app.get("/business-stats")
async def get_business_stats():
    data = workspace.get_active_data()
    if not data: return {"revenue": 0.0, "expenses": 0.0, "profit": 0.0, "margin": 0.0, "count": 0}
    df = pd.DataFrame(data)
    rev_col = next((c for c in df.columns if any(k in c.lower() for k in ['rev', 'sale', 'income', 'total', 'amount'])), None)
    exp_col = next((c for c in df.columns if any(k in c.lower() for k in ['exp', 'cost', 'tax', 'debit'])), None)
    revenue = float(pd.to_numeric(df[rev_col].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').sum()) if rev_col else 0.0
    expenses = float(pd.to_numeric(df[exp_col].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').sum()) if exp_col else 0.0
    profit = float(revenue - expenses)
    margin = float((profit / revenue * 100)) if revenue > 0 else 0.0
    return {"revenue": revenue, "expenses": expenses, "profit": profit, "margin": round(margin, 2), "count": len(df)}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), mode: str = Form("replace")):
    try:
        content = await file.read()
        filename = file.filename.lower()
        file_io = io.BytesIO(content)
        if filename.endswith('.csv'): df = pd.read_csv(file_io, low_memory=False)
        elif filename.endswith(('.xls', '.xlsx')): df = pd.read_excel(file_io, engine='openpyxl')
        else: return JSONResponse(status_code=400, content={"message": "Unsupported format."})
        
        new_data, new_cols = standardize_grid(df)
        if mode == "append":
            current_data = workspace.get_active_data()
            workspace.set_active_data(current_data + new_data, new_cols)
        else: workspace.add_sheet(file.filename, new_data, new_cols)
        return {"status": "success", "rows_loaded": len(new_data)}
    except Exception as e: return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/promote-header")
async def promote_header():
    try:
        df = pd.DataFrame(workspace.get_active_data())
        if df.empty: return {"status": "error"}
        new_header = df.iloc[0]; df = df[1:]; df.columns = new_header 
        cleaned_data, cols = standardize_grid(df)
        workspace.set_active_data(cleaned_data, cols)
        return {"status": "success"}
    except Exception as e: return {"error": str(e)}

@app.post("/cleanup")
async def cleanup_data():
    try:
        df = pd.DataFrame(workspace.get_active_data())
        for col in df.columns:
            if 'date' in col.lower() or df[col].astype(str).str.match(r'^\d{2,4}[-/]\d{2}[-/]\d{2,4}').any():
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d')
        df = df.ffill().fillna("")
        for col in df.columns:
            if any(k in col.lower() for k in ['amount', 'debit', 'credit', 'sales', 'revenue', 'expenses', 'profit', 'tax', 'cost', 'price', 'total']):
                df[col] = df[col].astype(str).str.replace(r'[^\d.-]', '', regex=True)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        df.dropna(how='all', inplace=True); df.drop_duplicates(inplace=True); df.fillna("", inplace=True)
        cleaned_data, cols = standardize_grid(df)
        workspace.set_active_data(cleaned_data, cols)
        return {"status": "cleaned"}
    except Exception as e: return JSONResponse(status_code=500, content={"message": str(e)})

class UpdateRequest(BaseModel): data: list; columns: list
@app.post("/sheet/update")
async def update_sheet(req: UpdateRequest):
    try:
        workspace.set_active_data(req.data, req.columns)
        return {"status": "success"}
    except Exception as e: return {"error": str(e)}

class ModelRequest(BaseModel): selected_cols: list; filter_val: str
@app.post("/model-data")
async def model_data(req: ModelRequest):
    try:
        df = pd.DataFrame(workspace.get_active_data())
        if req.selected_cols: df = df[[c for c in req.selected_cols if c in df.columns]]
        if req.filter_val:
            mask = np.column_stack([df[col].astype(str).str.contains(req.filter_val, case=False, na=False) for col in df])
            df = df.loc[mask.any(axis=1)]
        trans_data, trans_cols = standardize_grid(df)
        sheet_name = workspace.add_sheet(f"Custom Model - {len(workspace.sheets)}", trans_data, trans_cols)
        return {"status": "success", "sheet": sheet_name}
    except Exception as e: return {"error": str(e)}

class PivotRequest(BaseModel): group_col: str
@app.post("/pivot")
async def generate_pivot(req: PivotRequest):
    try:
        df = pd.DataFrame(workspace.get_active_data())
        if req.group_col not in df.columns: return {"error": "Invalid column"}
        for col in df.columns:
            if col != req.group_col: df[col] = pd.to_numeric(df[col].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce')
        pivot_df = df.groupby(req.group_col).sum(numeric_only=True).reset_index()
        pivot_data, pivot_cols = standardize_grid(pivot_df)
        sheet_name = workspace.add_sheet(f"Pivot - {req.group_col}", pivot_data, pivot_cols)
        return {"status": "success", "sheet": sheet_name}
    except Exception as e: return {"error": str(e)}

@app.get("/generate-insights")
async def generate_insights():
    if not model: return {"narrative": "AI not configured."}
    try:
        df = pd.DataFrame(workspace.get_active_data())
        prompt = f"Analyze this dataset summary: {df.describe().to_string()}. Provide a concise, 3-sentence executive summary identifying core trends. Use <b> tags."
        return {"narrative": model.generate_content(prompt).text.strip()}
    except Exception as e: return {"narrative": "Failed to generate insights."}

@app.post("/visualize/chart")
async def get_chart_data(request: Request):
    try:
        body = await request.json()
        chart_type, x_col, y_col, agg = body.get("type"), body.get("x"), body.get("y"), body.get("agg", "sum")
        df = pd.DataFrame(workspace.get_active_data())
        if df.empty: return {"error": "No data"}

        if y_col in df.columns:
            df[y_col] = pd.to_numeric(df[y_col].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').fillna(0)
        
        if x_col in df.columns: df[x_col] = df[x_col].astype(str)

        chart_data = {"x": [], "y": [], "type": chart_type}
        if x_col in df.columns and y_col in df.columns:
            if agg == 'sum': df = df.groupby(x_col, as_index=False)[y_col].sum()
            elif agg == 'avg': df = df.groupby(x_col, as_index=False)[y_col].mean()
            elif agg == 'count': df = df.groupby(x_col, as_index=False)[y_col].count()
            
            df = df.sort_values(by=y_col, ascending=False)
            chart_data["x"] = df[x_col].tolist(); chart_data["y"] = df[y_col].tolist()
            
        return {"chart_data": chart_data}
    except Exception as e: return {"error": str(e)}

@app.get("/grid")
async def get_grid():
    data = workspace.get_active_data()
    cols = workspace.columns.get(workspace.active_sheet, ["A","B","C","D"])
    return {"sheets": list(workspace.sheets.keys()), "active": workspace.active_sheet, "data": data, "columns": cols}

@app.post("/sheet/add")
async def add_sheet(name: str = Form(...), cols: str = Form(None)):
    col_list = json.loads(cols) if cols else ["Date","Department","Revenue","Expenses","Status"]
    workspace.add_sheet(name, [], col_list)
    return await get_grid()

@app.post("/sheet/switch")
async def switch_sheet(name: str = Form(...)):
    if name in workspace.sheets: workspace.active_sheet = name; workspace.save_to_disk()
    return await get_grid()

@app.post("/sheet/close")
async def close_sheet(name: str = Form(...)):
    workspace.remove_sheet(name)
    return await get_grid()

@app.post("/chat")
async def chat_ai(request: Request):
    if not model: return {"response": "⚠️ AI Model Key not verified."}
    try:
        body = await request.json()
        user_msg = body.get("message", "")
        context = body.get("context", "grid")
        df = pd.DataFrame(workspace.get_active_data())
        headers = list(df.columns) if not df.empty else []
        default_x = headers[0] if headers else 'Date'
        default_y = headers[1] if len(headers)>1 else 'Value'
        
        prompt = f"""Role: Enterprise BI Analyst. Active Tab: {context}. Columns: {headers}. Query: {user_msg}. 
        If user asks to generate, build, or combine sample data into the sheet, append the data as JSON: <<GRID_MERGE:[{{"New Col":"Val1"}}]>>. Make sure the length matches the row count ({len(df)} rows).
        If user asks for a chart, append: <<CHART_ACTION:{{"type":"bar","x":"{default_x}","y":"{default_y}"}}>>
        """
        response = model.generate_content(prompt)
        return {"response": response.text}
    except Exception as e: return {"response": f"AI Engine Exception: {str(e)}"}

class ReportRequest(BaseModel): report_type: str; layout_style: str
@app.post("/generate-report")
async def generate_executive_report(req: ReportRequest):
    if not model: return {"narrative": "AI Error: Gemini API key missing."}
    df = pd.DataFrame(workspace.get_active_data())
    prompt = f"Write an executive '{req.report_type}'. Style: {req.layout_style}. Data summary: {df.describe().to_string()}. Use HTML tags like <h2>, <p>, <ul>. NO markdown."
    return {"narrative": model.generate_content(prompt).text.replace("```html", "").replace("```", "").strip()}

class TextAction(BaseModel): action: str; text: str
@app.post("/publisher-ai")
async def publisher_ai(req: TextAction):
    if not model: return {"result": req.text}
    prompts = {"expand": f"Expand into a professional paragraph: '{req.text}'", "summarize": f"Summarize concisely: '{req.text}'", "professional": f"Rewrite to sound like a consultant: '{req.text}'"}
    return {"result": model.generate_content(prompts.get(req.action, req.text)).text.replace("```html", "").replace("```", "").strip()}

app.mount("/", StaticFiles(directory=".", html=True), name="static")
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860) 