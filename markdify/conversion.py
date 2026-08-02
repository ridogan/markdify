"""Docling dönüştürme motoru sarmalayıcısı.

Arayüzden bağımsızdır: arka uç seçimi, dönüştürücünün tembel (lazy) kurulumu ve
tek dosya dönüşümü burada yapılır.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .config import logger
from .environment import docling_parse_usable


class OutputFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"
    TEXT = "text"
    HTML = "html"

    @property
    def extension(self) -> str:
        return {
            OutputFormat.MARKDOWN: ".md",
            OutputFormat.JSON: ".json",
            OutputFormat.TEXT: ".txt",
            OutputFormat.HTML: ".html",
        }[self]

    @property
    def label(self) -> str:
        return {
            OutputFormat.MARKDOWN: "Markdown (.md)",
            OutputFormat.JSON: "JSON (.json)",
            OutputFormat.TEXT: "Düz metin (.txt)",
            OutputFormat.HTML: "HTML (.html)",
        }[self]

    @classmethod
    def from_label(cls, label: str) -> "OutputFormat":
        for fmt in cls:
            if fmt.label == label:
                return fmt
        return cls.MARKDOWN


class PdfBackend(str, Enum):
    AUTO = "auto"
    DOCLING_PARSE = "docling-parse"
    PYPDFIUM2 = "pypdfium2"

    @property
    def label(self) -> str:
        return {
            PdfBackend.AUTO: "Otomatik (önerilen)",
            PdfBackend.DOCLING_PARSE: "docling-parse (yüksek kalite)",
            PdfBackend.PYPDFIUM2: "pypdfium2 (uyumluluk)",
        }[self]

    @classmethod
    def from_label(cls, label: str) -> "PdfBackend":
        for backend in cls:
            if backend.label == label:
                return backend
        return cls.AUTO


# docling kurulu değilken (ilk açılış) kullanılan yedek liste.
_FALLBACK_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
    ".odt", ".ods", ".odp", ".html", ".htm", ".xhtml", ".epub",
    ".md", ".csv", ".txt", ".adoc", ".asciidoc", ".tex",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
})

_extension_cache: frozenset[str] | None = None


def supported_extensions() -> frozenset[str]:
    """Docling'in gerçekten okuyabildiği uzantılar (nokta ile, küçük harf).

    Liste docling'in kendi kayıt defterinden okunur; böylece docling
    güncellendiğinde uygulama elle bakım gerektirmeden güncel kalır.
    """
    global _extension_cache
    if _extension_cache is not None:
        return _extension_cache

    try:
        from docling.datamodel.base_models import FormatToExtensions

        found = {
            f".{ext.lower().lstrip('.')}"
            for extensions in FormatToExtensions.values()
            for ext in extensions
        }
        _extension_cache = frozenset(found) or _FALLBACK_EXTENSIONS
    except Exception as exc:
        logger.debug("Uzantı listesi docling'den alınamadı (%s); yedek liste kullanılıyor.", exc)
        _extension_cache = _FALLBACK_EXTENSIONS

    return _extension_cache


def is_supported(path: Path) -> bool:
    """Dosya docling tarafından okunabilir bir türde mi?

    ``.tar.gz`` gibi çok parçalı uzantıları da doğru tanımak için tam ad
    üzerinden kontrol edilir (``Path.suffix`` yalnız son parçayı verir).
    """
    name = path.name.lower()
    return any(name.endswith(ext) for ext in supported_extensions())


@dataclass(frozen=True)
class ConversionOptions:
    """Dönüştürücünün davranışını belirleyen ayarlar."""

    pdf_backend: PdfBackend = PdfBackend.AUTO
    enable_ocr: bool = False


class ConversionError(RuntimeError):
    """Tek bir dosyanın dönüşümü başarısız olduğunda fırlatılır."""


class ConversionService:
    """``DocumentConverter``'ı önbelleğe alan ince bir katman.

    Dönüştürücünün kurulumu pahalıdır (model yükleme), bu yüzden aynı seçenekler
    için yeniden kullanılır; seçenekler değişince yeniden kurulur.
    """

    def __init__(self) -> None:
        self._converter = None
        self._converter_options: ConversionOptions | None = None

    # ------------------------------------------------------------------ #

    @staticmethod
    def resolve_pdf_backend(requested: PdfBackend) -> PdfBackend:
        """İstenen arka ucu, ortamda gerçekten çalışabilecek olana çevirir.

        ``docling-parse`` ASCII olmayan kurulum yollarında çalışmaz; böyle bir
        ortamda otomatik olarak ``pypdfium2``'ye düşülür.
        """
        usable = docling_parse_usable()
        if requested is PdfBackend.AUTO:
            return PdfBackend.DOCLING_PARSE if usable else PdfBackend.PYPDFIUM2
        if requested is PdfBackend.DOCLING_PARSE and not usable:
            logger.warning(
                "docling-parse bu kurulumda kullanılamıyor (ASCII olmayan yol); "
                "pypdfium2'ye geçiliyor."
            )
            return PdfBackend.PYPDFIUM2
        return requested

    def _build_converter(self, options: ConversionOptions):
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        backend = self.resolve_pdf_backend(options.pdf_backend)
        logger.info(
            "Dönüştürücü kuruluyor (arka uç=%s, ocr=%s)", backend.value, options.enable_ocr
        )

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = options.enable_ocr

        pdf_option = PdfFormatOption(pipeline_options=pipeline_options)
        if backend is PdfBackend.PYPDFIUM2:
            from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

            pdf_option = PdfFormatOption(
                pipeline_options=pipeline_options, backend=PyPdfiumDocumentBackend
            )

        return DocumentConverter(format_options={InputFormat.PDF: pdf_option})

    def prepare(
        self, options: ConversionOptions, on_status: Callable[[str], None] | None = None
    ) -> None:
        """Dönüştürücüyü hazırlar (gerekiyorsa modelleri indirir/yükler)."""
        if self._converter is not None and self._converter_options == options:
            return
        if on_status:
            on_status("Docling modelleri yükleniyor (ilk çalıştırmada uzun sürebilir)…")
        self._converter = self._build_converter(options)
        self._converter_options = options

    def convert(self, path: Path, output_format: OutputFormat) -> str:
        """Tek bir dosyayı dönüştürür ve istenen biçimde metin döndürür."""
        if self._converter is None:
            raise RuntimeError("Dönüştürücü hazırlanmadan convert() çağrıldı.")

        try:
            result = self._converter.convert(str(path))
        except Exception as exc:
            raise ConversionError(self._humanize(exc)) from exc

        document = result.document
        if output_format is OutputFormat.MARKDOWN:
            return document.export_to_markdown()
        if output_format is OutputFormat.JSON:
            return json.dumps(document.export_to_dict(), ensure_ascii=False, indent=2)
        if output_format is OutputFormat.HTML:
            return document.export_to_html()
        return document.export_to_text()

    # ------------------------------------------------------------------ #

    @staticmethod
    def _humanize(exc: Exception) -> str:
        """Docling'in ham hatalarını anlaşılır Türkçe mesaja çevirir."""
        text = str(exc)
        if "pdf_resources" in text or "docling_parse" in text:
            return (
                "PDF ayrıştırıcısı kaynak dosyalarını açamadı. Bu genellikle kurulum "
                "yolunda Türkçe karakter bulunmasından kaynaklanır. Ayarlar'dan PDF "
                "arka ucunu 'pypdfium2' yapın veya uygulamayı ASCII adlı bir klasöre kurun."
            )
        if "not valid" in text or "DocumentLoadError" in text:
            return f"Dosya okunamadı veya bozuk olabilir. Ayrıntı: {text}"
        if "Timeout" in text or "timed out" in text:
            return "İşlem zaman aşımına uğradı. Dosya çok büyük olabilir."
        return text
