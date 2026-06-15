@echo off
REM Monthly prediction-refresh launcher for Windows Task Scheduler.
REM pushd auto-maps a temp drive for UNC paths, so it runs even if W: is not mapped.
pushd "%~dp0.."
".venv\Scripts\python.exe" "scripts\refresh_predictions.py" %*
popd
