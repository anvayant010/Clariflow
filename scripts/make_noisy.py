"""Make SIMULATED noisy variants of recorded clips (synthetic noise only, fixed seed).

  python -m scripts.make_noisy ME1 HE1 MHE1

Writes fixtures/audio/simulated/<ID>_sim-fan10.wav, _sim-fan5.wav, _sim-phone.wav and a
MANIFEST.json with every parameter. These are paired variants of the same utterance, NOT new
speakers and NOT real telephony; always call them "simulated".

  fan   : brown-noise rumble + 50 Hz hum harmonics + a little hiss, mixed at the stated SNR
          (speech level measured on active samples only, not silence).
  phone : 300-3400 Hz band-pass, 8 kHz sampling, mu-law 8-bit companding, hiss at ~25 dB SNR.
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "fixtures" / "audio"
OUT = AUDIO / "simulated"
EXTS = (".m4a", ".wav", ".mp3", ".ogg", ".flac", ".aac")
SR = 16000
SEED = 20261104


def load_mono(path: Path, sr: int = SR) -> np.ndarray:
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def active_rms(x: np.ndarray) -> float:
    active = x[np.abs(x) > 0.05 * np.max(np.abs(x))]
    return float(np.sqrt(np.mean(active**2))) if active.size else float(np.sqrt(np.mean(x**2)))


def fan_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    brown = np.cumsum(rng.standard_normal(n))
    brown -= np.linspace(brown[0], brown[-1], n)  # remove drift
    brown /= np.max(np.abs(brown))
    t = np.arange(n) / SR
    hum = sum(np.sin(2 * np.pi * 50 * k * t + rng.uniform(0, 6.28)) / k for k in (1, 2, 3, 4))
    hiss = rng.standard_normal(n)
    return 1.0 * brown + 0.15 * hum + 0.05 * hiss


def mix_at_snr(speech: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    target = active_rms(speech) / (10 ** (snr_db / 20))
    noise = noise * (target / np.sqrt(np.mean(noise**2)))
    return speech + noise


def bandpass(x: np.ndarray, lo: float, hi: float, sr: int) -> np.ndarray:
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    spec[(freqs < lo) | (freqs > hi)] = 0
    return np.fft.irfft(spec, len(x))


def mulaw_roundtrip(x: np.ndarray, mu: int = 255) -> np.ndarray:
    x = np.clip(x, -1, 1)
    comp = np.sign(x) * np.log1p(mu * np.abs(x)) / np.log1p(mu)
    q = np.round((comp + 1) / 2 * mu) / mu * 2 - 1  # 8-bit quantisation
    return np.sign(q) * ((1 + mu) ** np.abs(q) - 1) / mu


def phone(x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    x = bandpass(x, 300, 3400, SR)
    x = x[::2]  # 16 kHz -> 8 kHz (band is already below 4 kHz, so no aliasing)
    x = mix_at_snr(x, rng.standard_normal(len(x)), 25)
    x = x / max(np.max(np.abs(x)), 1e-9) * 0.9
    return mulaw_roundtrip(x)


def write_wav(path: Path, x: np.ndarray, sr: int) -> None:
    x = x / max(np.max(np.abs(x)), 1e-9) * 0.9
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def main() -> int:
    ids = [i.upper() for i in sys.argv[1:]]
    if not ids:
        print(__doc__)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for cid in ids:
        src = next((p for p in AUDIO.iterdir() if p.stem.upper() == cid and p.suffix.lower() in EXTS), None)
        if not src:
            print(f"skip {cid}: no clip in {AUDIO}")
            continue
        speech = load_mono(src)
        for name, snr in (("fan10", 10), ("fan5", 5), ("phone", None)):
            rng = np.random.default_rng([SEED, sum(map(ord, cid)), len(name)])
            if snr is None:
                out, sr, params = phone(speech, rng), 8000, {"band_hz": [300, 3400], "sample_rate": 8000, "codec": "mu-law 8-bit", "hiss_snr_db": 25}
            else:
                out, sr = mix_at_snr(speech, fan_noise(len(speech), rng), snr), SR
                params = {"noise": "brown rumble + 50 Hz hum harmonics + hiss", "snr_db": snr, "snr_basis": "active-speech RMS"}
            dest = OUT / f"{cid}_sim-{name}.wav"
            write_wav(dest, out, sr)
            manifest[dest.name] = {"source": src.name, "simulated": True, "seed": SEED, **params}
            print(f"wrote {dest.name} ({len(out) / sr:.1f}s)")
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
