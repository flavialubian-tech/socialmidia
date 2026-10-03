@echo off
rem Cria o icone "Social Midia" na Area de Trabalho. Rode uma vez so.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "windows\criar_atalho.ps1"
pause
