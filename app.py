"""Markdify — giriş noktası.

Kullanım:
    pythonw app.py        # konsolsuz (normal kullanım)
    python  app.py -v     # ayrıntılı günlük ile
"""

from __future__ import annotations

import sys
import traceback


def main() -> int:
    from markdify.config import configure_runtime_env, setup_logging, logger

    setup_logging(verbose="-v" in sys.argv or "--verbose" in sys.argv)
    configure_runtime_env()

    try:
        from markdify.ui import MainWindow
    except ImportError as exc:
        # customtkinter yoksa arayüz hiç açılamaz; konsola anlamlı mesaj bırak.
        print(
            f"Arayüz kütüphaneleri yüklenemedi: {exc}\n"
            "Çözüm: pip install -r requirements.txt",
            file=sys.stderr,
        )
        logger.exception("Arayüz içe aktarılamadı")
        return 1

    try:
        MainWindow().mainloop()
    except Exception:
        logger.exception("Uygulama beklenmedik şekilde sonlandı")
        # pythonw altında konsol yoktur: hatayı kullanıcıya pencereyle göster.
        try:
            from tkinter import messagebox

            messagebox.showerror(
                "Markdify",
                "Uygulama beklenmedik bir hatayla kapandı.\n\n"
                f"{traceback.format_exc(limit=3)}\n"
                "Ayrıntılar logs/markdify.log dosyasında.",
            )
        except Exception:
            pass
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
