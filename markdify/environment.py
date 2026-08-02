"""Bağımlılık tespiti ve kurulumu (docling paketi, LibreOffice).

Uygulama, eksik bağımlılıkları açılışta tespit eder ve arayüzden kurulmalarını
sağlar. Burada yalnızca tespit/kurulum mantığı bulunur; arayüzle bağı yoktur.
"""

from __future__ import annotations

import importlib
import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from .config import is_ascii_safe, logger

LIBREOFFICE_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)

LIBREOFFICE_WINGET_ID = "TheDocumentFoundation.LibreOffice"

# pythonw.exe altında alt süreçlerin konsol penceresi açmasını engeller.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

LineCallback = Callable[[str], None]


# --------------------------------------------------------------------------- #
# Tespit
# --------------------------------------------------------------------------- #

def docling_installed() -> bool:
    """docling paketi içe aktarılabilir durumda mı?"""
    return importlib.util.find_spec("docling") is not None


def docling_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("docling")
    except Exception:
        return None


def find_libreoffice() -> str | None:
    """LibreOffice'in ``soffice`` çalıştırılabilirini arar.

    DOCX içindeki DrawingML (çizim/şekil) nesnelerinin tam dönüşümü için gerekir;
    zorunlu değildir.
    """
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return found
    for candidate in LIBREOFFICE_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def winget_available() -> bool:
    return shutil.which("winget") is not None


def docling_parse_usable() -> bool:
    """Varsayılan (yüksek kaliteli) PDF arka ucu bu kurulumda çalışabilir mi?

    ``docling_parse`` yerel bir C++ eklentisidir ve kaynak dosyalarını kendi
    kurulum dizininden dar (narrow) karakterli yol ile açar. Kurulum yolu ASCII
    dışı karakter içeriyorsa (örn. ``C:\\Users\\Kullanıcı\\...``) bu dosyaları
    bulamaz ve her PDF dönüşümü ``DocumentLoadError`` ile başarısız olur.
    """
    spec = importlib.util.find_spec("docling_parse")
    if spec is None or not spec.origin:
        return False
    return is_ascii_safe(Path(spec.origin).parent)


def environment_report() -> dict[str, object]:
    """Tanılama için ortam özeti (günlüğe yazılır)."""
    return {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "in_venv": sys.prefix != sys.base_prefix,
        "docling": docling_version() or "kurulu değil",
        "docling_parse_usable": docling_parse_usable(),
        "libreoffice": find_libreoffice() or "bulunamadı",
        "winget": winget_available(),
    }


# --------------------------------------------------------------------------- #
# Kurulum
# --------------------------------------------------------------------------- #

def _stream_command(cmd: list[str], on_line: LineCallback | None) -> None:
    """Komutu çalıştırır, çıktısını satır satır geri bildirir.

    Hata durumunda ``RuntimeError`` fırlatır; mesaj son çıktı satırlarını içerir.
    """
    logger.info("Komut çalıştırılıyor: %s", " ".join(cmd))
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
    )

    tail: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip()
        if not line:
            continue
        tail.append(line)
        del tail[:-15]
        logger.debug("  %s", line)
        if on_line:
            on_line(line)

    if process.wait() != 0:
        raise RuntimeError("\n".join(tail) or f"Komut {process.returncode} koduyla bitti.")


def install_docling(on_line: LineCallback | None = None) -> None:
    """docling paketini bu Python yorumlayıcısına kurar."""
    _stream_command(
        [sys.executable, "-m", "pip", "install", "--upgrade", "docling"], on_line
    )
    importlib.invalidate_caches()
    if not docling_installed():
        raise RuntimeError("Kurulum tamamlandı ancak docling hâlâ içe aktarılamıyor.")


def install_libreoffice(on_line: LineCallback | None = None) -> None:
    """LibreOffice'i winget ile sessizce kurar."""
    if not winget_available():
        raise RuntimeError(
            "winget bulunamadı. LibreOffice'i elle kurun: "
            "https://www.libreoffice.org/download/download/"
        )
    _stream_command(
        [
            "winget", "install", "-e", "--id", LIBREOFFICE_WINGET_ID,
            "--accept-package-agreements", "--accept-source-agreements", "--silent",
        ],
        on_line,
    )
