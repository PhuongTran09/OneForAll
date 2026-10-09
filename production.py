import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv" / "Scripts"
PYTHON = VENV / "python.exe"
CELERY = VENV / "celery.exe"

LOG_DIR = Path(r"D:\OneForAllData\logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

PROCESSES = []
STOPPING = False


def check_dependencies():
    if not PYTHON.exists():
        raise RuntimeError(f"Khong tim thay Python: {PYTHON}")

    if not CELERY.exists():
        raise RuntimeError(f"Khong tim thay Celery: {CELERY}")

    if not (ROOT / ".env").exists():
        raise RuntimeError("Khong tim thay file .env")

    # Kiểm tra Redis có lắng nghe trên cổng 6379.
    try:
        with socket.create_connection(("127.0.0.1", 6379), timeout=3):
            pass
    except OSError as exc:
        raise RuntimeError(
            "Redis chua san sang tai 127.0.0.1:6379"
        ) from exc

    # Xác nhận Redis thực sự trả lời lệnh PING.
    result = subprocess.run(
        [
            str(PYTHON),
            "-c",
            (
                "import redis; "
                "r=redis.Redis(host='127.0.0.1', port=6379, "
                "socket_connect_timeout=3); "
                "assert r.ping()"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Redis khong phan hoi PING. "
            f"Chi tiet: {result.stderr.strip()}"
        )


def start_service(name, executable, arguments):
    stdout_path = LOG_DIR / f"{name}.out.log"
    stderr_path = LOG_DIR / f"{name}.err.log"

    stdout_file = stdout_path.open("a", encoding="utf-8")
    stderr_file = stderr_path.open("a", encoding="utf-8")

    try:
        process = subprocess.Popen(
            [str(executable), *arguments],
            cwd=ROOT,
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
        )
    except Exception:
        stdout_file.close()
        stderr_file.close()
        raise

    PROCESSES.append(
        {
            "name": name,
            "process": process,
            "stdout": stdout_file,
            "stderr": stderr_file,
        }
    )

    time.sleep(2)

    if process.poll() is not None:
        raise RuntimeError(
            f"{name} thoat som. Kiem tra log: {stderr_path}"
        )

    print(f"[OK] Da khoi dong {name}, PID={process.pid}")


def stop_all():
    global STOPPING

    if STOPPING:
        return

    STOPPING = True
    print("\nDang dung OneForAll...")

    # Yêu cầu tiến trình dừng trước khi buộc đóng.
    for item in reversed(PROCESSES):
        process = item["process"]

        if process.poll() is None:
            try:
                process.send_signal(signal.SIGINT)
                process.wait(timeout=10)
            except (subprocess.TimeoutExpired, OSError):
                process.terminate()

                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    for item in PROCESSES:
        item["stdout"].close()
        item["stderr"].close()

    print("Da dung cac tien trinh OneForAll.")


def main():
    try:
        os.chdir(ROOT)
        print("=== OneForAll Production ===")
        print(f"Project: {ROOT}")
        print(f"Logs: {LOG_DIR}")

        check_dependencies()

        # API production: không bật reload.
        start_service(
            "api",
            PYTHON,
            [
                "-m", "uvicorn",
                "app.main:app",
                "--host", "127.0.0.1",
                "--port", "8000",
                "--workers", "1",
            ],
        )

        # Một worker cho laptop Windows; xử lý tuần tự.
        start_service(
            "worker",
            CELERY,
            [
                "-A", "app.worker.celery_app",
                "worker",
                "-Q", "convert,image,video,gpu",
                "--loglevel=INFO",
                "-P", "solo",
            ],
        )

        # Chỉ chạy một Celery Beat.
        start_service(
            "beat",
            CELERY,
            [
                "-A", "app.worker.celery_app",
                "beat",
                "--loglevel=INFO",
            ],
        )

        print("\nOneForAll dang chay.")
        print("API Docs: http://127.0.0.1:8000/api/v1/docs")
        print("Health:   http://127.0.0.1:8000/health")
        print("Nhan Ctrl+C de dung.")

        while True:
            for item in PROCESSES:
                code = item["process"].poll()

                if code is not None:
                    raise RuntimeError(
                        f"Dich vu {item['name']} da dung, exit code={code}"
                    )

            time.sleep(2)

    except KeyboardInterrupt:
        pass
    finally:
        stop_all()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)