// Worker thread for reading compact recordings (bot/marketdata/compactRecording.ts mdcLines): takes one block's zstd
// frame, returns its text, so several blocks decode on other cores while the reader hands out lines. Bundled to
// dist/mdcWorker.cjs next to the bundled pipeline and trainer; under tsx it is loaded through research/workerDev.mjs.

import { parentPort } from 'worker_threads';
import { decodeFrameText } from './compactRecording';

parentPort?.on('message', (m: { id: number; frame: Uint8Array }) => {
  try {
    const { text, ascii } = decodeFrameText(Buffer.from(m.frame.buffer, m.frame.byteOffset, m.frame.byteLength));
    // A fresh copy owns its ArrayBuffer whole, so it can be handed over without copying again.
    const out = new Uint8Array(text.length); out.set(text);
    parentPort!.postMessage({ id: m.id, text: out, ascii }, [out.buffer]);
  } catch (e) {
    parentPort!.postMessage({ id: m.id, error: String((e as Error)?.stack ?? e) });
  }
});
