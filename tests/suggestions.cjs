// Exercise the shipped search code with controlled fetch and JSON completion order.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('src/atlas_cli/wiki/shell.html', 'utf8');
const script = html.slice(html.indexOf('  const input = document.querySelector(".navbar .search'), html.indexOf('  // Keys: / searches'));

async function scenario(stage, dismissal) {
  const handlers = {}, docHandlers = {};
  let timer, resolveFetch, resolveJSON;
  const input = {value: 'thing', addEventListener: (name, fn) => handlers[name] = fn, blur() {}};
  const box = {hidden: true, children: [], replaceChildren(...items) {this.children = items;}, contains() {return false;}};
  const document = {
    querySelector: s => s.includes('input') ? input : box,
    addEventListener: (name, fn) => docHandlers[name] = fn,
    createElement: () => ({setAttribute() {}, append() {}}),
  };
  vm.runInNewContext(script, {document, setTimeout: fn => timer = fn, clearTimeout() {},
    fetch: () => new Promise(resolve => resolveFetch = resolve), location: {}});
  handlers.input();
  const pending = timer();
  if (stage === 'json') {
    resolveFetch({json: () => new Promise(resolve => resolveJSON = resolve)});
    await new Promise(setImmediate);
    assert.ok(resolveJSON, 'JSON was awaited');
  }
  if (dismissal === 'clear') {input.value = ''; handlers.input();}
  else if (dismissal === 'escape') handlers.keydown({key: 'Escape'});
  else docHandlers.click({target: {}});
  const items = [{title: 'stale result', url: '/stale', sub: 'old'}];
  if (stage === 'fetch') resolveFetch({json: async () => items});
  else resolveJSON(items);
  await pending;
  assert.equal(box.hidden, true, `${stage}/${dismissal}: dismissed results reappeared`);
  assert.equal(box.children.length, 0);
}
(async () => {
  const failures = [];
  for (const stage of ['fetch', 'json'])
    for (const dismissal of ['clear', 'escape', 'outside']) {
      try { await scenario(stage, dismissal); } catch (err) { failures.push(err.message); }
    }
  assert.deepEqual(failures, []);
  console.log('6 suggestion cancellation scenarios passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
