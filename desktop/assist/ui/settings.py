"""Settings hub for account, transcript, support, and app information."""

import webbrowser

import httpx
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout

from ..auth import storage
from ..config import BACKEND_URL


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assist - Settings")
        self.setMinimumSize(440, 400)
        self.setStyleSheet(
            "QDialog { background: #1a1d26; color: #e6e8ee; }"
            "QLabel { color: #e6e8ee; }"
            "QPushButton { background: #6366f1; border: none; "
            "color: #fff; padding: 10px 14px; border-radius: 6px; "
            "text-align: left; font-size: 14px; }"
            "QPushButton:hover { background: #5058cc; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        title = QLabel("My account")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        hint = QLabel("Everything here talks directly to your Assist backend.")
        hint.setStyleSheet("color: #8a92a6; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addSpacing(8)

        for label, callback in (
            ("Edit my profile", self._open_profile),
            ("My meeting transcripts", self._open_transcripts),
            ("Message support on Telegram", self._open_telegram),
            ("About Assist", self._open_about),
        ):
            button = QPushButton(label)
            button.setMinimumHeight(44)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(callback)
            layout.addWidget(button)

        layout.addStretch()
        close_button = QPushButton("Close")
        close_button.setStyleSheet("background: #2a2f3a; color: #e6e8ee;")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

    def _open_profile(self):
        from .profile import ProfileDialog

        ProfileDialog(self).exec()

    def _open_transcripts(self):
        from .transcripts import TranscriptsDialog

        TranscriptsDialog(self).exec()

    def _open_telegram(self):
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
                "Your Telegram bot is not configured. Ask the admin for support.",
            )

    def _open_about(self):
        QMessageBox.about(
            self,
            "About Assist",
            "<h2>Assist v1.0</h2>"
            "<p>AI meeting assistant that shows answer suggestions on a "
            "transparent overlay during meetings.</p>"
            "<p>The overlay is hidden from screen sharing and screenshots.</p>"
            "<p>Powered by Parakeet STT + Groq LLM.</p>"
            "<p>&copy; 2026</p>",
        )
