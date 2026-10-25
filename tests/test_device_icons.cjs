'use strict';
// Offline SVG catalog checks, no private router data or browser network access.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'../app/static/devices.js'),'utf8');
const css=fs.readFileSync(path.join(__dirname,'../app/static/devices.css'),'utf8');
const match=script.match(/const categoryPaths=(\{[^;]+\});/);
assert.ok(match,'offline icon paths must be static and self-contained');
const paths=JSON.parse(match[1]);
const expected=['smartphone','tablet','laptop','desktop','game_console','smart_tv','streaming_box','printer','camera','robot_vacuum','network_device','iot','unknown'];
assert.deepEqual(Object.keys(paths).sort(),expected.sort());
for(const [name,svg] of Object.entries(paths)){
 assert.match(svg, /^<(path|rect|circle)/,name+' has no icon');
 assert.ok(!/script|onload|foreignObject|href=|https?:/i.test(svg),'unsafe SVG '+name);
 assert.ok(css.includes('cat-'+name)||name==='unknown','category has no CSS '+name);
}
assert.match(script,/aria-hidden=\\?"true\\?"/,'decorative icons should be hidden to screen readers');
assert.match(script,/categoryPaths\[category\(c\)\]/,'unknown class must use safe allowlisted fallback');
assert.match(script,/identity-symbol cat-/,'dossier and inventory must share category');
console.log('Offline category icon catalog passed: '+expected.length+' SVG types, fallback and a11y.');
