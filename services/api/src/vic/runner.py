"""Background run manager: 202 immediately, execution outside the HTTP request, bounded
concurrency, one active run per case, graceful shutdown. Single-instance prototype only:
a durable queue is the next step (see README)."""
import asyncio
from functools import lru_cache

from vic.config import Settings, get_settings
from vic.contracts import Run, RunCreate, RunStatus
from vic.errors import ApiError
from vic.llm import build_llm
from vic.modules import get_modules
from vic.pipeline import Pipeline
from vic.storage import get_repository, new_id


class RunManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()

    async def start(self, case_id: str, body: RunCreate) -> Run:
        repo = get_repository()
        async with self._lock:
            if await asyncio.to_thread(repo.count_active_runs, case_id) > 0:
                raise ApiError(409, "run_in_progress", "This case already has a run in progress")
            if await asyncio.to_thread(repo.count_active_runs) >= self.settings.max_concurrent_runs:
                raise ApiError(429, "too_many_runs",
                               "Too many runs are in progress; try again later", True)
            run = Run(id=new_id("run"), case_id=case_id, status=RunStatus.QUEUED,
                      trace_id=new_id("trace"), mode=body.mode, parent_report_id=body.parent_report_id)
            await asyncio.to_thread(repo.create_run, run)
            task = asyncio.create_task(self._execute(run))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return run

    async def _execute(self, run: Run) -> None:
        pipeline = Pipeline(get_repository(), self.settings,
                            modules_factory=lambda: get_modules(self.settings),
                            llm_factory=lambda: build_llm(self.settings))
        await pipeline.execute(run)  # records failures itself; only CancelledError escapes

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


@lru_cache
def get_manager() -> RunManager:
    return RunManager(get_settings())