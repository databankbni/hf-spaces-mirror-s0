import time
# Triggering build - EGR Extractor Update 2026-03-30
import threading
import sys
import os
import json
import uuid

from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory

from processors.registry import PROCESSORS, get_available_processors, get_report_folder
import requests
import tempfile

# SSL/Zscaler Certificate Handling
# Determine if running in a frozen PyInstaller bundle
IS_FROZEN = getattr(sys, 'frozen', False)
BASE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.resolve()))

# Locate the certificate bundle
custom_bundle = BASE_DIR / "custom_bundle.pem"
if custom_bundle.exists():
    bundle_path = str(custom_bundle)
    os.environ["REQUESTS_CA_BUNDLE"] = bundle_path
    os.environ["SSL_CERT_FILE"] = bundle_path
    print(f"SSL: Using custom certificate bundle at {bundle_path}")

UPLOAD_FOLDER = Path(os.getcwd()) / "uploads"
OUTPUT_FOLDER = Path(os.getcwd()) / "output"

UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

app = Flask(__name__)

# Basic Job Queue
jobs = {}

class Job:
    def __init__(self, job_id, filename, report_type):
        self.job_id = job_id
        self.filename = filename
        self.report_type = report_type
        self.status = "processing"
        self.message = "Initializing..."
        self.progress = 0
        self.current_page = 0
        self.total_pages = 0
        self.companies_found = 0
        self.output_file = None
        self.error = None
        self.start_time = time.time()
        self.end_time = None
        
    @property
    def elapsed_time(self):
        if self.end_time:
            return round(self.end_time - self.start_time)
        return round(time.time() - self.start_time)
        
    def to_dict(self):
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "report_type": self.report_type,
            "status": self.status,
            "message": self.message,
            "progress": self.progress,
            "current_page": self.current_page,
            "total_pages": self.total_pages,
            "companies_found": self.companies_found,
            "output_file": self.output_file,
            "error": self.error,
            "elapsed_time": self.elapsed_time
        }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/report-types")
def get_report_types():
    # Return registered processors with their metadata
    return jsonify(get_available_processors())

@app.route("/api/use-existing", methods=["POST"])
def use_existing():
    data = request.json
    report_type = data.get("report_type")
    filename = data.get("filename")
    
    # Use the mapping logic to find the correct folder
    folder_rel = get_report_folder(report_type)
    file_path = BASE_DIR / folder_rel / filename
    
    if not file_path.exists():
        # Fallback to direct filename in BASE_DIR for root files
        file_path = BASE_DIR / filename
        
    if not file_path.exists():
        return jsonify({"error": f"File not found: {filename}"}), 404
        
    job_id = str(uuid.uuid4())
    job = Job(job_id, filename, report_type)
    jobs[job_id] = job
    
    threading.Thread(target=process_report, args=(job, file_path)).start()
    return jsonify({"job_id": job_id})

@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file parameter"}), 400
        
    file = request.files["file"]
    report_type = request.form.get("report_type")
    
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
        
    filename = file.filename
    file_path = UPLOAD_FOLDER / filename
    file.save(file_path)
    
    job_id = str(uuid.uuid4())
    job = Job(job_id, filename, report_type)
    jobs[job_id] = job
    
    threading.Thread(target=process_report, args=(job, file_path)).start()
    return jsonify({"job_id": job_id})

@app.route("/api/download-url", methods=["POST"])
def download_url():
    data = request.json
    url = data.get("url")
    report_type = data.get("report_type")
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
        
    try:
        # Generate a filename from URL or use a timestamp
        filename = url.split("/")[-1].split("?")[0]
        if not filename or "." not in filename:
            filename = f"report_{int(time.time())}.pdf"
            
        # Download the file
        # Requests will automatically use REQUESTS_CA_BUNDLE if set in environment
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        file_path = UPLOAD_FOLDER / filename
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        job_id = str(uuid.uuid4())
        job = Job(job_id, filename, report_type)
        jobs[job_id] = job
        
        threading.Thread(target=process_report, args=(job, file_path)).start()
        return jsonify({"job_id": job_id})
        
    except Exception as e:
        return jsonify({"error": f"Failed to download URL: {str(e)}"}), 500

def process_report(job, file_path):
    try:
        processor_class = PROCESSORS.get(job.report_type)
        if not processor_class:
            raise ValueError(f"Unknown report type: {job.report_type}")
            
        processor = processor_class(api_keys=[], output_folder=OUTPUT_FOLDER)
        processor.run(str(file_path), job)
        
        # Only set completed if it hasn't failed internally
        if job.status != "error":
            job.status = "completed"
            job.message = "Successfully generated Excel report."
            job.progress = 100
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        job.status = "error"
        job.error = error_trace
        job.message = f"Error: {e}"
    finally:
        job.end_time = time.time()

@app.route("/api/status/<job_id>")
def status(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(jobs[job_id].to_dict())

@app.route("/api/download/<filename>")
def download_file(filename):
    return send_from_directory(str(OUTPUT_FOLDER), filename, as_attachment=True, download_name=filename)

@app.route("/api/jobs")
def get_jobs():
    return jsonify([j.to_dict() for j in jobs.values()])

if __name__ == "__main__":
    import os
    import webbrowser
    
    # Check if running in a cloud/Docker environment like Hugging Face
    is_cloud = "SPACE_ID" in os.environ or "KUBERNETES_SERVICE_HOST" in os.environ
    port = int(os.environ.get("PORT", 7860))
    
    if not is_cloud:
        # Open local browser automatically gracefully
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
        
    print(f"Starting Estimates Data Extractor on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)