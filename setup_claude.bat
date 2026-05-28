@echo off
echo Configuring Claude Desktop for Webull...
python "%~dp0setup_claude.py"
if errorlevel 1 pause
