/* Test harness: extracts the marked blocks out of fet_fom.html and loads the
 * goldens.  The regex extractor is the single point of failure of this whole
 * scheme, which is why markers.test.mjs exercises it separately. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(__dirname, '..');
export const HTML = fs.readFileSync(path.join(ROOT, 'fet_fom.html'), 'utf8');

export function extractBlock(html, name) {
  const re = new RegExp(
    '/\\* ==== ' + name + ' BEGIN ==== \\*/([\\s\\S]*?)/\\* ==== ' + name + ' END ==== \\*/');
  const m = html.match(re);
  if (!m) throw new Error('marker block ' + name + ' not found or unbalanced');
  return m[1];
}

export function loadEngine(html = HTML) {
  const src = extractBlock(html, 'ENGINE');
  (0, eval)(src);                       // indirect eval -> global scope
  if (!globalThis.FOMENGINE) throw new Error('ENGINE block did not define FOMENGINE');
  return globalThis.FOMENGINE;
}

export function loadJSON(...p) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, ...p), 'utf8'));
}

/* Approximate deep comparison.  null in the goldens means the oracle value was
 * NaN/Inf (JSON cannot carry those), so null matches null or a non-finite. */
export function assertClose(actual, expected, where = '', rel = 1e-9, abs = 1e-12) {
  if (expected === null || expected === undefined) {
    if (actual === null || actual === undefined) return;
    if (typeof actual === 'number' && !Number.isFinite(actual)) return;
    throw new Error(where + ': expected null/NaN, got ' + actual);
  }
  if (typeof expected === 'number') {
    if (typeof actual !== 'number' || !Number.isFinite(actual))
      throw new Error(where + ': expected ' + expected + ', got ' + actual);
    const tol = rel * Math.max(1, Math.abs(expected)) + abs;
    if (Math.abs(actual - expected) > tol)
      throw new Error(where + ': expected ' + expected + ', got ' + actual +
                      ' (delta ' + Math.abs(actual - expected) + ')');
    return;
  }
  if (typeof expected === 'string' || typeof expected === 'boolean') {
    if (actual !== expected) throw new Error(where + ': expected ' + expected + ', got ' + actual);
    return;
  }
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual) || actual.length !== expected.length)
      throw new Error(where + ': expected array of ' + expected.length + ', got ' + (actual && actual.length));
    expected.forEach((v, i) => assertClose(actual[i], v, where + '[' + i + ']', rel, abs));
    return;
  }
  if (typeof expected === 'object') {
    if (actual === null || typeof actual !== 'object')
      throw new Error(where + ': expected object, got ' + actual);
    for (const k of Object.keys(expected)) assertClose(actual[k], expected[k], where + '.' + k, rel, abs);
    return;
  }
  throw new Error(where + ': unsupported expected type ' + typeof expected);
}
