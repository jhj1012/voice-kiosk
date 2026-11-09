// The handset's button on the phone (phone mode). Android sends a headset button press to the
// app playing sound as play / pause; Chrome hands it to the page through the Media Session API,
// but only while the page plays sound with an <audio> element (the assistant's voice is Web
// Audio). So a silent loop plays from the first tap on. Measured on the team's phone (?buttons):
// one press is `pause` (also while the microphone is on), a double press `nexttrack`, a long
// press nothing more. Unplugging the handset pauses the loop: it is played again at once.

/** 10 s of 16-bit mono WAV at 8 kHz: silence, or noise far below hearing (-66 dB). */
export function loopWav(noise = false, random: () => number = Math.random): ArrayBuffer {
  const rate = 8000;
  const samples = rate * 10;
  const data = new DataView(new ArrayBuffer(44 + samples * 2));
  const text = (at: number, s: string) =>
    [...s].forEach((c, i) => data.setUint8(at + i, c.charCodeAt(0)));
  text(0, 'RIFF');
  data.setUint32(4, 36 + samples * 2, true);
  text(8, 'WAVEfmt ');
  data.setUint32(16, 16, true);
  data.setUint16(20, 1, true); // PCM
  data.setUint16(22, 1, true); // mono
  data.setUint32(24, rate, true);
  data.setUint32(28, rate * 2, true);
  data.setUint16(32, 2, true);
  data.setUint16(34, 16, true);
  text(36, 'data');
  data.setUint32(40, samples * 2, true);
  for (let i = 0; i < samples; i++) {
    data.setInt16(44 + i * 2, noise ? Math.round((random() - 0.5) * 32) : 0, true);
  }
  return data.buffer;
}

/** Plays `loopWav` on repeat. Call it from a tap: Chrome starts sound only after one. */
export function playLoop(noise = false): HTMLAudioElement {
  const audio = new Audio(URL.createObjectURL(new Blob([loopWav(noise)], { type: 'audio/wav' })));
  audio.loop = true;
  void audio.play().catch((error) => console.warn('the silent loop did not start', error));
  return audio;
}

/** Lets one press through, then none for `gapMs` (a press may arrive as more than one action). */
export function pressGate(gapMs: number, now: () => number = () => performance.now()) {
  let last = -Infinity;
  return (): boolean => {
    const at = now();
    if (at - last < gapMs) return false;
    last = at;
    return true;
  };
}

interface Playable {
  readonly paused: boolean;
  play(): Promise<void>;
  addEventListener(type: 'pause', listener: () => void): void;
}

/** Plays `audio` again whenever it stops: Android pauses it when the handset is unplugged (and
 * another app may take the sound), and a paused page gets no button presses: the next press
 * then starts the last music app instead. Checked every `everyMs` as well. The page had a tap,
 * so Chrome lets it play again without one. */
export function keepPlaying(
  audio: Playable,
  everyMs = 2000,
  every: (run: () => void, ms: number) => void = (run, ms) => void setInterval(run, ms),
): () => void {
  const resume = () => {
    if (audio.paused) void audio.play().catch(() => {}); // the next check tries again
  };
  audio.addEventListener('pause', () => setTimeout(resume, 300));
  every(resume, everyMs);
  return resume;
}

let resumeLoop: (() => void) | null = null;

/** From a tap on: a press of the handset's button (one press, not a double one) calls `onPress`. */
export function startMediaButton(onPress: () => void): void {
  const loop = playLoop();
  resumeLoop = keepPlaying(loop);
  navigator.mediaDevices?.addEventListener('devicechange', resumeLoop); // plugged in again
  const session = navigator.mediaSession;
  if (!session) return;
  session.metadata = new MediaMetadata({ title: '음성 키오스크', artist: 'voice-kiosk' });
  session.playbackState = 'playing';
  const pass = pressGate(800);
  for (const action of ['play', 'pause'] as const) {
    // the loop keeps playing, so the next press is a pause again; a `play` means it had stopped
    session.setActionHandler(action, () => {
      resumeLoop?.();
      session.playbackState = 'playing';
      if (pass()) onPress();
    });
  }
}

/** A tap on the screen: plays the silent loop again if it stopped (a tap always may). */
export function resumeMediaButton(): void {
  resumeLoop?.();
}
