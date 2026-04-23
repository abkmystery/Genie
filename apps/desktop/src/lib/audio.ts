type BrowserSpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
};

interface SpeechRecognitionAlternativeLike {
  transcript: string;
}

interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: SpeechRecognitionAlternativeLike;
}

interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}

declare global {
  interface Window {
    SpeechRecognition?: new () => BrowserSpeechRecognition;
    webkitSpeechRecognition?: new () => BrowserSpeechRecognition;
  }
}

export function formatSeconds(seconds: number) {
  const rounded = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

export function formatActivityTimer(session: {
  started_at: string;
  requested_duration_seconds: number;
}) {
  const startedAt = session.started_at ? new Date(session.started_at).getTime() : Date.now();
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const maxSeconds = Math.max(1, Math.floor(session.requested_duration_seconds || 60));
  return `${formatSeconds(Math.min(elapsedSeconds, maxSeconds))} / ${formatSeconds(maxSeconds)}`;
}

export function looksLikeBase64Audio(value: string): boolean {
  return value.length > 128 && /^[A-Za-z0-9+/=]+$/.test(value);
}

export function sanitizeSpeechText(value: string): string {
  return value
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

export function startBrowserSpeechRecognition({
  maxSeconds,
  onProgress,
}: {
  maxSeconds: number;
  onProgress?: (seconds: number) => void;
}): { stop(): void; result: Promise<string> } | null {
  const SpeechRecognitionCtor = window.SpeechRecognition ?? window.webkitSpeechRecognition;
  if (!SpeechRecognitionCtor) {
    return null;
  }

  const recognition = new SpeechRecognitionCtor();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";
  recognition.maxAlternatives = 1;

  const cappedSeconds = Math.max(1, Math.min(30, Math.floor(maxSeconds)));
  let transcript = "";
  let finished = false;
  const startedAt = performance.now();
  let progressTimer = 0;
  let stopTimer = 0;

  const cleanup = () => {
    if (progressTimer) window.clearInterval(progressTimer);
    if (stopTimer) window.clearTimeout(stopTimer);
  };

  const result = new Promise<string>((resolve, reject) => {
    recognition.onresult = (event) => {
      let nextTranscript = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const resultItem = event.results[index];
        const segment = resultItem?.[0]?.transcript ?? "";
        if (resultItem?.isFinal) {
          transcript += `${segment} `;
        } else {
          nextTranscript += segment;
        }
      }
      if (nextTranscript.trim()) {
        transcript = `${transcript}${nextTranscript}`.trim();
      }
      onProgress?.(Math.min(cappedSeconds, (performance.now() - startedAt) / 1000));
    };

    recognition.onerror = (event) => {
      if (finished) return;
      finished = true;
      cleanup();
      reject(new Error(event.error || "Speech recognition failed."));
    };

    recognition.onend = () => {
      if (finished) return;
      finished = true;
      cleanup();
      const elapsedSeconds = (performance.now() - startedAt) / 1000;
      if (!transcript.trim() && elapsedSeconds < 1.2) {
        reject(new Error("Speech recognition ended too quickly."));
        return;
      }
      resolve(transcript.trim());
    };
  });

  progressTimer = window.setInterval(() => {
    onProgress?.(Math.min(cappedSeconds, (performance.now() - startedAt) / 1000));
  }, 200);

  stopTimer = window.setTimeout(() => {
    try {
      recognition.stop();
    } catch {
      cleanup();
    }
  }, cappedSeconds * 1000);

  recognition.start();

  return {
    stop() {
      try {
        recognition.stop();
      } catch {
        cleanup();
      }
    },
    result,
  };
}

export function startWavRecording({
  maxSeconds,
  onProgress,
}: {
  maxSeconds: number;
  onProgress?: (seconds: number) => void;
}): { stop(): void; result: Promise<string> } {
  const cappedSeconds = Math.max(1, Math.min(30, Math.floor(maxSeconds)));
  let stopSignalResolve: (() => void) | null = null;
  const stopSignal = new Promise<void>((resolve) => {
    stopSignalResolve = resolve;
  });
  let stopped = false;

  const stop = () => {
    if (stopped) return;
    stopped = true;
    stopSignalResolve?.();
  };

  const startedAt = performance.now();
  const tickTimer = window.setInterval(() => {
    const seconds = (performance.now() - startedAt) / 1000;
    onProgress?.(Math.min(cappedSeconds, seconds));
    if (seconds >= cappedSeconds) stop();
  }, 200);

  const result = (async () => {
    let stream: MediaStream | null = null;
    let audioContext: AudioContext | null = null;
    let source: MediaStreamAudioSourceNode | null = null;
    let processor: ScriptProcessorNode | null = null;
    const chunks: Float32Array[] = [];

    const cleanup = async () => {
      try {
        processor?.disconnect();
      } catch {
        // ignore
      }
      try {
        source?.disconnect();
      } catch {
        // ignore
      }
      try {
        stream?.getTracks().forEach((track) => track.stop());
      } catch {
        // ignore
      }
      try {
        await audioContext?.close();
      } catch {
        // ignore
      }
    };

    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioContext = new AudioContext();
      source = audioContext.createMediaStreamSource(stream);
      processor = audioContext.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0);
        chunks.push(new Float32Array(input));
      };
      source.connect(processor);
      processor.connect(audioContext.destination);

      window.setTimeout(() => stop(), cappedSeconds * 1000 + 1000);
      await stopSignal;

      const sampleRate = audioContext.sampleRate || 48000;
      await cleanup();

      const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const pcm = new Float32Array(length);
      let offset = 0;
      for (const chunk of chunks) {
        pcm.set(chunk, offset);
        offset += chunk.length;
      }
      return bytesToBase64(encodeWavMono(pcm, sampleRate));
    } finally {
      window.clearInterval(tickTimer);
      await cleanup();
    }
  })();

  return { stop, result };
}

function encodeWavMono(samples: Float32Array, sampleRate: number): Uint8Array {
  const numChannels = 1;
  const bytesPerSample = 2;
  const blockAlign = numChannels * bytesPerSample;
  const byteRate = sampleRate * blockAlign;
  const dataSize = samples.length * bytesPerSample;

  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    offset += 2;
  }

  return new Uint8Array(buffer);
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}
