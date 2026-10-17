/** In-app hands-free capture: getUserMedia + WebAudio VAD + MediaRecorder.
 *  Same arm -> speech-start -> silence-stop state machine as the Python companion. */

import type { VBSettings } from "./types";

export type CaptureState = "armed" | "recording" | "timeout" | "done" | "cancelled";

export interface CaptureResult {
  state: CaptureState;
  blob: Blob | null;
}

export class CaptureCancelled extends Error {}

export async function captureWithVad(
  s: VBSettings,
  onState: (state: CaptureState, level: number) => void,
): Promise<CaptureResult> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true },
  });

  const ctx = new AudioContext({ sampleRate: 48000 });
  await ctx.resume();
  const source = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  source.connect(analyser);

  const silenceFrames = Math.max(1, Math.round(s.captureSilenceMs / 50));
  const maxMs = s.captureMaxS * 1000;

  const recorder = new MediaRecorder(stream);
  const chunks: BlobPart[] = [];
  let recording = false;
  let armedSince = Date.now();
  const armTimeoutMs = 15000;

  return new Promise<CaptureResult>((resolve) => {
    const buf = new Float32Array(analyser.fftSize);
    let quietStreak = 0;
    let stopped = false;

    const cleanup = (result: CaptureResult) => {
      if (stopped) return;
      stopped = true;
      try { recorder.state !== "inactive" && recorder.stop(); } catch { /* ignore */ }
      stream.getTracks().forEach((t) => t.stop());
      ctx.close().catch(() => {});
      onState(result.state, 0);
      resolve(result);
    };

    const tick = () => {
      if (stopped) return;
      analyser.getFloatTimeDomainData(buf);
      let acc = 0;
      for (const v of buf) acc += v * v;
      const rms = Math.sqrt(acc / buf.length);
      const loud = rms >= s.captureVadRms;

      if (!recording) {
        if (loud) {
          // speech detected — start the recorder NOW (MediaRecorder includes the
          // last fraction of a second from its own internal buffer)
          recording = true;
          recorder.start();
          onState("recording", Math.min(1, rms * 4));
        } else if (Date.now() - armedSince > armTimeoutMs) {
          cleanup({ state: "timeout", blob: null });
          return;
        } else {
          onState("armed", Math.min(1, rms * 4));
        }
      } else {
        onState("recording", Math.min(1, rms * 4));
        quietStreak = loud ? 0 : quietStreak + 1;
        if (quietStreak >= silenceFrames) {
          recorder.onstop = () => {
            cleanup({ state: "done", blob: new Blob(chunks, { type: recorder.mimeType }) });
          };
          recorder.stop();
          return;
        }
        if (Date.now() - armedSince > maxMs) {
          recorder.onstop = () => {
            cleanup({ state: "done", blob: new Blob(chunks, { type: recorder.mimeType }) });
          };
          recorder.stop();
          return;
        }
      }
      setTimeout(tick, 50);
    };

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };

    onState("armed", 0);
    tick();
  });
}
