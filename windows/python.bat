@echo off
rem Descobre qual Python usar e guarda em PY (ambiente virtual do projeto primeiro).
set "PY="
if exist "%~dp0..\.venv\Scripts\python.exe" set "PY=%~dp0..\.venv\Scripts\python.exe"
if not defined PY if exist "%~dp0..\venv\Scripts\python.exe" set "PY=%~dp0..\venv\Scripts\python.exe"
if defined PY exit /b 0
for /f "delims=" %%i in ('where python 2^>nul') do (
    echo %%i | findstr /i "WindowsApps" >nul || (set "PY=%%i" & goto :achou)
)
for /f "delims=" %%i in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%i"
:achou
if defined PY exit /b 0
echo O Python nao foi encontrado. Instale em https://www.python.org (marque "Add python.exe to PATH").
exit /b 1
