// Phone mode: the phone's microphone and speaker (the handset plugged into it) are the kiosk's
// handset. Over `/ws/audio` the phone sends 20 ms frames of 16 kHz 16-bit mono PCM (the Live
// API's input) while a conversation is on, and plays the 24 kHz PCM it gets back. "clear" from
// the laptop stops the playing at once (the customer interrupted). The phone reports how loud
// its speaker plays, `{"out": 0.4}`, for the assistant animation.
//
// The browser resamples: the microphone runs in a 16 kHz audio context, the speaker in a 24 kHz
// one. Chrome allows the microphone only over HTTPS, and sound only after a tap: `startPhoneAudio`
// must be called from the first tap.

export const MIC_RATE = 16000;
export const SPEAKER_RATE = 24000;
export const FRAME_SAMPLES = 320; // 20 ms at 16 kHz
const FULL_SCALE = 6000 / 32768; // as kiosk/voice/pcm.py: speech this loud is level 1
const LEVEL_EVERY_MS = 80;

/** Float samples (-1..1) as 16-bit PCM. */
export function toPcm16(samples: Float32Array): Int16Array<ArrayBuffer> {
  const pcm = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    pcm[i] = s < 0 ? Math.round(s * 32768) : Math.round(s * 32767);
  }
  return pcm;
}

/** 16-bit little-endian PCM as float samples (-1..1). */
export function fromPcm16(buffer: ArrayBuffer): Float32Array {
  const view = new DataView(buffer);
  const samples = new Float32Array(Math.floor(buffer.byteLength / 2));
  for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(i * 2, true) / 32768;
  return samples;
}

/** 0..1 loudness, as the laptop computes it. */
export function loudness(samples: Float32Array): number {
  if (!samples.length) return 0;
  let sum = 0;
  for (const s of samples) sum += s * s;
  return Math.min(1, Math.sqrt(sum / samples.length) / FULL_SCALE);
}

/** Collects the microphone's blocks (128 samples each in Chrome) into 20 ms frames. */
export class Framer {
  private buffer = new Float32Array(FRAME_SAMPLES);
  private filled = 0;

  push(samples: Float32Array): Int16Array<ArrayBuffer>[] {
    const frames: Int16Array<ArrayBuffer>[] = [];
    let from = 0;
    while (from < samples.length) {
      const take = Math.min(FRAME_SAMPLES - this.filled, samples.length - from);
      this.buffer.set(samples.subarray(from, from + take), this.filled);
      this.filled += take;
      from += take;
      if (this.filled === FRAME_SAMPLES) {
        frames.push(toPcm16(this.buffer));
        this.filled = 0;
      }
    }
    return frames;
  }

  reset(): void {
    this.filled = 0;
  }
}

// The two audio worklets, as source text (they run on the audio thread, outside the bundle).
const WORKLETS = `
class Capture extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
}
class Speaker extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.offset = 0;
    this.sum = 0;
    this.count = 0;
    this.port.onmessage = (event) => {
      if (event.data === 'clear') { this.queue = []; this.offset = 0; }
      else this.queue.push(event.data);
    };
  }
  process(inputs, outputs) {
    const out = outputs[0][0];
    let i = 0;
    while (i < out.length && this.queue.length) {
      const chunk = this.queue[0];
      const take = Math.min(out.length - i, chunk.length - this.offset);
      out.set(chunk.subarray(this.offset, this.offset + take), i);
      i += take;
      this.offset += take;
      if (this.offset >= chunk.length) { this.queue.shift(); this.offset = 0; }
    }
    out.fill(0, i);
    for (const s of out) this.sum += s * s;
    this.count += out.length;
    if (this.count >= sampleRate * ${LEVEL_EVERY_MS / 1000}) {
      this.port.postMessage(Math.sqrt(this.sum / this.count));
      this.sum = 0;
      this.count = 0;
    }
    return true;
  }
}
registerProcessor('kiosk-capture', Capture);
registerProcessor('kiosk-speaker', Speaker);
`;

export interface PhoneAudio {
  /** Send the microphone (while a conversation is on) or not. */
  setActive(active: boolean): void;
  close(): void;
}

/** Opens the microphone and the speaker and connects to the laptop. Call it from a tap. */
export async function startPhoneAudio(
  url = `wss://${location.host}/ws/audio`,
): Promise<PhoneAudio> {
  // Made before any await, so they count as started by the tap and may play sound.
  const micContext = new AudioContext({ sampleRate: MIC_RATE });
  const speakerContext = new AudioContext({ sampleRate: SPEAKER_RATE });
  const stream = await navigator.mediaDevices.getUserMedia({
    // A handset: its earpiece does not reach its microphone, so no echo cancellation.
    audio: {
      channelCount: 1,
      echoCancellation: false,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
  const module = URL.createObjectURL(new Blob([WORKLETS], { type: 'text/javascript' }));
  await Promise.all([
    micContext.audioWorklet.addModule(module),
    speakerContext.audioWorklet.addModule(module),
  ]);
  URL.revokeObjectURL(module);
  await Promise.all([micContext.resume(), speakerContext.resume()]);

  const capture = new AudioWorkletNode(micContext, 'kiosk-capture');
  micContext.createMediaStreamSource(stream).connect(capture);
  const speaker = new AudioWorkletNode(speakerContext, 'kiosk-speaker', {
    numberOfInputs: 0,
    outputChannelCount: [1],
  });
  speaker.connect(speakerContext.destination);

  let socket: WebSocket | null = null;
  let active = false;
  let closed = false;
  let retry = 500;
  let reported = -1;
  const framer = new Framer();
  const send = (data: ArrayBuffer | string) => {
    if (socket?.readyState === WebSocket.OPEN) socket.send(data);
  };

  capture.port.onmessage = (event: MessageEvent<Float32Array>) => {
    if (!active) return;
    for (const frame of framer.push(event.data)) send(frame.buffer);
  };
  speaker.port.onmessage = (event: MessageEvent<number>) => {
    const out = Math.round(Math.min(1, event.data / FULL_SCALE) * 100) / 100;
    if (out !== reported) {
      reported = out;
      send(JSON.stringify({ out }));
    }
  };

  const open = () => {
    socket = new WebSocket(url);
    socket.binaryType = 'arraybuffer';
    socket.onopen = () => {
      retry = 500;
      reported = -1;
    };
    socket.onmessage = (event: MessageEvent<ArrayBuffer | string>) => {
      if (typeof event.data === 'string') {
        if (event.data === 'clear') speaker.port.postMessage('clear');
        return;
      }
      const samples = fromPcm16(event.data);
      speaker.port.postMessage(samples, [samples.buffer]);
    };
    socket.onclose = () => {
      speaker.port.postMessage('clear');
      if (!closed) {
        setTimeout(open, retry);
        retry = Math.min(retry * 2, 5000);
      }
    };
  };
  open();

  return {
    setActive(on) {
      if (on === active) return;
      active = on;
      framer.reset();
      if (!on) speaker.port.postMessage('clear');
    },
    close() {
      closed = true;
      socket?.close();
      stream.getTracks().forEach((t) => t.stop());
      void micContext.close();
      void speakerContext.close();
    },
  };
}
