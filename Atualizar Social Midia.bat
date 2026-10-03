@echo off
rem Baixa a versao mais nova do app (depois de um merge no GitHub) e atualiza os componentes.
title Atualizando Social Midia Autonoma
cd /d "%~dp0"

where git >nul 2>nul
if errorlevel 1 (
    echo O Git nao foi encontrado. Instale em https://git-scm.com e tente de novo.
    pause
    exit /b 1
)

echo Baixando a versao mais nova...
git pull --ff-only || goto :erro

call "windows\python.bat" || goto :erro
echo Atualizando os componentes...
"%PY%" -m pip install -q -r requirements.txt || goto :erro

echo.
echo  Pronto! Se o app estiver aberto, feche a janela dele e abra de novo pelo atalho.
pause
exit /b 0

:erro
echo.
echo  Nao foi possivel atualizar. Leia a mensagem acima (ou mande um print para o Claude).
pause
exit /b 1
