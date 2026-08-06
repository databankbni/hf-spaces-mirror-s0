import asyncio
import logging
import signal
import sys
import os
from datetime import datetime
from pathlib import Path
from aiohttp import web
from database.firestore_repo import FirestoreBookRepository
from ai.service import GeminiAIService
from sources.manager import SourcesManager
from book_queue.manager import QueueManager
from telegram.publisher import TelegramPublisher
from telegram.client_manager import client_manager
from scheduler.runner import SystemScheduler
from utils.credentials import credential_pool
import config

# Initialize custom logger first
from monitoring.logger import setup_logger
logger = logging.getLogger("SYSTEM")

class ArabicBooksPublisherApp:
    def __init__(self):
        self.repo = None
        self.ai_service = None
        self.sources_manager = None
        self.queue_manager = None
        self.publisher = None
        self.scheduler = None
        self.shutdown_event = asyncio.Event()
        self.web_runner = None
        self.start_time = None

    async def initialize(self):
        """Initializes all app components and dependencies."""
        logger.system("Initializing Arabic Books Publisher (Enterprise Edition)...")
        logger.system(f"Version: {config.VERSION}")
        self.start_time = datetime.now()

        # Enable developer debug output in dry-run mode
        if config.DRY_RUN:
            logger.warning("APPLICATION RUNNING IN DRY-RUN MODE. No actual Telegram posts will be scheduled.")

        try:
            # Run credential discovery explicitly after logging is configured
            from utils.credentials import credential_pool
            credential_pool.discover_credentials()
            
            # 1. Initialize Firestore Repository (handles database connection)
            self.repo = FirestoreBookRepository()
            
            # Load maintenance mode from database
            db_maintenance = await self.repo.get_system_setting("maintenance_mode", False)
            config.MAINTENANCE_MODE = db_maintenance
            if config.MAINTENANCE_MODE:
                logger.warning("System loaded in MAINTENANCE MODE (Paused) from database settings.")
            
            # 2. Initialize AI Service
            self.ai_service = GeminiAIService(self.repo)
            
            # 3. Initialize Scrapers Sources Manager
            self.sources_manager = SourcesManager(self.repo)
            
            # 4. Initialize Queue Manager
            self.queue_manager = QueueManager(
                self.repo, self.ai_service, self.sources_manager
            )
            
            # 5. Initialize Telegram Publisher
            self.publisher = TelegramPublisher(self.repo)
            
            # 6. Initialize Background Scheduler Coordinator
            self.scheduler = SystemScheduler(
                self.repo, self.queue_manager, self.publisher
            )
            
            logger.success("All components initialized successfully.")
        except Exception as e:
            logger.critical(f"Critical initialization failure: {e}")
            sys.exit(1)

    async def start_web_server(self):
        """Starts the aiohttp web server on port 7860 for HuggingFace Spaces health checks."""
        logger.system("Starting status web dashboard on port 7860...")
        app = web.Application()
        app['app_instance'] = self
        app.router.add_get('/', self.handle_web_request)
        
        self.web_runner = web.AppRunner(app)
        await self.web_runner.setup()
        
        port = int(os.getenv("PORT", 7860))
        site = web.TCPSite(self.web_runner, '0.0.0.0', port)
        await site.start()
        logger.success(f"Web server is listening on port {port}")

    async def handle_web_request(self, request):
        """Serves the status page (Arabic/English UI)."""
        # Handle toggle action
        query_params = request.rel_url.query
        action = query_params.get("action")
        if action == "toggle_maintenance":
            config.MAINTENANCE_MODE = not config.MAINTENANCE_MODE
            await self.repo.set_system_setting("maintenance_mode", config.MAINTENANCE_MODE)
            return web.HTTPFound('/')
            
        # Fetch stats from DB
        queue_count = await self.repo.get_queue_count()
        channels = await self.repo.get_active_channels()
        
        # Fetch source metrics
        archive_metrics = await self.repo.get_source_metrics("archive")
        hindawi_metrics = await self.repo.get_source_metrics("hindawi")
        ol_metrics = await self.repo.get_source_metrics("openlibrary")
        
        # Calculate uptime
        uptime = "Initializing..."
        if self.start_time:
            diff = datetime.now() - self.start_time
            uptime = f"{diff.days}d {diff.seconds // 3600}h {(diff.seconds % 3600) // 60}m"

        html_content = f"""
        <!DOCTYPE html>
        <html lang="ar" dir="rtl">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>لوحة تحكم ناشر الكتب العربية | Arabic Books Publisher</title>
            <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap" rel="stylesheet">
            <style>
                :root {{
                    --primary-color: #0d6efd;
                    --bg-color: #0b192c;
                    --card-bg: #1e3e62;
                    --text-color: #f8f9fa;
                    --success-color: #198754;
                    --warning-color: #ffc107;
                    --error-color: #dc3545;
                }}
                * {{
                    box-sizing: border-box;
                    margin: 0;
                    padding: 0;
                    font-family: 'Cairo', sans-serif;
                }}
                body {{
                    background-color: var(--bg-color);
                    color: var(--text-color);
                    padding: 20px;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                }}
                .container {{
                    max-width: 1000px;
                    width: 100%;
                    background: var(--card-bg);
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                    padding: 30px;
                    border: 1px solid rgba(255,255,255,0.1);
                }}
                header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    border-bottom: 2px solid rgba(255,255,255,0.1);
                    padding-bottom: 20px;
                    margin-bottom: 30px;
                }}
                h1 {{
                    font-size: 24px;
                    color: #fff;
                    font-weight: 700;
                }}
                .badge {{
                    padding: 6px 12px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 14px;
                }}
                .badge-success {{ background-color: var(--success-color); color: #fff; }}
                .badge-warning {{ background-color: var(--warning-color); color: #000; }}
                .badge-danger {{ background-color: var(--error-color); color: #fff; }}
                .grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                .card {{
                    background: rgba(255,255,255,0.05);
                    border-radius: 10px;
                    padding: 20px;
                    border: 1px solid rgba(255,255,255,0.05);
                    text-align: center;
                }}
                .card h3 {{
                    font-size: 16px;
                    color: rgba(255,255,255,0.7);
                    margin-bottom: 10px;
                }}
                .card .val {{
                    font-size: 28px;
                    font-weight: bold;
                    color: #fff;
                }}
                .source-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                }}
                .source-table th, .source-table td {{
                    padding: 12px;
                    text-align: center;
                    border-bottom: 1px solid rgba(255,255,255,0.1);
                }}
                .source-table th {{
                    background: rgba(255,255,255,0.1);
                    color: #fff;
                }}
                .btn-white {{
                    background-color: #ffffff;
                    color: #0b192c;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 5px;
                    font-weight: bold;
                    cursor: pointer;
                    text-decoration: none;
                    display: inline-block;
                    margin-top: 20px;
                    transition: background 0.3s;
                }}
                .btn-white:hover {{
                    background-color: #e2e8f0;
                }}

                .footer {{
                    margin-top: 30px;
                    text-align: center;
                    font-size: 12px;
                    color: rgba(255,255,255,0.5);
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <header>
                    <div>
                        <h1>📚 ناشر الكتب العربية الذكي</h1>
                        <p style="color: rgba(255,255,255,0.6); font-size:14px;">Enterprise Edition v{config.VERSION}</p>
                    </div>
                    <div>
                        {
                            '<span class="badge badge-danger">موقوف مؤقتاً / Paused</span>' 
                            if config.MAINTENANCE_MODE else 
                            '<span class="badge badge-success">نشط / Running</span>'
                        }
                    </div>
                </header>
                
                <div class="grid">
                    <div class="card">
                        <h3>الكتب الجاهزة بالانتظار (Queue)</h3>
                        <div class="val">{queue_count} / {config.QUEUE_TARGET_SIZE}</div>
                    </div>
                    <div class="card">
                        <h3>قنوات التيليجرام النشطة</h3>
                        <div class="val">{len(channels)}</div>
                    </div>
                    <div class="card">
                        <h3>مدة التشغيل (Uptime)</h3>
                        <div class="val" style="font-size: 18px; margin-top:10px;">{uptime}</div>
                    </div>
                    <div class="card">
                        <h3>وضع التجربة (Dry Run)</h3>
                        <div class="val" style="color: {'var(--warning-color)' if config.DRY_RUN else 'var(--success-color)'}">{ 'مفعل' if config.DRY_RUN else 'معطل' }</div>
                    </div>
                </div>

                <h2 style="margin-bottom: 15px; font-size: 18px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 10px;">مؤشرات أداء مصادر الكتب</h2>
                <table class="source-table">
                    <thead>
                        <tr>
                            <th>المصدر</th>
                            <th>التقييم (Score)</th>
                            <th>الكتب المجلوبة</th>
                            <th>الفاشلة</th>
                            <th>نسبة النجاح</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>Internet Archive</td>
                            <td>{archive_metrics.score}/100</td>
                            <td>{archive_metrics.total_scraped}</td>
                            <td>{archive_metrics.total_failed}</td>
                            <td>{archive_metrics.success_rate:.1f}%</td>
                        </tr>
                        <tr>
                            <td>Hindawi Foundation</td>
                            <td>{hindawi_metrics.score}/100</td>
                            <td>{hindawi_metrics.total_scraped}</td>
                            <td>{hindawi_metrics.total_failed}</td>
                            <td>{hindawi_metrics.success_rate:.1f}%</td>
                        </tr>
                        <tr>
                            <td>Open Library</td>
                            <td>{ol_metrics.score}/100</td>
                            <td>{ol_metrics.total_scraped}</td>
                            <td>{ol_metrics.total_failed}</td>
                            <td>{ol_metrics.success_rate:.1f}%</td>
                        </tr>
                    </tbody>
                </table>
                <div style="text-align: center;">
                    <a href="/" class="btn-white">تحديث البيانات / Refresh</a>
                </div>

                <div class="footer">
                    جميع الحقوق محفوظة © 2026 - ناشر الكتب العربية الذكي
                </div>
            </div>
        </body>
        </html>
        """
        return web.Response(text=html_content, content_type='text/html', charset='utf-8')

    async def start(self):
        """Starts the application background scheduling tasks and web server."""
        await self.initialize()
        
        # Start background scheduling jobs
        await self.scheduler.start()
        
        # Start port 7860 web server for HuggingFace health checks
        await self.start_web_server()
        
        # Block until shutdown signal is received
        logger.system("Application is running. Press Ctrl+C to terminate.")
        await self.shutdown_event.wait()

    async def shutdown(self):
        """Gracefully shuts down all components and cleans temporary directories."""
        logger.system("Initiating graceful shutdown procedure...")
        
        # Stop Web Server
        if self.web_runner:
            logger.system("Stopping web server...")
            await self.web_runner.cleanup()
            
        # Stop scheduler background tasks
        if self.scheduler:
            await self.scheduler.stop()
            
        # Disconnect Telegram clients
        await client_manager.disconnect_all()
        
        # Clean up temp files
        self._cleanup_temp_dir()
        
        logger.success("Graceful shutdown complete. Exiting.")
        self.shutdown_event.set()

    def _cleanup_temp_dir(self):
        """Deletes all remaining temporary files in temp directory."""
        logger.system("Cleaning up temporary directory...")
        temp_dir = Path(config.TEMP_DIR)
        
        if not temp_dir.exists():
            return
            
        deleted_count = 0
        for item in temp_dir.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                    deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete temp file {item.name}: {e}")
                
        if deleted_count > 0:
            logger.success(f"Cleaned up {deleted_count} file(s) from temp directory.")
        else:
            logger.system("Temp directory is already empty.")

def handle_signals(app: ArabicBooksPublisherApp):
    """Registers OS signals to trigger graceful shutdown."""
    loop = asyncio.get_event_loop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(app.shutdown()))
        except NotImplementedError:
            # signal handlers are not supported on Windows Proactor Event Loops
            pass

async def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    app = ArabicBooksPublisherApp()
    handle_signals(app)
    
    try:
        await app.start()
    except (KeyboardInterrupt, SystemExit):
        logger.system("Interrupt signal received manually.")
        await app.shutdown()
    except Exception as e:
        logger.critical(f"Unhandled runtime exception: {e}")
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
