"""Qt application entry point."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import __app_name__, __version__
from ..config import load_config
from ..i18n import set_language
from .main_window import MainWindow

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    config = load_config()
    set_language(config.language)

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("niwciu")

    icon_path = Path(__file__).resolve().parent / "resources" / "icons" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow(config=config)

    screen = app.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        w = max(600, min(int(avail.width() * 0.45), 960))
        window.setMinimumWidth(w)
        window.adjustSize()
        h = window.sizeHint().height()
        x = avail.x() + (avail.width() - w) // 2
        y = avail.y() + (avail.height() - h) // 2
        window.move(x, y)
    else:
        window.adjustSize()

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
