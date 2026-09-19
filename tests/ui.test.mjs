/* Headless UI smoke test.
 *
 * The other suites only prove the ENGINE block is correct and that the UI block
 * parses.  This one actually executes the page in a DOM and checks it renders,
 * which is the closest thing to acceptance criterion 1 ("double-click it and it
 * works") that can run without a browser.
 *
 * jsdom is NOT a dependency of the product -- the tool is a single offline HTML
 * file with no runtime deps.  So this test skips cleanly when jsdom is absent;
 * install it locally (npm i --no-save jsdom, or NODE_PATH=... ) to run it.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { HTML, assertClose } from './_harness.mjs';

let JSDOM = null, importErr = '';
try {
  ({ JSDOM } = await import('jsdom'));
} catch (e) {
  importErr = e.message;
}

function boot() {
  const errors = [];
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    url: 'file:///fet_fom/fet_fom.html',
  });
  dom.window.addEventListener('error', e => errors.push(e.message || String(e.error)));
  dom.virtualConsole.on('jsdomError', e => errors.push('jsdomError: ' + (e.message || e)));
  return { dom, w: dom.window, errors };
}

/* Boot on the DeviceFOM.m reference point (58 V bus, 165.4 A rms, 40 kHz) with
   the seeded silicon part, driven through the URL hash rather than the page's
   own default scenario -- so a test that needs the reference behaviour (the
   IRF7759 runaway sweep, the L_loop = 0 row, the warning cards) keeps it
   whatever scenario the page happens to open on.  extraOp merges over the
   operating point. */
function bootReference(extraOp) {
  const scenario = encodeURIComponent(JSON.stringify({
    t: 'threephase',
    o: Object.assign({ Vdc: 58, Irms: 165.4, M: 1, PF: 0.9, fsw: 40000 }, extraOp || {}),
    a: 'EPC2361', b: 'IRF7759',
  }));
  const errors = [];
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    url: 'file:///fet_fom/fet_fom.html#' + scenario,
  });
  dom.window.addEventListener('error', e => errors.push(e.message || String(e.error)));
  dom.virtualConsole.on('jsdomError', e => errors.push('jsdomError: ' + (e.message || e)));
  return { dom, w: dom.window, errors };
}

/* saveHash() writes through history.replaceState, and jsdom refuses to apply a
   hash-only update to a file:// URL (it can only retarget http(s) history).  So
   capture the argument instead of reading location.hash back: this still runs
   the real saveHash path, and file:// is the deployment that matters. */
function bootHashed(hash) {
  const seen = [], errors = [];
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    url: 'file:///fet_fom/fet_fom.html' + (hash || ''),
    beforeParse(w) {
      const orig = w.history.replaceState.bind(w.history);
      w.history.replaceState = function (a, b, u) {
        seen.push(String(u));
        try { return orig(a, b, u); } catch (e) { /* jsdom's file:// limitation */ }
      };
    },
  });
  dom.window.addEventListener('error', e => errors.push(e.message || String(e.error)));
  dom.virtualConsole.on('jsdomError', e => errors.push('jsdomError: ' + (e.message || e)));
  const w = dom.window;
  return { dom, w, errors, lastHash: () => decodeURIComponent(seen[seen.length - 1] || '') };
}

/* jsdom cannot populate a real FileList, but the handler only reads files[0],
   so a defined-property array is enough to drive the real import path. */
function importFile(w, text, name = 'import.json') {
  const inp = w.document.getElementById('imp');
  const file = new w.File([text], name, { type: 'application/json' });
  Object.defineProperty(inp, 'files', { value: [file], configurable: true });
  inp.dispatchEvent(new w.Event('change'));
  return new Promise(res => {
    const t0 = Date.now();
    (function poll() {
      // the handler is async (FileReader); wait for alert() or a short timeout
      if (w.__alerts.length || Date.now() - t0 > 2000) return res();
      setTimeout(poll, 10);
    })();
  });
}

function readBlob(w, blob) {
  return new Promise((res, rej) => {
    const r = new w.FileReader();
    r.onload = () => res(r.result);
    r.onerror = () => rej(new Error('FileReader failed'));
    r.readAsText(blob);
  });
}

/* Capture what download() would have written, without touching the filesystem. */
function captureExport(w, btnId) {
  let captured = null;
  const saveCreate = w.URL.createObjectURL;
  const saveRevoke = w.URL.revokeObjectURL;
  const saveClick = w.HTMLAnchorElement.prototype.click;
  w.URL.createObjectURL = b => { captured = b; return 'blob:captured'; };
  w.URL.revokeObjectURL = () => {};
  w.HTMLAnchorElement.prototype.click = function () {};
  try {
    w.document.getElementById(btnId).dispatchEvent(new w.Event('click'));
  } finally {
    w.URL.createObjectURL = saveCreate;
    w.URL.revokeObjectURL = saveRevoke;
    w.HTMLAnchorElement.prototype.click = saveClick;
  }
  return captured;
}

function bootWithAlerts() {
  const b = boot();
  b.w.__alerts = [];
  b.w.alert = m => b.w.__alerts.push(String(m));
  return b;
}

test('UI: page boots and renders the A/B breakdown with no script errors',
  { skip: JSDOM ? false : 'jsdom not installed (' + importErr + ')' }, () => {
    const { w, errors } = boot();
    assert.deepEqual(errors, [], 'page raised script errors');
    const d = w.document;

    const header = d.getElementById('hdrstat').textContent;
    assert.match(header, /topologies/);
    assert.match(header, /schemaVersion 2/);

    // the three views
    const res = d.getElementById('results').textContent;
    assert.match(res, /Shared build/, 'view 1 (shared N) missing');
    assert.match(res, /its own N/, 'view 2 (each at own Nopt) missing');
    assert.match(res, /N-invariant/, 'view 3 (FOM) missing');
    assert.match(res, /Conduction/);
    assert.match(res, /Reverse recovery/);
    assert.match(res, /Die total/);
    assert.match(res, /R·E/, 'technology FOM row missing');

    // plots
    assert.match(d.getElementById('plotfsw').innerHTML, /<svg/, 'fsw sweep not drawn');
    assert.match(d.getElementById('plotn').innerHTML, /<svg/, 'N sweep not drawn');
    assert.match(d.getElementById('heat').innerHTML, /<rect/, 'N x fsw heatmap not drawn');

    // devices panel and library
    assert.ok(d.getElementById('selA'), 'device A selector missing');
    assert.ok(d.getElementById('selA').options.length >= 10, 'seeded parts not listed');
    assert.match(d.getElementById('devhint').textContent, /EPC2361/);

    // warnings panel must have rendered something (even "no warnings")
    assert.ok(d.getElementById('warns').textContent.trim().length > 0);
  });

test('UI: library panel exposes export, scenario save, import and link sharing',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    for (const id of ['exp', 'expScen', 'impBtn', 'link', 'resetLib', 'addPart']) {
      assert.ok(d.getElementById(id), 'library button #' + id + ' missing');
    }
    assert.deepEqual(errors, []);
  });

test('UI: every topology renders end to end',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    for (const topo of ['threephase', 'buck', 'boost', 'fourswitch']) {
      const { w, errors } = boot();
      const d = w.document;
      const sel = d.getElementById('topo');
      sel.value = topo;
      sel.dispatchEvent(new w.Event('change'));
      assert.deepEqual(errors, [], topo + ' raised script errors');
      assert.match(d.getElementById('results').textContent, /Die total/, topo + ' did not render');
      assert.match(d.getElementById('plotfsw').innerHTML, /<svg/, topo + ' fsw plot missing');
      assert.match(d.getElementById('heat').innerHTML, /<rect/, topo + ' heatmap missing');
    }
  });

