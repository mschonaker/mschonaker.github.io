const { chromium } = require('/Users/mschonaker/.config/opencode/skills/playwright-screenshot/node_modules/playwright-core');

const base = process.argv[2] || 'http://localhost:8099';
const out = process.argv[3];

const ready = async (page) => {
  await page.waitForFunction(
    () => document.images.length === 0 || [...document.images].every((i) => i.complete),
    null,
    { timeout: 10000 }
  ).catch(() => {});
  await page.waitForTimeout(250);
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));

  // Hybrid results, facets live
  await page.goto(`${base}/?q=noise%20cancelling%20earbuds&mode=hybrid`, { waitUntil: 'networkidle' });
  await ready(page);
  await page.screenshot({ path: `${out}/luxir-vector-hybrid.jpg`, type: 'jpeg', quality: 80 });

  // Vectors only, the recall knob at its smallest
  await page.goto(`${base}/?q=headphones&mode=vectors&pool=20`, { waitUntil: 'networkidle' });
  await ready(page);
  await page.screenshot({ path: `${out}/luxir-vector-vectors.jpg`, type: 'jpeg', quality: 80 });

  // Words only, same query, for the side-by-side
  await page.goto(`${base}/?q=headphones&mode=words`, { waitUntil: 'networkidle' });
  await ready(page);
  await page.screenshot({ path: `${out}/luxir-vector-words.jpg`, type: 'jpeg', quality: 80 });

  // Facet click on top of the fused list
  await page.goto(`${base}/?q=headphones&mode=hybrid`, { waitUntil: 'networkidle' });
  await page.click('.facets a:text("Sony")');
  await page.waitForTimeout(900);
  await ready(page);
  await page.screenshot({ path: `${out}/luxir-vector-facets.jpg`, type: 'jpeg', quality: 80 });

  console.log('done, pageerrors:', errors.length, errors.slice(0, 3));
  await browser.close();
})();