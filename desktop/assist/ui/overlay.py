"""Glass overlay — single persistent card, top-center, draggable."""

import ctypes

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
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
)


class AnswerCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AnswerCard")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 16, 16)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.status_label = QLabel("○ Waiting for a meeting…", self)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "color: rgba(140, 200, 255, 255);"
            "font-size: 11px;"
            "font-family: 'Segoe UI', sans-serif;"
            "letter-spacing: 0.5px;"
        )

        self.q_label = QLabel("", self)
        self.q_label.setWordWrap(True)
        self.q_label.setStyleSheet(
            f"color: {OVERLAY_QUESTION_COLOR};"
            f"font-size: {OVERLAY_QUESTION_FONT_PX}px;"
            "font-family: 'Segoe UI', sans-serif;"
        )
        self.q_label.hide()

        self.a_label = QLabel("", self)
        self.a_label.setWordWrap(True)
        self.a_label.setStyleSheet(
            f"color: {OVERLAY_ANSWER_COLOR};"
            f"font-size: {OVERLAY_ANSWER_FONT_PX}px;"
            "font-family: 'Segoe UI', sans-serif;"
        )

        self.settings_btn = QPushButton("⚙", self)
        self.settings_btn.setFixedSize(24, 24)
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #8cc8ff; "
            "border: none; font-size: 14px; padding: 0; }"
            "QPushButton:hover { color: #fff; background: #6366f1; "
            "border-radius: 4px; }"
        )
        self.settings_btn.clicked.connect(self._open_settings)
        header.addWidget(self.status_label, 1)
        header.addWidget(self.settings_btn)
        layout.addLayout(header)
        layout.addWidget(self.q_label)
        layout.addWidget(self.a_label)

        self.setStyleSheet(
            "#AnswerCard {"
            f"  background-color: {OVERLAY_CARD_BG};"
            "  border-radius: 14px;"
            f"  border: 1px solid {OVERLAY_CARD_BORDER};"
            "}"
        )

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_question(self, text: str):
        self.q_label.setText("Q:  " + text)
        self.q_label.show()

    def set_answer(self, text: str):
        self.a_label.setText(text)

    def append_answer(self, text: str):
        self.a_label.setText(self.a_label.text() + text)

    def _open_settings(self):
        from .settings import SettingsDialog

        dlg = SettingsDialog(self.window())
        dlg.exec()


class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(OVERLAY_WIDTH)
        self.setMinimumHeight(70)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._card = AnswerCard(self)
        layout.addWidget(self._card)

        self._drag_offset = None
        self._positioned = False
        self._has_content = False

    def _place_initial(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = screen.y() + OVERLAY_TOP_MARGIN
        self.move(x, y)
        self._positioned = True

    def new_question(self, question: str):
        self._card.set_question(question)
        self._card.set_answer("")
        self._has_content = True
        self.adjustSize()
        if not self._positioned:
            self._place_initial()

    def append_token(self, token: str):
        if not self._has_content:
            return
        self._card.append_answer(token)
        self.adjustSize()

    def set_status(self, status: str):
        self._card.set_status(status)
        self.adjustSize()

    def hide_from_capture(self):
        try:
            hwnd = int(self.winId())
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            ok = ctypes.windll.user32.SetWindowDisplayAffinity(
                hwnd, WDA_EXCLUDEFROMCAPTURE
            )
            if ok:
                print("[ui] excluded from screen capture")
            else:
                print("[ui] SetWindowDisplayAffinity failed")
        except Exception as e:
            print(f"[ui] hide_from_capture error: {e}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        event.accept()