test('UI: the 25 C / converged-Tj toggle changes the reported losses',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    const before = d.getElementById('results').textContent;
    d.getElementById('tjTog').dispatchEvent(new w.Event('click'));
    const after = d.getElementById('results').textContent;
    assert.deepEqual(errors, [], 'toggle raised script errors');
    assert.notEqual(before, after, 'the temperature toggle must change the breakdown');
    assert.match(after, /25|&deg;C|°C/);
  });

test('UI: switching device B re-renders and changes the verdict',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    const s = d.getElementById('selB');
    const before = d.getElementById('results').textContent;
    s.value = 'EPC2218';
    s.dispatchEvent(new w.Event('change'));
    assert.deepEqual(errors, [], 'device change raised script errors');
    assert.notEqual(d.getElementById('results').textContent, before);
    assert.match(d.getElementById('devhint').textContent, /EPC2218/);
  });

test('UI: editing a part through the JSON editor updates the run',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    d.getElementById('editA').dispatchEvent(new w.Event('click'));
    const ta = d.getElementById('pjson');
    assert.ok(ta, 'editor textarea did not open');
    const p = JSON.parse(ta.value);
    p.Rdson25 = p.Rdson25 * 4;                 // quadruple Rds(on)
    ta.value = JSON.stringify(p);
    d.getElementById('psave').dispatchEvent(new w.Event('click'));
    assert.deepEqual(errors, [], 'save raised script errors');
    // conduction must now be visibly worse in the rendered table
    assert.match(d.getElementById('results').textContent, /Die total/);
  });

test('UI: a scenario URL hash restores the operating point',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const scenario = encodeURIComponent(JSON.stringify({
      t: 'buck', o: { Vin: 24, Vout: 12, Pout: 100, fsw: 75000 }, a: 'IRF7759', b: 'EPC2361', n: 3, tj: 'none',
    }));
    const dom = new JSDOM(HTML, {
      runScripts: 'dangerously', pretendToBeVisual: true,
      url: 'file:///fet_fom/fet_fom.html#' + scenario,
    });
    const w = dom.window, errs = [];
    w.addEventListener('error', e => errs.push(e.message));
    assert.deepEqual(errs, []);
    const d = w.document;
    assert.equal(d.getElementById('topo').value, 'buck', 'topology not restored from hash');
    assert.equal(d.getElementById('selA').value, 'IRF7759', 'device A not restored');
    // a legacy single `n` must restore into BOTH per-device fields
    assert.equal(d.getElementById('f_NA').value, '3', 'N not restored for A');
    assert.equal(d.getElementById('f_NB').value, '3', 'N not restored for B');
    assert.match(d.getElementById('results').textContent, /Die total/);
  });

test('UI: per-device parallel counts survive a URL hash and are shown per column',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const scenario = encodeURIComponent(JSON.stringify({
      t: 'threephase', o: { Vdc: 58, Irms: 165.4, M: 1, PF: 0.9, fsw: 40000 },
      a: 'EPC2361', b: 'IRF7759', na: 4, nb: 2, tj: 'none',
    }));
    const dom = new JSDOM(HTML, {
      runScripts: 'dangerously', pretendToBeVisual: true,
      url: 'file:///fet_fom/fet_fom.html#' + scenario,
    });
    const w = dom.window, d = w.document, errs = [];
    w.addEventListener('error', e => errs.push(e.message));
    assert.deepEqual(errs, []);
    assert.equal(d.getElementById('f_NA').value, '4', 'A count restored');
    assert.equal(d.getElementById('f_NB').value, '2', 'B count restored');
    // the two columns carry their own N, and the heading is no longer "shared"
    const heads = Array.from(d.querySelectorAll('#results table th')).map(x => x.textContent);
    assert.ok(heads.some(t => /EPC2361 @ .* \(N=4\)/.test(t)), 'A column N: ' + heads.join(' | '));
    assert.ok(heads.some(t => /IRF7759 @ .* \(N=2\)/.test(t)), 'B column N: ' + heads.join(' | '));
    assert.match(d.getElementById('results').textContent, /Your build/);
    assert.match(d.getElementById('kpis').textContent, /you set N=4 \/ 2/);
  });

test('UI: a pre-per-device scenario/link migrates its shared Vdrv into A and B',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const scenario = encodeURIComponent(JSON.stringify({
      t: 'threephase', o: { Vdc: 58, Irms: 165.4, M: 1, PF: 0.9, fsw: 40000, Vdrv: 8 },
      a: 'EPC2361', b: 'IRF7759', n: 4, tj: 'converged',
    }));
    const dom = new JSDOM(HTML, {
      runScripts: 'dangerously', pretendToBeVisual: true,
      url: 'file:///fet_fom/fet_fom.html#' + scenario,
    });
    const w = dom.window, d = w.document, errs = [];
    w.addEventListener('error', e => errs.push(e.message));
    assert.deepEqual(errs, []);
    assert.equal(d.getElementById('fld_VdrvA').value, '8', 'legacy shared rail must show on A');
    assert.equal(d.getElementById('fld_VdrvB').value, '8', 'legacy shared rail must show on B');
  });

/* ------------------------------------------------- the redesigned layout */
test('UI: the hero shows the topology picture and the primary KPIs',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    const dia = d.getElementById('topodiagram').innerHTML;
    assert.match(dia, /<svg/, 'topology diagram not drawn');
    assert.match(dia, /HS/, 'half-bridge high side not shown');
    assert.match(dia, /LS/, 'half-bridge low side not shown');
    assert.match(dia, /3-phase motor/, 'the 3-phase diagram should show the motor');

    const k = d.getElementById('kpis').textContent;
    assert.match(k, /Winner at this build/);
    assert.match(k, /Total FET loss/);
    assert.match(k, /Power switched/);
    assert.match(k, /Efficiency \(FETs\)/);
    assert.match(k, /semiconductor-only/);
    assert.match(k, /Junction temp/);
    assert.match(k, /Parallel count/);
    assert.match(k, /Technology FOM/);
    // the winner KPI now quantifies the efficiency gap as well as the loss gap
    assert.match(k, /W better/);
    assert.match(k, /pt|identical/);
    // the four read-together metrics are two paired cards of two bubbles each,
    // and the three remaining metrics stay single cards
    const pairs = d.querySelectorAll('#kpis .kpi.pair');
    assert.equal(pairs.length, 2, 'expected two paired bubble cards');
    assert.equal(d.querySelectorAll('#kpis .kpi.pair .bub').length, 4, 'expected four bubbles');
    const labels = Array.from(pairs).map(c => Array.from(c.querySelectorAll('.l')).map(x => x.textContent));
    assert.deepEqual(labels[0], ['Winner at this build', 'Technology FOM'], 'verdict pair');
    assert.deepEqual(labels[1], ['Power switched', 'Efficiency (FETs)'], 'context pair');
    assert.equal(d.querySelectorAll('#kpis .kpi:not(.pair)').length, 3, 'expected three single cards');
    assert.deepEqual(errors, []);
  });

test('UI: the topology picture changes with the topology',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const shapes = {};
    for (const topo of ['threephase', 'buck', 'boost', 'fourswitch']) {
      const { w, errors } = boot();
      const d = w.document;
      const sel = d.getElementById('topo');
      sel.value = topo;
      sel.dispatchEvent(new w.Event('change'));
      assert.deepEqual(errors, [], topo + ' raised script errors');
      const dia = d.getElementById('topodiagram').innerHTML;
      assert.match(dia, /<svg/, topo + ': no diagram');
      shapes[topo] = dia;
      if (topo === 'threephase') assert.match(dia, /3-phase motor/);
      if (topo === 'buck') assert.match(dia, /load/);
      if (topo === 'fourswitch') assert.match(dia, /L/);
    }
    const uniq = new Set(Object.values(shapes));
    assert.equal(uniq.size, 4, 'each topology must draw a different schematic');
  });

