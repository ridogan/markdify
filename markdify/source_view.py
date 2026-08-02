"""Kaynak belgeyi (PDF / görüntü) sayfa sayfa gösteren önizleme bileşeni.

Yeni bağımlılık gerektirmez: PDF çizimi için ``pypdfium2`` (docling'in zaten
kurduğu), görüntüler ve ölçekleme için ``Pillow`` kullanılır. Office belgeleri
(docx/pptx/xlsx/odt…) doğrudan çizilemez; istenirse LibreOffice ile geçici bir
PDF'e çevrilip gösterilir.
"""

from __future__ import annotations

import subprocess
import tempfile
import threading
import tkinter as tk
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageTk

from .config import logger
from .environment import find_libreoffice

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}
# LibreOffice ile PDF'e çevrilerek önizlenebilenler.
OFFICE_EXTENSIONS = {
    ".docx", ".doc", ".dotx", ".odt", ".rtf",
    ".pptx", ".ppt", ".odp", ".xlsx", ".xls", ".ods", ".csv",
}

MIN_SCALE, MAX_SCALE = 0.15, 5.0
MAX_PIXELS = 40_000_000  # ~40 MP: aşırı yakınlaştırmada bellek koruması
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# --------------------------------------------------------------------------- #
# Kaynak soyutlaması
# --------------------------------------------------------------------------- #

class _Source:
    """Sayfalı bir belge kaynağı."""

    page_count: int = 0

    def page_size(self, index: int) -> tuple[float, float]:
        raise NotImplementedError

    def render(self, index: int, scale: float) -> Image.Image:
        raise NotImplementedError

    def close(self) -> None:
        pass


class _PdfSource(_Source):
    def __init__(self, path: Path) -> None:
        import pypdfium2 as pdfium

        self._document = pdfium.PdfDocument(str(path))
        self.page_count = len(self._document)

    def page_size(self, index: int) -> tuple[float, float]:
        return self._document[index].get_size()

    def render(self, index: int, scale: float) -> Image.Image:
        return self._document[index].render(scale=scale).to_pil()

    def close(self) -> None:
        try:
            self._document.close()
        except Exception:  # sürüm farkları; dosya kilidini bırakmak yeterli
            pass


class _ImageSource(_Source):
    def __init__(self, path: Path) -> None:
        self._image = Image.open(path)
        self._image.load()
        if self._image.mode not in ("RGB", "RGBA", "L"):
            self._image = self._image.convert("RGB")
        self.page_count = 1

    def page_size(self, index: int) -> tuple[float, float]:
        return float(self._image.width), float(self._image.height)

    def render(self, index: int, scale: float) -> Image.Image:
        width = max(1, int(self._image.width * scale))
        height = max(1, int(self._image.height * scale))
        return self._image.resize((width, height), Image.LANCZOS)

    def close(self) -> None:
        try:
            self._image.close()
        except Exception:
            pass


def open_source(path: Path) -> _Source:
    suffix = path.suffix.lower()
    if suffix in PDF_EXTENSIONS:
        return _PdfSource(path)
    if suffix in IMAGE_EXTENSIONS:
        return _ImageSource(path)
    raise ValueError(f"Bu tür doğrudan önizlenemiyor: {suffix}")


def count_pages(path: Path) -> int | None:
    """PDF sayfa sayısı; belirlenemiyorsa ``None``.

    Yalnızca gerçekten ölçülebilen bir bilgi döndürür — arayüzde tahmini yüzde
    değil, "12 sayfa" gibi doğrulanabilir bir ayrıntı göstermek için kullanılır.
    Ucuzdur: pypdfium2 belgeyi tembel açar, sayfaları çizmez.
    """
    if path.suffix.lower() not in PDF_EXTENSIONS:
        return None
    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(str(path))
        try:
            return len(document)
        finally:
            document.close()  # Windows'ta dosya kilidini bırak
    except Exception as exc:
        logger.debug("Sayfa sayısı okunamadı (%s): %s", path.name, exc)
        return None


