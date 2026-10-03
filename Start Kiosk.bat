@echo off
rem Double-click to start the kiosk; the display opens in its own window. See README.md.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
if errorlevel 1 pause