test('UI: charts expose a log-scale toggle and a reference line at the current fsw',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    const box = d.getElementById('logf');
    assert.ok(box, 'log-scale toggle missing');
    assert.equal(box.checked, true, 'log axis should default on');
    const before = d.getElementById('plotfsw').innerHTML;
    assert.match(before, /stroke-dasharray/, 'no reference line at the current fsw');
    box.checked = false;
    box.dispatchEvent(new w.Event('change'));
    assert.deepEqual(errors, [], 'log toggle raised script errors');
    assert.notEqual(d.getElementById('plotfsw').innerHTML, before, 'toggling must redraw');
  });

test('UI: loss terms and figures of merit carry hover definitions',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    const tips = d.querySelectorAll('#results .has-tip');
    assert.ok(tips.length >= 18, 'expected a definition on every loss term and FOM, got ' + tips.length);
    for (const el of tips) {
      assert.ok((el.getAttribute('data-tip') || '').length > 40,
        'tooltip too short on: ' + el.textContent);
    }
    // bars should report their share on hover (note: .has-tip cells also carry
    // a title, so exclude them to target the value cells)
    const bars = d.querySelectorAll('#results td[data-tip]:not(.has-tip)');
    assert.ok(bars.length >= 14, 'loss bars should carry W and % titles, got ' + bars.length);
    assert.match(bars[0].getAttribute('data-tip'), /W = .*% of .* total/);
    assert.deepEqual(errors, []);
  });

test('UI: the temperature toggle lives with the breakdown, not buried in Advanced',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w } = boot();
    const d = w.document;
    const tog = d.getElementById('tjTog');
    assert.ok(tog, 'toggle missing');
    assert.ok(d.getElementById('results').contains(tog), 'toggle should sit in the results panel');
  });

/* ------------------------------------- bar tracks, colours and density */
test('UI: every bar sits in a fixed-width track, in its own column, never under the number',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    const tracks = d.querySelectorAll('#results .track-bg');
    assert.ok(tracks.length >= 16, 'expected a track per loss term per device, got ' + tracks.length);
    for (const t of tracks) {
      const fill = t.querySelector('span');
      assert.ok(fill, 'track has no fill');
      const width = fill.getAttribute('style') || '';
      assert.match(width, /width:\s*[\d.]+%/, 'fill is not a percentage of its track');
      const pct = parseFloat(width.match(/([\d.]+)%/)[1]);
      assert.ok(pct >= 0 && pct <= 100, 'fill must stay inside its track, got ' + pct + '%');
    }
    // the numeral must live in a different cell than the bar
    const numCells = d.querySelectorAll('#results td.num');
    assert.ok(numCells.length >= 16, 'expected a separate number column');
    for (const c of numCells) {
      assert.equal(c.querySelector('.track-bg'), null, 'a bar leaked into a number cell');
    }
    assert.deepEqual(errors, []);
  });

test('UI: the two devices use one consistent colour each, with a non-colour winner cue',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    // A fills are the A colour, B fills carry .b
    const aFills = d.querySelectorAll('#results .track-bg > span:not(.b)');
    const bFills = d.querySelectorAll('#results .track-bg > span.b');
    assert.ok(aFills.length >= 8 && bFills.length >= 8, 'both devices need tracks');
    // winner cells must carry a letter as well as a colour
    const win = d.querySelectorAll('#results td.winA, #results td.winB');
    assert.ok(win.length >= 2, 'expected winner cues in both loss tables');
    for (const c of win) {
      assert.match(c.textContent, /[AB]/, 'winner cue must name the device, not rely on hue');
    }
    // the chart traces must use the same two device colours
    const fsw = d.getElementById('plotfsw').innerHTML;
    assert.match(fsw, /stroke="#4aa3ff"/, 'A trace should be the A colour');
    assert.match(fsw, /stroke="#ff9f43"/, 'B trace should be the B colour');
    assert.deepEqual(errors, []);
  });

test('UI: warnings render as separate cards with an icon, a title and a body',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = boot();
    const d = w.document;
    // The default drives each device at its own recommended rail (EPC2361 5 V,
    // IAUTN08S7N006ATMA1 10 V), so exercise the plateau safeguard explicitly by
    // forcing device B down to 4 V -- at/below its 4.4 V plateau.
    const fld = d.getElementById('fld_VdrvB');
    assert.ok(fld, 'per-device gate-drive field B is missing');
    fld.value = '4';
    fld.dispatchEvent(new w.Event('input', { bubbles: true }));
    await new Promise(r => w.requestAnimationFrame(() => w.requestAnimationFrame(r)));

    const cards = d.querySelectorAll('#warns .wcard');
    assert.ok(cards.length >= 1, 'expected at least one warning card for the default build');
    for (const c of cards) {
      assert.ok(c.querySelector('.wico'), 'no severity icon');
      assert.ok(c.querySelector('.wtitle'), 'no title');
      assert.ok(c.querySelector('.wbody'), 'no body');
      // severity must be a namespaced class: a bare `info` collides with the
      // help-badge rule and turns the card into a 15px inline-flex blob
      assert.ok(c.className.match(/sev-(critical|caution|info)/), 'no severity class on the card');
      assert.ok(!/(^|\s)(info|critical|caution)(\s|$)/.test(c.className),
        'severity must not use a bare class name: ' + c.className);
      assert.ok(c.querySelector('.wtitle').textContent.length > 3, 'title too short');
    }
    // the gate-rail auto-switch warning should be titled, not start mid-sentence
    const titles = Array.from(cards).map(c => c.querySelector('.wtitle').textContent);
    assert.ok(titles.includes('Gate drive rail below the plateau'), 'titles: ' + titles.join(' | '));
    assert.deepEqual(errors, []);
  });

test('UI: per-device gate-drive fields default to each part\'s recommended rail',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    const fa = d.getElementById('fld_VdrvA'), fb = d.getElementById('fld_VdrvB');
    assert.ok(fa && fb, 'per-device gate-drive fields A/B are missing');
    // Blank value = follow the device; the placeholder names the part's rail.
    assert.equal(fa.value, '', 'A must start blank (follow the device)');
    assert.equal(fb.value, '', 'B must start blank (follow the device)');
    assert.match(fa.getAttribute('placeholder'), /EPC2361 recommends 5 V/, 'A placeholder');
    assert.match(fb.getAttribute('placeholder'), /IAUTN08S7N006ATMA1 recommends 10 V/, 'B placeholder');
    assert.deepEqual(errors, []);
  });

test('UI: the heatmap carries a colour bar and a click-to-pin readout',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    const heat = d.getElementById('heat').innerHTML;
    assert.match(heat, /linearGradient id="cbg"/, 'no colour bar gradient');
    assert.match(heat, /fill="url\(#cbg\)"/, 'colour bar not drawn');
    assert.match(heat, /data-i="0"/, 'cells are not addressable');
    // tick labels around the bar
    const tickRe = /font-size="10" text-anchor="middle">[\d.]+</g;
    assert.ok((heat.match(tickRe) || []).length >= 5, 'colour bar needs labelled ticks');

    // pin a cell
    const before = d.getElementById('heatread').textContent;
    const cell = d.querySelector('#heat rect[data-i="3"][data-j="5"]');
    assert.ok(cell, 'could not find a cell to click');
    cell.dispatchEvent(new w.Event('click', { bubbles: true }));
    const after = d.getElementById('heatread').textContent;
    assert.notEqual(after, before);
    assert.match(after, /Pinned:/);
    assert.match(after, /W/, 'readout should give a wattage');
    assert.deepEqual(errors, [], 'pinning a cell raised script errors');
  });