def convert_to_pdf(path: Path, output_dir: Path) -> Path:
    """Office belgesini LibreOffice ile PDF'e çevirir ve yolunu döndürür."""
    soffice = find_libreoffice()
    if not soffice:
        raise RuntimeError("LibreOffice bulunamadı.")

    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [soffice, "--headless", "--norestore", "--convert-to", "pdf",
         "--outdir", str(output_dir), str(path)],
        check=True, capture_output=True, timeout=180, creationflags=_NO_WINDOW,
    )
    produced = output_dir / (path.stem + ".pdf")
    if not produced.exists():
        raise RuntimeError("LibreOffice çıktı üretmedi.")
    return produced


# --------------------------------------------------------------------------- #
# Görünüm
# --------------------------------------------------------------------------- #

class SourceView(ctk.CTkFrame):
    """Kaynak belgeyi sayfa gezinme ve yakınlaştırma ile gösterir."""

    def __init__(self, master, on_status=None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._on_status = on_status

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._source: _Source | None = None
        self._path: Path | None = None
        self._page = 0
        self._scale = 1.0
        self._fit_width = True
        self._photo: ImageTk.PhotoImage | None = None
        self._resize_job: str | None = None
        self._last_width = 0
        self._temp_dir: tempfile.TemporaryDirectory | None = None
        self._converting = False

        self._build_toolbar()
        self._build_canvas()
        self._update_controls()

    # ------------------------------------------------------------------ #

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        bar.grid_columnconfigure(3, weight=1)

        self.prev_button = ctk.CTkButton(
            bar, text="◀", width=32, height=26, command=self.previous_page
        )
        self.prev_button.grid(row=0, column=0)

        self.page_label = ctk.CTkLabel(bar, text="—", width=64, font=ctk.CTkFont(size=11))
        self.page_label.grid(row=0, column=1, padx=2)

        self.next_button = ctk.CTkButton(
            bar, text="▶", width=32, height=26, command=self.next_page
        )
        self.next_button.grid(row=0, column=2)

        self.zoom_label = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=11), text_color=("gray40", "gray60")
        )
        self.zoom_label.grid(row=0, column=3, padx=6)

        for index, (text, command) in enumerate((
            ("−", self.zoom_out), ("+", self.zoom_in), ("⤢", self.fit_to_width),
        )):
            ctk.CTkButton(
                bar, text=text, width=30, height=26, command=command,
                fg_color="transparent", border_width=1, text_color=("gray20", "gray85"),
            ).grid(row=0, column=4 + index, padx=(2, 0))

    def _build_canvas(self) -> None:
        holder = ctk.CTkFrame(self, fg_color=("gray82", "gray14"))
        holder.grid(row=1, column=0, sticky="nsew", padx=6, pady=(2, 6))
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(holder, borderwidth=0, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(2, 0), pady=2)

        self.vbar = ctk.CTkScrollbar(holder, command=self.canvas.yview)
        self.vbar.grid(row=0, column=1, sticky="ns", padx=(0, 2), pady=2)
        self.hbar = ctk.CTkScrollbar(holder, orientation="horizontal", command=self.canvas.xview)
        self.hbar.grid(row=1, column=0, sticky="ew", padx=(2, 0), pady=(0, 2))
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)

        self.message = ctk.CTkLabel(
            holder, text="", justify="center", wraplength=280,
            text_color=("gray35", "gray65"),
        )
        self.action_button = ctk.CTkButton(holder, text="", width=200)

        self.apply_theme()
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_shift_wheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)

    def apply_theme(self) -> None:
        self.canvas.configure(
            background=(
                "#4a4a4a" if ctk.get_appearance_mode() == "Dark" else "#9a9a9a"
            )
        )

    # ------------------------------------------------------------------ #
    # Genel giriş
    # ------------------------------------------------------------------ #

    def show(self, path: Path | None) -> None:
        """Verilen dosyayı gösterir; desteklenmiyorsa açıklama yazar."""
        self._release()
        self._path = path

        if path is None:
            self._show_message("Soldaki listeden bir dosya seçin.")
            self._update_controls()
            return

        suffix = path.suffix.lower()
        if suffix not in PDF_EXTENSIONS and suffix not in IMAGE_EXTENSIONS:
            if suffix in OFFICE_EXTENSIONS and find_libreoffice():
                self._show_message(
                    f"“{path.name}” doğrudan görüntülenemiyor.\n"
                    "LibreOffice ile geçici bir PDF'e çevrilerek önizlenebilir.",
                    action=("PDF'e çevir ve göster", self._convert_and_show),
                )
            else:
                self._show_message(
                    f"“{path.name}” için önizleme yok.\n"
                    "PDF ve görüntü dosyaları doğrudan gösterilir."
                )
            self._update_controls()
            return

        self._load(path)

    def _load(self, path: Path) -> None:
        try:
            self._source = open_source(path)
        except Exception as exc:
            logger.warning("Kaynak önizleme açılamadı (%s): %s", path.name, exc)
            self._show_message(f"Dosya açılamadı:\n{exc}")
            self._update_controls()
            return

        self._page = 0
        self._fit_width = True
        self._hide_message()
        self._render()
        self._update_controls()

    def clear(self) -> None:
        self._release()
        self._path = None
        self._show_message("Soldaki listeden bir dosya seçin.")
        self._update_controls()

    def _release(self) -> None:
        if self._source is not None:
            self._source.close()
            self._source = None
        self._photo = None
        self.canvas.delete("all")
        if self._temp_dir is not None:
            try:
                self._temp_dir.cleanup()
            except Exception:
                pass
            self._temp_dir = None

    def destroy(self) -> None:  # type: ignore[override]
        self._release()
        super().destroy()

    # ------------------------------------------------------------------ #
    # Office → PDF
    # ------------------------------------------------------------------ #

    def _convert_and_show(self) -> None:
        if self._converting or self._path is None:
            return
        source_path = self._path
        self._converting = True
        self.action_button.configure(state="disabled", text="Çevriliyor…")
        self._status(f"{source_path.name} PDF'e çevriliyor (LibreOffice)…")

        def worker() -> None:
            try:
                temp = tempfile.TemporaryDirectory(prefix="markdify-")
                produced = convert_to_pdf(source_path, Path(temp.name))
                self.after(0, lambda: self._conversion_done(source_path, temp, produced))
            except Exception as exc:
                logger.warning("LibreOffice önizleme dönüşümü başarısız: %s", exc)
                self.after(0, lambda: self._conversion_failed(str(exc)))

        threading.Thread(target=worker, daemon=True, name="preview-convert").start()

    def _conversion_done(self, source_path: Path, temp, produced: Path) -> None:
        self._converting = False
        # Kullanıcı bu arada başka dosyaya geçtiyse sonucu yok say.
        if self._path != source_path:
            temp.cleanup()
            return
        self._temp_dir = temp
        self._load(produced)
        self._status(f"{source_path.name} önizleme için PDF'e çevrildi.")

    def _conversion_failed(self, error: str) -> None:
        self._converting = False
        self.action_button.configure(state="normal", text="PDF'e çevir ve göster")
        self._show_message(
            f"PDF'e çevrilemedi:\n{error}",
            action=("Yeniden dene", self._convert_and_show),
        )

    # ------------------------------------------------------------------ #
    # Gezinme ve yakınlaştırma
    # ------------------------------------------------------------------ #

    def previous_page(self) -> None:
        if self._source and self._page > 0:
            self._page -= 1
            self._render()
            self._update_controls()

    def next_page(self) -> None:
        if self._source and self._page < self._source.page_count - 1:
            self._page += 1
            self._render()
            self._update_controls()

    def zoom_in(self) -> None:
        self._set_scale(self._scale * 1.25)

    def zoom_out(self) -> None:
        self._set_scale(self._scale / 1.25)

    def fit_to_width(self) -> None:
        self._fit_width = True
        self._render()
        self._update_controls()

    def _set_scale(self, scale: float) -> None:
        if not self._source:
            return
        self._fit_width = False
        self._scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        self._render()
        self._update_controls()

    # ------------------------------------------------------------------ #
    # Olaylar
    # ------------------------------------------------------------------ #

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_shift_wheel(self, event) -> None:
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_ctrl_wheel(self, event) -> str:
        self.zoom_in() if event.delta > 0 else self.zoom_out()
        return "break"

    def _on_canvas_resize(self, _event=None) -> None:
        """Genişlik değişince “sığdır” kipinde yeniden çiz (gecikmeli)."""
        if not self._source or not self._fit_width:
            return
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(220, self._rerender_if_needed)

    def _rerender_if_needed(self) -> None:
        self._resize_job = None
        width = self.canvas.winfo_width()
        if abs(width - self._last_width) >= 8:
            self._render()
            self._update_controls()

    # ------------------------------------------------------------------ #
    # Çizim
    # ------------------------------------------------------------------ #

    def _effective_scale(self) -> float:
        assert self._source is not None
        if not self._fit_width:
            return self._scale

        canvas_width = max(self.canvas.winfo_width(), 1)
        page_width = self._source.page_size(self._page)[0] or 1
        scale = (canvas_width - 24) / page_width
        return max(MIN_SCALE, min(MAX_SCALE, scale))

    def _render(self) -> None:
        if self._source is None:
            return

        self._last_width = self.canvas.winfo_width()
        scale = self._effective_scale()

        # Bellek koruması: çok büyük çıktıyı ölçeği düşürerek sınırla.
        page_w, page_h = self._source.page_size(self._page)
        if page_w * page_h * scale * scale > MAX_PIXELS:
            scale = (MAX_PIXELS / max(page_w * page_h, 1)) ** 0.5
        self._scale = scale

        try:
            image = self._source.render(self._page, scale)
        except Exception as exc:
            logger.warning("Sayfa çizilemedi (%s, s.%d): %s", self._path, self._page + 1, exc)
            self._show_message(f"Sayfa görüntülenemedi:\n{exc}")
            return

        self._photo = ImageTk.PhotoImage(image)  # referans tutulmalı, yoksa boş görünür
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self.canvas.configure(scrollregion=(0, 0, image.width, image.height))

        # Sayfa dar kaldıysa yatayda ortala.
        canvas_width = self.canvas.winfo_width()
        if image.width < canvas_width:
            offset = (canvas_width - image.width) // 2
            self.canvas.delete("all")
            self.canvas.create_image(offset, 0, anchor="nw", image=self._photo)
            self.canvas.configure(scrollregion=(0, 0, canvas_width, image.height))

    # ------------------------------------------------------------------ #
    # Mesaj / denetimler
    # ------------------------------------------------------------------ #

    def _show_message(self, text: str, action: tuple[str, object] | None = None) -> None:
        self.canvas.delete("all")
        self._photo = None
        self.message.configure(text=text)
        self.message.place(relx=0.5, rely=0.44, anchor="center")
        if action:
            label, command = action
            self.action_button.configure(text=label, command=command, state="normal")
            self.action_button.place(relx=0.5, rely=0.58, anchor="center")
        else:
            self.action_button.place_forget()

    def _hide_message(self) -> None:
        self.message.place_forget()
        self.action_button.place_forget()

    def _update_controls(self) -> None:
        if self._source is None:
            self.page_label.configure(text="—")
            self.zoom_label.configure(text="")
            self.prev_button.configure(state="disabled")
            self.next_button.configure(state="disabled")
            return

        total = self._source.page_count
        self.page_label.configure(text=f"{self._page + 1} / {total}")
        self.prev_button.configure(state="normal" if self._page > 0 else "disabled")
        self.next_button.configure(state="normal" if self._page < total - 1 else "disabled")
        self.zoom_label.configure(
            text=f"%{round(self._scale * 100)}" + (" · sığdır" if self._fit_width else "")
        )

    def _status(self, text: str) -> None:
        if self._on_status:
            self._on_status(text)
