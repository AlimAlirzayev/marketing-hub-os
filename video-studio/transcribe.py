"""Xalq Insurance Digital OS Video Studio - speech-to-captions.

Turns the base clip's audio into word-level timed captions for the Remotion
<Captions> component. Two interchangeable backends:

  groq  - Groq's hosted Whisper (whisper-large-v3-turbo). Free tier, fast,
          and crucially has NO native dependency. Needs GROQ_API_KEY.
  local - openai-whisper (PyTorch, CPU). Fully offline, zero key.

Why two: local ML runtimes (both ctranslate2 and PyTorch) fail to initialise
on this corporate Windows machine - the locked-down VC++ runtime / EDR blocks
their native DLLs (WinError 1114). The Groq backend sidesteps that entirely
and is the recommended path here; the local backend stays for offline use
once IT unblocks the runtime.

backend="auto" (the default) picks groq when GROQ_API_KEY is set, else local.
"""

from __future__ import annotations

import json
import os
import wave
from pathlib import Path

DEFAULT_MODEL = "base"            # openai-whisper model size (local backend)
GROQ_MODEL = "whisper-large-v3-turbo"  # Groq hosted model
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def _transcribe_groq(audio_path: str | Path) -> list[dict]:
    """Transcribe via Groq's hosted Whisper. Returns word dicts."""
    import requests

    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set")

    with open(audio_path, "rb") as fh:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (Path(audio_path).name, fh, "audio/wav")},
            data={
                "model": GROQ_MODEL,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
            },
            timeout=180,
        )
    resp.raise_for_status()
    data = resp.json()
    return [
        {
            "text": str(w["word"]).strip(),
            "start": round(float(w["start"]), 3),
            "end": round(float(w["end"]), 3),
        }
        for w in data.get("words", [])
    ]


def _load_wav_16k_mono(path: str | Path):
    """Read a 16 kHz mono PCM WAV into a float32 numpy array in [-1, 1]."""
    import numpy as np

    with wave.open(str(path), "rb") as wf:
        if wf.getsampwidth() != 2 or wf.getnchannels() != 1:
            raise ValueError("expected 16-bit mono WAV from extract_audio()")
        frames = wf.readframes(wf.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def _transcribe_local(
    audio_path: str | Path, language: str, model_size: str
) -> list[dict]:
    """Transcribe via local openai-whisper. Returns word dicts."""
    import whisper

    audio = _load_wav_16k_mono(audio_path)
    model = whisper.load_model(model_size)
    # task="translate" forces English; "transcribe" keeps the spoken language.
    task = "translate" if language == "en" else "transcribe"
    result = model.transcribe(audio, task=task, word_timestamps=True, fp16=False)

    words: list[dict] = []
    for segment in result.get("segments", []):
        for word in segment.get("words", []):
            words.append(
                {
                    "text": str(word["word"]).strip(),
                    "start": round(float(word["start"]), 3),
                    "end": round(float(word["end"]), 3),
                }
            )
    return words


def transcribe(
    audio_path: str | Path,
    out_json: str | Path,
    *,
    language: str = "en",
    model_size: str = DEFAULT_MODEL,
    backend: str = "auto",
) -> dict:
    """Transcribe audio to word-timed captions and write them as JSON.

    backend: "auto" (groq if GROQ_API_KEY else local), "groq", or "local".
    Returns {"language", "backend", "words": [{"text","start","end"}]}.
    """
    if backend == "auto":
        backend = "groq" if os.environ.get("GROQ_API_KEY") else "local"

    if backend == "groq":
        words = _transcribe_groq(audio_path)
    elif backend == "local":
        try:
            import whisper  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "openai-whisper is not installed and no GROQ_API_KEY is set. "
                "Either set GROQ_API_KEY (free) or pip install openai-whisper."
            ) from exc
        words = _transcribe_local(audio_path, language, model_size)
    else:
        raise ValueError(f"unknown backend: {backend}")

    captions = {"language": language, "backend": backend, "words": words}
    out_path = Path(out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(captions, indent=2), encoding="utf-8")
    return captions


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("usage: python transcribe.py <audio.wav> <out.json>")
        raise SystemExit(2)
    result = transcribe(sys.argv[1], sys.argv[2])
    print(f"{len(result['words'])} words ({result['backend']}) -> {sys.argv[2]}")
