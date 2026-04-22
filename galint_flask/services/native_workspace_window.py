"""Native window host for operational GALINT pages."""
from __future__ import annotations

import ctypes
from pathlib import Path
import sys

from PySide6.QtCore import QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox
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


def _default_download_dir() -> Path:
    candidate = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
    if candidate:
        return Path(candidate)
    return Path.home() / "Downloads"


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
        self._browser.page().profile().downloadRequested.connect(self._handle_download_requested)
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

    def _handle_download_requested(self, download) -> None:
        suggested_name = "download"
        for attr_name in ("downloadFileName", "suggestedFileName"):
            getter = getattr(download, attr_name, None)
            if not callable(getter):
                continue
            candidate = str(getter() or "").strip()
            if candidate:
                suggested_name = candidate
                break

        default_path = _default_download_dir() / suggested_name
        selected_path, _ = QFileDialog.getSaveFileName(self, "Salvar arquivo", str(default_path))
        if not selected_path:
            cancel = getattr(download, "cancel", None)
            if callable(cancel):
                cancel()
            return

        target_path = Path(selected_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        set_directory = getattr(download, "setDownloadDirectory", None)
        if callable(set_directory):
            set_directory(str(target_path.parent))

        set_filename = getattr(download, "setDownloadFileName", None)
        if callable(set_filename):
            set_filename(target_path.name)

        try:
            download.isFinishedChanged.connect(lambda: self._handle_download_finished(download, target_path))
        except Exception:
            pass
        download.accept()

    def _handle_download_finished(self, download, target_path: Path) -> None:
        is_finished = getattr(download, "isFinished", None)
        if callable(is_finished) and not is_finished():
            return

        state_getter = getattr(download, "state", None)
        state = state_getter() if callable(state_getter) else None
        state_enum = getattr(type(download), "DownloadState", None)
        completed_state = getattr(state_enum, "DownloadCompleted", None)
        cancelled_state = getattr(state_enum, "DownloadCancelled", None)
        interrupted_state = getattr(state_enum, "DownloadInterrupted", None)

        if completed_state is not None and state == completed_state:
            QMessageBox.information(self, "Download concluído", f"Arquivo salvo em:\n{target_path}")
            return

        if interrupted_state is not None and state == interrupted_state:
            reason_getter = getattr(download, "interruptReasonString", None)
            reason = reason_getter() if callable(reason_getter) else "Falha ao baixar o arquivo."
            QMessageBox.warning(self, "Falha no download", str(reason or "Falha ao baixar o arquivo."))
            return

        if cancelled_state is not None and state == cancelled_state:
            return

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