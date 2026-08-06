# Architecture Guide - Technical Design

This document details the software design, patterns, and workflows implemented in the **Arabic Books Publisher** application.

## 1. Architectural Patterns

The application is structured according to **Clean Architecture** principles to separate core business logic from external drivers like database providers, scrapers, and Telegram SDKs.

```mermaid
graph TD
    UI[Status Web Dashboard - aiohttp] --> Core
    App[Main Coordinator - app.py] --> Core
    Scheduler[APScheduler Runner] --> Core
    
    subgraph Core [Domain Core Layer]
        Models[Domain Models - core.models]
        Interfaces[Interfaces - core.interfaces]
    end
    
    subgraph Providers [Infrastructure Provider Layer]
        DB[Firestore Repo - database/firestore_repo] -.-> Interfaces
        AI[Gemini AI Service - ai/service] -.-> Interfaces
        Scrapers[Scrapers - sources/] -.-> Interfaces
        Telegram[Telegram Client Pool - telegram/]
    end
```

### Key Design Patterns:
1. **SOLID Principles**:
   - **Single Responsibility (SRP)**: Each class/module handles one aspect (e.g. `downloader` handles streaming downloads, `validator` handles PDF parsing, `fingerprint` handles normalization).
   - **Dependency Inversion (DIP)**: High-level queue management does not depend on Firestore or Gemini SDKs directly; it depends on `IBookRepository` and `IAIService` interfaces defined in `core/interfaces.py`.
2. **Provider Pattern**: Scrapers implement the `IBookSource` interface. Adding a new book source requires only writing a new class that implements `search_books` and registering it in `SourcesManager` without modifying core loops.
3. **Repository Pattern**: All database interactions are abstracted via `IBookRepository`. The main scheduler loop is completely unaware of Firestore's structure and can be migrated to SQLite, MongoDB, or PostgreSQL by writing a new repository adapter.
4. **Dependency Injection (DI)**: Classes receive their dependencies via their constructors (e.g., `QueueManager` receives the `IBookRepository`, `IAIService`, and `SourcesManager` instances at initialization in `app.py`).

## 2. Book Processing & Publishing Lifecycle

Here is the sequence of events when a book is scraped, processed, and scheduled:

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant Q as QueueManager
    participant Src as SourcesManager
    participant DB as Firestore Repository
    participant AI as Gemini AI Service
    participant TG as Telegram Publisher

    S->>Q: check_and_replenish()
    Q->>DB: get_queue_count()
    DB-->>Q: Count (e.g., 18/56)
    Note over Q: Replenishment Triggered (needed: 38)
    
    loop Until Target Reached
        Q->>Src: search_all(keyword)
        Src-->>Q: List of Books
        
        loop For each Book
            Q->>DB: is_book_published(preliminary_fingerprint)
            DB-->>Q: False
            
            Q->>Q: download_pdf()
            Q->>Q: validate_pdf() (magic bytes, page count, Arabic script)
            Q->>Q: extract_cover() (fitz page 1 to PNG)
            
            Q->>Q: generate_fingerprint(title, author, content_hash)
            Q->>DB: is_book_published(final_fingerprint)
            DB-->>Q: False
            
            Q->>AI: process_book(title, author, description)
            Note over AI: Checks Cache, if miss -> Calls Gemini
            AI-->>Q: {summary, category, hashtags}
            
            Q->>DB: add_post_to_queue(Post)
            Q->>DB: mark_book_published(Book)
        end
    end
    
    S->>S: sync_and_schedule_posts()
    S->>DB: get_pending_queue(limit=1)
    DB-->>S: Post payload
    S->>TG: schedule_book_post(Post, slot_utc)
    Note over TG: Uploads Cover (if exists) & PDF 10s apart
    TG-->>S: Telegram Scheduled Message IDs
    S->>DB: save_scheduled_post(ScheduledPost)
    S->>DB: update_post_status(post_id, "scheduled")
```

## 3. Credential Discovery & Failover Flow

The `utils/credentials.py` module manages credentials securely:
- **Discovery**: Scrapes environment variables using regex patterns.
- **Failover**:
  1. Requests a healthy credential.
  2. Executes call.
  3. If exception caught:
     - Flag key based on failure (e.g., `RATE_LIMITED` for 429, `INVALID` for 401/403).
     - Request next key in pool.
     - Retry call.
  4. If all keys fail, returns fallback mock output.
