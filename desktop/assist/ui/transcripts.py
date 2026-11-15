"""Transcript browser for the current authenticated user."""

import httpx
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ..auth import storage
from ..config import BACKEND_URL


class TranscriptsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assist - My transcripts")
        self.setMinimumSize(820, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)
        title = QLabel("My meeting transcripts")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)
        hint = QLabel(
            "Transcripts are saved when you finish a meeting with the app running. "
            "Click a session to view it."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        split = QHBoxLayout()
        left = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self._on_select)
        left.addWidget(self.list_widget, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._load_list)
        left.addWidget(refresh)
        split.addLayout(left, 1)

        right = QVBoxLayout()
        self.viewer = QTextEdit()
        self.viewer.setReadOnly(True)
        self.viewer.setPlaceholderText("Select a session to view its transcript.")
        right.addWidget(self.viewer, 1)
        split.addLayout(right, 2)
        root.addLayout(split, 1)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        root.addWidget(close)

        self._sessions = []
        self._load_list()

    def _load_list(self):
        token = storage.load().get("token")
        if not token:
            self.viewer.setPlainText("Not authenticated.")
            return
        try:
            response = httpx.get(
                f"{BACKEND_URL}/transcripts",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
            response.raise_for_status()
            self._sessions = response.json() or []
        except (httpx.HTTPError, ValueError) as exc:
            self.viewer.setPlainText(f"Failed to load transcripts: {exc}")
            return

        self.list_widget.clear()
        if not self._sessions:
            self.viewer.setPlainText(
                "No transcripts yet.\n\n"
                "Transcripts are created when you close a meeting session."
            )
            return
        for session in self._sessions:
            started = (session.get("session_started", "") or "")[:16].replace(
                "T", " "
            )
            count = session.get("segment_count", 0)
            item = QListWidgetItem(f"{started} - {count} segments")
            item.setData(Qt.UserRole, session.get("transcript_id"))
            self.list_widget.addItem(item)

    def _on_select(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        transcript_id = item.data(Qt.UserRole)
        token = storage.load().get("token")
        if not transcript_id or not token:
            return
        self.viewer.setPlainText("Loading...")
        try:
            response = httpx.get(
                f"{BACKEND_URL}/transcripts/{transcript_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
            response.raise_for_status()
            transcript = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            self.viewer.setPlainText(f"Failed to load transcript: {exc}")
            return

        segments = transcript.get("segments", []) or []
        lines = [
            f"Session: {transcript.get('session_started', '?')}",
            f"Ended:   {transcript.get('session_ended', '?')}",
            f"Segments: {len(segments)}",
            "-" * 40,
            "",
        ]
        for segment in segments:
            seconds = int(segment.get("t", 0))
            lines.append(
                f"[{seconds // 60:02d}:{seconds % 60:02d}] "
                f"{segment.get('text', '')}"
            )
        self.viewer.setPlainText("\n".join(lines))
