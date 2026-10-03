@echo off
rem Double-click to start the kiosk full screen (Alt+F4 closes the display). See README.md.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" -FullScreen
if errorlevel 1 pause
