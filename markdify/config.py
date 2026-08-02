"""Uygulama yolları, ayar kalıcılığı ve günlükleme kurulumu."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "Markdify"
APP_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = APP_DIR / "settings.json"
LOG_DIR = APP_DIR / "logs"
LOG_PATH = LOG_DIR / "markdify.log"

logger = logging.getLogger("markdify")


def is_ascii_safe(path: str | os.PathLike[str]) -> bool:
    """Yol yalnızca ASCII karakter içeriyor mu?

    docling-parse'ın C++ katmanı Windows'ta ASCII olmayan yolları (örn. Türkçe
    'ı' içeren kullanıcı adları) çözemiyor ve kaynak dosyalarını bulamıyor.
    Bu kontrol, hangi PDF arka ucunun güvenli olduğunu belirlemek için kullanılır.
    """
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def setup_logging(verbose: bool = False) -> None:
    """Dosyaya dönen (rotating) günlükleyiciyi kurar."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)

    # pythonw.exe altında stderr yoktur; konsol varsa oraya da yaz.
    if sys.stderr is not None:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(stream_handler)


def configure_runtime_env() -> None:
    """Gürültülü ve gereksiz uyarıları susturur.

    Not: Hugging Face model önbelleği (``~/.cache/huggingface``) ASCII olmayan bir
    yolda olsa bile sorunsuz çalışır — o katman saf Python dosya G/Ç'si kullanır.
    Yalnızca ``docling-parse``ın C++ katmanı ASCII dışı yollarda başarısız olur;
    o da arka uç seçimiyle çözülür (bkz. ``conversion.resolve_pdf_backend``).
    """
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


@dataclass
class Settings:
    """Kullanıcı tercihleri; ``settings.json`` içinde saklanır."""

    output_format: str = "markdown"
    pdf_backend: str = "auto"  # auto | docling-parse | pypdfium2
    enable_ocr: bool = False
    appearance: str = "system"  # system | light | dark
    show_source: bool = True  # kaynak belge sütunu görünsün mü
    last_input_dir: str = ""
    last_output_dir: str = ""
    recent_files: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Settings":
        if not SETTINGS_PATH.exists():
            return cls()
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Ayarlar okunamadı, varsayılanlar kullanılıyor: %s", exc)
            return cls()

        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        try:
            SETTINGS_PATH.write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("Ayarlar kaydedilemedi: %s", exc)