test('UI: chart mark labels are clamped inside the plot and haloed off the curves',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    // The fsw sweep deliberately carries NO marker: FET loss is monotonic in
    // frequency, so a "minimum" dot would be a lie.  The N sweep still marks both
    // optima, and those labels must be de-collided.
    assert.ok(!/paint-order="stroke"[^>]*>\d+k</.test(d.getElementById('plotfsw').innerHTML),
      'the fsw sweep must not mark a minimum');
    for (const id of ['plotn']) {
      const svg = d.getElementById(id).innerHTML;
      // mark labels are the only haloed text
      const marks = Array.from(svg.matchAll(
        /<text x="([\d.]+)"[^>]*y="([\d.]+)"[^>]*paint-order="stroke"/g));
      assert.equal(marks.length, 2, id + ': expected two marked optima, got ' + marks.length);
      assert.notEqual(marks[0][2], marks[1][2],
        id + ': the two mark labels must be offset vertically so they cannot stack');
      // clamped inside the plot box, clear of the y-axis tick labels
      for (const m of marks) {
        const x = parseFloat(m[1]);
        assert.ok(x > 60, id + ': label at x=' + x + ' would collide with the axis ticks');
        assert.ok(x < 560, id + ': label at x=' + x + ' runs off the right edge');
      }
    }
    assert.deepEqual(errors, []);
  });

test('UI: the header reads as specified', { skip: JSDOM ? false : 'jsdom not installed' }, () => {
  const { w } = boot();
  const sub = w.document.querySelector('header .sub').textContent;
  assert.equal(sub.trim(), 'Offline losses calculator \u00b7 EPC AN030 method');
});

test('UI: implementation notes never leak into visible text',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    // walk the rendered DOM only -- document.body.textContent would include the
    // script source, which is not what the user sees
    const visible = [];
    (function walk(n) {
      if (n.nodeType === 3) {
        const t = n.textContent.replace(/\s+/g, ' ').trim();
        if (t) visible.push(t);
      } else if (n.nodeType === 1 && !/^(SCRIPT|STYLE)$/.test(n.tagName)) {
        for (const c of n.childNodes) walk(c);
      }
    })(w.document.body);
    const text = visible.join(' ');
    const banned = [
      /offset vertically/, /background halo/, /switches drawn as device/,
      /share one zero/, /scaled to the largest component term/,
    ];
    for (const re of banned) {
      assert.ok(!re.test(text), 'implementation note is visible to the user: ' + re);
    }
    assert.deepEqual(errors, []);
  });

test('UI: every topology schematic stays inside its viewBox',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    // Guards against a coordinate retune silently clipping a symbol.
    for (const topo of ['threephase', 'buck', 'boost', 'fourswitch']) {
      const { w, errors } = boot();
      const d = w.document;
      const sel = d.getElementById('topo');
      sel.value = topo;
      sel.dispatchEvent(new w.Event('change'));
      const svg = d.querySelector('#topodiagram svg');
      assert.ok(svg, topo + ': no schematic');
      const [vx, vy, VW, VH] = svg.getAttribute('viewBox').split(' ').map(Number);
      for (const el of svg.querySelectorAll('line,rect,circle,text')) {
        const g = a => el.getAttribute(a);
        let xs, ys;
        if (el.tagName === 'line') { xs = [+g('x1'), +g('x2')]; ys = [+g('y1'), +g('y2')]; }
        else if (el.tagName === 'rect') { xs = [+g('x'), +g('x') + +g('width')]; ys = [+g('y'), +g('y') + +g('height')]; }
        else if (el.tagName === 'circle') { xs = [+g('cx') - +g('r'), +g('cx') + +g('r')]; ys = [+g('cy') - +g('r'), +g('cy') + +g('r')]; }
        else { xs = [+g('x')]; ys = [+g('y') - 12, +g('y') + 3]; }
        assert.ok(Math.min(...xs) >= vx && Math.max(...xs) <= vx + VW,
          topo + ': a ' + el.tagName + ' escapes the viewBox horizontally');
        assert.ok(Math.min(...ys) >= vy && Math.max(...ys) <= vy + VH,
          topo + ': a ' + el.tagName + ' escapes the viewBox vertically');
      }
      assert.deepEqual(errors, []);
    }
  });

test('UI: loss and Tj are two stacked charts, not one dual-axis chart',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    const loss = d.getElementById('plotn').innerHTML;
    const tj = d.getElementById('plottj').innerHTML;
    assert.ok(tj.length > 200, 'no separate Tj chart');

    // the loss chart must NOT carry a secondary axis or inline limit text
    assert.ok(!/Tj max/.test(loss), 'loss chart still has inline Tj annotations');
    assert.ok(!/stroke-dasharray="2 3"/.test(loss), 'loss chart still has limit lines');

    // the Tj chart carries the axis, the limit lines and both curves
    assert.match(tj, /Tj \[/, 'no Tj axis label');
    assert.ok((tj.match(/stroke-dasharray="2 3"/g) || []).length >= 2, 'expected two dotted limit lines');
    assert.ok((tj.match(/<path /g) || []).length >= 2, 'expected a Tj curve per device');
    assert.match(d.getElementById('plottj').textContent, /limit \(150 \/ 175/, 'legend must name both limits');
    assert.deepEqual(errors, []);
  });

test('UI: the runaway point cannot dictate the Tj axis scale',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    // The reference point is forced via the hash because it is the silicon part
    // there that breaks: IRF7759 at N=1 is thermal runaway (NaN) and N=2 is
    // ~1127 C. The axis must be capped near the limits, not stretched to 1262.
    const { w } = bootReference();
    const d = w.document;
    const svg = d.getElementById('plottj').innerHTML;
    const ticks = Array.from(svg.matchAll(/font-size="11" text-anchor="end">([\d.]+)</g)).map(m => parseFloat(m[1]));
    assert.ok(ticks.length >= 5, 'expected y ticks');
    const top = Math.max(...ticks);
    assert.ok(top <= 250, 'Tj axis top tick is ' + top + '; a runaway point is dictating the scale');
    assert.ok(top >= 175, 'the axis must still reach past the 175 C limit');
  });

test('UI: the Loop ringing row reads "off" when L_loop is 0, not 0.00',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    // The page default carries a 1 nH loop, so clear it through the hash to get
    // the switched-off state this test is about.
    const { w } = bootReference({ Lloop: 0 });
    const d = w.document;
    const row = Array.from(d.querySelectorAll('#results tbody tr'))
      .find(tr => /Loop ringing/.test(tr.textContent));
    assert.ok(row, 'no Loop ringing row');
    assert.match(row.textContent, /off/, 'a switched-off term should say so');
    assert.ok(!/\b0\.00\b/.test(row.textContent), 'must not print 0.00 for a switched-off term');
    assert.match(row.querySelector('.has-tip').getAttribute('data-tip'), /L_loop = 0/);
  });

test('UI: no HTML-only tag leaks out of a generated SVG',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    // <sub>/<sup>/<b> are not SVG elements.  Inside an SVG <text> the parser
    // closes the <svg> early and hoists the tail into the page as stray text,
    // which renders as floating text sitting on top of unrelated panels.
    const { w, errors } = boot();
    const d = w.document;
    for (const id of ['plotfsw', 'plotn', 'plottj', 'heat']) {
      const host = d.getElementById(id);
      const svgs = host.querySelectorAll('svg');
      assert.ok(svgs.length >= 1, id + ': no svg');
      for (const svg of svgs) {
        const bad = svg.querySelectorAll('sub,sup,b,i,span,div,p');
        assert.equal(bad.length, 0,
          id + ': ' + bad.length + ' HTML-only element(s) inside the svg (' +
          Array.from(bad).map(e => e.tagName).join(',') + ')');
      }
      // and nothing may be hoisted out of the svg into the host div
      for (const n of host.childNodes) {
        if (n.nodeType === 3) {
          assert.equal(n.textContent.trim(), '', id + ': stray text outside the svg: ' + n.textContent.trim().slice(0, 60));
        }
      }
    }
    assert.deepEqual(errors, []);
  });

