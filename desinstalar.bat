@echo off
rem Remove o ambiente Python e o atalho. Os dados (pasta dados) sao mantidos.
chcp 65001 >nul
cd /d "%~dp0"
echo Isto remove a pasta .venv e o atalho da area de trabalho.
echo A pasta "dados" (historico e arquivos convertidos) sera mantida.
choice /M "Continuar"
if errorlevel 2 exit /b 0
if exist ".venv" rmdir /s /q ".venv"
powershell -NoProfile -Command "Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Conversor PDF para Word.lnk') -ErrorAction SilentlyContinue"
echo Desinstalado. Para remover tudo, apague esta pasta.
pause
