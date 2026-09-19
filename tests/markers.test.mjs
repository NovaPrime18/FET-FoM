/* Marker-integrity tests.
 *
 * tests/_harness.mjs extracts the engine out of the HTML with a regex, so a
 * stray, duplicated or unbalanced marker silently yields an empty or truncated
 * engine -- and every other test would then pass vacuously or fail confusingly.
 * This is the single point of failure of the whole extraction scheme, so it is
 * tested directly.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { HTML, extractBlock, loadEngine, ROOT } from './_harness.mjs';

const BLOCKS = ['ENGINE', 'UI', 'PARTS', 'MAGPARTS'];

function count(src, needle) {
  let n = 0, i = 0;
  for (;;) {
    const k = src.indexOf(needle, i);
    if (k < 0) return n;
    n++; i = k + needle.length;
  }
}

test('every marker appears exactly once, and BEGIN precedes END', () => {
  for (const b of BLOCKS) {
    const begin = '/* ==== ' + b + ' BEGIN ==== */';
    const end = '/* ==== ' + b + ' END ==== */';
    assert.equal(count(HTML, begin), 1, b + ' BEGIN must appear exactly once');
    assert.equal(count(HTML, end), 1, b + ' END must appear exactly once');
    assert.ok(HTML.indexOf(begin) < HTML.indexOf(end), b + ' BEGIN must precede END');
  }
});

