# Changelog - Arabic Books Publisher

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-07-04

### Added
- **Core Framework**: Full domain models and interfaces reflecting Clean Architecture and SOLID design guidelines.
- **Credential Discovery Engine**: Scans environment variables for Gemini keys, Telegram sessions, and Firebase Firestore credentials with dynamic pool support.
- **Failover Pool & Health Monitoring**: Automatic failover, rate-limit cooling down, and ban tracking for API keys.
- **Firestore Integration**: Asynchronous collection adapters for caching AI reviews, storing queue posts, channels metadata, and performance statistics.
- **Asynchronous Downloader**: 3-trial exponential backoff retries with size limits (<20MB).
- **PDF Validator**: Magic byte checking, page count extraction, Arabic language validation, and first-page cover extraction using PyMuPDF.
- **Arabic Fingerprinting**: tashkeel stripping, character normalization, and SHA-256 file hashing for duplicate checking.
- **Gemini AI service**: Versioned prompt configurations, automatic summary adjustment (6-8 lines), category classifications, and hashtag listings.
- **Sources Scrapers**: Scraper providers for Internet Archive, Hindawi Foundation, and Open Library with dynamic scoring, ranking, and rate limits.
- **Telegram Scheduled Messages**: Multi-account publisher that schedules cover photos and PDF files sequentially, and queries actual schedules.
- **APScheduler Coordinator**: Timezone-aware background loops for scheduling, queue replenishments, and log rotations.
- **Status Dashboard**: aiohttp web server running on port 7860 to support HuggingFace Space health checks and display status metrics.
- **Graceful Shutdown**: Signal interceptors for clean shutdowns, disconnecting client connections, and temporary directory purges.
- **Production Setup**: Multistage Dockerfile configurations, requirements specifications, and architectural documentation.
