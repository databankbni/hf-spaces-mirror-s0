import gradio as gr
import pandas as pd
import os
import gzip
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Internal compressed data file path
DATA_FILE_PATH = "stock.csv.gz"

def calculate_pivots_preloaded(user_symbols_str):
    # 1. Verify file presence
    if not os.path.exists(DATA_FILE_PATH):
        return None, f"Error: '{DATA_FILE_PATH}' not found in the app directory.", None, ""
        
    if not user_symbols_str.strip():
        return None, "Please enter at least one stock symbol.", None, ""
        
    target_stocks = [s.strip().upper() for s in user_symbols_str.split(',') if s.strip()]
    report_date = "N/A"

    try:
        # 2. Extract Date metadata if available
        # Attempts to read comment metadata inside the gzip header or look for a date column/row
        with gzip.open(DATA_FILE_PATH, 'rt') as f:
            first_line = f.readline()
            # If your source tracking scripts inject a comment line like '# Date: Monday, July 06, 2026'
            if first_line.startswith('#'):
                extracted_date = re.search(r'[\w]+, \s*[\w]+\s+\d+,\s*\d+', first_line)
                if extracted_date:
                    report_date = extracted_date.group(0)

        # Read dataset 
        df = pd.read_csv(DATA_FILE_PATH, compression='gzip', comment='#')
        df.columns = [col.strip().lower() for col in df.columns]
        
        # Check if Date is a dedicated column value instead of header comment
        if 'date' in df.columns and not df.empty:
            report_date = str(df['date'].iloc[0]).strip()

        # Identify numerical rate columns dynamically
        symbol_col = next((col for col in df.columns if 'symbol' in col or 'ticker' in col or 'code' in col), None)
        high_col = next((col for col in df.columns if 'high' in col), None)
        low_col = next((col for col in df.columns if 'low' in col), None)
        close_col = next((col for col in df.columns if 'close' in col or 'last' in col), None)
        
        if not all([symbol_col, high_col, low_col, close_col]):
            return None, "Columns mismatch in dataset. Structural keys missing.", None, ""

        # Filter symbols
        df[symbol_col] = df[symbol_col].astype(str).str.strip().str.upper()
        df_filtered = df[df[symbol_col].isin(target_stocks)].copy()
        
        df_filtered[high_col] = pd.to_numeric(df_filtered[high_col], errors='coerce')
        df_filtered[low_col] = pd.to_numeric(df_filtered[low_col], errors='coerce')
        df_filtered[close_col] = pd.to_numeric(df_filtered[close_col], errors='coerce')
        
        extracted_data = {}
        for _, row in df_filtered.iterrows():
            ticker = row[symbol_col]
            if pd.notna(row[high_col]) and pd.notna(row[low_col]) and pd.notna(row[close_col]):
                extracted_data[ticker] = {
                    'High': row[high_col],
                    'Low': row[low_col],
                    'Close': row[close_col]
                }

    except Exception as e:
        return None, f"Error processing database file: {str(e)}", None, ""

    # Calculate levels
    results = []
    for ticker in target_stocks:
        if ticker in extracted_data:
            high = extracted_data[ticker]['High']
            low = extracted_data[ticker]['Low']
            close = extracted_data[ticker]['Close']
            
            pp = (high + low + close) / 3.0
            r1 = (2 * pp) - low
            s1 = (2 * pp) - high
            r2 = pp + (high - low)
            s2 = pp - (high - low)
            r3 = high + 2 * (pp - low)
            s3 = low - 2 * (high - pp)
            
            results.append({
                'Symbol': ticker, 'High': round(high, 2), 'Low': round(low, 2), 'Close': round(close, 2),
                'PP': round(pp, 2), 'S1': round(s1, 2), 'S2': round(s2, 2), 'S3': round(s3, 2),
                'R1': round(r1, 2), 'R2': round(r2, 2), 'R3': round(r3, 2)
            })
        else:
            results.append({
                'Symbol': ticker, 'High': '-', 'Low': '-', 'Close': '-',
                'PP': '-', 'S1': '-', 'S2': '-', 'S3': '-', 'R1': '-', 'R2': '-', 'R3': '-'
            })

    result_df = pd.DataFrame(results)
    
    # Generate the printable report specifying the isolated single date
    pdf_filename = "pivot_points_report.pdf"
    generate_pdf_report(result_df, pdf_filename, report_date)
    
    date_display_markdown = f"### 📅 Data Record Date: **{report_date}**" if report_date != "N/A" else ""
    
    return result_df, f"Processing complete! Found levels matching criteria.", pdf_filename, date_display_markdown


