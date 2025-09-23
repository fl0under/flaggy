import threading
import signal
import logging
from queue import Queue
from typing import Set

from ctf_solver.core.runner import ChallengeRunner

logger = logging.getLogger(__name__)


class SimpleOrchestrator:
    def __init__(self, db_conn, max_parallel=1, optimized_agent_name=None):
        self.db = db_conn
        self.max_parallel = max_parallel
        self.optimized_agent_name = optimized_agent_name
        self.job_queue = Queue()
        self.workers = []
        self.active_runners: Set[ChallengeRunner] = set()
        self._shutdown_event = threading.Event()
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
        
        for i in range(max_parallel):
            worker = threading.Thread(target=self._worker, daemon=True)
            worker.start()
            self.workers.append(worker)
    
    def submit_challenge(self, challenge_id):
        self.job_queue.put(challenge_id)
    
    def _worker(self):
        while not self._shutdown_event.is_set():
            try:
                challenge_id = self.job_queue.get(timeout=1)
            except:
                continue  # Timeout, check shutdown event
                
            runner = ChallengeRunner(
                self.db, 
                f"exegol_{challenge_id}", 
                use_presenter=True,
                optimized_agent_name=self.optimized_agent_name
            )
            
            # Track active runner for cleanup
            self.active_runners.add(runner)
            
            try:
                flag = runner.run_attempt(challenge_id)
                print(f"Challenge {challenge_id}: {flag or 'FAILED'}")
            finally:
                # Remove from active runners when done
                self.active_runners.discard(runner)
    
    def _handle_interrupt(self, signum, frame):
        """Handle Ctrl+C and cleanup containers"""
        logger.info("Received interrupt signal, cleaning up containers...")
        print("\n🛑 Shutting down and cleaning containers...")
        
        # Signal shutdown to workers
        self._shutdown_event.set()
        
        # Cleanup all active runners and their containers
        for runner in list(self.active_runners):
            try:
                if hasattr(runner, 'container') and runner.container:
                    logger.info(f"Stopping container: {runner.container.container_name}")
                    runner.container.stop()
            except Exception as e:
                logger.error(f"Error stopping container: {e}")
        
        print("✅ Cleanup complete")
        exit(0)
    
    def shutdown(self):
        """Graceful shutdown method"""
        logger.info("Shutting down orchestrator...")
        
        # Signal shutdown to workers
        self._shutdown_event.set()
        
        # Cleanup all active runners and their containers
        for runner in list(self.active_runners):
            try:
                if hasattr(runner, 'container') and runner.container:
                    logger.debug(f"Stopping container: {runner.container.container_name}")
                    runner.container.cleanup()
            except Exception as e:
                logger.error(f"Error stopping container: {e}")
        
        logger.debug("Orchestrator shutdown complete")


