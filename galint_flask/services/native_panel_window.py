"""Native fullscreen host for the mirror panel."""
from __future__ import annotations

import ctypes
from pathlib import Path
import sys
from typing import Sequence

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView


def choose_target_screen(screens: Sequence[object]):
    if not screens:
        return None
    primary = QGuiApplication.primaryScreen()
    for screen in screens:
        if primary is not None and screen is not primary:
            return screen
    return screens[0]


def _resolve_icon_path() -> Path | None:
    static_img_dir = Path(__file__).resolve().parents[1] / "static" / "img"
    for name in ("galint-icon.ico", "galint-icon.png"):
        candidate = static_img_dir / name
        if candidate.exists():
            return candidate
    return None


def _load_galint_icon() -> QIcon:
    icon_path = _resolve_icon_path()
    if icon_path is None:
        return QIcon()
    return QIcon(str(icon_path))


class NativeMirrorPanelWindow(QWidget):
    def __init__(self, *, url: str, title: str) -> None:
        super().__init__()
        self._target_screen = choose_target_screen(list(QGuiApplication.screens()))
        self._browser = QWebEngineView(self)
        self._close_button = QPushButton("×", self)
        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._window_icon = _load_galint_icon()

        self.setObjectName("nativeMirrorPanel")
        self.setWindowTitle(title)
        if not self._window_icon.isNull():
            self.setWindowIcon(self._window_icon)
        self.setWindowFlag(Qt.Window, True)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setStyleSheet(
            """
            QWidget#nativeMirrorPanel {
                background: #05131d;
            }
            QPushButton {
                background: rgba(5, 13, 20, 0.64);
                color: #f6fbff;
                border: 1px solid rgba(173, 216, 255, 0.18);
                border-radius: 18px;
                padding: 0;
                font-size: 20px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(123, 23, 23, 0.78);
                border-color: rgba(255, 204, 204, 0.28);
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._browser)

        settings = self._browser.settings()
        settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.ShowScrollBars, False)
        self._browser.setContextMenuPolicy(Qt.NoContextMenu)
        self._browser.loadFinished.connect(self._on_load_finished)
        self._browser.setUrl(QUrl(url))

        self._close_button.clicked.connect(self.close)
        self._close_button.setToolTip("Fechar painel")
        self._close_button.setCursor(Qt.PointingHandCursor)
        self._close_button.raise_()
        self._escape_shortcut.activated.connect(self.close)

    def open_fullscreen(self) -> None:
        target_screen = self._target_screen or self.screen() or QGuiApplication.primaryScreen()
        window_handle = self.windowHandle()
        if target_screen is not None:
            if window_handle is not None:
                window_handle.setScreen(target_screen)
            self.setGeometry(target_screen.geometry())
        self.showFullScreen()
        QApplication.processEvents()
        self._promote_window()
        for delay in (120, 320, 800):
            QTimer.singleShot(delay, self._promote_window)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        width = 36
        height = 36
        self._close_button.resize(width, height)
        self._close_button.move(max(10, self.width() - width - 12), 10)
        self._close_button.raise_()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            return
        self._browser.page().runJavaScript(
            """
            document.documentElement.style.overflow = 'hidden';
            document.body.style.overflow = 'hidden';
            document.body.dataset.nativeMirror = '1';
            """
        )
        QTimer.singleShot(0, self._promote_window)

    def _promote_window(self) -> None:
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self._browser.setFocus(Qt.ActiveWindowFocusReason)
        window_handle = self.windowHandle()
        if window_handle is not None:
            window_handle.requestActivate()
        self._promote_on_windows()
        self._close_button.raise_()

    def _promote_on_windows(self) -> None:
        if not sys.platform.startswith("win"):
            return
        hwnd = int(self.winId())
        if not hwnd:
            return
        user32 = ctypes.windll.user32
        hwnd_topmost = -1
        sw_restore = 9
        swp_nosize = 0x0001
        swp_nomove = 0x0002
        swp_showwindow = 0x0040
        try:
            user32.ShowWindow(hwnd, sw_restore)
            user32.BringWindowToTop(hwnd)
            user32.SetWindowPos(hwnd, hwnd_topmost, 0, 0, 0, 0, swp_nosize | swp_nomove | swp_showwindow)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        except Exception:
            return


def run_native_panel(*, url: str, title: str) -> int:
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    _configure_windows_app_identity()
    app = QApplication.instance()
    if app is None:
        app = QApplication([sys.argv[0]])
    app.setApplicationName("GALINT")
    app.setApplicationDisplayName(title)
    icon = _load_galint_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    app.setQuitOnLastWindowClosed(True)

    window = NativeMirrorPanelWindow(url=url, title=title)
    window.open_fullscreen()
    return app.exec()


def _configure_windows_app_identity() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GALINT.PainelVisualizacao")
    except Exception:
        return