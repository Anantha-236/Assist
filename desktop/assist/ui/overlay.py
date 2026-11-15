"""Glass overlay — answer card with pause, copy, settings, and saved position."""

import ctypes
import json

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import (
    OVERLAY_ANSWER_COLOR,
    OVERLAY_ANSWER_FONT_PX,
    OVERLAY_CARD_BG,
    OVERLAY_CARD_BORDER,
    OVERLAY_QUESTION_COLOR,
    OVERLAY_QUESTION_FONT_PX,
    OVERLAY_TOP_MARGIN,
    OVERLAY_WIDTH,
    UI_STATE_FILE,
)


class AnswerCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AnswerCard")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 16, 14)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)

        self.status_label = QLabel("○ Waiting for a meeting…", self)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "color: rgba(140, 200, 255, 255); font-size: 11px;"
            "font-family: 'Segoe UI', sans-serif; letter-spacing: 0.5px;"
        )
        header.addWidget(self.status_label, 1)

        button_style = (
            "QPushButton { background: transparent; color: rgba(200, 200, 220, 200);"
            " border: none; font-size: 13px; padding: 0 4px; min-width: 22px;"
            " min-height: 22px; }"
            "QPushButton:hover { color: #fff; background: rgba(99, 102, 241, 90);"
            " border-radius: 4px; }"
        )

        self.pause_btn = QPushButton("⏸", self)
        self.pause_btn.setToolTip("Pause / resume")
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.setStyleSheet(button_style)
        self.pause_btn.clicked.connect(self._toggle_pause)
        header.addWidget(self.pause_btn)

        self.copy_btn = QPushButton("📋", self)
        self.copy_btn.setToolTip("Copy answer")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setStyleSheet(button_style)
        self.copy_btn.clicked.connect(self._copy_answer)
        self.copy_btn.setVisible(False)
        header.addWidget(self.copy_btn)

        self.settings_btn = QPushButton("⚙", self)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setStyleSheet(button_style)
        self.settings_btn.clicked.connect(self._open_settings)
        header.addWidget(self.settings_btn)
        layout.addLayout(header)

        self.q_label = QLabel("", self)
        self.q_label.setWordWrap(True)
        self.q_label.setStyleSheet(
            f"color: {OVERLAY_QUESTION_COLOR}; font-size: {OVERLAY_QUESTION_FONT_PX}px;"
            "font-family: 'Segoe UI', sans-serif;"
        )
        self.q_label.hide()
        layout.addWidget(self.q_label)

        self.a_label = QLabel("", self)
        self.a_label.setWordWrap(True)
        self.a_label.setStyleSheet(
            f"color: {OVERLAY_ANSWER_COLOR}; font-size: {OVERLAY_ANSWER_FONT_PX}px;"
            "font-family: 'Segoe UI', sans-serif;"
        )
        layout.addWidget(self.a_label)

        self.setStyleSheet(
            "#AnswerCard {"
            f" background-color: {OVERLAY_CARD_BG}; border-radius: 14px;"
            f" border: 1px solid {OVERLAY_CARD_BORDER}; }}"
        )

    def _toggle_pause(self):
        from ..pause_state import toggle_paused

        paused = toggle_paused()
        self.pause_btn.setText("▶" if paused else "⏸")
        self.pause_btn.setToolTip("Resume" if paused else "Pause")
        self.status_label.setText(
            "⏸ Paused — no new answers"
            if paused
            else "○ Waiting for a meeting…"
        )

    def _copy_answer(self):
        text = self.a_label.text().strip()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.copy_btn.setText("✓")
            QTimer.singleShot(1200, lambda: self.copy_btn.setText("📋"))

    def _open_settings(self):
        from .settings import SettingsDialog

        dialog = SettingsDialog(self.window())
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.exec()

    def set_status(self, text: str):
        from ..pause_state import is_paused

        if not is_paused():
            self.status_label.setText(text)

    def set_question(self, text: str):
        self.q_label.setText("Q:  " + text)
        self.q_label.show()

    def set_answer(self, text: str):
        self.a_label.setText(text)
        self.copy_btn.setVisible(bool(text))

    def append_answer(self, text: str):
        self.a_label.setText(self.a_label.text() + text)
        self.copy_btn.setVisible(True)


class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(OVERLAY_WIDTH)
        self.setMinimumHeight(60)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._card = AnswerCard(self)
        layout.addWidget(self._card)

        self._drag_offset = None
        self._positioned = False
        self._has_content = False
        self._restore_position()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "_save_timer") and self._save_timer is not None:
            self._save_timer.stop()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_position)
        self._save_timer.start(400)

    def _place_initial(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            screen.y() + OVERLAY_TOP_MARGIN,
        )
        self._positioned = True

    def _restore_position(self):
        try:
            if UI_STATE_FILE.exists():
                data = json.loads(UI_STATE_FILE.read_text(encoding="utf-8"))
                x, y = int(data.get("x", 0)), int(data.get("y", 0))
                screen = QApplication.primaryScreen().geometry()
                if 0 <= x <= screen.width() and 0 <= y <= screen.height():
                    self.move(x, y)
                    self._positioned = True
                    return
        except (OSError, TypeError, ValueError) as exc:
            print(f"[ui] restore position error: {type(exc).__name__}")
        self._place_initial()

    def _save_position(self):
        try:
            UI_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            UI_STATE_FILE.write_text(
                json.dumps({"x": self.x(), "y": self.y()}),
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"[ui] save position error: {type(exc).__name__}")

    def new_question(self, question: str):
        self._card.set_question(question)
        self._card.set_answer("")
        self._card.copy_btn.setVisible(False)
        self._has_content = True
        self.adjustSize()
        if not self._positioned:
            self._place_initial()

    def append_token(self, token: str):
        if self._has_content:
            self._card.append_answer(token)
            self.adjustSize()

    def set_status(self, status: str):
        self._card.set_status(status)
        self.adjustSize()

    def hide_from_capture(self):
        try:
            hwnd = int(self.winId())
            ok = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11)
            if ok:
                print("[ui] excluded from screen capture")
            else:
                print("[ui] SetWindowDisplayAffinity failed")
        except Exception as exc:
            print(f"[ui] hide_from_capture error: {type(exc).__name__}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle = self.windowHandle()
            if handle is not None:
                try:
                    handle.startSystemMove()
                    event.accept()
                    return
                except RuntimeError:
                    pass
            event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()
