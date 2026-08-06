import { chromium } from 'playwright';
import { existsSync, readdirSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';

const appUrl = process.env.QA_URL || 'http://127.0.0.1:8787/';
const outputDir = process.env.QA_OUTPUT_DIR || '/tmp/ayuda-zoom-qa';
const minZoom = 6;
const maxZoom = 21;
const nationalMaxZoom = 14;
const damageMaxZoom = 18;
const mockTileSvg = Buffer.from(
  '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#d7e3d8"/><path d="M0 190 70 150 130 170 210 120 256 142v114H0z" fill="#7f9f72"/><path d="M0 82h256" stroke="#a8b8bd" stroke-width="18" opacity=".55"/></svg>'
);

function cachedPlaywrightChromiumExecutable() {
  const cacheDir = `${process.env.HOME || ''}/Library/Caches/ms-playwright`;
  if (!existsSync(cacheDir)) return undefined;

  return readdirSync(cacheDir)
    .filter((entry) => entry.startsWith('chromium_headless_shell-'))
    .sort()
    .reverse()
    .flatMap((entry) => [
      `${cacheDir}/${entry}/chrome-headless-shell-mac-arm64/chrome-headless-shell`,
      `${cacheDir}/${entry}/chrome-headless-shell-linux/chrome-headless-shell`
    ])
    .find((path) => existsSync(path));
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function currentZoom(page) {
  const raw = await page.locator('main.map-shell').getAttribute('data-map-zoom');
  return Number(raw);
}

async function waitForZoom(page, target) {
  await page.waitForFunction(
    (expected) => Number(document.querySelector('main.map-shell')?.getAttribute('data-map-zoom')) === expected,
    target,
    { timeout: 7000 }
  );
}

async function zoomTo(page, target, label) {
  const zoomIn = page.getByRole('button', { name: 'Zoom in map' });
  const zoomOut = page.getByRole('button', { name: 'Zoom out map' });

  for (let attempt = 0; attempt < 40; attempt += 1) {
    const before = await currentZoom(page);
    if (before === target) return;

    const direction = target > before ? 'in' : 'out';
    const control = direction === 'in' ? zoomIn : zoomOut;
    assert(await control.isEnabled(), `${label}: zoom ${direction} was disabled at ${before}, before reaching ${target}`);
    await control.click();
    await page.waitForFunction(
      ({ previous, expected }) => {
        const next = Number(document.querySelector('main.map-shell')?.getAttribute('data-map-zoom'));
        return expected > previous ? next > previous : next < previous;
      },
      { previous: before, expected: target },
      { timeout: 7000 }
    );
  }

  throw new Error(`${label}: zoom did not reach ${target}; current zoom ${await currentZoom(page)}`);
}

async function assertZoomRange(page, label, observations, expectedMaxZoom = maxZoom) {
  const zoomIn = page.getByRole('button', { name: 'Zoom in map' });
  const zoomOut = page.getByRole('button', { name: 'Zoom out map' });
  const start = await currentZoom(page);

  await zoomTo(page, expectedMaxZoom, label);
  await waitForZoom(page, expectedMaxZoom);
  assert(await zoomOut.isEnabled(), `${label}: zoom out disabled at max zoom`);
  assert(!(await zoomIn.isEnabled()), `${label}: zoom in still enabled at max zoom`);
  await page.screenshot({ path: `${outputDir}/${label.replaceAll(' ', '-')}-max.png`, fullPage: true });

  await zoomTo(page, minZoom, label);
  await waitForZoom(page, minZoom);
  assert(await zoomIn.isEnabled(), `${label}: zoom in disabled at min zoom`);
  assert(!(await zoomOut.isEnabled()), `${label}: zoom out still enabled at min zoom`);
  await page.screenshot({ path: `${outputDir}/${label.replaceAll(' ', '-')}-min.png`, fullPage: true });

  observations.push({ label, start, max: expectedMaxZoom, min: minZoom });
}

async function configurePage(page) {
  await page.route(/https:\/\/(?:tiles\.maps\.eox\.at|tiles\.openaerialmap\.org|titiler\.hotosm\.org)\/.*/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'image/svg+xml',
      body: mockTileSvg
    });
  });

  await page.route('https://nominatim.openstreetmap.org/search**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          place_id: 26062027,
          osm_type: 'node',
          osm_id: 424243,
          display_name: 'Catia La Mar, Municipio Vargas, La Guaira, Venezuela',
          lat: '10.602000',
          lon: '-67.030000',
          type: 'town',
          class: 'place',
          importance: 0.78,
          boundingbox: ['10.601900', '10.602100', '-67.030100', '-67.029900'],
          address: {
            town: 'Catia La Mar',
            state: 'La Guaira',
            country: 'Venezuela'
          }
        }
      ])
    });
  });

  await page.goto(appUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.getByRole('button', { name: 'English' }).click();
  await page.locator('main.map-shell[data-map-zoom]').waitFor({ timeout: 10000 });
  await page.waitForFunction(
    () => [...document.querySelectorAll('.leaflet-tile')].some((image) => image.complete && image.naturalWidth > 0),
    null,
    { timeout: 30000 }
  );
}

