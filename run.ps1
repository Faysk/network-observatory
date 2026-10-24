$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not $env:FNO_PORT) { $env:FNO_PORT = '8767' }
Write-Host "Abre http://127.0.0.1:$env:FNO_PORT" -ForegroundColor Cyan
$observatoryCredentialsPath = Join-Path $PSScriptRoot 'login.txt'
if (Test-Path -LiteralPath $observatoryCredentialsPath -PathType Leaf) {
  python -u -m app.adapters.huawei_b7 --credentials-file $observatoryCredentialsPath --serve --watch --with-probes --port $env:FNO_PORT
} else {
  Write-Host 'Sem login.txt: apenas painel e sondas configuradas; telemetria autenticada indisponivel.' -ForegroundColor Yellow
  python -m app.server --host 127.0.0.1 --port $env:FNO_PORT
}
