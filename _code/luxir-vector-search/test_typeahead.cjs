const { chromium } = require('/Users/mschonaker/.config/opencode/skills/playwright-screenshot/node_modules/playwright-core');

const base = process.argv[2] || 'http://localhost:8099';

let pass = 0, fail = 0;
function check(name, got, want) {
  const ok = got === want;
  ok ? pass++ : fail++;
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${name}${ok ? '' : `  (got ${got}, want ${want})`}`);
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

  const q = page.locator('input[name=q]');
  const open = async () => {
    await q.click();
    await q.pressSequentially('earbud', { delay: 80 });
    await page.waitForSelector('.ta-box', { timeout: 6000 });
    await page.waitForTimeout(250);
  };
  const taLen = () => page.evaluate(() => document.querySelector('.ta').innerHTML.length);
  const found = () => page.evaluate(() => {
    const m = document.querySelector('.meta');
    return m ? (m.textContent.match(/([\d]+) products/) || [])[1] : null;
  });
  const reset = async () => {
    await page.goto(base + '/', { waitUntil: 'networkidle' });
    await page.waitForTimeout(400);
  };

  // 1. typing opens it
  await reset();
  await open();
  check('typeahead opens while typing', (await taLen()) > 500, true);

  // 2. Enter closes it, submits the form, and lands on the query URL
  await q.press('Enter');
  await page.waitForTimeout(1000);
  check('Enter closes the dropdown', await taLen(), 0);
  check('Enter submits the form', new URL(page.url()).searchParams.get('q'), 'earbud');
  check('Enter shows results for the query',
    (await found()) !== null && (await found()) !== '0', true);

  // 3. Enter fires immediately, before the debounce can issue its request
  await reset();
  await q.click();
  await q.pressSequentially('tv', { delay: 40 });
  await q.press('Enter');
  await page.waitForTimeout(1500);
  check('fast Enter closes the dropdown', await taLen(), 0);
  check('fast Enter submits the form', new URL(page.url()).searchParams.get('q'), 'tv');

  // 4. The Search button closes it too, and submits
  await reset();
  await open();
  await page.locator('button[type=submit]').click();
  await page.waitForTimeout(1200);
  check('Search button closes the dropdown', await taLen(), 0);
  check('Search button submits', new URL(page.url()).searchParams.get('q'), 'earbud');

  // 5. Escape closes it. type=search clears itself on Escape in WebKit, so the
  // box emptying afterwards is native behaviour, not a bug.
  await reset();
  await open();
  await q.press('Escape');
  await page.waitForTimeout(600);
  check('Escape closes the dropdown', await taLen(), 0);
  check('Escape empties the box (native)', await q.inputValue(), '');
  check('Escape does not submit the form', new URL(page.url()).searchParams.has('q'), false);

  // 6. Typing again after Enter reopens it
  await reset();
  await open();
  await q.press('Enter');
  await page.waitForTimeout(900);
  check('closed after Enter', await taLen(), 0);
  await q.click();
  await q.press('Meta+A');
  await q.pressSequentially('tv', { delay: 80 });
  await page.waitForTimeout(1000);
  check('reopens on the next keystrokes', (await taLen()) > 100, true);

  // 7. A query with no prefix matches still reopens, as "No matches"
  await q.click();
  await q.press('Meta+A');
  await q.pressSequentially('zzzzqqq', { delay: 40 });
  await page.waitForTimeout(1000);
  check('no-match query still opens', (await taLen()) > 0, true);

  // 7. Clicking a suggestion still lands (needs the 250 ms blur window)
  await reset();
  await open();
  const href = await page.evaluate(() => {
    const a = document.querySelector('.ta a[href]');
    return a ? a.getAttribute('href') : null;
  });
  check('suggestions are links', href !== null, true);
  await page.locator('.ta a[href]').first().click();
  await page.waitForTimeout(1200);
  check('clicking a suggestion navigates',
    page.url().includes(encodeURIComponent(href).replace(/%20/g, '+').replace(/%2B/gi, '+'))
      || page.url() !== base + '/', true);

  // 8. Back navigation restores a full page, dropdown empty
  await reset();
  await open();
  await q.press('Enter');
  await page.waitForTimeout(900);
  await page.goBack();
  await page.waitForTimeout(1200);
  check('history restore has no dropdown', await taLen(), 0);
  check('history restore is a full page',
    await page.evaluate(() => !!document.querySelector('header form')), true);

  console.log(`\n${pass} passed, ${fail} failed`);
  console.log('errors:', errors.length, errors.slice(0, 3));
  await browser.close();
  process.exit(fail ? 1 : 0);
})();