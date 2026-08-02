# Markdify — kurulum betiği
#
# Bu klasörü hedef bilgisayara kopyalayıp kur.bat dosyasına çift tıklamak yeterlidir.
# Betik şunları yapar:
#   1. Python yoksa kurar
#   2. Uygulama klasöründe izole bir sanal ortam (.venv) oluşturur
#   3. Gerekli paketleri bu ortama kurar
#   4. LibreOffice yoksa kurar (isteğe bağlı bileşen)
#   5. Masaüstüne konsolsuz bir kısayol ekler
#
# .venv'in uygulama klasöründe olması yalnızca temizlik için değil, aynı zamanda
# bir HATA DÜZELTMESİDİR: docling-parse'ın C++ katmanı, kurulum yolunda ASCII
# dışı karakter (örn. "C:\Users\Kullanıcı") olduğunda PDF kaynaklarını açamaz.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Test-Cmd($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Sync-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

Write-Host ""
Write-Host "=== Markdify Kurulumu ===" -ForegroundColor Cyan
Write-Host ""

# --- 0. Kurulum yolu kontrolü ------------------------------------------------
$asciiSafe = ($root -match '^[\x00-\x7F]+$')
if (-not $asciiSafe) {
    Write-Host "UYARI: Kurulum yolu Türkçe/ASCII dışı karakter içeriyor:" -ForegroundColor Yellow
    Write-Host "  $root" -ForegroundColor Yellow
    Write-Host "  Yüksek kaliteli PDF ayrıştırıcı (docling-parse) bu yolda çalışmaz;" -ForegroundColor Yellow
    Write-Host "  uygulama otomatik olarak pypdfium2'ye düşecek." -ForegroundColor Yellow
    Write-Host "  Öneri: bu klasörü C:\markdify gibi bir yola taşıyın." -ForegroundColor Yellow
    Write-Host ""
}

# --- 1. Python ---------------------------------------------------------------
$hasPython = $false
if (Test-Cmd "python") {
    try { if ((python --version 2>&1) -match "Python 3\.(1[0-9]|[9])") { $hasPython = $true } } catch {}
}

if (-not $hasPython) {
    if (-not (Test-Cmd "winget")) {
        Write-Host "HATA: Python yok ve winget bulunamadı." -ForegroundColor Red
        Write-Host "Python'u elle kurun: https://www.python.org/downloads/" -ForegroundColor Red
        exit 1
    }
    Write-Host "[1/5] Python kuruluyor..." -ForegroundColor Yellow
    winget install -e --id Python.Python.3.12 `
        --accept-package-agreements --accept-source-agreements
    Sync-Path
} else {
    Write-Host "[1/5] Python zaten kurulu." -ForegroundColor Green
}

# --- 2. Sanal ortam ----------------------------------------------------------
$venv = Join-Path $root ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "[2/5] Sanal ortam oluşturuluyor (.venv)..." -ForegroundColor Yellow
    python -m venv $venv
} else {
    Write-Host "[2/5] Sanal ortam zaten mevcut." -ForegroundColor Green
}

# --- 3. Python paketleri -----------------------------------------------------
Write-Host "[3/5] Paketler kuruluyor (docling ~2 GB, ilk kurulum uzun sürebilir)..." -ForegroundColor Yellow
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host "HATA: Paket kurulumu başarısız." -ForegroundColor Red
    exit 1
}

# --- 4. LibreOffice (isteğe bağlı) -------------------------------------------
$loPaths = @(
    "C:\Program Files\LibreOffice\program\soffice.exe",
    "C:\Program Files (x86)\LibreOffice\program\soffice.exe"
)
$hasLo = $false
foreach ($p in $loPaths) { if (Test-Path $p) { $hasLo = $true } }

if (-not $hasLo) {
    if (Test-Cmd "winget") {
        Write-Host "[4/5] LibreOffice kuruluyor (Word çizim/şekilleri için)..." -ForegroundColor Yellow
        winget install -e --id TheDocumentFoundation.LibreOffice `
            --accept-package-agreements --accept-source-agreements --silent
    } else {
        Write-Host "[4/5] winget yok; LibreOffice atlandı (uygulamadan sonra kurulabilir)." -ForegroundColor Yellow
    }
} else {
    Write-Host "[4/5] LibreOffice zaten kurulu." -ForegroundColor Green
}

# --- 5. Masaüstü kısayolu ----------------------------------------------------
Write-Host "[5/5] Masaüstü kısayolu oluşturuluyor..." -ForegroundColor Yellow
$venvPythonw = Join-Path $venv "Scripts\pythonw.exe"
if (-not (Test-Path $venvPythonw)) { $venvPythonw = $venvPython }

# Uygulama ikonu; yoksa pythonw'unkine düşülür (kısayol yine çalışır).
$iconFile = Join-Path $root "assets\markdify.ico"
if (Test-Path $iconFile) { $iconLocation = "$iconFile,0" } else { $iconLocation = "$venvPythonw,0" }

$shortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Markdify.lnk"
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($shortcut)
$lnk.TargetPath       = $venvPythonw
$lnk.Arguments        = "`"$root\app.py`""
$lnk.WorkingDirectory = $root
$lnk.IconLocation     = $iconLocation
$lnk.Description      = "Markdify — Belge Dönüştürücü"
$lnk.Save()

Write-Host ""
Write-Host "Kurulum tamamlandı." -ForegroundColor Cyan
Write-Host "Masaüstündeki 'Markdify' kısayolundan başlatabilirsiniz." -ForegroundColor Cyan
Write-Host ""
