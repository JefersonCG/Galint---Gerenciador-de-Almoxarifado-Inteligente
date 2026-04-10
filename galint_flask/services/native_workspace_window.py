"""Native window host for operational GALINT pages."""
from __future__ import annotations

import ctypes
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView


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


def _normalize_slot(slot: int | str | None) -> int:
    try:
        value = int(slot or 2)
    except (TypeError, ValueError):
        value = 2
    return value if value in (2, 3) else 2


class NativeWorkspaceWindow(QMainWindow):
    def __init__(self, *, url: str, title: str, slot: int = 2) -> None:
        super().__init__()
        self._slot = _normalize_slot(slot)
        self._browser = QWebEngineView(self)
        self._window_icon = _load_galint_icon()

        self.setObjectName("nativeWorkspaceWindow")
        self.setWindowTitle(title)
        if not self._window_icon.isNull():
            self.setWindowIcon(self._window_icon)
        self.setWindowFlag(Qt.Window, True)
        self.setMinimumSize(1080, 720)
        self.setCentralWidget(self._browser)
        self.setStyleSheet(
            """
            QMainWindow#nativeWorkspaceWindow {
                background: #08111f;
            }
            """
        )

        settings = self._browser.settings()
        settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        self._browser.loadFinished.connect(self._on_load_finished)
        self._browser.setUrl(QUrl(url))

    def open_window(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = max(1180, min(1560, round(available.width() * 0.78)))
            height = max(760, min(980, round(available.height() * 0.86)))
            positions = {
                2: {
                    "left": available.x() + max(24, round((available.width() - width) * 0.18)),
                    "top": available.y() + 42,
                },
                3: {
                    "left": available.x() + max(72, round((available.width() - width) * 0.26)),
                    "top": available.y() + 88,
                },
            }
            target = positions.get(self._slot, positions[2])
            self.setGeometry(target["left"], target["top"], width, height)

        self.show()
        QApplication.processEvents()
        self._promote_window()
        for delay in (120, 260):
            QTimer.singleShot(delay, self._promote_window)

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            return
        self._browser.page().runJavaScript(
            """
            (() => {
                try {
                    const targetUrl = new URL(window.location.href);
                    if (targetUrl.searchParams.has('workspace_token')) {
                        targetUrl.searchParams.delete('workspace_token');
                        history.replaceState({}, document.title, targetUrl.pathname + targetUrl.search + targetUrl.hash);
                    }
                    document.body.dataset.nativeWorkspace = '1';
                } catch (error) {
                }
            })();
            """
        )

    def _promote_window(self) -> None:
        self.raise_()
        self.activateWindow()
        self._browser.setFocus(Qt.ActiveWindowFocusReason)
        window_handle = self.windowHandle()
        if window_handle is not None:
            window_handle.requestActivate()
        self._promote_on_windows()

    def _promote_on_windows(self) -> None:
        if not sys.platform.startswith("win"):
            return
        hwnd = int(self.winId())
        if not hwnd:
            return
        user32 = ctypes.windll.user32
        sw_restore = 9
        try:
            user32.ShowWindow(hwnd, sw_restore)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            return


def run_native_workspace_window(*, url: str, title: str, slot: int = 2) -> int:
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

    window = NativeWorkspaceWindow(url=url, title=title, slot=slot)
    window.open_window()
    return app.exec()


def _configure_windows_app_identity() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GALINT.WorkspaceWindow")
    except Exception:
        return