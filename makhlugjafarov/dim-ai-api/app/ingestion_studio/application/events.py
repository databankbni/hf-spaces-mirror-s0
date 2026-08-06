import asyncio
import json
from collections import defaultdict
from typing import AsyncGenerator

job_event_channels: dict[str, list[asyncio.Queue]] = defaultdict(list)

def broadcast_job_event(job_id: str, event_type: str, data: dict) -> None:
    """Broadcast an event to all connected SSE clients for a specific job."""
    if job_id not in job_event_channels:
        return
        
    message = f"data: {json.dumps({'type': event_type, 'data': data})}\n\n"
    for q in job_event_channels[job_id]:
        q.put_nowait(message)

async def event_generator(job_id: str) -> AsyncGenerator[str, None]:
    """Yields SSE events from the job's queue."""
    q = asyncio.Queue()
    job_event_channels[job_id].append(q)
    try:
        while True:
            message = await q.get()
            yield message
    except asyncio.CancelledError:
        pass
    finally:
        if job_id in job_event_channels:
            job_event_channels[job_id].remove(q)
            if not job_event_channels[job_id]:
                del job_event_channels[job_id]
