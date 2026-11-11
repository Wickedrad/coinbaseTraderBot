// A tiny NPY v1.0 writer (and a reader for tests) for the oracle-setups part directories (python/oracle/SPEC.md
// section 1: plain .npy arrays, numpy format v1.0, little-endian, C order). The miner loads them with np.load(mmap_mode='r').
//
// Format: magic "\x93NUMPY", version 1 0, a little-endian uint16 header length, then the header dict
// "{'descr': '<f4', 'fortran_order': False, 'shape': (n, F), }" padded with spaces and ended by '\n' so the data starts at
// a multiple of 64 bytes, then the raw little-endian data in C order. Large arrays are streamed in row blocks
// (NpyWriter): the shape is fixed up front and the writer checks that exactly that many elements arrive.

import fs from 'fs';
import os from 'os';
import path from 'path';

export type Dtype = 'int8' | 'uint8' | 'int16' | 'uint16' | 'int32' | 'int64' | 'float32' | 'float64';
export type Typed = Int8Array | Uint8Array | Int16Array | Uint16Array | Int32Array | BigInt64Array | Float32Array | Float64Array;

export const DESCR: Record<Dtype, string> = { int8: '|i1', uint8: '|u1', int16: '<i2', uint16: '<u2', int32: '<i4', int64: '<i8', float32: '<f4', float64: '<f8' };
const BYTES: Record<Dtype, number> = { int8: 1, uint8: 1, int16: 2, uint16: 2, int32: 4, int64: 8, float32: 4, float64: 8 };
const CTOR = { int8: Int8Array, uint8: Uint8Array, int16: Int16Array, uint16: Uint16Array, int32: Int32Array, int64: BigInt64Array, float32: Float32Array, float64: Float64Array } as const;

if (os.endianness() !== 'LE') throw new Error('npy.ts writes typed-array memory as little-endian: big-endian hosts are not supported');

/** The dtype a typed array holds. */
export function dtypeOf(a: Typed): Dtype {
  for (const [k, C] of Object.entries(CTOR)) if (a instanceof C) return k as Dtype;
  throw new Error('npy: unsupported array type');
}

/** A typed array of `dtype` from plain numbers (int64 from integer-valued numbers, e.g. epoch ms). */
export function typed(dtype: Dtype, xs: ArrayLike<number>): Typed {
  if (dtype === 'int64') {
    const out = new BigInt64Array(xs.length);
    for (let i = 0; i < xs.length; i++) { const v = xs[i]; if (!Number.isSafeInteger(v)) throw new Error(`npy int64: ${v} is not a safe integer`); out[i] = BigInt(v); }
    return out;
  }
  return CTOR[dtype].from(xs as ArrayLike<number>) as Typed;
}

/** The full NPY v1.0 preamble (magic, version, length, padded dict) for a C-order array. */
export function npyHeader(dtype: Dtype, shape: number[]): Buffer {
  if (!shape.length || shape.length > 2) throw new Error(`npy: only 1-D and 2-D arrays (shape ${JSON.stringify(shape)})`);
  for (const d of shape) if (!Number.isSafeInteger(d) || d < 0) throw new Error(`npy: bad dimension ${d}`);
  const shp = shape.length === 1 ? `(${shape[0]},)` : `(${shape.join(', ')})`;
  const dict = `{'descr': '${DESCR[dtype]}', 'fortran_order': False, 'shape': ${shp}, }`;
  const pre = 10; // magic 6 + version 2 + uint16 length 2
  const total = Math.ceil((pre + dict.length + 1) / 64) * 64;
  const hlen = total - pre;
  if (hlen > 65535) throw new Error('npy: header too long for v1.0');
  const b = Buffer.alloc(total, 0x20);
  b[0] = 0x93; b.write('NUMPY', 1, 'latin1'); b[6] = 1; b[7] = 0; b.writeUInt16LE(hlen, 8);
  b.write(dict, pre, 'latin1');
  b[total - 1] = 0x0a;
  return b;
}

