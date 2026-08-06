import subprocess
import threading
import time
from datetime import datetime
import os
import sys
import json
from database import get_db_connection

class JobService:
    def __init__(self):
        self.running_processes = {}
        self._sync_db_on_startup()

    def _sync_db_on_startup(self):
        """Reset running status to idle if app crashed/restarted"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE system_jobs SET status = 'idle' WHERE status = 'running'")
        conn.commit()
        conn.close()

    def get_all_jobs(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM system_jobs WHERE is_active = 1")
        rows = cursor.fetchall()
        
        jobs = []
        for row in rows:
            job = dict(row)
            # Parse JSON args
            try:
                job["args"] = json.loads(job["args"]) if job["args"] else []
            except (json.JSONDecodeError, TypeError):
                job["args"] = []
            
            # Truncate output for list view
            job["output"] = job["output"][-1000:] if job["output"] else ""
            jobs.append(job)
            
        conn.close()
        return jobs

    def update_job_definition(self, job_id, updates):
        """Allows editing job name, description, args, path etc."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        allowed_fields = ["name", "description", "path", "args", "service", "method", "is_active"]
        update_parts = []
        params = []
        
        for field in allowed_fields:
            if field in updates:
                val = updates[field]
                if field == "args" and isinstance(val, list):
                    val = json.dumps(val)
                update_parts.append(f"{field} = ?")
                params.append(val)
        
        if not update_parts:
            conn.close()
            return False, "No valid fields to update"
            
        params.append(job_id)
        cursor.execute(f"UPDATE system_jobs SET {', '.join(update_parts)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", params)
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success, "Updated" if success else "Job not found"

    def run_job(self, job_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM system_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return False, "Job not found"
        
        if row["status"] == "running":
            conn.close()
            return False, "Job already running"

        # Mark as running in DB immediately
        cursor.execute("UPDATE system_jobs SET status = 'running', last_run = ? WHERE id = ?", 
                      (datetime.now().isoformat(), job_id))
        conn.commit()
        conn.close()

        # Run in background thread
        thread = threading.Thread(target=self._execute_job, args=(job_id,))
        thread.start()
        return True, "Job started"

    def _execute_job(self, job_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM system_jobs WHERE id = ?", (job_id,))
        job_data = cursor.fetchone()
        if not job_data:
            conn.close()
            return
            
        job = dict(job_data)
        output = f"--- Job Started at {datetime.now().isoformat()} ---\n"
        status = "running"
        
        try:
            if job["type"] == "script":
                status, output = self._handle_script_job(job, output)
            elif job["type"] == "internal":
                status, output = self._handle_internal_job(job, output)
        except Exception as e:
            status = "error"
            output += f"ERROR: {str(e)}\n"
        finally:
            self.running_processes.pop(job_id, None)
            output += f"\n--- Job Completed at {datetime.now().isoformat()} ---\n"
            cursor.execute("UPDATE system_jobs SET status = ?, output = ? WHERE id = ?", (status, output, job_id))
            conn.commit()
            conn.close()

    def _handle_script_job(self, job, output):
        script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), job["path"])
        args = json.loads(job["args"]) if job.get("args") else []
        cmd = [sys.executable, script_path] + args
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=os.path.dirname(os.path.dirname(__file__))
        )
        
        self.running_processes[job["id"]] = process
        for line in process.stdout:
            output += line
        
        process.wait()
        status = "success" if process.returncode == 0 else "failed"
        if process.returncode != 0:
            output += f"\n--- Process exited with code {process.returncode} ---\n"
        return status, output

    def _handle_internal_job(self, job, output):
        from services.news_service import news_service
        from services.market_service import market_provider
        
        services = {"news_service": news_service, "market_service": market_provider}
        service = services.get(job["service"])
        
        if service:
            method = getattr(service, job["method"])
            output += f"Executing {job['service']}.{job['method']}...\n"
            result = method()
            output += f"Success: Modified {len(result) if isinstance(result, list) else 'N/A'} items.\n"
            return "success", output
        
        output += f"Service {job['service']} not found.\n"
        return "failed", output

job_runner = JobService()
