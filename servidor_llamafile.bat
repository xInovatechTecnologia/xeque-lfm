@echo off
REM Opcional: expoe o GGUF modificado via llamafile (API local em http://127.0.0.1:8080)
REM O motor de jogo NAO precisa disto; serve para demonstrar o modelo no llamafile.
cd /d "%~dp0"
"%USERPROFILE%\Downloads\llamafile-0.10.5.exe" -m modelo\XequeLFM-230M.Q8_0.gguf --server --host 127.0.0.1 --port 8080 -c 512 --nobrowser
