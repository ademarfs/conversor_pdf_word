@echo off
rem Instala o Conversor PDF para Word (duplo clique). Nao precisa de administrador.
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*
if errorlevel 1 (
  echo.
  echo A instalacao falhou. Leia a mensagem acima.
  pause
  exit /b 1
)
