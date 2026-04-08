import os
import shutil
import threading
import time
import uuid
import queue


TEMP_BASE = "/tmp/schemagic"
JOB_TTL = 1800  # 30 minutes


class JobStore:
    def __init__(self):
        self._jobs: dict = {}
        self._lock = threading.Lock()
        self._cleanup_timer = None
        self._start_cleanup()

    def create(self) -> str:
        job_id = str(uuid.uuid4())
        output_dir = os.path.join(TEMP_BASE, job_id)
        os.makedirs(output_dir, exist_ok=True)

        with self._lock:
            self._jobs[job_id] = {
                "status": "created",
                "pipeline": None,
                "datasheet": None,
                "match": None,
                "candidates": [],
                "suffix_code": None,
                "pins": [],
                "output_dir": output_dir,
                "queue": queue.Queue(),
                "package_event": threading.Event(),
                "selected_package": None,
                "created_at": time.time(),
            }
        return job_id

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(kwargs)

    def delete(self, job_id: str):
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job and os.path.isdir(job["output_dir"]):
            shutil.rmtree(job["output_dir"], ignore_errors=True)

    def _start_cleanup(self):
        self._cleanup_timer = threading.Timer(300, self._cleanup)
        self._cleanup_timer.daemon = True
        self._cleanup_timer.start()

    def _cleanup(self):
        now = time.time()
        expired = []
        with self._lock:
            for job_id, job in self._jobs.items():
                if now - job["created_at"] > JOB_TTL:
                    expired.append(job_id)
        for job_id in expired:
            self.delete(job_id)
        self._start_cleanup()

    def shutdown(self):
        if self._cleanup_timer:
            self._cleanup_timer.cancel()