test('UI: tooltips are a positioned portal layer, not native title attributes',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;

    // the layer is a portal on <body>, outside every panel
    const tip = d.getElementById('tip');
    assert.ok(tip, 'no tooltip layer');
    assert.equal(tip.parentNode, d.body, 'the tooltip layer must hang off <body>');
    assert.equal(tip.closest('.panel'), null, 'the layer must not live inside a panel');

    // and nothing may fall back to a native tooltip, which cannot wrap or be sized:
    // neither a title attribute nor an SVG <title> element, which does the same thing
    assert.equal(d.querySelectorAll('[title]').length, 0, 'native title attributes remain');
    for (const id of ['plotfsw', 'plotn', 'plottj', 'heat', 'results', 'adv', 'warns']) {
      assert.equal(d.getElementById(id).querySelectorAll('title').length, 0,
        id + ': an SVG <title> is still a native, clipping tooltip');
    }

    // hovering a term shows the full definition, positioned
    const term = d.querySelector('#results .has-tip');
    assert.ok(term, 'no hoverable term');
    term.dispatchEvent(new w.MouseEvent('mouseover', { bubbles: true }));
    assert.ok(tip.classList.contains('on'), 'tooltip did not show');
    assert.ok(tip.textContent.length > 40,
      'tooltip content is a stub, not the whole sentence: ' + JSON.stringify(tip.textContent));
    assert.ok(tip.style.left !== '' && tip.style.top !== '', 'tooltip was not positioned');

    // and it must dismiss when the pointer leaves
    term.dispatchEvent(new w.MouseEvent('mouseout', { bubbles: true }));
    assert.ok(!tip.classList.contains('on'), 'tooltip did not dismiss on leave');
    assert.deepEqual(errors, []);
  });

test('UI: an info-severity warning card is a full-width block, like every other card',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    // Regression: `class="wcard info"` used to match the `.info` help-badge rule
    // (inline-flex, 15x15, border-radius 50%), collapsing the card into a blob and
    // pushing its body into a 76px column. The card must keep the same geometry
    // regardless of severity.  The reference point is forced via the hash so the
    // regression state (an info card, plus criticals to sort) always exists,
    // whatever scenario the page opens on.
    const { w, errors } = bootReference();
    const d = w.document;
    const cards = Array.from(d.querySelectorAll('#warns .wcard'));
    assert.ok(cards.length >= 1, 'no warning cards');
    for (const c of cards) {
      assert.equal(c.querySelectorAll('.wbody').length, 1, 'card must own exactly one body');
      assert.equal(c.querySelector('.wbody').parentElement, c,
        'the body must be a direct child of its card');
      const kids = Array.from(c.children).map(x => x.className);
      assert.deepEqual(kids, ['whead', 'wbody'], 'unexpected card structure: ' + kids.join(','));
    }
    // critical must sort first (rank 0 is falsy, so a `|| 3` fallback breaks it)
    const sevs = cards.map(c => (c.className.match(/sev-(\w+)/) || [])[1]);
    const firstCritical = sevs.indexOf('critical');
    const lastNonCritical = sevs.map((s, i) => s === 'critical' ? -1 : i).reduce((a, b) => Math.max(a, b), -1);
    if (firstCritical >= 0) {
      assert.ok(firstCritical <= lastNonCritical || lastNonCritical === -1,
        'critical warnings must sort first, got: ' + sevs.join(','));
    }
    assert.deepEqual(errors, []);
  });

/* ------------------------------------------- file import / export (crit 6) */
test('UI: importing a scenario JSON file applies it',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = bootWithAlerts();
    const d = w.document;
    const scen = {
      schemaVersion: 1, kind: 'scenario', topology: 'fourswitch',
      op: { Vin: 24, Vout: 48, Pout: 150, fsw: 120000 },
      A: 'EPC2218', B: 'EPC2361', N: 2, tj: 'none', cossBasis: 'VQoss',
    };
    await importFile(w, JSON.stringify(scen), 'scen.json');
    assert.deepEqual(errors, [], 'scenario import raised script errors');
    assert.deepEqual(w.__alerts, ['Scenario loaded.']);
    assert.equal(d.getElementById('topo').value, 'fourswitch', 'topology not applied');
    assert.equal(d.getElementById('selA').value, 'EPC2218', 'device A not applied');
    assert.equal(d.getElementById('selB').value, 'EPC2361', 'device B not applied');
    assert.equal(d.getElementById('f_NA').value, '2', 'N not applied to A');
    assert.equal(d.getElementById('f_NB').value, '2', 'legacy N not applied to B');
    assert.match(d.getElementById('results').textContent, /Die total/);
    assert.match(d.getElementById('plotfsw').innerHTML, /<svg/);
  });

test('UI: exporting the library then importing it round-trips end to end',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = bootWithAlerts();
    const d = w.document;
    const blob = captureExport(w, 'exp');
    assert.ok(blob, 'Export library produced no blob');
    const text = await readBlob(w, blob);
    const parsed = JSON.parse(text);
    assert.equal(parsed.schemaVersion, 2, 'exported library must carry schemaVersion 2');
    assert.ok(parsed.parts, 'exported library must carry a parts object');
    const before = Object.keys(w.FOMENGINE.PARTS).length;
    assert.equal(Object.keys(parsed.parts).length, before, 'export must contain every part');

    await importFile(w, text, 'lib.json');
    assert.deepEqual(errors, [], 'library re-import raised script errors');
    assert.equal(w.__alerts.length, 1);
    assert.match(w.__alerts[0], /Imported \d+ parts\./);
    assert.equal(Object.keys(w.FOMENGINE.PARTS).length, before, 'round-trip changed the part count');
    assert.match(d.getElementById('results').textContent, /Die total/);
  });

test('UI: importing a parts library adds a new part to the selectors',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = bootWithAlerts();
    const d = w.document;
    const clone = Object.assign({}, w.FOMENGINE.PARTS.EPC2361, { PN: 'TESTPART' });
    const lib = { schemaVersion: 1, parts: { TESTPART: clone } };
    await importFile(w, JSON.stringify(lib), 'one.json');
    assert.deepEqual(errors, []);
    assert.ok(w.FOMENGINE.PARTS.TESTPART, 'imported part not added to the library');
    const names = Array.from(d.getElementById('selA').options).map(o => o.value);
    assert.ok(names.includes('TESTPART'), 'imported part not offered in the selector');
  });

test('UI: a wrong schemaVersion is refused rather than silently mis-read',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = bootWithAlerts();
    const before = Object.keys(w.FOMENGINE.PARTS).length;
    await importFile(w, JSON.stringify({ schemaVersion: 99, parts: { X: {} } }), 'bad.json');
    assert.deepEqual(errors, []);
    assert.equal(w.__alerts.length, 1);
    assert.match(w.__alerts[0], /schemaVersion 99 is not supported/);
    assert.equal(Object.keys(w.FOMENGINE.PARTS).length, before, 'refused import must not mutate the library');
  });

test('UI: a file that is neither a library nor a scenario is rejected',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = bootWithAlerts();
    const before = Object.keys(w.FOMENGINE.PARTS).length;
    await importFile(w, JSON.stringify({ schemaVersion: 1, nope: true }), 'odd.json');
    assert.deepEqual(errors, []);
    assert.match(w.__alerts[0] || '', /Neither a parts library nor a scenario/);
    assert.equal(Object.keys(w.FOMENGINE.PARTS).length, before);
  });

test('UI: a malformed part is refused without poisoning the library',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    // The old code committed each entry as it went, so a payload with one null
    // value was "refused" but still written -- and every later render threw.
    const { w, errors } = bootWithAlerts();
    const d = w.document;
    const before = Object.keys(w.FOMENGINE.PARTS).length;
    await importFile(w, JSON.stringify({ schemaVersion: 1, parts: { NULLY: null, ARR: [1, 2] } }), 'null.json');
    assert.equal(w.__alerts.length, 1);
    assert.match(w.__alerts[0], /Import refused/);
    assert.equal(Object.keys(w.FOMENGINE.PARTS).length, before, 'nothing may be committed');
    assert.equal(w.FOMENGINE.PARTS.NULLY, undefined);
    assert.equal(w.FOMENGINE.PARTS.ARR, undefined);
    const names = Array.from(d.getElementById('selA').options).map(o => o.value);
    assert.ok(!names.includes('NULLY') && !names.includes('ARR'));
    assert.deepEqual(errors, []);
  });

