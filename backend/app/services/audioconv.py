"""Turn whatever the browser or phone sends into 16 kHz mono WAV, safely.

Browsers record WebM/Opus (Chrome, Firefox) or MP4/AAC (Safari); Prisma's list of accepted
extensions does not include WebM, and we never relabel one container as another. So every clip
is decoded by ffmpeg and re-encoded as WAV, which also lets us enforce the 30 s limit for every format.

Untrusted input: the container is identified from its magic bytes (never from the file name) and
passed to ffmpeg with an explicit demuxer, so a text/playlist file cannot make ffmpeg read other
files or URLs. Output length is capped before decoding finishes, and the whole call has a timeout.
"""
import io
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg

MAX_BYTES = 8_000_000
MAX_SECONDS = 30
MIN_SECONDS = 0.3
TIMEOUT_SECONDS = 25
OUT_RATE = 16000


class AudioError(ValueError):
    """code: too_large | empty | unsupported | too_long | too_short | decode_failed | timeout"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Clip:
    wav: bytes
    seconds: float
    container: str  # what the upload actually was


def sniff(data: bytes) -> tuple[str, str] | None:
    """(label, ffmpeg demuxer) from magic bytes, or None if not a supported audio container."""
    head = data[:12]
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav", "wav"
    if head[4:8] == b"ftyp":
        return "mp4/m4a", "mov,mp4,m4a,3gp,3g2,mj2"
    if head[:4] == b"OggS":
        return "ogg", "ogg"
    if head[:4] == b"fLaC":
        return "flac", "flac"
    if head[:4] == b"\x1aE\xdf\xa3":
        return "webm", "matroska,webm"
    if head[:3] == b"ID3":
        return "mp3", "mp3"
    if len(head) >= 2 and head[0] == 0xFF:
        if head[1] & 0xF6 == 0xF0:
            return "aac", "aac"
        if head[1] & 0xE0 == 0xE0:
            return "mp3", "mp3"
    return None


def _duration(wav: bytes) -> float:
    with wave.open(io.BytesIO(wav)) as w:
        return w.getnframes() / float(w.getframerate())


def to_wav(data: bytes) -> Clip:
    if not data:
        raise AudioError("empty", "the recording is empty")
    if len(data) > MAX_BYTES:
        raise AudioError("too_large", "the recording is too large")
    found = sniff(data)
    if found is None:
        raise AudioError("unsupported", "unsupported audio format; use wav, m4a, mp3, ogg, flac, aac or a browser recording")
    label, demuxer = found
    with tempfile.TemporaryDirectory(prefix="clariflow-audio-") as tmp:
        src, dst = Path(tmp) / "in.bin", Path(tmp) / "out.wav"
        src.write_bytes(data)
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-nostdin", "-y", "-protocol_whitelist", "file",
               "-f", demuxer, "-i", str(src), "-t", str(MAX_SECONDS + 1), "-vn", "-ac", "1", "-ar", str(OUT_RATE),
               "-sample_fmt", "s16", "-f", "wav", str(dst)]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired:
            raise AudioError("timeout", "the recording took too long to process") from None
        if proc.returncode != 0 or not dst.is_file():
            raise AudioError("decode_failed", f"the {label} recording could not be read")
        wav = dst.read_bytes()
    try:
        seconds = _duration(wav)
    except (wave.Error, EOFError, ZeroDivisionError):
        raise AudioError("decode_failed", "the recording could not be read") from None
    if seconds > MAX_SECONDS:
        raise AudioError("too_long", f"the recording is longer than {MAX_SECONDS} seconds")
    if seconds < MIN_SECONDS:
        raise AudioError("too_short", "the recording is too short")
    return Clip(wav=wav, seconds=round(seconds, 2), container=label)
