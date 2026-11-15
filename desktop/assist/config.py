
"""All tunables."""

import os
from pathlib import Path

# ---- backend ----
BACKEND_URL = "https://assist-backend-d8w1.onrender.com"

# ---- capture mode ----
# "system_loopback"  — all speaker audio
# "per_process"      — only meeting app
# "auto"             — per-process if available
CAPTURE_MODE = "system_loopback"

# ---- capture params ----
CAPTURE_SR = 48000
STT_SR = 16000
BLOCK_FRAMES = 9600             # was 4800 — 200ms blocks, fewer overruns

# ---- microphone ----
ENABLE_MIC_CAPTURE = False
MIC_DEVICE = None
MIC_GAIN = 1.0

# ---- VAD / segmentation ----
VAD_FRAME_MS = 30
VAD_FRAME_SAMPLES = STT_SR * VAD_FRAME_MS // 1000
START_FRAMES = 3
END_FRAMES = 16
PRE_ROLL_SEC = 1.0
MAX_SEGMENT_SEC = 7
QUESTION_COALESCE_SEC = 0.5
SILENCE_RMS = 10 ** (-50 / 20)

# ---- queue discipline ----
MAX_AUDIO_QUEUE = 100           # was 200
MAX_SEGMENT_QUEUE = 2           # was 4 — drop stale segments aggressively
MAX_SEGMENT_AGE_SEC = 12.0      # discard if not transcribed within 12s

# ---- device ----
DEVICE_POLL_SEC = 2.0

# ---- STT ----
STT_BACKEND = "parakeet"
PARAKEET_MODEL = "nemo-parakeet-tdt-0.6b-v2"
VAD_MODE = 2

# ---- storage / upload ----
# Store transcripts in the user's AppData directory instead of the
# installation directory, which may be read-only.
_APP_DATA = Path(os.environ.get("APPDATA", str(Path.home()))) / "Assist"
TRANSCRIPTS_DIR = _APP_DATA / "transcripts"
UI_STATE_FILE = _APP_DATA / "ui_state.json"

UPLOAD_EVERY_SEC = 30.0         # periodic transcript sync
EMAIL_TRANSCRIPT_ON_END = True  # email transcript on shutdown

# ---- overlay UI ----
OVERLAY_WIDTH = 900
OVERLAY_TOP_MARGIN = 12
OVERLAY_QUESTION_COLOR = "rgba(190, 190, 255, 255)"
OVERLAY_ANSWER_COLOR = "rgba(255, 255, 255, 255)"
OVERLAY_CARD_BG = "rgba(18, 18, 28, 235)"
OVERLAY_CARD_BORDER = "rgba(255, 255, 255, 45)"
OVERLAY_QUESTION_FONT_PX = 13
OVERLAY_ANSWER_FONT_PX = 17
OVERLAY_POLL_MS = 50

# ---- meeting app detection ----
MEETING_APPS = {
    "Zoom": ["zoom.exe", "zoom"],
    "Teams": ["teams.exe", "ms-teams.exe", "teams"],
    "Webex": ["webex.exe", "webexmta.exe", "webex"],
    "GoTo": ["goto.exe", "gotomeeting.exe", "gotomeeting"],
    "Slack Huddle": ["slack.exe"],
    "Discord": ["discord.exe"],
}
MEETING_POLL_SEC = 3.0
MEETING_SILENCE_END_SEC = 30.0