test('UI: a sparse part does not print NaN in the selector or undefined in the Tj legend',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = bootWithAlerts();
    const d = w.document;
    await importFile(w, JSON.stringify({
      schemaVersion: 1, parts: { SPARSE: { PN: 'SPARSE', technology: 'Si', kind: 'discrete' } },
    }), 'sparse.json');
    const opts = Array.from(d.getElementById('selA').options).map(o => o.textContent).join(' ');
    assert.ok(!/NaN/.test(opts), 'the selector must not print NaN: ' + opts);
    const selB = d.getElementById('selB');
    selB.value = 'SPARSE';
    selB.dispatchEvent(new w.Event('change'));
    const tjHtml = d.getElementById('plottj').innerHTML;
    assert.ok(!/undefined/.test(tjHtml), 'the Tj legend must not print undefined');
    assert.ok(!/NaN/.test(tjHtml), 'the Tj chart must not contain NaN');
    assert.deepEqual(errors, []);
  });

test('UI: a blank fsw says so instead of claiming a line at 0 kHz',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = boot();
    const d = w.document;
    const f = d.getElementById('fld_fsw');
    f.value = '';
    f.dispatchEvent(new w.Event('input', { bubbles: true }));
    await new Promise(r => w.requestAnimationFrame(r));
    const tools = d.getElementById('plottools').textContent;
    assert.ok(!/your f\s*sw\s*=\s*0\s*kHz/.test(tools), 'no dashed line exists, so do not claim one: ' + tools);
    assert.match(tools, /no valid f/);
    assert.match(d.getElementById('plotfsw').innerHTML, /<svg/);
    assert.deepEqual(errors, []);
  });

test('UI: a parallel count past the swept band is not described as outlined',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const hash = '#' + encodeURIComponent(JSON.stringify({
      t: 'threephase', o: { Vdc: 58, Irms: 80, M: 1, PF: 0.9, fsw: 25000 },
      a: 'EPC2361', b: 'IAUTN08S7N006ATMA1', na: 20, nb: 20,
    }));
    const { w, errors } = bootHashed(hash);
    const d = w.document;
    assert.match(d.getElementById('heathint').textContent, /outside the/);
    assert.ok(!/outlined row is your N=20/.test(d.getElementById('heathint').textContent));
    assert.deepEqual(errors, []);
  });

test('UI: the provenance disclosure survives a keystroke',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = boot();
    const d = w.document;
    const det = d.querySelector('#devhint details');
    assert.ok(det, 'provenance disclosure missing');
    det.open = true;
    const f = d.getElementById('fld_Irms');
    f.value = '81';
    f.dispatchEvent(new w.Event('input', { bubbles: true }));
    await new Promise(r => w.requestAnimationFrame(r));
    assert.equal(d.querySelector('#devhint details').open, true, 'it closed on its own');
    assert.deepEqual(errors, []);
  });

/* ------------------------------------------------------- design workspace */
test('UI: the workspace switcher shows one workspace at a time and persists in the hash',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors, lastHash } = bootHashed();
    const d = w.document;
    const fet = d.getElementById('ws-fet'), bridge = d.getElementById('ws-bridge');
    // The comparator is the landing workspace, so an existing habit still works.
    assert.equal(fet.hidden, false, 'FET workspace must be visible on load');
    assert.equal(bridge.hidden, true, 'design workspace must start hidden');
    assert.equal(d.getElementById('wsfet').getAttribute('aria-pressed'), 'true');
    assert.equal(d.getElementById('wsbridge').getAttribute('aria-pressed'), 'false');

    d.getElementById('wsbridge').dispatchEvent(new w.Event('click'));
    assert.equal(fet.hidden, true, 'FET workspace must hide');
    assert.equal(bridge.hidden, false, 'design workspace must show');
    assert.equal(d.getElementById('wsbridge').getAttribute('aria-pressed'), 'true');
    assert.match(lastHash(), /"ws":"bridge"/, 'workspace must reach the hash');
    // It rendered something real rather than an empty panel.
    assert.match(d.getElementById('bs-kpis').textContent, /System loss/);
    assert.match(d.getElementById('bs-sizing').textContent, /winding inductance sets the ripple/i);

    d.getElementById('wsfet').dispatchEvent(new w.Event('click'));
    assert.equal(fet.hidden, false);
    assert.equal(bridge.hidden, true);
    assert.match(lastHash(), /"ws":"fet"/);
    assert.deepEqual(errors, [], 'switching workspaces raised script errors');
  });

test('UI: a workspace round-trip does not disturb the comparator numbers',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    // The inactive workspace is hidden, not re-rendered, so its state and its
    // rendered numbers must survive a round-trip untouched.
    const { w } = bootReference();
    const d = w.document;
    const results = d.getElementById('results').textContent;
    const hero = d.getElementById('kpis').textContent;
    d.getElementById('wsbridge').dispatchEvent(new w.Event('click'));
    d.getElementById('wsfet').dispatchEvent(new w.Event('click'));
    assert.equal(d.getElementById('results').textContent, results, 'loss table changed');
    assert.equal(d.getElementById('kpis').textContent, hero, 'hero changed');
  });

test('UI: each topology renders its own magnetics profile',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors } = boot();
    const d = w.document;
    d.getElementById('wsbridge').dispatchEvent(new w.Event('click'));
    const setTopo = t => {
      const sel = d.getElementById('bf-topo');
      sel.value = t;
      // bubbles: the design form delegates change handling on its container so
      // that a form rebuild cannot drop the listener, and a real change event
      // bubbles even though `new Event('change')` does not.
      sel.dispatchEvent(new w.Event('change', { bubbles: true }));
    };

    // 3-phase: the machine panel exists, the winding is the inductance and the
    // stator iron is the core.
    setTopo('threephase');
    assert.equal(d.getElementById('bm-machine-panel').hidden, false, 'machine panel must show for 3-phase');
    assert.match(d.getElementById('bf-form').textContent, /Winding inductance/);
    assert.match(d.getElementById('bf-form').textContent, /Series line choke/);
    let note = d.getElementById('bs-sizing').textContent;
    assert.match(note, /winding inductance sets the ripple/);
    assert.match(note, /stator iron is the core/);
    assert.match(note, /Required phase inductance/);
    assert.match(note, /Machine ripple current/);

    // DC-DC: no machine at all, and the inductance is the discrete filter
    // inductor with its own steel, not the motor.
    for (const t of ['buck', 'boost']) {
      setTopo(t);
      assert.equal(d.getElementById('bm-machine-panel').hidden, true, t + ': no machine panel');
      assert.match(d.getElementById('bf-form').textContent, /Filter inductor/, t + ': filter inductor input');
      assert.ok(!/Winding inductance/.test(d.getElementById('bf-form').textContent), t + ': no winding field');
      note = d.getElementById('bs-sizing').textContent;
      assert.match(note, /filter inductor sets the ripple/, t + ': profile note');
      assert.match(note, /Required filter inductance/, t + ': sizing row');
    }
    // The 4-switch converter's note is about the mode, because that is what
    // decides which node is the smooth one.
    setTopo('fourswitch');
    assert.equal(d.getElementById('bm-machine-panel').hidden, true, '4-switch has no machine panel');
    assert.match(d.getElementById('bs-sizing').textContent, /depends on the mode/);
    assert.deepEqual(errors, [], 'topology switching raised script errors');
  });

