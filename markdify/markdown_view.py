"""Markdown'ı biçimli gösteren salt-okunur görüntüleyici bileşeni.

Dış bağımlılık kullanmaz: markdown satır satır ayrıştırılır ve Tk metin
etiketleriyle (tag) biçimlendirilir. Tablolar tek aralıklı (monospace) yazı tipiyle
kutu çizgileri kullanılarak hizalanır; sütun genişlikleri pencerenin o anki
genişliğine göre hesaplanır ve pencere yeniden boyutlandırılınca güncellenir.

``CTkTextbox`` etiketlerde ``font`` seçeneğini yasakladığı için (ölçekleme uyumu),
burada doğrudan ``tkinter.Text`` kullanılıp CTk teması elle uygulanır.
"""

from __future__ import annotations

import re
import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont

import customtkinter as ctk

MONO_FAMILY = "Consolas"
BODY_FAMILY = "Segoe UI"

# Satır içi biçimlendirme. Sıralama önemlidir: önce uzun işaretçiler denenir.
_INLINE_PATTERN = re.compile(
    r"(?P<code>`[^`\n]+`)"
    r"|(?P<bolditalic>\*\*\*[^\s*][^*]*?\*\*\*)"
    r"|(?P<bold>\*\*[^\s*][^*]*?\*\*|__[^\s_][^_]*?__)"
    r"|(?P<italic>\*[^\s*][^*]*?\*|_[^\s_][^_]*?_)"
    r"|(?P<strike>~~[^~]+?~~)"
    r"|(?P<link>\[[^\]]*\]\([^)]*\))"
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_HR_RE = re.compile(r"^\s*([-*_])\s*(\1\s*){2,}$")
_ULIST_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OLIST_RE = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)(.*)$")
_IMAGE_COMMENT_RE = re.compile(r"^\s*<!--\s*image\s*-->\s*$", re.IGNORECASE)
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")

MIN_COLUMN_WIDTH = 5
MAX_TABLE_WIDTH = 200

# Bir hücrenin önizlemede kaplayacağı en fazla satır. PDF'lerden çıkarılan
# içindekiler tabloları boşluksuz uzun nokta dizileri ("......") içerir; bunlar
# sarıldığında satır yüksekliği patlar ve tablo okunamaz hâle gelir. Kesilen
# hücrenin sonuna "…" konur — kısaltma yalnızca GÖRÜNÜMÜ etkiler, kaydedilen
# ya da düzenlenen metni değil.
MAX_CELL_LINES = 6


def pick_color(color) -> str:
    """CTk'nin ``[açık, koyu]`` renk çiftinden geçerli temaya uyanı seçer."""
    if isinstance(color, (list, tuple)):
        return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]
    return color


@dataclass
class _Table:
    rows: list[list[str]]
    alignments: list[str]
    has_header: bool


# --------------------------------------------------------------------------- #
# Görüntüleyici bileşen
# --------------------------------------------------------------------------- #

