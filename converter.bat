@echo off
rem Converte os PDFs arrastados sobre este arquivo; o .docx fica ao lado de cada PDF.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Execute instalar.bat primeiro.
  pause
  exit /b 1
)
if "%~1"=="" (
  echo Arraste um ou mais arquivos PDF sobre converter.bat.
  pause
  exit /b 1
)
pushd "%~dp0"
".venv\Scripts\python.exe" -m conversor %*
popd
echo.
pause
