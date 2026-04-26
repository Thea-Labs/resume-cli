"""Text-to-speech: ElevenLabs first (female, energetic), OpenAI fallback.

Public surface:
  - synthesize(text) -> Path           # picks a backend based on env
  - play_async(path) -> Thread
  - TTSUnavailable

Backend selection:
  - ELEVENLABS_API_KEY set → ElevenLabs (Rachel by default, expressive).
  - else OPENAI_API_KEY set → OpenAI TTS ("nova"), preserves old behavior.
  - else → TTSUnavailable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

# ElevenLabs defaults — female voice "Rachel", warm and natural.
ELEVENLABS_DEFAULT_VOICE_ID = "4RZ84U1b4WCqpu57LvIq"
ELEVENLABS_DEFAULT_MODEL = "eleven_turbo_v2_5"
ELEVENLABS_VOICE_SETTINGS = {
    "stability": 0.85,
    "similarity_boost": 0.75,
    "style": 0.45,
    "use_speaker_boost": True,
    "speed": 1.2,
}

_SPEED_MAP = {
    "natural": 1.15,
    "fast": 1.35,
    "calm": 1.0,
}

# OpenAI fallback defaults.
OPENAI_DEFAULT_MODEL = "gpt-4o-mini-tts"
OPENAI_DEFAULT_VOICE = "nova"


class TTSUnavailable(Exception):
    """Raised when TTS cannot proceed (no API key, no network, etc.)."""


def synthesize(text: str, speech_speed: str = "natural") -> Path:
    """Synthesize `text` to an MP3 file. Returns the temp file path.

    ElevenLabs is preferred when ELEVENLABS_API_KEY is set. Falls back to
    OpenAI TTS if only OPENAI_API_KEY is available. `speech_speed` is one
    of "natural" / "fast" / "calm" (unknown values fall through to default).
    """
    if os.environ.get("ELEVENLABS_API_KEY"):
        return _synthesize_elevenlabs(text, speech_speed=speech_speed)
    if os.environ.get("OPENAI_API_KEY"):
        return _synthesize_openai(text)
    raise TTSUnavailable(
        "No TTS provider configured. Set ELEVENLABS_API_KEY (preferred) or OPENAI_API_KEY, "
        "or run with --text."
    )


def _tempfile() -> Path:
    tmp = tempfile.NamedTemporaryFile(prefix="resume-", suffix=".mp3", delete=False)
    tmp.close()
    return Path(tmp.name)


def _synthesize_elevenlabs(text: str, speech_speed: str = "natural") -> Path:
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError as exc:
        raise TTSUnavailable(
            "elevenlabs package not installed. Run `pip install elevenlabs>=1.0`."
        ) from exc

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID") or ELEVENLABS_DEFAULT_VOICE_ID
    model_id = os.environ.get("ELEVENLABS_MODEL") or ELEVENLABS_DEFAULT_MODEL

    voice_settings = dict(ELEVENLABS_VOICE_SETTINGS)
    voice_settings["speed"] = _SPEED_MAP.get(speech_speed, voice_settings["speed"])

    try:
        client = ElevenLabs(api_key=api_key)
        audio_stream = client.text_to_speech.convert(
            voice_id=voice_id,
            model_id=model_id,
            text=text,
            voice_settings=voice_settings,
            output_format="mp3_44100_128",
        )
    except TypeError:
        # Older SDKs may not accept voice_settings or output_format kwargs.
        try:
            client = ElevenLabs(api_key=api_key)
            audio_stream = client.text_to_speech.convert(
                voice_id=voice_id,
                model_id=model_id,
                text=text,
            )
        except Exception as exc:
            raise TTSUnavailable(f"ElevenLabs request failed: {exc}") from exc
    except Exception as exc:
        raise TTSUnavailable(f"ElevenLabs request failed: {exc}") from exc

    out_path = _tempfile()
    try:
        with out_path.open("wb") as fh:
            for chunk in audio_stream:
                if chunk:
                    fh.write(chunk)
    except Exception as exc:
        raise TTSUnavailable(f"Failed to write ElevenLabs audio: {exc}") from exc

    if out_path.stat().st_size == 0:
        raise TTSUnavailable("ElevenLabs returned an empty audio stream.")

    return out_path


def _synthesize_openai(text: str) -> Path:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise TTSUnavailable("openai package not installed.") from exc

    api_key = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
    out_path = _tempfile()

    try:
        with client.audio.speech.with_streaming_response.create(
            model=OPENAI_DEFAULT_MODEL, voice=OPENAI_DEFAULT_VOICE, input=text
        ) as response:
            response.stream_to_file(str(out_path))
    except Exception as exc:
        try:
            response = client.audio.speech.create(
                model=OPENAI_DEFAULT_MODEL, voice=OPENAI_DEFAULT_VOICE, input=text
            )
            out_path.write_bytes(response.read())
        except Exception:
            raise TTSUnavailable(f"OpenAI TTS request failed: {exc}") from exc

    return out_path


def play(path: Path) -> None:
    """Play an audio file using the best available backend."""
    try:
        from playsound import playsound

        playsound(str(path))
        return
    except Exception:
        pass

    if sys.platform == "darwin" and shutil.which("afplay"):
        subprocess.run(["afplay", str(path)], check=False)
        return

    if sys.platform.startswith("linux"):
        for player in ("mpg123", "ffplay", "aplay"):
            exe = shutil.which(player)
            if exe:
                args = (
                    [exe, "-nodisp", "-autoexit", str(path)]
                    if player == "ffplay"
                    else [exe, str(path)]
                )
                subprocess.run(args, check=False)
                return

    if sys.platform == "win32":
        try:
            import winsound  # type: ignore

            winsound.PlaySound(str(path), winsound.SND_FILENAME)
            return
        except Exception:
            pass

    raise TTSUnavailable("No audio backend available. Try `resume --text`.")


def play_async(path: Path) -> threading.Thread:
    """Start playback in a background daemon thread and return the handle."""
    thread = threading.Thread(target=_safe_play, args=(path,), daemon=True)
    thread.start()
    return thread


def _safe_play(path: Path) -> None:
    try:
        play(path)
    except TTSUnavailable:
        pass
