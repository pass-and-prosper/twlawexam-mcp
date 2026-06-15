# serve_phone.ps1 — 啟動 twexam 題庫 MCP 的 HTTP 模式（給手機透過 Cloudflare Tunnel 連線）
# 用法：右鍵以 PowerShell 執行，或 `powershell -File scripts\serve_phone.ps1`
$ErrorActionPreference = "Stop"
# 自動定位專案根目錄（本檔在 <proj>\scripts\ 底下），不寫死磁碟路徑，搬到任何位置都能跑
$proj = Split-Path -Parent $PSScriptRoot
$tokenFile = Join-Path $proj ".twexam_token"

# 穩定密碼：第一次產生後存檔，之後重啟都用同一把（手機連接器才不用一直改）
if (-not (Test-Path $tokenFile)) {
    $tok = & python -c "import secrets; print(secrets.token_urlsafe(32))"
    Set-Content -Path $tokenFile -Value $tok -NoNewline -Encoding ascii
    Write-Host "已產生新密碼並存到 $tokenFile"
}
$token = (Get-Content $tokenFile -Raw).Trim()

Write-Host "=================================================="
Write-Host " 你的連線密碼 (TWEXAM_TOKEN):"
Write-Host "   $token"
Write-Host " Claude 連接器網址結尾要加  /mcp"
Write-Host " 另開一個視窗執行： cloudflared tunnel --url http://127.0.0.1:8000 --http-host-header 127.0.0.1:8000"
Write-Host " （--http-host-header 必加，否則帶密碼請求會回 421 Invalid Host header）"
Write-Host "=================================================="

$env:TWEXAM_TRANSPORT = "http"
$env:TWEXAM_TOKEN = $token
$env:TWEXAM_HOST = "127.0.0.1"
$env:TWEXAM_PORT = "8000"
Set-Location $proj
& python -m twexam_mcp.server