async function runScenario(browser, label, callback, observations) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    deviceScaleFactor: 1
  });
  const page = await context.newPage();
  const consoleIssues = [];
  const pageErrors = [];

  page.on('console', (message) => {
    if (['error', 'warning'].includes(message.type())) consoleIssues.push(`${message.type()}: ${message.text()}`);
  });
  page.on('pageerror', (error) => pageErrors.push(error.message));

  try {
    await configurePage(page);
    await callback(page);
    assert(consoleIssues.length === 0, `${label}: console issues ${JSON.stringify(consoleIssues)}`);
    assert(pageErrors.length === 0, `${label}: page errors ${JSON.stringify(pageErrors)}`);
  } finally {
    await context.close();
  }
}

async function enableComparison(page) {
  const addressSearch = page.getByRole('textbox', { name: 'Search address or place in Venezuela' });
  await addressSearch.fill('Catia La Mar');
  await page.waitForFunction(() => document.querySelectorAll('.address-results [role="option"]').length > 0, null, { timeout: 15000 });
  await page.getByRole('option', { name: /Catia La Mar/ }).click();
  await page.getByRole('slider', { name: 'Move before and after satellite comparison' }).waitFor({ state: 'visible' });
  await waitForZoom(page, 19);
}

async function enableDamage(page) {
  await page.getByRole('button', { name: 'Microsoft AI affected buildings' }).click();
  await page.waitForFunction(
    () => document.querySelector('.layer-row[aria-label="Microsoft AI affected buildings"]')?.getAttribute('aria-pressed') === 'true',
    null,
    { timeout: 5000 }
  );
}

async function enableSuperResolution(page) {
  const control = page.getByRole('button', { name: 'AI super-resolution' });
  if ((await control.count()) === 0) return false;
  await control.click();
  await page.locator('.super-resolution-panel').waitFor({ state: 'visible', timeout: 10000 });
  return true;
}

async function enableWorstArea(page, rank) {
  if ((await page.locator('.app[data-worst-experience="true"]').count()) === 0) {
    await page.getByRole('button', { name: 'View key affected areas' }).click();
    await page.locator('.app[data-worst-experience="true"]').waitFor({ timeout: 10000 });
  }

  const selector = `button[aria-label^="Area ${rank}:"]`;
  await page.locator(selector).click();
  await page.waitForFunction(
    () => Number(document.querySelector('main.map-shell')?.getAttribute('data-map-zoom')) === 20,
    null,
    { timeout: 10000 }
  );
}

async function dispatchPinchOut(client, centerX, centerY) {
  await client.send('Input.dispatchTouchEvent', {
    type: 'touchStart',
    touchPoints: [
      { x: centerX - 22, y: centerY, id: 11 },
      { x: centerX + 22, y: centerY, id: 12 }
    ]
  });

  for (const distance of [36, 58, 86, 118, 152]) {
    await client.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [
        { x: centerX - distance, y: centerY, id: 11 },
        { x: centerX + distance, y: centerY, id: 12 }
      ]
    });
    await new Promise((resolve) => setTimeout(resolve, 80));
  }

  await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
}

