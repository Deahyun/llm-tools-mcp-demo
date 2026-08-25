# 최초 1회 셋업 (Windows 11 네이티브)
#   .\scripts\setup.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== 1/5  Python 확인 ==" -ForegroundColor Cyan
python --version

Write-Host "== 2/5  venv 생성 ==" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) { python -m venv .venv }
$py = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "== 3/5  의존성 설치 ==" -ForegroundColor Cyan
& $py -m pip install --upgrade pip
& $py -m pip install -e ".[dev]"

Write-Host "== 4/5  Playwright Chromium 설치 ==" -ForegroundColor Cyan
& $py -m playwright install chromium

Write-Host "== 5/5  Ollama 확인 ==" -ForegroundColor Cyan
try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
    $names = $tags.models | ForEach-Object { $_.name }
    Write-Host ("보유 모델: " + ($names -join ", "))
    if ($names -notcontains "qwen3.6:27b") {
        Write-Host "qwen3.6:27b 가 없습니다. 'ollama pull qwen3.6:27b' 를 실행하거나 .env 의 OLLAMA_MODEL 을 바꾸세요." -ForegroundColor Yellow
    }
} catch {
    Write-Host "Ollama(127.0.0.1:11434)에 연결할 수 없습니다. Ollama 를 먼저 실행하세요." -ForegroundColor Yellow
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ".env 생성됨 (.env.example 복사)" -ForegroundColor Green
}

Write-Host ""
Write-Host "완료. 다음 순서로 실행하세요:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  python -m toolsdemo.mocksite.server            # 터미널 1"
Write-Host "  python -m toolsdemo.agent_tools `"내일 오전 9시쯤 서울에서 부산 가는 기차 예매해줘`"   # 터미널 2"
