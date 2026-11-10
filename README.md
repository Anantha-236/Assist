# Assist

A desktop meeting assistant that listens to meeting-app audio, detects questions,
and displays answers as a transparent glass overlay (subtitle-style).

## Status
- v0.1 — early development

## Structure
- `backend/`  — FastAPI: activation keys, transcript sync, OpenRouter proxy
- `desktop/`  — Audio capture (WASAPI loopback), VAD, STT, overlay UI
- `docs/`     — Architecture and design notes
- `scripts/`  — Dev helpers

## Requirements
- Windows 10 2004+ (per-process audio loopback)
- Python 3.11+
- Git

## Setup
(coming soon)

## License
Private