async function assertMobileXComparisonGestures(browser, observations) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 3,
    hasTouch: true,
    isMobile: true,
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 ' +
      '(KHTML, like Gecko) Version/17.5 Mobile/15E148 Twitter for iPhone XTwitter'
  });
  const page = await context.newPage();
  const consoleIssues = [];
  const pageErrors = [];

  page.on('console', (message) => {
    if (['error', 'warning'].includes(message.type())) consoleIssues.push(`${message.type()}: ${message.text()}`);
  });
  page.on('pageerror', (error) => pageErrors.push(error.message));

  try {
    await configurePage(page);
    await page.getByRole('button', { name: 'View key affected areas' }).click();
    await page.locator('.app[data-worst-experience="true"]').waitFor({ timeout: 10000 });
    await waitForZoom(page, 20);
    const slider = page.getByRole('slider', { name: 'Move before and after satellite comparison' });
    const baseline = await page.evaluate(() => ({
      xWebview: document.querySelector('.app')?.getAttribute('data-x-webview'),
      toolbarDisplay: getComputedStyle(document.querySelector('.map-toolbar')).display,
      surfacePointerEvents: getComputedStyle(document.querySelector('.satellite-comparison-controls')).pointerEvents,
      split: Number(document.querySelector('.comparison-control')?.getAttribute('aria-valuenow')),
      zoom: Number(document.querySelector('main.map-shell')?.getAttribute('data-map-zoom'))
    }));

    assert(baseline.xWebview === 'true', 'mobile X comparison: X webview mode was not detected');
    assert(baseline.toolbarDisplay !== 'none', 'mobile X comparison: map toolbar hidden in comparison mode');
    assert(
      baseline.surfacePointerEvents === 'none',
      'mobile X comparison: full-screen comparison overlay still intercepts map gestures'
    );

    const client = await context.newCDPSession(page);
    const sliderBox = await slider.boundingBox();
    assert(sliderBox, 'mobile X comparison: slider handle has no bounding box');
    const sliderY = Math.round(sliderBox.y + sliderBox.height / 2);
    await client.send('Input.dispatchTouchEvent', {
      type: 'touchStart',
      touchPoints: [{ x: Math.round(sliderBox.x + sliderBox.width / 2), y: sliderY, id: 1 }]
    });
    await client.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x: 330, y: sliderY, id: 1 }]
    });
    await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await page.waitForFunction(
      () => Number(document.querySelector('.comparison-control')?.getAttribute('aria-valuenow')) > 65,
      null,
      { timeout: 5000 }
    );

    const mapBox = await page.locator('.map-canvas').boundingBox();
    assert(mapBox, 'mobile X comparison: map canvas has no bounding box');
    const zoomBeforePinch = await currentZoom(page);
    await dispatchPinchOut(
      client,
      Math.round(mapBox.x + mapBox.width / 2),
      Math.round(mapBox.y + mapBox.height / 2 + 80)
    );
    await page.waitForFunction(
      (previousZoom) => Number(document.querySelector('main.map-shell')?.getAttribute('data-map-zoom')) > previousZoom,
      zoomBeforePinch,
      { timeout: 7000 }
    );

    const finalState = {
      split: Number(await slider.getAttribute('aria-valuenow')),
      zoom: await currentZoom(page)
    };
    assert(finalState.split > 65, `mobile X comparison: slider did not move, got ${finalState.split}`);
    assert(finalState.zoom > zoomBeforePinch, `mobile X comparison: pinch did not zoom in from ${zoomBeforePinch}`);
    assert(consoleIssues.length === 0, `mobile X comparison: console issues ${JSON.stringify(consoleIssues)}`);
    assert(pageErrors.length === 0, `mobile X comparison: page errors ${JSON.stringify(pageErrors)}`);

    observations.push({
      label: 'mobile X comparison gestures',
      startZoom: baseline.zoom,
      pinchZoom: finalState.zoom,
      startSplit: baseline.split,
      dragSplit: finalState.split
    });
  } finally {
    await context.close();
  }
}

await mkdir(outputDir, { recursive: true });
const chromiumExecutablePath =
  process.env.CHROMIUM_EXECUTABLE_PATH ||
  cachedPlaywrightChromiumExecutable() ||
  [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
  ].find((path) => existsSync(path));
const browser = await chromium.launch({
  headless: true,
  ...(chromiumExecutablePath ? { executablePath: chromiumExecutablePath } : {})
});
const observations = [];

try {
  await runScenario(browser, 'national', async (page) => {
    await assertZoomRange(page, 'national view', observations, nationalMaxZoom);
  }, observations);

  await runScenario(browser, 'damage', async (page) => {
    await enableDamage(page);
    await assertZoomRange(page, 'damage layer view', observations, damageMaxZoom);
  }, observations);

  await runScenario(browser, 'comparison', async (page) => {
    await enableComparison(page);
    await assertZoomRange(page, 'comparison view', observations);
  }, observations);

  await runScenario(browser, 'super-resolution', async (page) => {
    const enabled = await enableSuperResolution(page);
    if (!enabled) {
      observations.push({ label: 'super-resolution view', skipped: 'No super-resolution index available' });
      return;
    }
    await assertZoomRange(page, 'super-resolution view', observations, nationalMaxZoom);
  }, observations);

  await runScenario(browser, 'affected areas', async (page) => {
    for (const rank of [1, 2, 3]) {
      await enableWorstArea(page, rank);
      await assertZoomRange(page, `affected area ${rank}`, observations);
    }
  }, observations);

  await assertMobileXComparisonGestures(browser, observations);
} finally {
  await browser.close();
}

await writeFile(`${outputDir}/summary.json`, JSON.stringify({ appUrl, minZoom, maxZoom, observations }, null, 2));
console.log(JSON.stringify({ appUrl, minZoom, maxZoom, observations }, null, 2));
