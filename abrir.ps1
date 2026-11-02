# Atalho do Radar do Vale: abre o painel na hora; se os dados tem mais de 6h, atualiza antes (~1 min).
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$js = Join-Path $PSScriptRoot 'painel\noticias.js'
$py = (Get-Command python).Source
if (-not (Test-Path $js)) {
    Write-Host 'Primeira coleta (cerca de 2 minutos)...'
    & $py (Join-Path $PSScriptRoot 'coletor.py') --dias 30
} elseif (((Get-Date) - (Get-Item $js).LastWriteTime).TotalHours -gt 6) {
    Write-Host 'Atualizando noticias do Vale (cerca de 1 minuto)...'
    & $py (Join-Path $PSScriptRoot 'coletor.py') --dias 3
}
Start-Process (Join-Path $PSScriptRoot 'painel\index.html')