const bytesOf = (a: Typed) => Buffer.from(a.buffer, a.byteOffset, a.byteLength);

/** Streams one array to disk: the shape is known up front, data arrives in C-order chunks (row blocks of a 2-D array).
 *  Written to <file>.tmp and renamed on close, so a crash never leaves a short file under the final name. */
export class NpyWriter {
  private fd: number;
  private left: number;
  private readonly tmp: string;
  constructor(readonly file: string, readonly dtype: Dtype, readonly shape: number[]) {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    this.tmp = `${file}.tmp`;
    this.fd = fs.openSync(this.tmp, 'w');
    const h = npyHeader(dtype, shape);
    fs.writeSync(this.fd, h);
    this.left = shape.reduce((a, d) => a * d, 1);
  }
  /** Appends a chunk (its dtype must match; pass a subarray to write part of a reused buffer). */
  write(chunk: Typed): void {
    if (dtypeOf(chunk) !== this.dtype) throw new Error(`npy ${this.file}: chunk ${dtypeOf(chunk)} != ${this.dtype}`);
    if (chunk.length > this.left) throw new Error(`npy ${this.file}: ${chunk.length} elements, only ${this.left} left`);
    const b = bytesOf(chunk);
    let off = 0;
    while (off < b.length) off += fs.writeSync(this.fd, b, off, b.length - off);
    this.left -= chunk.length;
  }
  close(): void {
    fs.closeSync(this.fd);
    if (this.left !== 0) { fs.rmSync(this.tmp, { force: true }); throw new Error(`npy ${this.file}: ${this.left} elements missing`); }
    fs.renameSync(this.tmp, this.file);
  }
}

/** Writes a whole array (1-D by default; pass shape [n, F] for a 2-D C-order array). */
export function writeNpy(file: string, a: Typed, shape: number[] = [a.length]): void {
  const w = new NpyWriter(file, dtypeOf(a), shape);
  w.write(a);
  w.close();
}

export interface Npy { dtype: Dtype; shape: number[]; fortran: boolean; dataOffset: number; data: Typed }

/** Parses an .npy file written by numpy or by this module (v1.0 / v2.0, little-endian, the dtypes above). */
export function readNpy(file: string): Npy {
  const buf = fs.readFileSync(file);
  if (buf[0] !== 0x93 || buf.toString('latin1', 1, 6) !== 'NUMPY') throw new Error(`${file}: not an .npy file`);
  const major = buf[6];
  const hlen = major === 1 ? buf.readUInt16LE(8) : buf.readUInt32LE(8);
  const start = major === 1 ? 10 : 12;
  const dict = buf.toString('latin1', start, start + hlen);
  const descr = /'descr':\s*'([^']+)'/.exec(dict)?.[1];
  const fortran = /'fortran_order':\s*True/.test(dict);
  const shapeS = /'shape':\s*\(([^)]*)\)/.exec(dict)?.[1] ?? '';
  const shape = shapeS.split(',').map((s) => s.trim()).filter(Boolean).map(Number);
  const dtype = (Object.keys(DESCR) as Dtype[]).find((k) => DESCR[k] === descr || (BYTES[k] === 1 && descr?.slice(1) === DESCR[k].slice(1)));
  if (!dtype) throw new Error(`${file}: unsupported descr ${descr}`);
  const dataOffset = start + hlen, count = shape.reduce((a, d) => a * d, 1);
  const bytes = buf.subarray(dataOffset, dataOffset + count * BYTES[dtype]);
  if (bytes.length !== count * BYTES[dtype]) throw new Error(`${file}: truncated (${bytes.length} of ${count * BYTES[dtype]} bytes)`);
  const copy = new Uint8Array(bytes.length); copy.set(bytes); // aligned copy
  const data = new CTOR[dtype](copy.buffer, 0, count) as Typed;
  return { dtype, shape, fortran, dataOffset, data };
}
