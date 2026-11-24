import asyncio
import logging
from pydantic import BaseModel

log = logging.getLogger(__name__)


# One row in usage_logs

class UsageRecord(BaseModel):
    api_key_id: int
    model: str
    provider: str | None = None
    provider_model: str | None = None
    stream: bool = False
    status_code: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms : int
    cost_usd : float = 0.0
    error: str | None = None

INSERT_SQL = """
INSERT INTO usage_logs (api_key_id, model, provider, provider_model, stream, status_code,
                        prompt_tokens, completion_tokens, latency_ms, cost_usd, error)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
"""

# Collects records in memory and writes them to Postgres in the background

class UsageLogger:

    def __init__(self, pool, max_queue: int = 10_000, batch_size : int = 100):
        self.pool = pool
        self.queue : asyncio.Queue[UsageRecord] = asyncio.Queue(maxsize=max_queue)
        self.batch_size = batch_size
        self._task : asyncio.Task | None = None

    # Start the background worker (call once at startup)
    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    # Called by the endpoint: instant, never waits for the database
    def log(self, record:UsageRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except asyncio.QueueFull:
            log.warning("Usage queue full, dropping record")
    
    # Worker loop: wait for a record, grab any others already waiting, write them together
    async def _run(self) -> None:
        while True:
            batch = [await self.queue.get()]
            while len(batch) < self.batch_size and not self.queue.empty():
                batch.append(self.queue.get_nowait())
            try:
                await self._write(batch)
            except Exception:
                log.exception("Failed to write %d usage records", len(batch))

    async def _write(self, batch: list[UsageRecord])-> None:
        await self.pool.executemany(INSERT_SQL, [
            (r.api_key_id, r.model, r.provider, r.provider_model, r.stream,
             r.status_code, r.prompt_tokens, r.completion_tokens, r.latency_ms,
             r.cost_usd, r.error) for r in batch
        ])

    # Stop the worker and write whatever is still in the queue (call at shutdown)
    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        remaining = []
        while not self.queue.empty():
            remaining.append(self.queue.get_nowait())
        if remaining:
            await self._write(remaining)