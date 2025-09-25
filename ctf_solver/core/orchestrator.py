import asyncio
import logging
import signal
import threading
from dataclasses import dataclass
from queue import Queue, Empty
from typing import Callable, Dict, Optional, Set

from ctf_solver.core.runner import ChallengeRunner

logger = logging.getLogger(__name__)


@dataclass
class _Job:
    challenge_id: int
    on_attempt_created: Optional[Callable[[int], None]] = None
    on_attempt_finished: Optional[Callable[[int, str], None]] = None
    optimized_agent_name: Optional[str] = None
    use_presenter: bool = True




class SimpleOrchestrator:
    def __init__(
        self,
        db_factory,
        max_parallel: int = 1,
        optimized_agent_name: Optional[str] = None,
        install_signal_handlers: bool = True,
    ):
        if callable(db_factory):
            self._db_factory = db_factory  # type: ignore[assignment]
            self._close_db_after_job = True
        else:
            self._db_factory = lambda: db_factory  # type: ignore[assignment]
            self._close_db_after_job = False

        self.max_parallel = max_parallel
        self.optimized_agent_name = optimized_agent_name
        self.job_queue: "Queue[_Job]" = Queue()
        self.workers = []
        self.active_runners: Set[ChallengeRunner] = set()
        self._shutdown_event = threading.Event()
        self._lock = threading.Lock()
        self._attempt_to_runner: Dict[int, ChallengeRunner] = {}

        if install_signal_handlers and threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self._handle_interrupt)
            signal.signal(signal.SIGTERM, self._handle_interrupt)

        for _ in range(max_parallel):
            worker = threading.Thread(target=self._worker, daemon=True)
            worker.start()
            self.workers.append(worker)

    def submit_challenge(
        self,
        challenge_id: int,
        *,
        on_attempt_created: Optional[Callable[[int], None]] = None,
        on_attempt_finished: Optional[Callable[[int, str], None]] = None,
        optimized_agent_name: Optional[str] = None,
        use_presenter: bool = True,
    ) -> None:
        job = _Job(
            challenge_id=challenge_id,
            on_attempt_created=on_attempt_created,
            on_attempt_finished=on_attempt_finished,
            optimized_agent_name=optimized_agent_name,
            use_presenter=use_presenter,
        )
        self.job_queue.put(job)

    async def solve_challenge_by_id(
        self,
        challenge_id: int,
        *,
        on_attempt_created: Optional[Callable[[int], None]] = None,
        on_attempt_finished: Optional[Callable[[int, str], None]] = None,
        optimized_agent_name: Optional[str] = None,
        use_presenter: bool = True,
    ) -> None:
        job = _Job(
            challenge_id=challenge_id,
            on_attempt_created=on_attempt_created,
            on_attempt_finished=on_attempt_finished,
            optimized_agent_name=optimized_agent_name,
            use_presenter=use_presenter,
        )
        await asyncio.to_thread(self._run_job, job)

    def request_cancel(self, attempt_id: int) -> bool:
        with self._lock:
            runner = self._attempt_to_runner.get(attempt_id)
        if not runner:
            return False
        runner.request_stop()
        return True

    def _worker(self):
        while not self._shutdown_event.is_set():
            try:
                job = self.job_queue.get(timeout=1)
            except Empty:
                continue
            try:
                self._run_job(job)
            finally:
                self.job_queue.task_done()

    def _run_job(self, job: _Job) -> None:
        db_conn = self._db_factory()
        runner = ChallengeRunner(
            db_conn,
            f"exegol_{job.challenge_id}",
            use_presenter=job.use_presenter,
            optimized_agent_name=job.optimized_agent_name or self.optimized_agent_name,
        )

        def _on_attempt_created(attempt_id: int) -> None:
            with self._lock:
                self._attempt_to_runner[attempt_id] = runner
            if job.on_attempt_created:
                try:
                    job.on_attempt_created(attempt_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Attempt callback failed: %s", exc)

        runner.on_attempt_created = _on_attempt_created  # type: ignore[attr-defined]
        if job.on_attempt_finished:
            runner.on_attempt_finished = job.on_attempt_finished  # type: ignore[attr-defined]

        self.active_runners.add(runner)

        try:
            flag = runner.run_attempt(job.challenge_id)
            logger.info("Challenge %s finished with flag=%s", job.challenge_id, bool(flag))
        except Exception as exc:  # noqa: BLE001
            logger.error("Runner error for challenge %s: %s", job.challenge_id, exc)
        finally:
            self.active_runners.discard(runner)
            with self._lock:
                attempt_ids = [aid for aid, r in self._attempt_to_runner.items() if r is runner]
                for attempt_id in attempt_ids:
                    self._attempt_to_runner.pop(attempt_id, None)
            if self._close_db_after_job:
                try:
                    db_conn.close()
                except Exception:  # noqa: BLE001
                    pass

    def _handle_interrupt(self, signum, frame):  # noqa: D401, ANN001, D401
        logger.info("Received interrupt signal (%s), cleaning up containers...", signum)
        print("\n🛑 Shutting down and cleaning containers...")

        self._shutdown_event.set()

        for runner in list(self.active_runners):
            try:
                runner.request_stop()
            except Exception as exc:  # noqa: BLE001
                logger.error("Error stopping runner: %s", exc)

        print("✅ Cleanup complete")
        raise SystemExit(0)

    def shutdown(self):
        logger.info("Shutting down orchestrator...")
        self._shutdown_event.set()

        for runner in list(self.active_runners):
            try:
                runner.request_stop()
            except Exception as exc:  # noqa: BLE001
                logger.error("Error stopping runner: %s", exc)

        logger.debug("Orchestrator shutdown complete")

