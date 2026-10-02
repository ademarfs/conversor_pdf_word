@echo off
rem Inicia a interface do conversor e abre o navegador. Feche a janela para encerrar.
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist ".venv\Scripts\python.exe" (
  echo Conversor ainda nao instalado. Iniciando a instalacao...
  call "%~dp0instalar.bat"
  exit /b
)
title Conversor PDF para Word
echo Conversor PDF para Word - o navegador abrira em instantes.
echo Mantenha esta janela aberta enquanto usar o conversor; feche-a para encerrar.
echo.
".venv\Scripts\python.exe" -m conversor.web
if errorlevel 1 pause
