import { useCallback, useEffect, useRef, useState } from "react";

export type RecState = "idle" | "recording" | "denied" | "unsupported";

const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
const MIN_MS = 700;

function pickMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m));
}

/**
 * Tap to start, tap to stop (works with a mouse, a touch screen and a keyboard).
 * Stops by itself a little before the server's limit. The recorded blob keeps the browser's real
 * container type; the server converts it, so nothing here pretends it is WAV.
 */
export function useRecorder(maxSeconds: number, onClip: (blob: Blob) => void, onProblem: (message: string) => void) {
  const [state, setState] = useState<RecState>(() =>
    typeof navigator.mediaDevices?.getUserMedia === "function" && pickMime() ? "idle" : "unsupported");
  const [seconds, setSeconds] = useState(0);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<number | null>(null);
  const started = useRef(0);
  const cancelled = useRef(false);
  const latest = useRef({ onClip, onProblem });
  latest.current = { onClip, onProblem };

  const release = useCallback(() => {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  }, []);

  const stop = useCallback(() => {
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
  }, []);

  const start = useCallback(async () => {
    const mime = pickMime();
    if (!mime || !navigator.mediaDevices?.getUserMedia) {
      setState("unsupported");
      return;
    }
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
      stream.current = media;
      const chunks: BlobPart[] = [];
      const rec = new MediaRecorder(media, { mimeType: mime });
      recorder.current = rec;
      cancelled.current = false;
      rec.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);
      rec.onstop = () => {
        const length = Date.now() - started.current;
        release();
        setState("idle");
        setSeconds(0);
        if (cancelled.current) return;
        if (length < MIN_MS || chunks.length === 0) {
          latest.current.onProblem("That was too short. Tap, speak, then tap again to stop.");
          return;
        }
        latest.current.onClip(new Blob(chunks, { type: rec.mimeType || mime }));
      };
      rec.start();
      started.current = Date.now();
      setSeconds(0);
      setState("recording");
      timer.current = window.setInterval(() => {
        const s = (Date.now() - started.current) / 1000;
        setSeconds(Math.floor(s));
        if (s >= maxSeconds) stop();
      }, 250);
    } catch (e) {
      release();
      const name = (e as DOMException)?.name;
      if (name === "NotAllowedError" || name === "SecurityError") {
        setState("denied");
      } else {
        setState("idle");
        latest.current.onProblem("No microphone was found, or it is busy in another app.");
      }
    }
  }, [maxSeconds, release, stop]);

  const cancel = useCallback(() => {
    cancelled.current = true;
    stop();
    release();
  }, [release, stop]);

  useEffect(() => () => {
    cancelled.current = true;
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
    release();
  }, [release]);

  return { state, seconds, start, stop, cancel };
}
