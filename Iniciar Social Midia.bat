@echo off
rem Abre o Social Midia Autonoma com dois cliques.
rem Feche esta janela para desligar o app.
title Social Midia Autonoma - feche esta janela para desligar
cd /d "%~dp0"
set "PORTA=8501"
set "URL=http://localhost:%PORTA%"

rem Ja esta aberto? So abre o navegador.
netstat -ano | findstr /r /c:":%PORTA% .*LISTENING" >nul
if not errorlevel 1 (
    start "" "%URL%"
    exit /b 0
)

call "windows\python.bat" || goto :erro

"%PY%" -c "import streamlit" >nul 2>nul
if errorlevel 1 (
    echo Primeira vez: instalando os componentes do app. Isso pode levar alguns minutos...
    "%PY%" -m pip install -r requirements.txt || goto :erro
)

rem Abre o navegador assim que o app estiver pronto.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 120;$i++){try{(New-Object Net.Sockets.TcpClient('127.0.0.1',%PORTA%)).Close();Start-Process '%URL%';break}catch{Start-Sleep 1}}"

echo.
echo  Social Midia Autonoma rodando em %URL%
echo  Pode minimizar esta janela. Para DESLIGAR o app, feche-a.
echo.
"%PY%" -m streamlit run app.py --server.headless true --server.port %PORTA%
if errorlevel 1 goto :erro
exit /b 0

:erro
echo.
echo  Algo deu errado. Leia a mensagem acima (ou mande um print para o Claude).
pause
exit /b 1
