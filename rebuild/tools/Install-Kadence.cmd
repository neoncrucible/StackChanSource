@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_desktop.ps1"
if errorlevel 1 (
  echo Installation did not complete. Your previous Kadence shortcut is unchanged.
  pause
  exit /b 1
)
