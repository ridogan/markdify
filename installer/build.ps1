# Markdify kurulum sihirbazını derler.
#
# Gereksinim: Inno Setup 6  ->  winget install -e --id JRSoftware.InnoSetup
# Çıktı:      dist\Markdify-Setup-<sürüm>.exe

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

$candidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Host "HATA: Inno Setup derleyicisi (ISCC.exe) bulunamadı." -ForegroundColor Red
    Write-Host "Kurmak için: winget install -e --id JRSoftware.InnoSetup" -ForegroundColor Yellow
    exit 1
}

Write-Host "Derleyici: $iscc" -ForegroundColor DarkGray
& $iscc "$PSScriptRoot\markdify.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Host "HATA: Derleme başarısız (kod $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
}

$output = Get-ChildItem "$root\dist\Markdify-Setup-*.exe" -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($output) {
    Write-Host ""
    Write-Host "Hazır: $($output.FullName)" -ForegroundColor Cyan
    Write-Host "Boyut: $([math]::Round($output.Length / 1MB, 2)) MB" -ForegroundColor Cyan
}
