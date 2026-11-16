"""Test sherpa-onnx Nemotron Streaming on the model's own test WAVs."""

import time
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx

MODEL_DIR = (
    Path(__file__).parent
    / "models"
    / "sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-560ms-int8-2026-06-11"
)

if not MODEL_DIR.exists():
    print(f"Model dir not found: {MODEL_DIR}")
    raise SystemExit(1)

test_wavs = MODEL_DIR / "test_wavs"
wav_files = sorted(test_wavs.rglob("*.wav")) if test_wavs.exists() else []
if not wav_files:
    print(f"No WAV files in {test_wavs}")
    raise SystemExit(1)

wav_path = wav_files[0]
print(f"Using test file: {wav_path.name}")


def display_text(text):
    return str(text).encode("ascii", "backslashreplace").decode("ascii")


with wave.open(str(wav_path), "rb") as wav:
    sr = wav.getframerate()
    n = wav.getnframes()
    channels = wav.getnchannels()
    sample_width = wav.getsampwidth()
    frames = wav.readframes(n)
    print(
        f"WAV: {sr} Hz, {channels} ch, {sample_width * 8}-bit, "
        f"{n / sr:.2f}s"
    )

    if sample_width == 2:
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        samples = (
            np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
        )
    else:
        print(f"Unsupported sample width: {sample_width}")
        raise SystemExit(1)

    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)

if sr != 16000:
    import soxr

    print(f"Resampling {sr} -> 16000")
    samples = soxr.resample(samples, sr, 16000).astype(np.float32)

print(f"\nLoading model from {MODEL_DIR.name} (takes 5-15s)...")
t_load = time.time()
recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
    tokens=str(MODEL_DIR / "tokens.txt"),
    encoder=str(MODEL_DIR / "encoder.int8.onnx"),
    decoder=str(MODEL_DIR / "decoder.int8.onnx"),
    joiner=str(MODEL_DIR / "joiner.int8.onnx"),
    num_threads=2,
    sample_rate=16000,
    feature_dim=80,
    decoding_method="greedy_search",
    enable_endpoint_detection=True,
    rule1_min_trailing_silence=2.4,
    rule2_min_trailing_silence=1.2,
    rule3_min_utterance_length=20,
)
print(f"Model loaded in {time.time() - t_load:.1f}s\n")

stream = recognizer.create_stream()
chunk_size = 3200
last_partial = ""
finals = []

print("Streaming...")
t0 = time.time()

for i in range(0, len(samples), chunk_size):
    chunk = samples[i : i + chunk_size]
    stream.accept_waveform(16000, chunk)

    while recognizer.is_ready(stream):
        recognizer.decode_stream(stream)

    partial = recognizer.get_result(stream)
    if partial and partial != last_partial:
        print(f"  [partial] {display_text(partial)}")
        last_partial = partial

    if recognizer.is_endpoint(stream):
        final = recognizer.get_result(stream)
        if final:
            print(f"  [FINAL]   {display_text(final)}")
            finals.append(final)
        recognizer.reset(stream)
        last_partial = ""

stream.accept_waveform(16000, np.zeros(int(0.5 * 16000), dtype=np.float32))
while recognizer.is_ready(stream):
    recognizer.decode_stream(stream)
final = recognizer.get_result(stream)
if final:
    print(f"  [FINAL]   {display_text(final)}")
    finals.append(final)

elapsed = time.time() - t0
audio_duration = len(samples) / 16000
rtf = elapsed / audio_duration if audio_duration > 0 else 0.0

print("\n" + "=" * 60)
print("RESULT")
print("=" * 60)
print(f"Audio duration:    {audio_duration:.2f}s")
print(f"Processing time:   {elapsed:.2f}s")
print(f"Real-time factor:  {rtf:.2f}x  (<1.0 = faster than real-time)")
print(f"Final segments:    {len(finals)}")
if finals:
    print("\nFull transcript:")
    print(display_text(" ".join(finals)))
else:
    print("\nNo final segments produced - model returned empty text")