test('UI: the design workspace renders its answers and reacts to a target change',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = boot();
    const d = w.document;
    d.getElementById('wsbridge').dispatchEvent(new w.Event('click'));

    // The headline answers are there, not just the inputs.
    const kpis = d.getElementById('bs-kpis').textContent;
    assert.match(kpis, /System loss/, 'system loss KPI');
    assert.match(kpis, /Required L/, 'required-L KPI');
    assert.match(kpis, /Required C/, 'required-C KPI');
    assert.match(kpis, /optimum/, 'fsw optimum KPI');
    // The budget lists real terms and a total that is the whole stage, not the
    // semiconductor-only figure the comparator reports.
    const budget = d.getElementById('bs-budget').textContent;
    assert.match(budget, /Semiconductors/);
    assert.match(budget, /Machine/);
    assert.match(budget, /Total/);
    // Both charts drew, and the feasibility map shaded at least one cell.
    assert.match(d.getElementById('bs-fswplot').innerHTML, /<svg/);
    assert.match(d.getElementById('bs-feas').innerHTML, /<rect/);
    // The design workspace must never claim a semiconductor-only efficiency.
    assert.match(kpis, /whole P/);
    assert.ok(d.getElementById('bm-warns').textContent.trim().length > 0, 'warnings panel empty');

    const reqL = () => {
      const m = d.getElementById('bs-sizing').textContent
        .match(/Required phase inductance\s*([\d.]+)\s*\u00b5H/);
      return m ? parseFloat(m[1]) : null;
    };
    const l1 = reqL();
    assert.ok(l1 > 0, 'no required-inductance answer rendered');

    // Halving the allowed ripple must roughly double the required inductance.
    // This is the whole point of the sizing panel, and it proves the input path
    // (delegated listener -> debounce -> recompute) is actually wired.
    const ip = d.getElementById('bf-ippPct');
    ip.value = '10';
    ip.dispatchEvent(new w.Event('input', { bubbles: true }));
    await new Promise(r => w.requestAnimationFrame(r));
    const l2 = reqL();
    assert.ok(l2 > l1 * 1.8 && l2 < l1 * 2.2,
      'halving the ripple target should double L, got ' + l1 + ' -> ' + l2);

    // Selecting the custom part must reveal its own fields, because none of the
    // committed inductors can carry this current.  They live in their own panel
    // so the results pass cannot rewrite them while they are being typed into.
    const indSel = d.getElementById('bf-ind');
    indSel.value = 'custom';
    indSel.dispatchEvent(new w.Event('change', { bubbles: true }));
    assert.equal(d.getElementById('bm-custom-panel').hidden, false, 'custom panel must show');
    assert.match(d.getElementById('bm-custom').textContent, /Custom inductor/);
    assert.ok(d.getElementById('bf-cL'), 'custom inductance field missing');
    assert.deepEqual(errors, [], 'design workspace raised script errors');
  });

test('UI: the design workspace can be told its current, and its inputs survive typing',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = boot();
    const d = w.document;
    const frame = () => new Promise(r => w.requestAnimationFrame(r));
    const setv = (id, v, ev) => {
      const el = d.getElementById(id);
      el.value = v;
      el.dispatchEvent(new w.Event(ev, { bubbles: true }));
    };
    d.getElementById('wsbridge').dispatchEvent(new w.Event('click'));

    // (1) The design workspace must have its OWN operating-point inputs.  It
    // silently used whatever the comparator held before, which meant "system
    // loss" had no stated current behind it.
    assert.ok(d.getElementById('bg-Irms'), 'no phase-current input in the design workspace');
    assert.ok(d.getElementById('bg-Vdc'), 'no bus-voltage input');
    assert.ok(d.getElementById('bg-fsw'), 'no switching-frequency input');
    const before = d.getElementById('bs-kpis').textContent;
    setv('bg-Irms', '160', 'input');
    await frame();
    assert.notEqual(d.getElementById('bs-kpis').textContent, before,
      'changing the phase current did not change the answers');
    // ...and the comparator's form followed, so the two cannot diverge.
    assert.equal(d.getElementById('fld_Irms').value, '160', 'the comparator did not follow the shared op');

    // (2) Typing into a custom-part field must not destroy it.  The fields used
    // to live inside the readout container that every keystroke rewrites, so the
    // caret was lost after the first digit.
    setv('bf-ind', 'custom', 'change');
    const f = d.getElementById('bf-cIsat10');
    f.focus();
    f.value = '1';
    f.dispatchEvent(new w.Event('input', { bubbles: true }));
    await frame();
    assert.equal(d.getElementById('bf-cIsat10'), f, 'the field was replaced while typing');
    assert.equal(d.activeElement, f, 'the caret was lost while typing');
    f.value = '120';
    f.dispatchEvent(new w.Event('input', { bubbles: true }));
    await frame();
    assert.equal(d.getElementById('bf-cIsat10').value, '120', 'the whole number must be accepted');
    assert.equal(d.activeElement, f, 'the caret must survive a second edit');

    // (3) A custom capacitor bank, because the four seeded ones are generic
    // MATLAB placeholders rather than parts anybody stocks.
    setv('bf-cap', 'custom', 'change');
    assert.equal(d.getElementById('bm-custom-panel').hidden, false);
    assert.match(d.getElementById('bm-custom').textContent, /Custom capacitor bank/);
    assert.ok(d.getElementById('bf-cCapC'), 'custom capacitance field missing');
    assert.ok(d.getElementById('bf-cCapESR'), 'custom ESR field missing');
    assert.match(d.getElementById('bm-passives').textContent, /Bank \(effective\)/);

    // (4) A selected-but-uncounted choke must SHOW its data and say it is
    // outside the budget, instead of claiming no inductor is selected.
    setv('bf-ind', 'WE_7443641500', 'change');
    let ptxt = d.getElementById('bm-passives').textContent;
    assert.match(ptxt, /Inductance/, 'the selected part must be shown');
    assert.match(ptxt, /Loss NOT accounted/, 'and must say it is outside the budget');
    const ck = d.getElementById('bf-choke');
    ck.checked = true;
    ck.dispatchEvent(new w.Event('input', { bubbles: true }));
    await frame();
    ptxt = d.getElementById('bm-passives').textContent;
    assert.match(ptxt, /Loss accounted/, 'ticking the choke must move it into the budget');
    // The scraped REDEXPERT bias curve must surface as a roll-off, and the
    // thermal model must either give a rise or say why it cannot.
    assert.match(ptxt, /Inductance roll-off/, 'the bias curve must be reported');
    assert.match(ptxt, /Saturated ripple/, 'the saturated ripple must be reported');
    assert.match(ptxt, /Temperature rise|outside REDEXPERT/,
      'the thermal estimate must be reported or explicitly refused');
    assert.deepEqual(errors, [], 'design workspace raised script errors');
  });

test('UI: the design workspace and the comparator share one topology choice',
  { skip: JSDOM ? false : 'jsdom not installed' }, () => {
    const { w, errors, lastHash } = bootHashed();
    const d = w.document;
    d.getElementById('wsbridge').dispatchEvent(new w.Event('click'));
    const sel = d.getElementById('bf-topo');
    sel.value = 'boost';
    sel.dispatchEvent(new w.Event('change', { bubbles: true }));
    // The comparator's own selector must have followed, and the hash with it.
    assert.equal(d.getElementById('topo').value, 'boost', 'comparator did not follow the design workspace');
    assert.match(lastHash(), /"t":"boost"/);
    // And the other way round.
    const back = d.getElementById('topo');
    back.value = 'buck';
    back.dispatchEvent(new w.Event('change'));
    assert.equal(d.getElementById('bf-topo').value, 'buck', 'design workspace did not follow the comparator');
    assert.deepEqual(errors, []);
  });

