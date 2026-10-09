@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"

IF EXIST ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) ELSE (
    set "PYTHON_EXE=python"
)

echo ============================================================
echo   OneForAll - Quick Start
echo ============================================================

"%PYTHON_EXE%" run.py %*
