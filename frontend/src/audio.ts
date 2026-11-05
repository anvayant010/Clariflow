import { ApiError } from "./api";

// One shared player so two clips never talk over each other. Audio is fetched first (not given to
// <audio src>) so a quota or server message can be shown instead of a silent failure.
let current: HTMLAudioElement | null = null;
let currentEnd: (() => void) | null = null;
const urls = new Map<string, Promise<string>>(); // the promise is cached, so two quick calls share one request

async function fetchObjectUrl(url: string): Promise<string> {
  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new ApiError("network", "Cannot reach the server.", 0);
  }
  if (!res.ok) {
    let message = "That audio is not available.";
    let code = "http_" + res.status;
    try {
      const j = await res.json();
      message = j.error?.message ?? message;
      code = j.error?.code ?? code;
    } catch {
      /* not JSON */
    }
    throw new ApiError(code, message, res.status);
  }
  return URL.createObjectURL(await res.blob());
}

export function stopAudio(): void {
  if (current) {
    current.pause();
    current = null;
  }
  currentEnd?.();
  currentEnd = null;
}

export async function playUrl(url: string, onEnd: () => void): Promise<void> {
  stopAudio();
  let pending = urls.get(url);
  if (!pending) {
    pending = fetchObjectUrl(url);
    urls.set(url, pending);
  }
  let objectUrl: string;
  try {
    objectUrl = await pending;
  } catch (e) {
    urls.delete(url); // do not remember a failure (quota, network): a later tap should try again
    throw e;
  }
  const audio = new Audio(objectUrl);
  current = audio;
  currentEnd = onEnd;
  audio.onended = () => {
    if (current === audio) current = null;
    currentEnd = null;
    onEnd();
  };
  try {
    await audio.play();
  } catch {
    current = null;
    currentEnd = null;
    throw new ApiError("blocked", "Your browser blocked playback. Tap the play button.", 0);
  }
}
