@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Instalando dependencias do Xeque-LFM ===
python -m pip install --only-binary=:all: llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
python -m pip install chess numpy gguf
if not exist modelo\XequeLFM-230M.Q8_0.gguf (
  if exist modelo\LFM2.5-230M-Chess.Q8_0.gguf (
    echo === Gerando GGUF modificado ===
    python ferramentas\modificar_gguf.py modelo\LFM2.5-230M-Chess.Q8_0.gguf modelo\XequeLFM-230M.Q8_0.gguf
  ) else (
    echo ATENCAO: coloque LFM2.5-230M-Chess.Q8_0.gguf na pasta modelo\ e rode de novo.
  )
)
echo === Testando ===
python benchmark.py --rapido
pause
