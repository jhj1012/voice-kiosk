@echo off
rem Double-click to start the kiosk with an Android phone as the screen, microphone and
rem speaker (the handset plugged into the phone). See README.md.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" -Phone %*
if errorlevel 1 pause