def generate_pdf_report(df, filename, date_str):
    doc = SimpleDocTemplate(filename, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'], fontSize=22, leading=26, textColor=colors.HexColor("#1A365D"), alignment=1
    )
    date_style = ParagraphStyle(
        'DocDate', parent=styles['Normal'], fontSize=11, leading=15, textColor=colors.HexColor("#4A5568"), alignment=1
    )
    normal_style = ParagraphStyle('DocNorm', parent=styles['Normal'], fontSize=10, leading=14)
    header_style = ParagraphStyle('TableHeader', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.white, fontName="Helvetica-Bold")
    cell_style = ParagraphStyle('TableCell', parent=styles['Normal'], fontSize=9, leading=11, alignment=1)

    story = [
        Paragraph("<b>Stock Exchange Pivot Points Report</b>", title_style),
        Spacer(1, 4),
        Paragraph(f"<b>Market Session Date:</b> {date_str}", date_style),
        Spacer(1, 15),
        Paragraph("Calculated Support and Resistance lines using standard floor pivot mathematical models.", normal_style),
        Spacer(1, 15)
    ]
    
    table_data = [[Paragraph(f"<b>{col}</b>", header_style) for col in df.columns]]
    for _, row in df.iterrows():
        row_cells = []
        for val in row:
            row_cells.append(Paragraph(str(val), cell_style))
        table_data.append(row_cells)
        
    col_widths = [50, 45, 45, 45, 52, 45, 45, 45, 45, 45, 45]
    
    pivot_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    pivot_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
    ]))
    
    story.append(pivot_table)
    doc.build(story)


# Layout structural tree
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 📈 Pre-loaded Stock Pivot Point Calculator & Exporter")
    gr.Markdown("Enter tickers below to parse data from `stock.csv.gz` and generate a dated PDF report.")
    
    with gr.Row():
        symbols_input = gr.Textbox(
            label="Stock Symbols to Search (Comma-separated)", 
            value="GHNI, GAL, ATRL, LOTCHEM, SAZEW, OGDC, NCPL, NPL, BOP, UBL, PPL, LUCK, TRG, MLCF, OBOY, DGKC, FCCL",
            placeholder="E.g. GHNI, GAL, ATRL, LOTCHEM, SAZEW, OGDC, NCPL, NPL, BOP, UBL, PPL, LUCK, TRG, MLCF, OBOY, DGKC, FCCL"
        )
            
    submit_btn = gr.Button("Calculate Pivot Points from System Data", variant="primary")
    
    # Component to show extracted single date notice on UI
    date_display = gr.Markdown(value="")
    status_output = gr.Markdown(value="*System Ready. Click button to compute.*")
    
    with gr.Row():
        pdf_output = gr.File(label="📥 Download Generated PDF Report")
        
    output_table = gr.Dataframe(
        label="Calculated Pivot Levels Table",
        headers=['Symbol', 'High', 'Low', 'Close', 'PP', 'S1', 'S2', 'S3', 'R1', 'R2', 'R3'],
        datatype=["str"] + ["number"]*10
    )
    
    submit_btn.click(
        fn=calculate_pivots_preloaded, 
        inputs=[symbols_input], 
        outputs=[output_table, status_output, pdf_output, date_display]
    )

if __name__ == "__main__":
    demo.launch()