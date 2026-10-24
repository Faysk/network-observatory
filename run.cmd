@echo off
setlocal
cd /d "%~dp0"
if not defined FNO_PORT set "FNO_PORT=8767"
echo Abre http://127.0.0.1:%FNO_PORT%
if exist "login.txt" (
  python -u -m app.adapters.huawei_b7 --credentials-file "login.txt" --serve --watch --with-probes --port %FNO_PORT%
) else (
  echo Sem login.txt: apenas painel e sondas configuradas.
  python -m app.server --host 127.0.0.1 --port %FNO_PORT%
)