test('markers are balanced in order and do not interleave', () => {
  const order = [];
  for (const m of HTML.matchAll(/\/\* ==== (\w+) (BEGIN|END) ==== \*\//g)) order.push(m[1] + ':' + m[2]);
  assert.deepEqual(order, [
    'ENGINE:BEGIN', 'PARTS:BEGIN', 'PARTS:END',
    'MAGPARTS:BEGIN', 'MAGPARTS:END', 'ENGINE:END',
    'UI:BEGIN', 'UI:END',
  ], 'marker nesting/order changed unexpectedly: ' + order.join(' '));
});

test('PARTS and MAGPARTS are both nested inside ENGINE', () => {
  const e0 = HTML.indexOf('/* ==== ENGINE BEGIN ==== */');
  const e1 = HTML.indexOf('/* ==== ENGINE END ==== */');
  for (const b of ['PARTS', 'MAGPARTS']) {
    const p0 = HTML.indexOf('/* ==== ' + b + ' BEGIN ==== */');
    const p1 = HTML.indexOf('/* ==== ' + b + ' END ==== */');
    assert.ok(e0 < p0 && p1 < e1, b + ' block must sit inside the ENGINE block');
  }
});

test('no extracted block contains a literal closing script tag', () => {
  for (const b of BLOCKS) {
    assert.ok(!extractBlock(HTML, b).includes('</script'),
      b + ' block contains </script and would truncate the HTML parse');
  }
});

test('extraction fails loudly on an unbalanced marker instead of silently returning empty', () => {
  const broken = fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', 'broken.html'), 'utf8');
  assert.throws(() => extractBlock(broken, 'ENGINE'), /not found or unbalanced/);
});

test('the ENGINE block evaluates and exposes the documented API', () => {
  const E = loadEngine();
  const api = ['computeLosses', 'fomMetrics', 'derive', 'gateConfig', 'deadVsd', 'rcsiOf',
               'sweepFsw', 'optimizeN', 'compare', 'defaultOp', 'profileFor',
               'svpwmRipple', 'ripIrms', 'ripIpp', 'ripRequiredL',
               'fitInductorLoss', 'inductorFit', 'inductorAcLoss', 'inductorDcLoss',
               'inductorFitRange', 'dcRequiredL',
               'satCurve', 'satInductance', 'inductorRise', 'applySaturation',
               'capBank', 'triHarmPeak', 'smoothCapLoss', 'capNodes', 'capNodeResult', 'capRequired',
               'motorDerive', 'lehnerOpPoint', 'motorLosses', 'dowellFr', 'skinFr', 'lamEddyFactor',
               'dcLinkCurrent', 'stageSystem', 'sweepStage', 'feasibility',
               'qossRef', 'eossRef', 'qossAt', 'eossAt'];
  for (const k of api) assert.equal(typeof E[k], 'function', 'FOMENGINE.' + k + ' must be a function');
  assert.equal(E.schemaVersion, 2);
  // Every topology must declare what its magnetics ARE, because the design
  // workspace has no free "load model" selector to fall back on.
  for (const t of ['threephase', 'buck', 'boost', 'fourswitch']) {
    const p = E.profileFor(t, 'buck');
    assert.ok(p, 'no magnetics profile for ' + t);
    assert.ok(['svpwm', 'derive'].includes(p.ripple), t + ' declares no ripple model');
    assert.ok(p.caps && Object.keys(p.caps).length, t + ' declares no capacitor nodes');
  }
  assert.ok(Object.keys(E.PARTS).length >= 12, 'expected the twelve seeded parts');
  for (const t of ['threephase', 'buck', 'boost', 'fourswitch'])
    assert.ok(E.TOPOLOGIES.includes(t), 'missing topology ' + t);
});

test('the UI block is wired to the engine rather than a second implementation', () => {
  const ui = extractBlock(HTML, 'UI');
  assert.ok(/FOMENGINE/.test(ui), 'UI must reference the extracted engine');
  assert.ok(!/function\s+computeLosses/.test(ui), 'UI must not re-implement the loss model');
});

test('the page needs no server, no network and no build step', () => {
  assert.ok(!/<script[^>]+src=/i.test(HTML), 'no external script tags allowed');
  assert.ok(!/<link[^>]+href=["']https?:/i.test(HTML), 'no external stylesheets allowed');
  assert.ok(!/fetch\s*\(|XMLHttpRequest|import\s*\(/.test(HTML), 'no network calls allowed');
  assert.ok(!/require\s*\(|module\.exports/.test(HTML), 'no module system at runtime');
});

/* Layout invariants that only exist in the stylesheet, so jsdom's computed-style
   support (which is partial) is not a reliable place to test them. */
test('number columns use tabular figures so decimal points line up down a column', () => {
  assert.match(HTML, /table\{[^}]*font-variant-numeric:tabular-nums/,
    'the comparison tables must set font-variant-numeric: tabular-nums');
});

test('the bars have a fixed-width track anchored at zero', () => {
  assert.match(HTML, /\.track-bg\{[^}]*width:110px/,
    'the track must have a fixed width independent of the number text');
  assert.match(HTML, /\.track-bg>span\{[^}]*background:var\(--a\)/,
    'the fill must be anchored to the left of its track');
  assert.match(HTML, /\.track-bg>span\.b\{[^}]*background:var\(--b\)/,
    'device B needs its own fill colour');
});

test('one colour per device, used for bars and chart traces alike', () => {
  assert.match(HTML, /--a:#4aa3ff/, 'device A colour missing');
  assert.match(HTML, /--b:#ff9f43/, 'device B colour missing');
});

test('the hero puts the schematic and the KPI panel at a shared row height', () => {
  assert.match(HTML, /\.hero\{[^}]*align-items:stretch/,
    'hero cells must stretch to one row height, not merely centre against each other');
  assert.match(HTML, /\.topo\{[^}]*display:flex/,
    'the schematic box must be a flex column so the drawing can fill it');
  assert.match(HTML, /\.topo svg\{[^}]*height:100%/,
    'the schematic should fill its box rather than keep a fixed intrinsic height');
});

test('the help-badge rule is scoped so it cannot match a warning card', () => {
  // `.info { display:inline-flex; width:15px }` applied to `div.wcard.info`
  // collapsed the card into a 15px blob.  Scope the badge to spans, and keep
  // severity modifiers namespaced.
  assert.match(HTML, /span\.info\{/, 'the help badge must be scoped to span.info');
  assert.ok(!/[^-\w]\.info\{/.test(HTML), 'an unscoped .info rule exists');
  assert.match(HTML, /\.wcard\.sev-info\{/, 'severity modifiers must be namespaced');
  assert.ok(!/\.wcard\.info\{/.test(HTML), 'the colliding .wcard.info rule is back');
});

test('the tooltip layer is fixed, above content, and ignores the pointer', () => {
  assert.match(HTML, /#tip\{[^}]*position:fixed/, 'tooltip must be positioned, not in flow');
  assert.match(HTML, /#tip\{[^}]*z-index:9999/, 'tooltip must sit above the page');
  assert.match(HTML, /#tip\{[^}]*pointer-events:none/, 'tooltip must never intercept the pointer');
  assert.match(HTML, /#tip\{[^}]*max-width:340px/, 'tooltip needs a bounded width so it wraps');
  assert.match(HTML, /#tip\{[^}]*white-space:pre-line/, 'tooltip must honour its own line breaks');
});

test('the three comparison sections are separated by dividers', () => {
  assert.match(HTML, /\.tbl-h\{[^}]*border-top:1px solid var\(--line\)/,
    'section headings need a divider to break the blocks apart');
  assert.match(HTML, /\.tbl-h:first-child\{[^}]*border-top:0/,
    'the first section heading should not carry a leading divider');
});