test('UI: every DC-DC topology reports a required filter inductance',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    // The ripple target used to be taken from op.Irms, which does not exist for
    // a DC-DC converter, so "Required filter inductance" was permanently blank on
    // three of the four topologies.
    const { w, errors } = boot();
    const d = w.document;
    const frame = () => new Promise(r => w.requestAnimationFrame(r));
    d.getElementById('wsbridge').dispatchEvent(new w.Event('click'));
    const setTopo = t => {
      const s = d.getElementById('bf-topo');
      s.value = t;
      s.dispatchEvent(new w.Event('change', { bubbles: true }));
    };
    for (const t of ['buck', 'boost', 'fourswitch']) {
      setTopo(t);
      await frame();
      const m = d.getElementById('bs-sizing').textContent
        .match(/Required filter inductance\s*([\d.]+)\s*\u00b5H/);
      assert.ok(m && parseFloat(m[1]) > 0,
        t + ': no required filter inductance rendered: ' +
        d.getElementById('bs-sizing').textContent.slice(0, 140));
    }
    assert.deepEqual(errors, [], 'DC-DC sizing raised script errors');
  });

test('UI: unticking capacitor ESR loss keeps the sizing answers',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = boot();
    const d = w.document;
    const frame = () => new Promise(r => w.requestAnimationFrame(r));
    d.getElementById('wsbridge').dispatchEvent(new w.Event('click'));
    const reqC = () => {
      const k = [...d.querySelectorAll('#bs-kpis .kpi')]
        .find(x => x.querySelector('.l') && x.querySelector('.l').textContent.trim() === 'Required C');
      return k ? k.querySelector('.v').textContent.trim() : null;
    };
    // 3-phase: the DC-link bank is sized from the bus excursion, not the ESR loss.
    assert.notEqual(reqC(), '\u2014');
    const cap = d.getElementById('bf-useCap');
    cap.checked = false;
    cap.dispatchEvent(new w.Event('input', { bubbles: true }));
    await frame();
    assert.notEqual(reqC(), '\u2014', 'unticking the ESR loss blanked the DC-link sizing answer');
    assert.match(d.getElementById('bm-passives').textContent, /loss not counted/);
    assert.match(d.getElementById('bm-passives').textContent, /DC link \(pulsed-svpwm\)/,
      'the DC-link ripple data must still be reported');
    // DC-DC: the worst-node bank requirement must survive the same toggle.
    const s = d.getElementById('bf-topo');
    s.value = 'buck';
    s.dispatchEvent(new w.Event('change', { bubbles: true }));
    await frame();
    assert.notEqual(reqC(), '\u2014', 'unticking the ESR loss blanked the DC-DC sizing answer');
    assert.deepEqual(errors, [], 'the capacitor toggle raised script errors');
  });

test('UI: a 3-phase series choke is not counted twice',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = boot();
    const d = w.document;
    const E = w.FOMENGINE;
    const frame = () => new Promise(r => w.requestAnimationFrame(r));
    const setv = (id, v, ev) => {
      const el = d.getElementById(id);
      el.value = v;
      el.dispatchEvent(new w.Event(ev || 'input', { bubbles: true }));
    };
    d.getElementById('wsbridge').dispatchEvent(new w.Event('click'));
    setv('bf-Ls', '3.73');
    await frame();
    setv('bf-ind', 'WE_7443634700', 'change');
    const ck = d.getElementById('bf-choke');
    ck.checked = true;
    ck.dispatchEvent(new w.Event('input', { bubbles: true }));
    await frame();
    const got = parseFloat((d.getElementById('bs-sizing').textContent
      .match(/Ripple with the selected L\s*([\d.]+)\s*A/) || [])[1]);
    assert.ok(got > 0, 'no ripple answer rendered');
    const choke = E.INDUCTORS.WE_7443634700;
    const op = Object.assign(E.defaultOp('threephase'),
      { Vdc: 58, Irms: 80, M: 1, PF: 0.9, fsw: 25000, Lcsi: 3e-10, Lloop: 1e-9, Ls: 3.73e-6, f1: 300 });
    const good = E.stageSystem({ A: 'EPC2361', NA: 2, ind: choke }, op, {}).ipp;
    const bad = E.stageSystem({ A: 'EPC2361', NA: 2, ind: choke },
      Object.assign({}, op, { Ls: 3.73e-6 + choke.L }), {}).ipp;
    assert.ok(Math.abs(got - good) < 0.02 * Math.abs(good),
      'ripple must match the once-counted call: got ' + got + ', want ' + good);
    assert.ok(Math.abs(got - bad) > 0.2 * Math.abs(bad),
      'and must not match the double-counted call: bad ' + bad);
    assert.deepEqual(errors, [], 'fitting a choke raised script errors');
  });

test('UI: a blank switching frequency degrades cleanly instead of drawing NaN',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors } = boot();
    const d = w.document;
    const frame = () => new Promise(r => w.requestAnimationFrame(r));
    d.getElementById('wsbridge').dispatchEvent(new w.Event('click'));
    const s = d.getElementById('bf-topo');
    s.value = 'buck';
    s.dispatchEvent(new w.Event('change', { bubbles: true }));
    await frame();
    const fsw = d.getElementById('bg-fsw');
    fsw.value = '';
    fsw.dispatchEvent(new w.Event('input', { bubbles: true }));
    await frame();
    assert.ok(!/NaN/.test(d.getElementById('bs-fswplot').innerHTML), 'fsw chart contained NaN');
    assert.ok(!/NaN/.test(d.getElementById('bs-feas').innerHTML), 'feasibility map contained NaN');
    assert.match(d.getElementById('bs-fswplot').textContent, /Enter a switching frequency/);
    assert.deepEqual(errors, [], 'a blank fsw raised script errors');
  });

test('UI: the design-workspace state rides the share link and a scenario',
  { skip: JSDOM ? false : 'jsdom not installed' }, async () => {
    const { w, errors, lastHash } = bootHashed();
    const d = w.document;
    const frame = () => new Promise(r => w.requestAnimationFrame(r));
    d.getElementById('wsbridge').dispatchEvent(new w.Event('click'));
    const ls = d.getElementById('bf-Ls');
    ls.value = '5.5';
    ls.dispatchEvent(new w.Event('input', { bubbles: true }));
    await frame();
    assert.match(lastHash(), /"bd"/, 'the design state must reach the hash');
    const h = JSON.parse(lastHash().slice(1));
    assertClose(h.bd.Ls, 5.5e-6, 'Ls in the hash', 1e-12);
    // A v2 scenario export must carry the same state.
    const blob = captureExport(w, 'expScen');
    const obj = JSON.parse(await readBlob(w, blob));
    assert.ok(obj.bd && Math.abs(obj.bd.Ls - 5.5e-6) < 1e-15, 'scenario must carry the design state');
    // ...and a link that carries it restores it, opening the workspace it names.
    const hash = '#' + encodeURIComponent(JSON.stringify({
      t: 'threephase', o: { Vdc: 58, Irms: 80, M: 1, PF: 0.9, fsw: 25000 },
      a: 'EPC2361', b: 'IAUTN08S7N006ATMA1',
      bd: { Ls: 6.6e-6, ippPct: 15, ind: 'WE_7443634700' }, ws: 'bridge',
    }));
    const r2 = bootHashed(hash);
    const d2 = r2.w.document;
    assert.equal(d2.getElementById('ws-bridge').hidden, false, 'the named workspace must open');
    assertClose(parseFloat(d2.getElementById('bf-Ls').value), 6.6, 'Ls restored from the link', 1e-9);
    assertClose(parseFloat(d2.getElementById('bf-ippPct').value), 15, 'target restored', 1e-9);
    assert.equal(d2.getElementById('bf-ind').value, 'WE_7443634700', 'selected inductor restored');
    assert.deepEqual(errors, [], 'the design-state round trip raised script errors');
    assert.deepEqual(r2.errors, []);
  });


