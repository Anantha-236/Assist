"""Unified settings dialog with inline profile, transcript, and support panels."""

import os
import webbrowser

import httpx
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..auth import storage
from ..config import BACKEND_URL


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assist - Settings")
        self.setMinimumSize(920, 640)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint
        )
        self.setStyleSheet(
            "QDialog { background: #1a1d26; color: #e6e8ee; }"
            "QLabel { color: #e6e8ee; }"
            "QLineEdit, QComboBox, QTextEdit { background: #0a0c12; "
            "border: 1px solid #2a2f3a; border-radius: 6px; color: #e6e8ee; "
            "padding: 8px; font-size: 13px; }"
            "QListWidget { background: #0a0c12; border: 1px solid #2a2f3a; "
            "border-radius: 6px; color: #e6e8ee; padding: 4px; }"
            "QListWidget::item { padding: 8px; border-radius: 4px; }"
            "QListWidget::item:selected { background: #6366f1; color: #fff; }"
            "QPushButton { background: #6366f1; border: none; color: #fff; "
            "padding: 8px 14px; border-radius: 6px; font-size: 13px; }"
            "QPushButton:hover { background: #5058cc; }"
            "QPushButton:disabled { background: #2a2f3a; color: #8a92a6; }"
            "QPushButton#nav { background: transparent; color: #8a92a6; "
            "text-align: left; padding: 12px 16px; border-radius: 6px; }"
            "QPushButton#nav:checked { background: #6366f1; color: #fff; }"
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        sidebar = QVBoxLayout()
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 18px; font-weight: 600; padding: 4px;")
        sidebar.addWidget(title)
        self.nav_buttons = []
        for index, name in enumerate(("Profile", "Transcripts", "Support")):
            button = QPushButton(name)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda checked, idx=index: self._switch(idx)
            )
            sidebar.addWidget(button)
            self.nav_buttons.append(button)
        sidebar.addStretch()
        close = QPushButton("Close")
        close.setStyleSheet("background: #2a2f3a; color: #e6e8ee;")
        close.clicked.connect(self.accept)
        sidebar.addWidget(close)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_profile_panel())
        self.stack.addWidget(self._build_transcripts_panel())
        self.stack.addWidget(self._build_support_panel())
        root.addLayout(sidebar)
        root.addWidget(self.stack, 1)

    def _switch(self, index):
        for current, button in enumerate(self.nav_buttons):
            button.setChecked(current == index)
        self.stack.setCurrentIndex(index)

    def _build_profile_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        header = QLabel("Your profile")
        header.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(header)
        hint = QLabel(
            "Upload a resume to fill these fields automatically, or edit them manually."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8a92a6; font-size: 12px;")
        layout.addWidget(hint)

        upload_row = QHBoxLayout()
        self.upload_btn = QPushButton("Upload resume (PDF / MD / TXT)")
        self.upload_btn.clicked.connect(self._upload_resume)
        upload_row.addWidget(self.upload_btn)
        self.upload_status = QLabel("")
        self.upload_status.setStyleSheet("color: #8a92a6; font-size: 12px;")
        self.upload_status.setWordWrap(True)
        upload_row.addWidget(self.upload_status, 1)
        layout.addLayout(upload_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setSpacing(10)
        self.profile_fields = {}
        for key, label in (
            ("role", "Current role"),
            ("experience", "Years of experience"),
            ("skills", "Core skills"),
            ("company", "Current company"),
            ("target_role", "Target role"),
            ("target_company", "Target company"),
            ("target_salary", "Target salary"),
            ("notice_period", "Notice period"),
        ):
            from PySide6.QtWidgets import QLineEdit

            field = QLineEdit()
            self.profile_fields[key] = field
            form.addRow(label, field)
        self.answer_style = QComboBox()
        self.answer_style.addItems(["", "star", "concise", "detailed"])
        form.addRow("Answer style", self.answer_style)
        scroll.setWidget(form_widget)
        layout.addWidget(scroll, 1)

        self.profile_status = QLabel("")
        self.profile_status.setStyleSheet("color: #8a92a6; font-size: 12px;")
        layout.addWidget(self.profile_status)
        save = QPushButton("Save profile")
        save.clicked.connect(self._save_profile)
        layout.addWidget(save)
        self._load_profile()
        return panel

    def _load_profile(self):
        token = storage.load().get("token")
        if not token:
            self.profile_status.setText("Not authenticated.")
            return
        try:
            response = httpx.get(
                f"{BACKEND_URL}/me/profile",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
            response.raise_for_status()
            profile = response.json() or {}
            for key, field in self.profile_fields.items():
                field.setText(profile.get(key) or "")
            self.answer_style.setCurrentText(
                (profile.get("answer_style") or "").lower()
            )
            self.profile_status.setText("Loaded.")
        except (httpx.HTTPError, ValueError) as exc:
            self.profile_status.setText(f"Load error: {type(exc).__name__}")

    def _save_profile(self):
        token = storage.load().get("token")
        if not token:
            self.profile_status.setText("Not authenticated.")
            return
        payload = {
            key: field.text().strip()
            for key, field in self.profile_fields.items()
        }
        payload["answer_style"] = self.answer_style.currentText()
        print(f"[profile] POST /me/profile payload: {payload}")
        try:
            response = httpx.post(
                f"{BACKEND_URL}/me/profile",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
            print(f"[profile] HTTP {response.status_code}: {response.text[:200]}")
            if response.status_code == 200:
                self.profile_status.setText("Saved.")
            elif response.status_code == 401:
                self.profile_status.setText(
                    "Session expired. Delete %APPDATA%\\Assist\\config.json "
                    "and re-activate."
                )
            else:
                self.profile_status.setText(
                    f"Save failed: HTTP {response.status_code}"
                )
        except httpx.HTTPError as exc:
            print(f"[profile] exception: {type(exc).__name__}: {exc}")
            self.profile_status.setText(f"Save error: {type(exc).__name__}")

    def _upload_resume(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Upload resume",
            "",
            "Resume files (*.pdf *.md *.txt);;All files (*.*)",
        )
        if not path:
            return
        token = storage.load().get("token")
        if not token:
            self.upload_status.setText("Not authenticated.")
            return

        self.upload_btn.setEnabled(False)
        self.upload_btn.setText("Parsing resume...")
        try:
            mime = "application/pdf" if path.lower().endswith(".pdf") else "text/plain"
            with open(path, "rb") as resume:
                response = httpx.post(
                    f"{BACKEND_URL}/me/resume",
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": (os.path.basename(path), resume, mime)},
                    timeout=90.0,
                )
            response.raise_for_status()
            parsed = (response.json() or {}).get("parsed", {})
            for key, field in self.profile_fields.items():
                if parsed.get(key):
                    field.setText(parsed[key])
            self.upload_status.setText("Resume parsed. Review and save the fields.")
        except (OSError, httpx.HTTPError, ValueError) as exc:
            self.upload_status.setText(f"Upload error: {type(exc).__name__}")
        finally:
            self.upload_btn.setEnabled(True)
            self.upload_btn.setText("Upload resume (PDF / MD / TXT)")

    def _build_transcripts_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        header = QLabel("Meeting transcripts")
        header.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(header)
        hint = QLabel("Saved after each meeting session. Click a session to view it.")
        hint.setStyleSheet("color: #8a92a6; font-size: 12px;")
        layout.addWidget(hint)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.transcript_list = QListWidget()
        self.transcript_list.itemSelectionChanged.connect(
            self._on_transcript_select
        )
        left_layout.addWidget(self.transcript_list, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._load_transcripts)
        left_layout.addWidget(refresh)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.transcript_viewer = QTextEdit()
        self.transcript_viewer.setReadOnly(True)
        right_layout.addWidget(self.transcript_viewer, 1)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        self._transcripts = []
        self._load_transcripts()
        return panel

    def _load_transcripts(self):
        token = storage.load().get("token")
        if not token:
            self.transcript_viewer.setPlainText("Not authenticated.")
            return
        try:
            response = httpx.get(
                f"{BACKEND_URL}/transcripts",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
            response.raise_for_status()
            self._transcripts = response.json() or []
        except (httpx.HTTPError, ValueError) as exc:
            self.transcript_viewer.setPlainText(
                f"Failed to load transcripts: {type(exc).__name__}"
            )
            return
        self.transcript_list.clear()
        for session in self._transcripts:
            started = (session.get("session_started") or "")[:16].replace("T", " ")
            item = QListWidgetItem(
                f"{started} - {session.get('segment_count', 0)} segments"
            )
            item.setData(Qt.UserRole, session.get("transcript_id"))
            self.transcript_list.addItem(item)
        if not self._transcripts:
            self.transcript_viewer.setPlainText("No transcripts yet.")

    def _on_transcript_select(self):
        item = self.transcript_list.currentItem()
        token = storage.load().get("token")
        transcript_id = item.data(Qt.UserRole) if item else None
        if not token or not transcript_id:
            return
        try:
            response = httpx.get(
                f"{BACKEND_URL}/transcripts/{transcript_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
            response.raise_for_status()
            transcript = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            self.transcript_viewer.setPlainText(
                f"Failed to load transcript: {type(exc).__name__}"
            )
            return
        lines = [
            f"Session: {transcript.get('session_started', '?')}",
            f"Ended:   {transcript.get('session_ended', '?')}",
            "-" * 40,
            "",
        ]
        for segment in transcript.get("segments", []) or []:
            seconds = int(segment.get("t", 0))
            lines.append(
                f"[{seconds // 60:02d}:{seconds % 60:02d}] "
                f"{segment.get('text', '')}"
            )
        self.transcript_viewer.setPlainText("\n".join(lines))

    def _build_support_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        header = QLabel("Contact support")
        header.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(header)
        hint = QLabel("Message the admin directly on Telegram.")
        hint.setStyleSheet("color: #8a92a6; font-size: 12px;")
        layout.addWidget(hint)
        button = QPushButton("Open Telegram chat")
        button.clicked.connect(self._open_telegram)
        layout.addWidget(button)
        self.support_status = QLabel("")
        self.support_status.setStyleSheet("color: #8a92a6; font-size: 12px;")
        layout.addWidget(self.support_status)
        layout.addStretch()
        return panel

    def _open_telegram(self):
        token = storage.load().get("token")
        if not token:
            self.support_status.setText("Not authenticated.")
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
            self.support_status.setText(f"Error: {type(exc).__name__}")
            return
        if url:
            webbrowser.open(url)
            self.support_status.setText("Opened in browser.")
        else:
            self.support_status.setText("Bot URL not configured. Contact admin.")
