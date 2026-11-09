@echo off
rem Double-click to start the kiosk with an Android phone or tablet as the screen, microphone and
rem speaker, connected by a USB cable (no Wi-Fi on the phone). See README.md.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" -Usb %*
if errorlevel 1 pause
