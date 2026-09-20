const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const {JSDOM} = require('jsdom');

const source = path.resolve(__dirname, '../../frontend/app.js');

test('a slower screen cannot overwrite the latest navigation', async () => {
  const dom = new JSDOM(
    '<div class="sidebar"><button data-screen="fast"></button></div><header><strong id="title"></strong></header><main id="view"></main>',
    {runScripts: 'outside-only'},
  );
  const {window} = dom;
  window.eval(`${fs.readFileSync(source, 'utf8')}
    window.stopCamera = () => {};
    window.visibleMenu = () => [['slow', 'Slow'], ['fast', 'Fast']];
    window.homeScreen = () => 'fast';
    state.user = {mustChangePassword: false};
    screens.slow = async view => {
      await new Promise(resolve => { window.releaseSlowScreen = resolve; });
      view.innerHTML = '<h2>Slow response</h2>';
    };
    screens.fast = async view => { view.innerHTML = '<h2>Fast response</h2>'; };
  `);

  const slowNavigation = window.navigate('slow');
  await window.navigate('fast');
  window.releaseSlowScreen();
  await slowNavigation;

  assert.equal(window.document.querySelector('#view h2')?.textContent, 'Fast response');
  dom.window.close();
});