class MarkdownView(ctk.CTkFrame):
    """Markdown'ı biçimli gösteren, salt-okunur, kaydırılabilir görünüm."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.text = tk.Text(
            self, wrap="word", borderwidth=0, highlightthickness=0,
            padx=16, pady=12, spacing1=1, spacing2=1, cursor="arrow",
        )
        self.text.grid(row=0, column=0, sticky="nsew", padx=(2, 0), pady=2)

        self.scrollbar = ctk.CTkScrollbar(self, command=self.text.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 2), pady=2)
        self.text.configure(yscrollcommand=self.scrollbar.set)

        self._renderer = MarkdownRenderer(self.text)
        self._source = ""
        self._plain = False
        self._resize_job: str | None = None
        self._last_columns = 0

        self.apply_theme()
        self.text.bind("<Configure>", self._on_resize)
        # Salt okunur ama seçilebilir/kopyalanabilir olsun.
        self.text.bind("<Key>", self._block_typing)

    # ------------------------------------------------------------------ #

    @staticmethod
    def _block_typing(event):
        allowed = {"c", "C", "a", "A"}  # Ctrl+C / Ctrl+A
        if event.state & 0x4 and event.keysym in allowed:
            return None
        if event.keysym in ("Up", "Down", "Left", "Right", "Prior", "Next", "Home", "End"):
            return None
        return "break"

    def apply_theme(self) -> None:
        """CTk temasını alttaki Tk metin bileşenine uygular."""
        theme = ctk.ThemeManager.theme["CTkTextbox"]
        self.text.configure(
            background=pick_color(theme["fg_color"]),
            foreground=pick_color(theme["text_color"]),
            insertbackground=pick_color(theme["text_color"]),
            selectbackground=pick_color(["#3a7ebf", "#1f6aa5"]),
            selectforeground="white",
        )
        self.configure(fg_color=theme["fg_color"])
        self._renderer.configure_tags()

    def _on_resize(self, _event=None) -> None:
        """Genişlik değişince tabloları yeniden hizalamak için gecikmeli çizim."""
        if self._plain or not self._source:
            return
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(250, self._rerender_if_needed)

    def _rerender_if_needed(self) -> None:
        self._resize_job = None
        columns = self._renderer.available_columns()
        # Yalnızca anlamlı bir değişimde yeniden çiz.
        if abs(columns - self._last_columns) >= 2:
            self._paint()

    # ------------------------------------------------------------------ #

    def show_markdown(self, source: str) -> None:
        self._source, self._plain = source, False
        self._paint()

    def show_plain(self, source: str) -> None:
        self._source, self._plain = source, True
        self._paint()

    def clear(self) -> None:
        self._source = ""
        self._paint()

    def _paint(self) -> None:
        scroll_top = self.text.yview()[0]
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        try:
            if self._plain:
                self.text.insert("1.0", self._source, "codeblock")
            else:
                self._last_columns = self._renderer.available_columns()
                for chunk, tags in self._renderer.blocks(self._source, self._last_columns):
                    self.text.insert("end", chunk, tags)
        finally:
            self.text.configure(state="disabled")
        self.text.yview_moveto(scroll_top)


# --------------------------------------------------------------------------- #
# Ayrıştırıcı / biçimlendirici
# --------------------------------------------------------------------------- #

class MarkdownRenderer:
    """Markdown'ı ``tkinter.Text`` etiketlerine dönüştürür."""

    def __init__(self, text_widget: tk.Text) -> None:
        self.text = text_widget
        self._fonts: dict[str, tkfont.Font] = {}

    # ------------------------------------------------------------------ #

    def _scaling(self) -> float:
        try:
            from customtkinter.windows.widgets.scaling import ScalingTracker

            return ScalingTracker.get_widget_scaling(self.text)
        except Exception:
            return 1.0

    def _font(self, key: str, family: str, size: int, **kwargs) -> tkfont.Font:
        # Tk yazı tipleri referans tutulmazsa çöpe atılır; sözlükte saklıyoruz.
        if key not in self._fonts:
            scaled = max(7, int(round(size * self._scaling())))
            self._fonts[key] = tkfont.Font(family=family, size=scaled, **kwargs)
        return self._fonts[key]

    def configure_tags(self) -> None:
        text = self.text
        body_fg = pick_color(ctk.ThemeManager.theme["CTkTextbox"]["text_color"])
        subtle = pick_color(["gray45", "gray60"])
        code_bg = pick_color(["#ECEFF4", "#2B2F36"])

        for level, size in {1: 21, 2: 18, 3: 16, 4: 14, 5: 13, 6: 12}.items():
            text.tag_config(
                f"h{level}",
                font=self._font(f"h{level}", BODY_FAMILY, size, weight="bold"),
                foreground=body_fg,
                spacing1=16 if level <= 2 else 11,
                spacing3=5,
            )

        text.tag_config("body", font=self._font("body", BODY_FAMILY, 12), spacing3=3)
        text.tag_config("bold", font=self._font("bold", BODY_FAMILY, 12, weight="bold"))
        text.tag_config("italic", font=self._font("it", BODY_FAMILY, 12, slant="italic"))
        text.tag_config(
            "bolditalic", font=self._font("bi", BODY_FAMILY, 12, weight="bold", slant="italic")
        )
        text.tag_config("strike", overstrike=True)
        text.tag_config(
            "code", font=self._font("code", MONO_FAMILY, 11), background=code_bg
        )
        text.tag_config(
            "codeblock",
            font=self._font("codeblock", MONO_FAMILY, 11),
            background=code_bg, lmargin1=26, lmargin2=26, rmargin=16,
            spacing1=2, spacing3=2,
        )
        text.tag_config(
            "link", foreground=pick_color(["#1A6FC4", "#5AA9F0"]), underline=True
        )
        text.tag_config(
            "quote",
            font=self._font("quote", BODY_FAMILY, 12, slant="italic"),
            foreground=subtle, lmargin1=26, lmargin2=26,
        )
        text.tag_config(
            "image",
            font=self._font("image", BODY_FAMILY, 11, slant="italic"),
            foreground=subtle,
        )
        text.tag_config("hr", foreground=pick_color(["gray70", "gray40"]), spacing1=6, spacing3=6)

        # Tablo satırlarında satır arası boşluk SIFIR olmalı: aksi hâlde dikey
        # kenarlık karakterleri (│) birbirine değmez ve kenarlık kesik görünür.
        table_spacing = {"spacing1": 0, "spacing2": 0, "spacing3": 0}
        text.tag_config(
            "table", font=self._font("table", MONO_FAMILY, 11),
            lmargin1=18, lmargin2=18, **table_spacing,
        )
        text.tag_config(
            "table_header",
            font=self._font("table_h", MONO_FAMILY, 11, weight="bold"),
            lmargin1=18, lmargin2=18, **table_spacing,
        )
        text.tag_config(
            "table_rule",
            font=self._font("table_r", MONO_FAMILY, 11),
            foreground=subtle, lmargin1=18, lmargin2=18, **table_spacing,
        )

        for level in range(4):
            text.tag_config(
                f"list{level}",
                font=self._font("body", BODY_FAMILY, 12),
                lmargin1=20 + level * 22,
                lmargin2=34 + level * 22,
                spacing3=2,
            )

    # ------------------------------------------------------------------ #

    def available_columns(self) -> int:
        """Metin alanına sığan yaklaşık tek aralıklı karakter sayısı."""
        try:
            width_px = self.text.winfo_width()
            char_px = self._font("table", MONO_FAMILY, 11).measure("0") or 8
            usable = max(width_px - 60, 200)
            return max(24, min(MAX_TABLE_WIDTH, usable // char_px))
        except Exception:
            return 90

    # ------------------------------------------------------------------ #
    # Blok ayrıştırma
    # ------------------------------------------------------------------ #

    def blocks(self, text: str, columns: int):
        """(metin parçası, etiketler) çiftleri üretir."""
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        index, total = 0, len(lines)

        while index < total:
            line = lines[index]

            fence = _FENCE_RE.match(line)
            if fence:
                marker = fence.group(1)
                index += 1
                body: list[str] = []
                while index < total and not lines[index].lstrip().startswith(marker):
                    body.append(lines[index])
                    index += 1
                index += 1  # kapanış çizgisi
                yield "\n".join(body) + "\n\n", ("codeblock",)
                continue

            if self._looks_like_table(lines, index):
                table, consumed = self._parse_table(lines, index)
                index += consumed
                yield from self._render_table(table, columns)
                continue

            if _IMAGE_COMMENT_RE.match(line):
                yield "🖼  [görsel]\n", ("image",)
                index += 1
                continue

            if _HR_RE.match(line):
                yield "─" * max(20, min(columns, 80)) + "\n", ("hr",)
                index += 1
                continue

            heading = _HEADING_RE.match(line)
            if heading:
                level = len(heading.group(1))
                yield from self._inline(heading.group(2).strip(), f"h{level}")
                yield "\n", (f"h{level}",)
                index += 1
                continue

            quote = _QUOTE_RE.match(line)
            if quote:
                yield from self._inline(quote.group(1), "quote")
                yield "\n", ("quote",)
                index += 1
                continue

            ordered = _OLIST_RE.match(line)
            unordered = _ULIST_RE.match(line)
            if ordered or unordered:
                match = ordered or unordered
                indent = len(match.group(1).replace("\t", "    "))
                level = min(indent // 2, 3)
                if ordered:
                    marker, content = f"{ordered.group(2)}. ", ordered.group(3)
                else:
                    marker = ("• ", "◦ ", "▪ ", "· ")[level]
                    content = unordered.group(2)
                yield marker, (f"list{level}",)
                yield from self._inline(content, f"list{level}")
                yield "\n", (f"list{level}",)
                index += 1
                continue

            if not line.strip():
                yield "\n", ("body",)
                index += 1
                continue

            yield from self._inline(line, "body")
            yield "\n", ("body",)
            index += 1

    # ------------------------------------------------------------------ #
    # Satır içi biçimlendirme
    # ------------------------------------------------------------------ #

    def _inline(self, text: str, base_tag: str):
        position = 0
        for match in _INLINE_PATTERN.finditer(text):
            if match.start() > position:
                yield text[position:match.start()], (base_tag,)

            kind, raw = match.lastgroup, match.group()
            if kind == "code":
                yield raw[1:-1], (base_tag, "code")
            elif kind == "bolditalic":
                yield raw[3:-3], (base_tag, "bolditalic")
            elif kind == "bold":
                yield raw[2:-2], (base_tag, "bold")
            elif kind == "italic":
                yield raw[1:-1], (base_tag, "italic")
            elif kind == "strike":
                yield raw[2:-2], (base_tag, "strike")
            elif kind == "link":
                label, _, target = raw[1:-1].partition("](")
                yield label, (base_tag, "link")
                if target and target not in label:
                    yield f" ({target})", (base_tag, "image")
            position = match.end()

        if position < len(text):
            yield text[position:], (base_tag,)

    @staticmethod
    def strip_inline(text: str) -> str:
        """Tablo hücrelerinde hizayı bozmamak için işaretleri kaldırır."""
        def unwrap(match: re.Match) -> str:
            kind, raw = match.lastgroup, match.group()
            if kind == "code":
                return raw[1:-1]
            if kind == "bolditalic":
                return raw[3:-3]
            if kind in ("bold", "strike"):
                return raw[2:-2]
            if kind == "italic":
                return raw[1:-1]
            if kind == "link":
                return raw[1:-1].partition("](")[0]
            return raw

        return _INLINE_PATTERN.sub(unwrap, text).replace("<br>", " ").strip()

    # ------------------------------------------------------------------ #
    # Tablolar
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_table_row(line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith("|") and stripped.count("|") >= 2

    @classmethod
    def _looks_like_table(cls, lines: list[str], index: int) -> bool:
        if not cls._is_table_row(lines[index]):
            return False
        following = lines[index + 1] if index + 1 < len(lines) else ""
        return _TABLE_SEP_RE.match(following) is not None or cls._is_table_row(following)

    @classmethod
    def _split_row(cls, line: str) -> list[str]:
        stripped = line.strip()
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|") and not stripped.endswith("\\|"):
            stripped = stripped[:-1]
        parts = re.split(r"(?<!\\)\|", stripped)
        return [cls.strip_inline(p.replace("\\|", "|")) for p in parts]

    @classmethod
    def _parse_table(cls, lines: list[str], start: int) -> tuple[_Table, int]:
        rows: list[list[str]] = []
        alignments: list[str] = []
        has_header = False
        index = start

        while index < len(lines) and cls._is_table_row(lines[index]):
            if _TABLE_SEP_RE.match(lines[index]) and rows:
                has_header = True
                for cell in cls._split_row(lines[index]):
                    left, right = cell.startswith(":"), cell.endswith(":")
                    alignments.append("center" if left and right else "right" if right else "left")
                index += 1
                continue
            rows.append(cls._split_row(lines[index]))
            index += 1

        width = max((len(r) for r in rows), default=0)
        for row in rows:
            row.extend([""] * (width - len(row)))
        alignments.extend(["left"] * (width - len(alignments)))

        return _Table(rows, alignments[:width], has_header), index - start

    @staticmethod
    def _wrap_cell(text: str, width: int) -> list[str]:
        """Hücreyi sütun genişliğine göre kelime kelime sarar."""
        if not text:
            return [""]
        out: list[str] = []
        for paragraph in text.split("\n"):
            line = ""
            for word in paragraph.split():
                while len(word) > width:  # tek başına sığmayan uzun kelime
                    if line:
                        out.append(line)
                        line = ""
                    out.append(word[:width])
                    word = word[width:]
                candidate = f"{line} {word}".strip()
                if len(candidate) <= width:
                    line = candidate
                else:
                    out.append(line)
                    line = word
            out.append(line)
        return out or [""]

    @staticmethod
    def _clamp_cell(lines: list[str], width: int) -> list[str]:
        """Aşırı uzun hücreleri görünüm için kısaltır (bkz. ``MAX_CELL_LINES``)."""
        if len(lines) <= MAX_CELL_LINES:
            return lines
        kept = lines[: MAX_CELL_LINES - 1]
        kept.append("…"[:width] if width >= 1 else "")
        return kept

    def _column_widths(self, table: _Table, columns: int) -> list[int]:
        count = len(table.alignments)
        if count == 0:
            return []

        natural = [max((len(row[i]) for row in table.rows), default=0) or 1 for i in range(count)]
        overhead = count * 3 + 1  # "│ " + " " her sütun, artı kapanış "│"
        budget = max(count * MIN_COLUMN_WIDTH, columns - overhead)

        if sum(natural) <= budget:
            return natural

        widths = natural[:]
        while sum(widths) > budget:
            widest = max(range(count), key=lambda i: widths[i])
            if widths[widest] <= MIN_COLUMN_WIDTH:
                break
            widths[widest] -= 1
        return widths

    @staticmethod
    def _align(text: str, width: int, how: str) -> str:
        if how == "right":
            return text.rjust(width)
        if how == "center":
            return text.center(width)
        return text.ljust(width)

    def _render_table(self, table: _Table, columns: int):
        if not table.rows:
            return

        widths = self._column_widths(table, columns)
        if not widths:
            return

        def rule(left: str, mid: str, right: str) -> str:
            return left + mid.join("─" * (w + 2) for w in widths) + right + "\n"

        yield rule("┌", "┬", "┐"), ("table_rule",)

        for row_index, row in enumerate(table.rows):
            is_header = table.has_header and row_index == 0
            wrapped = [
                self._clamp_cell(self._wrap_cell(cell, widths[i]), widths[i])
                for i, cell in enumerate(row)
            ]
            height = max(len(w) for w in wrapped)

            for line_index in range(height):
                pieces = []
                for col, cell_lines in enumerate(wrapped):
                    content = cell_lines[line_index] if line_index < len(cell_lines) else ""
                    pieces.append(" " + self._align(content, widths[col], table.alignments[col]) + " ")
                yield "│" + "│".join(pieces) + "│\n", ("table_header" if is_header else "table",)

            if is_header:
                yield rule("├", "┼", "┤"), ("table_rule",)

        yield rule("└", "┴", "┘"), ("table_rule",)
        yield "\n", ("body",)
