import argparse
import os
import signal
import subprocess
import sys
import time

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

IS_WINDOWS = sys.platform == "win32"
VENV_BIN = os.path.join(".venv", "Scripts" if IS_WINDOWS else "bin")
PYTHON_EXEC = (
    os.path.join(VENV_BIN, "python.exe" if IS_WINDOWS else "python")
    if os.path.exists(os.path.join(VENV_BIN, "python.exe" if IS_WINDOWS else "python"))
    else sys.executable
)
CELERY_EXEC = (
    os.path.join(VENV_BIN, "celery.exe" if IS_WINDOWS else "celery")
    if os.path.exists(os.path.join(VENV_BIN, "celery.exe" if IS_WINDOWS else "celery"))
    else "celery"
)
UVICORN_EXEC = (
    os.path.join(VENV_BIN, "uvicorn.exe" if IS_WINDOWS else "uvicorn")
    if os.path.exists(os.path.join(VENV_BIN, "uvicorn.exe" if IS_WINDOWS else "uvicorn"))
    else "uvicorn"
)


def get_command(service: str) -> list[str]:
    if service == "api":
        return [
            UVICORN_EXEC,
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--reload",
        ]
    elif service == "worker":
        cmd = [
            CELERY_EXEC,
            "-A",
            "app.worker.celery_app",
            "worker",
            "-Q",
            "convert,image,video,gpu",
            "--loglevel=INFO",
        ]
        if IS_WINDOWS:
            cmd.extend(["-P", "solo"])
        return cmd
    elif service == "beat":
        return [
            CELERY_EXEC,
            "-A",
            "app.worker.celery_app",
            "beat",
            "--loglevel=INFO",
        ]
    elif service == "test":
        return [PYTHON_EXEC, "-m", "pytest"]
    raise ValueError(f"Unknown service: {service}")


def check_redis():
    """Kiểm tra nhanh kết nối Redis trên localhost:6379."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect(("127.0.0.1", 6379))
        s.close()
        return True
    except Exception:
        return False


def run_single(service: str):
    cmd = get_command(service)
    print(f"🚀 Đang khởi chạy [{service.upper()}]: {' '.join(cmd)}\n")
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print(f"\n🛑 Đã dừng [{service.upper()}].")


def run_all():
    print("=" * 60)
    print("🔥 OneForAll - Khởi chạy toàn bộ hệ thống (Dev Mode)")
    print("=" * 60)

    # 1. Kiểm tra Redis
    if not check_redis():
        print("⚠️ CẢNH BÁO: Không kết nối được Redis tại 127.0.0.1:6379!")
        print("👉 Vui lòng bật Redis trước (ví dụ: 'docker run -d -p 6379:6379 redis:7-alpine').\n")

    services = ["api", "worker", "beat"]
    processes: list[tuple[str, subprocess.Popen]] = []

    def stop_all(*args):
        print("\n\n🛑 Đang dừng tất cả tiến trình...")
        for name, proc in processes:
            try:
                if IS_WINDOWS:
                    subprocess.call(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    proc.terminate()
            except Exception:
                pass
        print("✅ Tất cả tiến trình đã dừng an toàn.")
        sys.exit(0)

    signal.signal(signal.SIGINT, stop_all)
    if not IS_WINDOWS:
        signal.signal(signal.SIGTERM, stop_all)

    for name in services:
        cmd = get_command(name)
        print(f"▶️ Khởi động [{name.upper()}]: {' '.join(cmd)}")
        proc = subprocess.Popen(cmd)
        processes.append((name, proc))
        time.sleep(1.0)  # Giãn cách 1 giây để các service khởi động ổn định

    print("\n✨ Tất cả dịch vụ đã chạy! Nhấn Ctrl + C để dừng toàn bộ.\n")

    try:
        while True:
            for name, proc in processes:
                ret = proc.poll()
                if ret is not None:
                    print(f"⚠️ Tiến trình [{name}] đã thoát với mã: {ret}")
                    stop_all()
            time.sleep(1.0)
    except KeyboardInterrupt:
        stop_all()


def main():
    parser = argparse.ArgumentParser(description="OneForAll Service Runner")
    parser.add_argument(
        "service",
        nargs="?",
        default="all",
        choices=["all", "api", "worker", "beat", "test", "docker"],
        help="Dịch vụ cần chạy: all (mặc định), api, worker, beat, test, docker",
    )
    args = parser.parse_args()

    if args.service == "docker":
        print("🐳 Đang chạy toàn bộ stack bằng Docker Compose...")
        subprocess.run(["docker", "compose", "up", "--build"])
    elif args.service == "all":
        run_all()
    else:
        run_single(args.service)


if __name__ == "__main__":
    main()
