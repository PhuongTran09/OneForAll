"""Job workspace and SSD temporary directory management.

Ensures worker jobs operate in isolated temporary directories:
    /tmp/oneforall/{job_id}/
    ├── input.{ext}
    ├── output.{ext}
    └── work/

Enforces strict disk cleanup via try...finally: cleanup_job_temp_dir(job_id).
Includes disk space validation to prevent SSD exhaustion on large media jobs.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import AppException
from app.utils.logger import logger


def get_base_temp_dir() -> Path:
    """Return the base temporary directory for OneForAll jobs.

    Defaults to /tmp/oneforall on POSIX, or system temp / oneforall on Windows.
    """
    configured = getattr(settings, "TEMP_DIR", None)
    if configured:
        p = Path(configured)
    elif os.name == "nt":
        p = Path(tempfile.gettempdir()) / "oneforall"
    else:
        p = Path("/tmp/oneforall")

    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Fallback to system temp if default path is not writable
        p = Path(tempfile.gettempdir()) / "oneforall"
        p.mkdir(parents=True, exist_ok=True)
    return p


class JobWorkspace:
    """Isolated SSD workspace for a single processing job."""

    def __init__(self, job_id: str, base_dir: Path | None = None) -> None:
        self.job_id = str(job_id).strip()
        self.base_dir = base_dir or get_base_temp_dir()
        self.dir_path = self.base_dir / self.job_id
        self.work_dir = self.dir_path / "work"
        self._created = False

    def ensure_dirs(self) -> JobWorkspace:
        """Create the job directory and working subfolder."""
        self.dir_path.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._created = True
        return self

    def input_path(self, ext: str = "bin") -> Path:
        """Return the standardized input file path."""
        self.ensure_dirs()
        clean_ext = ext.lstrip(".").strip() or "bin"
        return self.dir_path / f"input.{clean_ext}"

    def output_path(self, ext: str = "bin") -> Path:
        """Return the standardized output file path."""
        self.ensure_dirs()
        clean_ext = ext.lstrip(".").strip() or "bin"
        return self.dir_path / f"output.{clean_ext}"

    def check_disk_space(self, required_bytes: int = 100 * 1024 * 1024) -> None:
        """Ensure sufficient free disk space exists before processing large media.

        Default minimum free space required: 100 MB.
        """
        try:
            target_path = self.dir_path if self.dir_path.exists() else self.base_dir
            usage = shutil.disk_usage(str(target_path))
            if usage.free < required_bytes:
                free_mb = usage.free / (1024 * 1024)
                req_mb = required_bytes / (1024 * 1024)
                logger.error(
                    "[workspace] Insufficient disk space for job %s: free=%.1fMB, required=%.1fMB",
                    self.job_id,
                    free_mb,
                    req_mb,
                )
                raise AppException(
                    status_code=507,
                    detail=f"Dung lượng đĩa không đủ để xử lý tác vụ (trống {free_mb:.1f}MB, yêu cầu {req_mb:.1f}MB).",
                )
        except AppException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("[workspace] Could not check disk usage: %s", exc)

    def cleanup(self) -> None:
        """Recursively delete the job's temporary directory from SSD."""
        if self.dir_path.exists():
            try:
                shutil.rmtree(self.dir_path, ignore_errors=True)
                logger.debug("[workspace] Cleaned up temporary directory for job %s", self.job_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[workspace] Failed to cleanup %s: %s", self.dir_path, exc)


def get_job_workspace(job_id: str) -> JobWorkspace:
    """Factory creating and preparing a workspace for the given job_id."""
    workspace = JobWorkspace(job_id)
    workspace.ensure_dirs()
    return workspace


def cleanup_job_temp_dir(job_id: str) -> None:
    """Idempotently clean up a job's temporary directory on SSD."""
    workspace = JobWorkspace(job_id)
    workspace.cleanup()
