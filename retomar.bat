@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Retomando a ultima partida salva...
python jogar.py --retomar %*
pause
