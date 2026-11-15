"""Profile editing dialog — opens from a button on the overlay."""

import httpx
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox, QPushButton, QLabel,
)

from ..auth import storage
from ..config import BACKEND_URL


class ProfileDialog(QDialog):
    def __init__(self, parent=None, profile: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("My profile")
        self.setMinimumWidth(420)
        profile = profile or {}

        form = QFormLayout(self)

        self.role = QLineEdit(profile.get("role", ""))
        self.experience = QLineEdit(profile.get("experience", ""))
        self.skills = QLineEdit(profile.get("skills", ""))
        self.company = QLineEdit(profile.get("company", ""))
        self.target_role = QLineEdit(profile.get("target_role", ""))
        self.target_company = QLineEdit(profile.get("target_company", ""))
        self.target_salary = QLineEdit(profile.get("target_salary", ""))
        self.notice_period = QLineEdit(profile.get("notice_period", ""))

        self.answer_style = QComboBox()
        self.answer_style.addItems(["", "star", "concise", "detailed"])
        self.answer_style.setCurrentText(profile.get("answer_style", ""))

        form.addRow("Role", self.role)
        form.addRow("Experience", self.experience)
        form.addRow("Skills (comma-separated)", self.skills)
        form.addRow("Current company", self.company)
        form.addRow("Target role", self.target_role)
        form.addRow("Target company", self.target_company)
        form.addRow("Target salary", self.target_salary)
        form.addRow("Notice period", self.notice_period)
        form.addRow("Answer style", self.answer_style)

        self.status = QLabel("")
        form.addRow(self.status)

        save = QPushButton("Save")
        save.clicked.connect(self._save)
        form.addRow(save)

        if not profile:
            self._load()

    def _load(self):
        token = storage.load().get("token")
        if not token:
            self.status.setText("Not authenticated.")
            return
        try:
            response = httpx.get(
                f"{BACKEND_URL}/me/profile",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
            if response.status_code == 200:
                profile = response.json() or {}
                for field in (
                    "role", "experience", "skills", "company",
                    "target_role", "target_company", "target_salary",
                    "notice_period",
                ):
                    getattr(self, field).setText(profile.get(field, "") or "")
                self.answer_style.setCurrentText(
                    (profile.get("answer_style", "") or "").lower()
                )
                self.status.setText("Loaded.")
            elif response.status_code == 401:
                self.status.setText("Session expired — re-activate the app.")
            else:
                self.status.setText(f"Load failed: HTTP {response.status_code}")
        except httpx.HTTPError as exc:
            self.status.setText(f"Load error: {type(exc).__name__}")

    def _save(self):
        token = storage.load().get("token")
        if not token:
            self.status.setText("Not authenticated.")
            return

        payload = {
            "role": self.role.text().strip(),
            "experience": self.experience.text().strip(),
            "skills": self.skills.text().strip(),
            "company": self.company.text().strip(),
            "target_role": self.target_role.text().strip(),
            "target_company": self.target_company.text().strip(),
            "target_salary": self.target_salary.text().strip(),
            "notice_period": self.notice_period.text().strip(),
            "answer_style": self.answer_style.currentText(),
        }

        try:
            r = httpx.post(
                f"{BACKEND_URL}/me/profile",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
            if r.status_code == 200:
                self.status.setText("✅ Saved. Next answers will use this profile.")
            else:
                self.status.setText(f"❌ HTTP {r.status_code}")
        except Exception as e:
            self.status.setText(f"❌ {type(e).__name__}")