"""Tabbed settings dialog for profile, transcripts, and support."""

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assist - Settings")
        self.setMinimumSize(720, 560)

        root = QVBoxLayout(self)
        header = QLabel("Settings")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(header)

        tabs = QTabWidget()
        tabs.addTab(
            self._make_tab(
                "Your profile shapes every answer on the overlay. "
                "Update it whenever you change roles or targets.",
                "Open profile editor",
                self._open_profile,
            ),
            "Profile",
        )
        tabs.addTab(
            self._make_tab(
                "Meeting transcripts are saved locally and synced to the backend.",
                "Open transcript browser",
                self._open_transcripts,
            ),
            "Transcripts",
        )
        tabs.addTab(
            self._make_tab(
                "Message the admin directly on Telegram. Typical response: same day.",
                "Open Telegram chat",
                self._open_telegram,
            ),
            "Support",
        )
        root.addWidget(tabs, 1)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        root.addWidget(close)

    def _make_tab(self, hint_text, button_text, callback):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        hint = QLabel(hint_text)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8a92a6; font-size: 12px;")
        layout.addWidget(hint)
        button = QPushButton(button_text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        layout.addStretch()
        return tab

    def _open_profile(self):
        from .profile import ProfileDialog

        ProfileDialog(self).exec()

    def _open_transcripts(self):
        from .transcripts import TranscriptsDialog

        TranscriptsDialog(self).exec()

    def _open_telegram(self):
        import webbrowser

        import httpx

        from ..auth import storage
        from ..config import BACKEND_URL

        token = storage.load().get("token")
        if not token:
            QMessageBox.warning(self, "Telegram", "Not authenticated.")
            return
        try:
            response = httpx.get(
                f"{BACKEND_URL}/me/links",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            response.raise_for_status()
            url = response.json().get("telegram_bot_url")
        except (httpx.HTTPError, ValueError) as exc:
            QMessageBox.warning(self, "Telegram", f"Could not open: {exc}")
            return
        if url:
            webbrowser.open(url)
        else:
            QMessageBox.information(
                self,
                "Telegram",
                "Your bot is not configured yet. Ask the admin for support.",
            )
