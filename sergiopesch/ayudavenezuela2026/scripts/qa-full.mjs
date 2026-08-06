import { chromium } from 'playwright';
import { existsSync, readdirSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';

const appUrl = process.env.QA_URL || 'http://localhost:5173/';
const outputDir = process.env.QA_OUTPUT_DIR || '/tmp/ayuda-full-qa';
const ownerToolsEnabled = process.env.QA_OWNER_TOOLS === '1' || process.env.VITE_OWNER_TOOLS === 'true';
function cachedPlaywrightChromiumExecutable() {
  const cacheDir = `${process.env.HOME || ''}/Library/Caches/ms-playwright`;
  if (!existsSync(cacheDir)) return undefined;

  return readdirSync(cacheDir)
    .filter((entry) => entry.startsWith('chromium_headless_shell-'))
    .sort()
    .reverse()
    .map((entry) => `${cacheDir}/${entry}/chrome-headless-shell-mac-arm64/chrome-headless-shell`)
    .find((path) => existsSync(path));
}

const chromiumExecutablePath =
  process.env.CHROMIUM_EXECUTABLE_PATH ||
  cachedPlaywrightChromiumExecutable() ||
  [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
  ].find((path) => existsSync(path));
const errors = [];
const warnings = [];
const observations = [];

function log(name, value = 'ok') {
  observations.push({ name, value });
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function text(locator) {
  return (await locator.textContent()) || '';
}

async function hasClass(locator, className) {
  return locator.evaluate((el, cls) => el.classList.contains(cls), className);
}

async function hasText(locator, expected, message) {
  const startedAt = Date.now();
  let currentText = '';

  while (Date.now() - startedAt < 5000) {
    try {
      currentText = await text(locator);
      if (currentText.includes(expected)) return;
    } catch {
      currentText = '';
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }

  assert(currentText.includes(expected), message || `Expected text ${expected}`);
}

async function moveComparisonSliderTo(page, slider, target) {
  await slider.focus();

  for (let attempts = 0; attempts < 60; attempts += 1) {
    const current = Number(await slider.getAttribute('aria-valuenow'));
    if (current === target) return;
    await page.keyboard.press(current > target ? 'ArrowLeft' : 'ArrowRight');
  }

  const finalValue = await slider.getAttribute('aria-valuenow');
  assert(Number(finalValue) === target, `Comparison slider reached ${finalValue}, expected ${target}`);
}

async function touchDragComparisonSliderTo(page, slider, target) {
  const mapBox = await page.locator('.map-canvas').boundingBox();
  const sliderBox = await slider.boundingBox();
  assert(mapBox, 'Map canvas was not measurable for touch slider drag');
  assert(sliderBox, 'Comparison slider was not measurable for touch slider drag');

  const startX = sliderBox.x + sliderBox.width / 2;
  const targetX = mapBox.x + mapBox.width * (target / 100);
  const y = sliderBox.y + sliderBox.height / 2;
  await touchPanMap(page, { x: startX, y }, { x: targetX, y });

  const finalValue = Number(await slider.getAttribute('aria-valuenow'));
  assert(Math.abs(finalValue - target) <= 2, `Touch comparison slider reached ${finalValue}, expected ${target}`);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await assertComparisonAlignment(page, 'touch slider alignment');
}

async function touchPanMap(page, start, end) {
  const client = await page.context().newCDPSession(page);
  await client.send('Input.dispatchTouchEvent', {
    type: 'touchStart',
    touchPoints: [{ x: start.x, y: start.y }]
  });

  const steps = 12;
  for (let step = 1; step <= steps; step += 1) {
    const progress = step / steps;
    await client.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [
        {
          x: start.x + (end.x - start.x) * progress,
          y: start.y + (end.y - start.y) * progress
        }
      ]
    });
  }

  await client.send('Input.dispatchTouchEvent', {
    type: 'touchEnd',
    touchPoints: []
  });
  await client.detach();
}

async function captureMapCanvas(page, path) {
  const box = await page.locator('.map-canvas').boundingBox();
  assert(box, 'Map canvas was not measurable for screenshot comparison');
  return page.screenshot({
    path,
    clip: {
      x: Math.max(0, box.x),
      y: Math.max(0, box.y),
      width: Math.max(1, Math.min(box.width, page.viewportSize().width - box.x)),
      height: Math.max(1, Math.min(box.height, page.viewportSize().height - box.y))
    }
  });
}

async function withMapChromeHidden(page, callback) {
  const styleHandle = await page.addStyleTag({
    content: `
      .comparison-divider,
      .comparison-control,
      .comparison-context,
      .comparison-side-labels,
      .damage-legend,
      .map-status,
      .map-toolbar,
      .mobile-map-controls,
      .super-resolution-panel {
        visibility: hidden !important;
      }
    `
  });

  try {
    return await callback();
  } finally {
    await styleHandle.evaluate((element) => element.remove());
  }
}

function byteDifferenceRatio(left, right) {
  const length = Math.max(left.length, right.length);
  let differences = Math.abs(left.length - right.length);
  const shared = Math.min(left.length, right.length);

  for (let index = 0; index < shared; index += 1) {
    if (left[index] !== right[index]) differences += 1;
  }

  return differences / length;
}

async function waitForComparisonTiles(page) {
  await page.waitForFunction(
    () => {
      const beforeImages = [...document.querySelectorAll('.comparison-before-tile-layer img')];
      const afterImages = [...document.querySelectorAll('.comparison-after-tile-layer img')];
      const loaded = (image) => image.complete && image.naturalWidth >= 256 && image.naturalHeight >= 256;
      return beforeImages.some(loaded) && afterImages.some(loaded);
    },
    null,
    { timeout: 25000 }
  );
}

async function assertComparisonAlignment(page, label) {
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const metrics = await page.evaluate(() => {
    const rect = (element) => {
      const box = element?.getBoundingClientRect();
      return box ? { left: box.left, right: box.right, width: box.width, x: box.x } : null;
    };
    const loadedTiles = (selector) => [...document.querySelectorAll(`${selector} img`)].filter((image) =>
      image.complete && image.naturalWidth >= 256 && image.naturalHeight >= 256
    );
    const visibleTiles = (selector) => loadedTiles(selector).filter((image) => {
      const box = image.getBoundingClientRect();
      const style = getComputedStyle(image);
      return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0;
    });
    const slider = document.querySelector('.comparison-control');
    const canvas = rect(document.querySelector('.map-canvas'));
    const mapPane = rect(document.querySelector('.leaflet-map-pane'));
    const divider = rect(document.querySelector('.comparison-divider'));
    const grip = rect(document.querySelector('.comparison-grip'));
    const beforeLayer = document.querySelector('.comparison-before-tile-layer');
    const afterLayer = document.querySelector('.comparison-after-tile-layer');
    const damageLayer = document.querySelector('.comparison-damage-raster-layer');
    const value = Number(slider?.getAttribute('aria-valuenow') || 0);
    const splitX = canvas ? canvas.left + canvas.width * (value / 100) : 0;
    const clip = (layer) => (layer ? getComputedStyle(layer).clip : '');
    const parseRect = (value) => {
      const match = value.match(/rect\(([^)]+)\)/);
      if (!match) return null;
      const parts = match[1].trim().split(/[,\s]+/).filter(Boolean).map((part) => Number.parseFloat(part));
      if (parts.some((part) => Number.isNaN(part))) return null;
      const [top, right, bottom, left] = parts;
      return { top, right, bottom, left };
    };
    const beforeRect = rect(beforeLayer);
    const afterRect = rect(afterLayer);
    const damageRect = rect(damageLayer);
    const beforeRectClip = parseRect(clip(beforeLayer));
    const afterRectClip = parseRect(clip(afterLayer));
    const damageRectClip = parseRect(clip(damageLayer));

    return {
      value,
      splitX,
      dividerCenter: divider ? divider.left + divider.width / 2 : null,
      gripCenter: grip ? grip.left + grip.width / 2 : null,
      beforeClip: clip(beforeLayer),
      afterClip: clip(afterLayer),
      damageClip: clip(damageLayer),
      beforeVisibleTiles: visibleTiles('.comparison-before-tile-layer').length,
      afterVisibleTiles: visibleTiles('.comparison-after-tile-layer').length,
      beforeTiles: loadedTiles('.comparison-before-tile-layer').length,
      afterTiles: loadedTiles('.comparison-after-tile-layer').length,
      beforeBoundary: mapPane && beforeRect && beforeRectClip ? mapPane.left + beforeRectClip.right : null,
      afterBoundary: mapPane && afterRect && afterRectClip ? mapPane.left + afterRectClip.left : null,
      damageBoundary: mapPane && damageRect && damageRectClip ? mapPane.left + damageRectClip.left : null,
      hasDamageLayer: Boolean(damageLayer),
      damageTiles: document.querySelectorAll('.comparison-damage-raster-layer img').length
    };
  });

  assert(Math.abs(metrics.dividerCenter - metrics.splitX) <= 1.5, `${label}: divider is not aligned to split ${JSON.stringify(metrics)}`);
  assert(Math.abs(metrics.gripCenter - metrics.splitX) <= 1.5, `${label}: grip is not aligned to split ${JSON.stringify(metrics)}`);
  assert(metrics.beforeClip.includes('rect') && metrics.afterClip.includes('rect'), `${label}: comparison layers should use rect pixel clips ${JSON.stringify(metrics)}`);
  assert(metrics.beforeVisibleTiles > 0 && metrics.afterVisibleTiles > 0, `${label}: comparison layers should stay visible ${JSON.stringify(metrics)}`);
  assert(metrics.beforeTiles > 0 && metrics.afterTiles > 0, `${label}: comparison layers should keep loaded tiles ${JSON.stringify(metrics)}`);
  assert(Math.abs(metrics.beforeBoundary - metrics.splitX) <= 1.5, `${label}: before layer clip boundary is not aligned ${JSON.stringify(metrics)}`);
  assert(Math.abs(metrics.afterBoundary - metrics.splitX) <= 1.5, `${label}: after layer clip boundary is not aligned ${JSON.stringify(metrics)}`);
  if (metrics.hasDamageLayer && metrics.damageTiles > 0) {
    assert(metrics.damageClip === metrics.afterClip, `${label}: damage layer should share after-side clipping ${JSON.stringify(metrics)}`);
    assert(Math.abs(metrics.damageBoundary - metrics.splitX) <= 1.5, `${label}: damage layer clip boundary is not aligned ${JSON.stringify(metrics)}`);
  }
}

async function assertWorstPanelViewport(page, label) {
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const metrics = await page.evaluate(() => {
    const panel = document.querySelector('.worst-experience-panel');
    if (!panel) return { exists: false };

    const bounds = panel.getBoundingClientRect();
    const style = getComputedStyle(panel);
    const previousScrollTop = panel.scrollTop;
    panel.scrollTop = 1;
    const canScroll = panel.scrollTop > 0;
    panel.scrollTop = previousScrollTop;

    return {
      exists: true,
      visible: style.display !== 'none' && style.visibility !== 'hidden' && bounds.width > 0 && bounds.height > 0,
      left: bounds.left,
      top: bounds.top,
      right: bounds.right,
      bottom: bounds.bottom,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      constrained: panel.scrollHeight > panel.clientHeight + 1,
      canScroll,
      overflowY: style.overflowY
    };
  });

  assert(metrics.exists, `${label}: affected areas panel should exist`);
  assert(metrics.visible, `${label}: affected areas panel should be visible ${JSON.stringify(metrics)}`);
  assert(
    metrics.left >= -1 && metrics.top >= -1 && metrics.right <= metrics.viewportWidth + 1 && metrics.bottom <= metrics.viewportHeight + 1,
    `${label}: affected areas panel should stay fully within viewport ${JSON.stringify(metrics)}`
  );
  if (metrics.constrained) {
    assert(['auto', 'scroll', 'overlay'].includes(metrics.overflowY) && metrics.canScroll, `${label}: constrained affected areas panel should scroll ${JSON.stringify(metrics)}`);
  }
}

async function mapView(page) {
  return page.locator('.map-shell').evaluate((element) => ({
    center: element.getAttribute('data-map-center') || '',
    zoom: Number(element.getAttribute('data-map-zoom') || '0')
  }));
}

async function placeWorstAreaPins(page, ratios) {
  const mapBox = await page.locator('.map-canvas').boundingBox();
  assert(mapBox, 'Map canvas was not measurable for affected-area pin placement');

  for (const ratio of ratios) {
    await page.mouse.click(mapBox.x + mapBox.width * ratio.x, mapBox.y + mapBox.height * ratio.y);
    await page.waitForTimeout(250);
  }
}

const browser = await chromium.launch({
  headless: true,
  ...(chromiumExecutablePath ? { executablePath: chromiumExecutablePath } : {})
});
await mkdir(outputDir, { recursive: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 980 }, deviceScaleFactor: 1 });
await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: appUrl.replace(/\/$/, '') });

page.on('console', (msg) => {
  if (msg.text().includes('Failed to load resource: the server responded with a status of 404')) return;
  if (['error', 'warning'].includes(msg.type())) errors.push(`${msg.type()}: ${msg.text()}`);
});
page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
await page.route('https://nominatim.openstreetmap.org/search**', async (route) => {
  const query = new URL(route.request().url()).searchParams.get('q') || '';
  const isCatiaQuery = /catia/i.test(query);
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify([
      isCatiaQuery ? {
        place_id: 26062027,
        osm_type: 'node',
        osm_id: 424243,
        display_name: 'Hospital Dr. Alfredo Machado, Catia La Mar, Municipio Vargas, La Guaira, Venezuela',
        lat: '10.6001961',
        lon: '-67.0387244',
        type: 'town',
        class: 'place',
        importance: 0.78,
        boundingbox: ['10.6000961', '10.6002961', '-67.0388244', '-67.0386244'],
        address: {
          town: 'Catia La Mar',
          state: 'La Guaira',
          country: 'Venezuela'
        }
      } : {
        place_id: 26062026,
        osm_type: 'node',
        osm_id: 424242,
        display_name: 'Plaza Venezuela, Parroquia El Recreo, Caracas, Municipio Libertador, Distrito Capital, Venezuela',
        lat: '10.500640',
        lon: '-66.889000',
        type: 'square',
        class: 'place',
        importance: 0.8,
        boundingbox: ['10.499900', '10.501500', '-66.890200', '-66.887900'],
        address: {
          neighbourhood: 'Plaza Venezuela',
          city: 'Caracas',
          state: 'Distrito Capital',
          country: 'Venezuela'
        }
      }
    ])
  });
});

await page.goto(appUrl, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => document.querySelector('.map-canvas.leaflet-container'), null, { timeout: 30000 });
assert((await page.title()).replaceAll(' ', '').includes('AyudaVenezuela2026DamageMap'), 'Wrong page title');
await hasText(page.locator('body'), 'Ayuda Venezuela 2026', 'App shell did not render');
assert(!(await text(page.locator('body'))).includes('Internal Server Error'), 'Framework error overlay visible');
await page.screenshot({ path: `${outputDir}/desktop-initial.png`, fullPage: true });
log('page identity');

await page.getByRole('button', { name: /English/ }).click();
assert(await hasClass(page.getByRole('button', { name: /English/ }), 'active'), 'English language button not active');
await hasText(page.locator('body'), 'Public damage visualization', 'Viewer title did not render');
await hasText(page.locator('.impact-summary-panel'), 'Verified damage', 'Verified damage summary did not render');
await hasText(page.locator('.focus-area-card'), 'Venezuela: national view', 'National view focus card did not render');
assert((await page.getByLabel('Operations area', { exact: true }).count()) === 0, 'Old operations area selector should not render');
assert((await page.locator('select#area-select').count()) === 0, 'Old area select should not exist');
await hasText(page.locator('.trusted-panel'), 'Status', 'Trusted source status panel did not render');
await hasText(page.locator('.trusted-panel'), 'Microsoft/HDX', 'Trusted source summary did not render');
await hasText(page.locator('.trusted-panel'), 'NASA', 'NASA trusted source summary did not render');
const appOrigin = appUrl.replace(/\/$/, '');
let trustedSnapshot = await page.request.get(`${appOrigin}/api/trusted-data`);
if (!trustedSnapshot.ok()) {
  trustedSnapshot = await page.request.get(`${appOrigin}/data/trusted-data.json`);
}
assert(trustedSnapshot.ok(), 'Trusted data snapshot did not return OK');
const trustedPayload = await trustedSnapshot.json();
assert(trustedPayload.summary.okSourceCount >= 11, 'Trusted data snapshot has too few active sources');
assert(trustedPayload.summary.googleDatasetCount === 2, 'Trusted data snapshot lost Google datasets');
assert(trustedPayload.summary.microsoftDamageFootprints === 9128, 'Trusted data snapshot lost Microsoft damage count');
assert(!(await page.locator('.damage-legend').isVisible()), 'Damage legend should not render before the opt-in damage layer is enabled');
await hasText(page.locator('.map-status'), 'Current', 'Initial national view should not render blank before/after comparison');
await hasText(page.locator('.map-status'), '0', 'Initial active layer count should be zero before overlay opt-in');
assert((await page.getByRole('slider', { name: 'Move before and after satellite comparison' }).count()) === 0, 'Initial national view should not render the before/after split slider');
await page.waitForFunction(() => {
  return [...document.querySelectorAll('.leaflet-tile')].filter((image) =>
    image.currentSrc.includes('s2cloudless-2024_3857') && image.complete && image.naturalWidth >= 256
  ).length >= 20;
}, null, { timeout: 25000 });
const initialMapResources = await page.evaluate(() => {
  const entries = performance.getEntriesByType('resource').map((entry) => entry.name);
  return {
    localDamageTiles: entries.filter((name) => name.includes('/data/damage-tiles/')).length,
    localSentinelTiles: entries.filter((name) => name.includes('/data/sentinel-tiles/')).length,
    localEnhancedSatelliteTiles: entries.filter((name) => name.includes('/data/enhanced-satellite-tiles/')).length,
    hotosmAreas: entries.filter((name) => name.includes('/data/hotosm-venezuela-damage-areas')).length,
    nationalOpenImageryTiles: entries.filter((name) => name.includes('s2cloudless-2024_3857')).length,
    openAerialMapTiles: entries.filter((name) => name.includes('tiles.openaerialmap.org')).length
  };
});
assert(initialMapResources.localDamageTiles === 0, 'Damage raster tiles should not load before damage layer opt-in');
assert(initialMapResources.localSentinelTiles === 0, 'Legacy Sentinel comparison tiles should not load on initial national view');
assert(initialMapResources.localEnhancedSatelliteTiles === 0, 'Enhanced comparison tiles should wait until the map is over sourced imagery bounds');
assert(initialMapResources.hotosmAreas === 0, 'HOTOSM area GeoJSON should not load on initial map view');
assert(initialMapResources.nationalOpenImageryTiles > 0, 'Initial national view should load EOX Sentinel-2 Cloudless tiles');
assert(initialMapResources.openAerialMapTiles === 0, 'Legacy OpenAerialMap comparison tiles should not load on initial national view');
log('trusted source context and damage-off default');

assert((await page.locator('.right-rail').count()) === 0, 'Right operations rail should not render');
assert((await page.locator('.selected-report-card').count()) === 0, 'Selected data card should not render');
assert((await page.locator('.queue').count()) === 0, 'Public data feed should not render');
assert((await page.locator('.triage').count()) === 0, 'Bottom triage table should not render');
assert((await page.locator('.workbench-nav').count()) === 0, 'Bottom/mobile workflow nav should not render');
assert((await page.getByRole('button', { name: /New report/ }).count()) === 0, 'New report submission button should not render');
assert((await page.getByRole('button', { name: /Validate/ }).count()) === 0, 'Validate workflow button should not render');
log('operations UI removed');

const addressSearch = page.getByRole('textbox', { name: 'Search address or place in Venezuela' });
await addressSearch.fill('Plaza Venezuela Caracas');
await page.waitForFunction(() => document.querySelectorAll('.address-results [role="option"]').length > 0, null, { timeout: 15000 });
await page.getByRole('option', { name: /Plaza Venezuela/ }).click();
await hasText(page.locator('.map-status'), 'Plaza Venezuela', 'Address search did not update map status');
await hasText(page.locator('.map-status'), 'Current', 'Address search outside comparison imagery should not force blank before/after mode');
assert((await page.getByRole('slider', { name: 'Move before and after satellite comparison' }).count()) === 0, 'Outside-footprint address search should not render the before/after split slider');
await page.waitForFunction(() => {
  const center = document.querySelector('.map-shell')?.getAttribute('data-map-center') || '';
  const [lat, lng] = center.split(',').map(Number);
  return lat > 10.45 && lat < 10.55 && lng > -66.95 && lng < -66.82;
}, null, { timeout: 25000 });
await hasText(page.locator('.focus-area-card'), 'North-central Venezuela', 'Address search outside Catia should switch the affected panel to national Venezuela context');
await hasText(page.locator('.focus-area-card'), 'Verified Microsoft/HDX footprints', 'Damage card should stay concise after national context switch');
await page.getByRole('button', { name: /Center searched address/ }).click();
await page.waitForFunction(() => {
  const center = document.querySelector('.map-shell')?.getAttribute('data-map-center') || '';
  const [lat, lng] = center.split(',').map(Number);
  return lat > 10.45 && lat < 10.55 && lng > -66.95 && lng < -66.82;
}, null, { timeout: 10000 });
log('venezuela address search');

await hasText(page.locator('.sidebar'), 'Imagery', 'Imagery source control did not render');
await hasText(page.locator('.sidebar'), 'Layers', 'Layer controls did not render');
await hasText(page.locator('.sidebar .satellite-pair-card'), '7 Apr 2026', 'Pre-event satellite date did not render');
await hasText(page.locator('.sidebar .satellite-pair-card'), '27 Jun 2026', 'Post-event satellite date did not render');
assert((await page.locator('.sidebar .base-map-grid button').count()) === 0, 'Old base-map buttons should not render');
assert((await page.locator('.sidebar .layer-row').count()) === 2, 'Sidebar should expose only damage and SR overlays');
assert((await page.locator('.sidebar .layer-row').filter({ hasText: 'Coverage' }).count()) === 0, 'Coverage layer control should not render');
assert((await page.locator('.sidebar .layer-row').filter({ hasText: 'NASA/NISAR' }).count()) === 0, 'NASA/NISAR layer control should not render');
const damageLayer = page.locator('.sidebar .layer-row').filter({ hasText: 'Damage' });
const srLayer = page.locator('.sidebar .layer-row').filter({ hasText: 'SR review' });
assert(!(await hasClass(damageLayer, 'selected')), 'Microsoft damage layer should be off by default');
assert(!(await hasClass(srLayer, 'selected')), 'AI super-resolution layer should be off by default');
await hasText(page.locator('.map-status'), 'Current', 'Comparison should stay hidden until an address inside comparison imagery is searched');
await srLayer.click();
assert(await hasClass(srLayer, 'selected'), 'AI super-resolution layer did not enable after opt-in');
await hasText(page.locator('.super-resolution-panel'), 'caidas/swin2SR-realworld-sr-x4-64', 'Super-resolution model label did not render');
await hasText(page.locator('.super-resolution-panel'), '3', 'Super-resolution AOI count did not render');
await page.waitForFunction(() => {
  const pane = document.querySelector('.leaflet-super-resolution-pane-pane');
  const markerCount = Number(pane?.getAttribute('data-aoi-count') || '0');
  const canvas = pane?.querySelector('canvas');
  const image = document.querySelector('.super-resolution-preview img');
  return markerCount >= 3 && canvas && (!image || (image.complete && image.naturalWidth >= 1000 && image.naturalHeight >= 600));
}, null, { timeout: 10000 });
const superResolutionResources = await page.evaluate(() => {
  const entries = performance.getEntriesByType('resource').map((entry) => entry.name);
  const image = document.querySelector('.super-resolution-preview img');
  return {
    index: entries.filter((name) => name.includes('/data/super-resolution/swin2sr-pilot/index.json')).length,
    contactSheet: entries.filter((name) => name.includes('/data/super-resolution/swin2sr-pilot/contact-sheet.jpg')).length,
    currentSrc: image?.currentSrc || ''
  };
});
assert(superResolutionResources.index >= 1 && superResolutionResources.index <= 2, 'Super-resolution index should load once, or twice under React dev checks');
if (superResolutionResources.currentSrc) {
  assert(superResolutionResources.currentSrc.includes('/data/super-resolution/swin2sr-pilot/contact-sheet.jpg'), 'Super-resolution contact sheet should use the active SWIN2SR source when available');
}
await page.screenshot({ path: `${outputDir}/desktop-super-resolution-review.png`, fullPage: false });
await page.getByRole('button', { name: 'Close super-resolution' }).click();
assert(!(await page.locator('.super-resolution-panel').isVisible()), 'Super-resolution panel did not close');
assert(!(await hasClass(srLayer, 'selected')), 'AI super-resolution layer did not turn off after panel close');
log('super-resolution review layer', superResolutionResources);
await addressSearch.fill('Catia La Mar');
await page.waitForFunction(() => document.querySelectorAll('.address-results [role="option"]').length > 0, null, { timeout: 15000 });
await page.getByRole('option', { name: /Catia La Mar/ }).click();
await page.waitForFunction(() => {
  const center = document.querySelector('.map-shell')?.getAttribute('data-map-center') || '';
  const [lat, lng] = center.split(',').map(Number);
  return lat > 10.57 && lat < 10.63 && lng > -67.07 && lng < -66.99;
}, null, { timeout: 10000 });
assert((await page.getByRole('slider', { name: 'Move before and after satellite comparison' }).count()) === 1, 'Before/after comparison slider should render automatically for searched addresses inside comparison imagery');
await hasText(page.locator('.map-status'), 'Compare', 'Satellite comparison should switch on automatically for in-footprint address search');
assert(!((await page.locator('.map-status').textContent()) || '').includes('Coverage'), 'Coverage status should not render after coverage layer removal');
await waitForComparisonTiles(page);
await hasText(page.locator('.comparison-side-labels'), 'Before 7 Apr', 'Before comparison label did not render');
await hasText(page.locator('.comparison-side-labels'), 'After 27 Jun', 'After comparison label did not render');
await page.waitForFunction(() => document.querySelectorAll('.named-place-label').length > 0, null, { timeout: 12000 });
const namedLabelState = await page.evaluate(() => {
  const labels = [...document.querySelectorAll('.named-place-label')].map((label) => ({
    text: label.textContent?.trim() || '',
    sourceUrl: label.getAttribute('data-source-url') || '',
    kind: label.getAttribute('data-kind') || ''
  }));
  return {
    labels,
    cacheRequests: performance.getEntriesByType('resource').filter((entry) =>
      entry.name.includes('/data/osm-named-places-catia.geojson')
    ).length,
    sourcedCount: labels.filter((label) => label.sourceUrl.startsWith('https://www.openstreetmap.org/')).length
  };
});
assert(namedLabelState.cacheRequests === 1, 'OSM named-place cache should load once in comparison mode');
assert(namedLabelState.sourcedCount === namedLabelState.labels.length, `Every rendered named-place label should keep an OSM source URL ${JSON.stringify(namedLabelState)}`);
assert(namedLabelState.labels.some((label) => label.text.includes('Hospital Dr. Alfredo Machado')), `Expected visible OSM label did not render ${JSON.stringify(namedLabelState)}`);
  assert(!(await page.locator('.damage-legend').isVisible()), 'Damage legend should not render inside clean satellite comparison mode');
  await assertComparisonAlignment(page, 'initial desktop comparison');
  const slider = page.getByRole('slider', { name: 'Move before and after satellite comparison' });
  await moveComparisonSliderTo(page, slider, 38);
  await assertComparisonAlignment(page, 'desktop comparison before zoom at 38');
  const comparisonViewBeforeZoom = await mapView(page);
  await page.getByRole('button', { name: 'Zoom in map' }).click();
  await page.waitForFunction((previousZoom) => Number(document.querySelector('.map-shell')?.getAttribute('data-map-zoom') || 0) > previousZoom, comparisonViewBeforeZoom.zoom, { timeout: 5000 });
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await assertComparisonAlignment(page, 'desktop comparison after zoom at 38');
  const comparisonViewAfterZoomIn = await mapView(page);
  await page.getByRole('button', { name: 'Zoom out map' }).click();
  await page.waitForFunction((previousZoom) => Number(document.querySelector('.map-shell')?.getAttribute('data-map-zoom') || 0) < previousZoom, comparisonViewAfterZoomIn.zoom, { timeout: 5000 });
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await assertComparisonAlignment(page, 'desktop comparison after zoom out at 38');
  const comparisonViewBeforePan = await mapView(page);
  await page.mouse.move(930, 520);
  await page.mouse.down();
  await page.mouse.move(760, 500, { steps: 16 });
  await page.mouse.up();
  await page.waitForFunction((previousCenter) => document.querySelector('.map-shell')?.getAttribute('data-map-center') !== previousCenter, comparisonViewBeforePan.center, { timeout: 5000 });
  await moveComparisonSliderTo(page, slider, 8);
await assertComparisonAlignment(page, 'desktop comparison at 8');
const comparisonAt8 = await withMapChromeHidden(page, () => captureMapCanvas(page, `${outputDir}/desktop-comparison-8.png`));
await moveComparisonSliderTo(page, slider, 92);
await assertComparisonAlignment(page, 'desktop comparison at 92');
const comparisonAt92 = await withMapChromeHidden(page, () => captureMapCanvas(page, `${outputDir}/desktop-comparison-92.png`));
const comparisonDiff = byteDifferenceRatio(comparisonAt8, comparisonAt92);
assert(comparisonDiff > 0.002, `High-resolution comparison slider did not visibly change map pixels; screenshot byte diff ratio ${comparisonDiff}`);
const cleanComparisonResources = await page.evaluate(() => {
  const entries = performance.getEntriesByType('resource').map((entry) => entry.name);
  const comparisonImages = [...document.querySelectorAll('.comparison-before-tile-layer img, .comparison-after-tile-layer img')].map((image) => image.currentSrc);
  const nationalOpenImageryImages = [...document.querySelectorAll('.national-open-imagery-tile img')].map((image) => image.currentSrc);
  const urls = [...entries, ...comparisonImages];
  return {
    localDamageTiles: urls.filter((name) => name.includes('/data/damage-tiles/')).length,
    localEnhancedAfterTiles: urls.filter((name) => name.includes('/data/enhanced-satellite-tiles/after/')).length,
    localEnhancedBeforeTiles: urls.filter((name) => name.includes('/data/enhanced-satellite-tiles/before/')).length,
    postEventVantorTiles: urls.filter((name) => name.includes('B15000110186C610.tif')).length,
    preEventVantorTiles: urls.filter((name) => name.includes('B120001100513B10.tif')).length,
    nationalOpenImageryTilesVisible: nationalOpenImageryImages.length
  };
});
assert(cleanComparisonResources.localDamageTiles === 0, 'Clean satellite comparison should not load damage raster tiles before damage opt-in');
assert(
  cleanComparisonResources.postEventVantorTiles + cleanComparisonResources.localEnhancedAfterTiles > 0,
  'Clean satellite comparison did not load post-event Vantor or enhanced after tiles'
);
assert(
  cleanComparisonResources.preEventVantorTiles + cleanComparisonResources.localEnhancedBeforeTiles > 0,
  'Clean satellite comparison did not load pre-event Vantor or enhanced before tiles'
);
assert(cleanComparisonResources.nationalOpenImageryTilesVisible > 0, 'Clean satellite comparison should keep open national imagery available as a low-priority underlay');
await page.locator('.sidebar .satellite-toggle').click();
await page.waitForFunction(() => !document.querySelector('.map-shell')?.classList.contains('comparison-active'), null, { timeout: 10000 });
await page.waitForFunction(
  () => [...document.querySelectorAll('.high-resolution-focus-tile-layer img')].some((image) =>
    image.complete && image.naturalWidth >= 256 && image.naturalHeight >= 256
  ),
  null,
  { timeout: 20000 }
);
const focusImageryResources = await page.evaluate(() => {
  const focusImages = [...document.querySelectorAll('.high-resolution-focus-tile-layer img')].map((image) => image.currentSrc);
  return {
    focusFallbackTiles: focusImages.filter((name) => name.includes('B15000110186C610.tif')).length,
    focusEnhancedTiles: focusImages.filter((name) => name.includes('/data/enhanced-satellite-tiles/after/')).length,
    comparisonTiles: document.querySelectorAll('.comparison-before-tile-layer img, .comparison-after-tile-layer img').length
  };
});
assert(focusImageryResources.comparisonTiles === 0, 'Comparison tiles should unmount when comparison is toggled off');
assert(
  focusImageryResources.focusFallbackTiles + focusImageryResources.focusEnhancedTiles > 0,
  'Comparison-off focused map should keep high-resolution post-event imagery visible'
);
await page.locator('.sidebar .satellite-toggle').click();
await waitForComparisonTiles(page);
await damageLayer.click();
assert(await hasClass(damageLayer, 'selected'), 'Microsoft damage layer did not show after opt-in');
await page.waitForFunction(() => /\d[\d,]*\s+building footprints/.test(document.querySelector('.damage-legend')?.textContent || ''), null, { timeout: 20000 });
await hasText(page.locator('.damage-legend'), 'Estimated damage', 'Damage legend did not render after opt-in');
await hasText(page.locator('.damage-legend'), 'Microsoft AI for Good Lab', 'Damage source did not render after opt-in');
assert((await page.getByRole('slider', { name: 'Move before and after satellite comparison' }).count()) === 1, 'Before/after comparison slider should stay visible with damage enabled');
await hasText(page.locator('.map-status'), 'Damage', 'Showing damage layer did not update compact map status');
await page.waitForFunction(() => {
  const resourceLoaded = performance.getEntriesByType('resource').some((entry) => entry.name.includes('/data/damage-tiles/'));
  const domLoaded = [...document.querySelectorAll('.damage-raster-layer img')].some((image) =>
    image.currentSrc.includes('/data/damage-tiles/')
  );
  return resourceLoaded || domLoaded;
}, null, { timeout: 25000 });
await assertComparisonAlignment(page, 'desktop comparison with damage');
log('minimal damage layer controls and visible comparison');

await page.waitForFunction(() => {
  const resources = performance.getEntriesByType('resource').map((entry) => entry.name);
  const damageImages = [...document.querySelectorAll('.damage-raster-layer img')].map((image) => image.currentSrc);
  const comparisonImages = [...document.querySelectorAll('.comparison-before-tile-layer img, .comparison-after-tile-layer img')].map((image) => image.currentSrc);
  const urls = [...resources, ...damageImages, ...comparisonImages];
  return urls.some((name) => name.includes('/data/damage-tiles/')) &&
    urls.some((name) => name.includes('B120001100513B10.tif') || name.includes('/data/enhanced-satellite-tiles/before/')) &&
    urls.some((name) => name.includes('B15000110186C610.tif') || name.includes('/data/enhanced-satellite-tiles/after/'));
}, null, { timeout: 10000 });
const resourceSummary = await page.evaluate(() => {
  const entries = performance.getEntriesByType('resource').map((entry) => entry.name);
  const damageImages = [...document.querySelectorAll('.damage-raster-layer img')].map((image) => image.currentSrc);
  const comparisonImages = [...document.querySelectorAll('.comparison-before-tile-layer img, .comparison-after-tile-layer img')].map((image) => image.currentSrc);
  const urls = [...entries, ...damageImages, ...comparisonImages];
  return {
    legacyTitilerRequests: entries.filter((name) => name.includes('titiler.xyz')).length,
    localEnhancedAfterTiles: urls.filter((name) => name.includes('/data/enhanced-satellite-tiles/after/')).length,
    localEnhancedBeforeTiles: urls.filter((name) => name.includes('/data/enhanced-satellite-tiles/before/')).length,
    postEventVantorTiles: urls.filter((name) => name.includes('B15000110186C610.tif')).length,
    preEventVantorTiles: urls.filter((name) => name.includes('B120001100513B10.tif')).length,
    arcgisDamageRequests: entries.filter((name) => name.includes('Catia_La_Mar_3D_WFL1/FeatureServer')).length,
    nationalOpenImageryTiles: entries.filter((name) => name.includes('s2cloudless-2024_3857')).length,
    localSentinelTiles: entries.filter((name) => name.includes('/data/sentinel-tiles/')).length,
    openAerialMapTiles: urls.filter((name) => name.includes('tiles.openaerialmap.org')).length,
    localDamageTiles: urls.filter((name) => name.includes('/data/damage-tiles/')).length,
    localDamageViewIndex: entries.filter((name) => name.includes('/data/damage-view-index.json')).length,
    localDamageSnapshots: entries.filter((name) => name.includes('/data/microsoft-damage-catia')).length
  };
});
assert(resourceSummary.arcgisDamageRequests === 0, `Map should not request live ArcGIS damage pages, saw ${resourceSummary.arcgisDamageRequests}`);
assert(resourceSummary.nationalOpenImageryTiles > 0, 'Map did not request EOX Sentinel-2 Cloudless national imagery tiles');
assert(resourceSummary.localSentinelTiles === 0, 'Legacy Sentinel comparison tiles should not load in damage comparison mode');
assert(resourceSummary.legacyTitilerRequests === 0, `Map should not request legacy titiler.xyz tiles, saw ${resourceSummary.legacyTitilerRequests}`);
assert(resourceSummary.postEventVantorTiles + resourceSummary.localEnhancedAfterTiles > 0, 'Map did not request post-event Vantor LG05 or enhanced after tiles');
assert(resourceSummary.preEventVantorTiles + resourceSummary.localEnhancedBeforeTiles > 0, 'Map did not request pre-event Vantor LG02 7 Apr or enhanced before tiles');
assert(
  resourceSummary.preEventVantorTiles + resourceSummary.postEventVantorTiles +
    resourceSummary.localEnhancedAfterTiles + resourceSummary.localEnhancedBeforeTiles > 0,
  'Map did not request comparison imagery from canonical Vantor STAC COGs or local enhanced tiles'
);
assert(resourceSummary.localDamageTiles > 0, 'Map did not request local damage raster tiles');
assert(resourceSummary.localDamageViewIndex === 1, 'Map should request one compact damage view index');
assert(resourceSummary.localDamageSnapshots === 0, 'Initial map should not request damage GeoJSON snapshots');
await page.screenshot({ path: `${outputDir}/desktop-damage-comparison.png`, fullPage: false });
if ((await page.getByRole('button', { name: 'Hide' }).count()) === 1) {
  await page.getByRole('button', { name: 'Hide' }).click();
}
assert((await page.getByRole('slider', { name: 'Move before and after satellite comparison' }).count()) === 0, 'Before/after comparison slider should hide before broad viewport panning checks');
await hasText(page.locator('.map-status'), 'Current', 'Map status should return to current satellite mode after hiding comparison');
const beforePanCount = await page.locator('.damage-legend-status').textContent();
const beforePanCoordinate = await page.locator('.focus-area-card em').textContent();
await page.mouse.move(1100, 320);
await page.mouse.down();
await page.mouse.move(300, 320, { steps: 24 });
await page.mouse.up();
await page.waitForTimeout(1000);
const afterPanCount = await page.locator('.damage-legend-status').textContent();
const afterPanArea = await page.locator('.focus-area-card strong').textContent();
const afterPanCoordinate = await page.locator('.focus-area-card em').textContent();
assert(beforePanCount !== afterPanCount, 'Visible damage count did not change after panning the map');
assert(Boolean(afterPanArea?.trim()), 'Verified damage label should remain populated after panning the map');
assert(beforePanCoordinate !== afterPanCoordinate, 'Verified damage coordinate did not change after panning the map');
await hasText(page.locator('.impact-summary-panel'), 'Current view', 'Verified damage panel did not switch to current-view mode');
await page.mouse.move(1100, 320);
await page.mouse.down();
await page.mouse.move(120, 320, { steps: 40 });
await page.mouse.up();
await page.waitForTimeout(1000);
  log('damage comparison slider, viewport summaries, and high-resolution map assets', resourceSummary);

  assert((await page.getByRole('textbox', { name: 'Search address or place in Venezuela' }).count()) === 1, 'Address search should render in the public damage view');
  await page.getByRole('button', { name: /Center searched address/ }).click();
  await page.waitForTimeout(800);
  if ((await page.getByRole('slider', { name: 'Move before and after satellite comparison' }).count()) === 0) {
    await page.getByRole('button', { name: 'Compare', exact: true }).click();
  }
  await hasText(page.locator('.map-status'), 'Compare', 'Satellite comparison should be available after viewport panning checks');
  await page.screenshot({ path: `${outputDir}/desktop-after-full-audit.png`, fullPage: true });
log('minimal map controls and recenter');

if (ownerToolsEnabled) {
  await page.getByRole('button', { name: 'Pin three key affected areas' }).click();
  await page.waitForSelector('.worst-pin-panel', { state: 'visible', timeout: 10000 });
  await page.waitForFunction(() => Number(document.querySelector('.map-shell')?.getAttribute('data-map-zoom') || 0) >= 19, null, { timeout: 15000 });
  await page.waitForFunction(() => !document.querySelector('.damage-legend'), null, { timeout: 5000 });
  await page.getByRole('button', { name: 'Microsoft AI affected buildings' }).click();
  await page.waitForFunction(() => document.querySelector('.damage-legend')?.textContent?.includes('building footprints'), null, { timeout: 20000 });
  await placeWorstAreaPins(page, [{ x: 0.30, y: 0.45 }, { x: 0.36, y: 0.58 }, { x: 0.44, y: 0.66 }]);
  await page.waitForFunction(() => document.querySelectorAll('.worst-area-draft-pin-icon').length === 3, null, { timeout: 5000 });
  await hasText(page.locator('.worst-pin-panel'), '3/3', 'Affected-area pin panel should show three pinned areas');
  await page.getByRole('button', { name: 'Copy' }).click();
  await page.waitForFunction(() => document.querySelector('.worst-pin-panel')?.textContent?.includes('Copied'), null, { timeout: 5000 });
  const desktopPinnedAreas = JSON.parse(await page.evaluate(() => navigator.clipboard.readText()));
  assert(desktopPinnedAreas.type === 'AyudaVenezuela2026 key affected-area pins', 'Affected-area pin export type changed');
  assert(desktopPinnedAreas.pins?.length === 3, 'Affected-area pin export should contain three pins');
  assert(desktopPinnedAreas.pins.every((pin, index) => pin.rank === index + 1 && Number.isFinite(pin.lat) && Number.isFinite(pin.lng)), 'Affected-area pin export should contain ranked coordinates');
  await page.screenshot({ path: `${outputDir}/desktop-affected-area-pins.png`, fullPage: true });
  await page.getByRole('button', { name: 'Close area pinning' }).click();
  await page.waitForSelector('.worst-pin-panel', { state: 'detached', timeout: 5000 });
  log('desktop affected-area pin export', desktopPinnedAreas);
} else {
  assert((await page.getByRole('button', { name: 'Pin three key affected areas' }).count()) === 0, 'Owner-only affected-area pin button should not render in public QA');
  assert((await page.locator('.worst-pin-panel').count()) === 0, 'Owner-only affected-area pin panel should not render in public QA');
  log('desktop affected-area pin export', 'hidden in public build');
}

const spanishLanguageButton = page.locator('.language-switch').getByRole('button', { name: /ES/ });
await spanishLanguageButton.click();
assert(await hasClass(spanishLanguageButton, 'active'), 'Spanish language button not active');
await hasText(page.locator('body'), 'Visualizador publico de dano', 'Spanish viewer title did not render');
await hasText(page.locator('.impact-summary-panel'), 'Dano verificado', 'Spanish verified damage summary did not render');
await hasText(page.locator('.comparison-side-labels'), 'Antes 7 Abr', 'Spanish before comparison label did not render');
await hasText(page.locator('.comparison-side-labels'), 'Despues 27 Jun', 'Spanish post-event comparison label did not render');
await page.screenshot({ path: `${outputDir}/desktop-spanish-return.png`, fullPage: true });
log('spanish language switch');

const mobile = await browser.newPage({ viewport: { width: 390, height: 900 }, isMobile: true, hasTouch: true });
mobile.on('console', (msg) => {
  if (msg.text().includes('Failed to load resource: the server responded with a status of 404')) return;
  if (['error', 'warning'].includes(msg.type())) errors.push(`mobile ${msg.type()}: ${msg.text()}`);
});
mobile.on('pageerror', (error) => errors.push(`mobile pageerror: ${error.message}`));
await mobile.route('https://nominatim.openstreetmap.org/search**', async (route) => {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify([
      {
        place_id: 26062027,
        osm_type: 'node',
        osm_id: 424243,
        display_name: 'Hospital Dr. Alfredo Machado, Catia La Mar, Municipio Vargas, La Guaira, Venezuela',
        lat: '10.6001961',
        lon: '-67.0387244',
        type: 'town',
        class: 'place',
        importance: 0.78,
        boundingbox: ['10.6000961', '10.6002961', '-67.0388244', '-67.0386244'],
        address: {
          town: 'Catia La Mar',
          state: 'La Guaira',
          country: 'Venezuela'
        }
      }
    ])
  });
});
await mobile.goto(appUrl, { waitUntil: 'domcontentloaded' });
await mobile.waitForFunction(() => document.querySelector('.map-canvas.leaflet-container'), null, { timeout: 30000 });
await mobile.getByRole('button', { name: /English/ }).click();
assert((await mobile.locator('.queue').count()) === 0, 'Mobile public data feed should not render');
assert((await mobile.locator('.selected-report-card').count()) === 0, 'Mobile selected data card should not render');
assert((await mobile.locator('.workbench-nav').count()) === 0, 'Mobile bottom workflow nav should not render');
const mobileMapLayers = mobile.getByRole('button', { name: 'Map layers' });
const mobileInitialChrome = await mobile.evaluate(() => {
  const rect = (selector) => {
    const element = document.querySelector(selector);
    if (!element) return null;
    const bounds = element.getBoundingClientRect();
    return {
      x: bounds.x,
      y: bounds.y,
      width: bounds.width,
      height: bounds.height,
      display: getComputedStyle(element).display
    };
  };
  const overlaps = (a, b) => Boolean(a && b && a.display !== 'none' && b.display !== 'none' && !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  ));
  const search = rect('.address-search');
  const tools = rect('.map-tool-cluster');
  return {
    hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    searchToolsOverlap: overlaps(search, tools)
  };
});
assert(!mobileInitialChrome.hasHorizontalOverflow, 'Mobile map chrome should not create horizontal overflow');
assert(!mobileInitialChrome.searchToolsOverlap, 'Mobile search bar should not overlap zoom/layer controls');
await mobileMapLayers.click();
assert(await hasClass(mobileMapLayers, 'active'), 'Mobile map layers drawer button did not activate');
await hasText(mobile.locator('.mobile-map-controls'), 'Damage', 'Mobile damage layer control did not render');
await mobile.waitForFunction(
  () => [...document.querySelectorAll('.mobile-map-controls .layer-row')].some((row) => row.textContent?.includes('SR review')),
  null,
  { timeout: 10000 }
);
assert((await mobile.locator('.mobile-map-controls .layer-row').count()) === 2, 'Mobile layers drawer should expose only damage and SR overlays');
assert((await mobile.locator('.mobile-map-controls .layer-row').filter({ hasText: 'Coverage' }).count()) === 0, 'Mobile coverage layer control should not render');
assert((await mobile.locator('.mobile-map-controls .layer-row').filter({ hasText: 'NASA/NISAR' }).count()) === 0, 'Mobile NASA layer control should not render');
const mobileDamageLayer = mobile.locator('.mobile-map-controls .layer-row').filter({ hasText: 'Damage' });
const mobileSrLayer = mobile.locator('.mobile-map-controls .layer-row').filter({ hasText: 'SR review' });
assert(!(await hasClass(mobileDamageLayer, 'selected')), 'Mobile damage layer should be off by default');
assert(!(await hasClass(mobileSrLayer, 'selected')), 'Mobile AI super-resolution layer should be off by default');
assert(!(await mobile.locator('.damage-legend').isVisible()), 'Mobile damage legend should not render before opt-in');
await mobileMapLayers.click();
const mobileSlider = mobile.getByRole('slider', { name: 'Move before and after satellite comparison' });
assert((await mobileSlider.count()) === 0, 'Mobile comparison slider should not render before an in-footprint address search');
assert(!(await mobile.locator('.mobile-map-controls').isVisible()), 'Mobile layers drawer should close when toggled');
const mobileAddressSearch = mobile.getByRole('textbox', { name: 'Search address or place in Venezuela' });
await mobileAddressSearch.fill('Catia La Mar');
await mobile.waitForFunction(() => document.querySelectorAll('.address-results [role="option"]').length > 0, null, { timeout: 15000 });
await mobile.getByRole('option', { name: /Catia La Mar/ }).click();
assert((await mobileSlider.count()) === 1, 'Mobile comparison slider should render automatically after an in-footprint address search');
const mobileGripBox = await mobile.locator('.comparison-grip').boundingBox();
assert(Boolean(mobileGripBox && mobileGripBox.width >= 56 && mobileGripBox.height >= 56), 'Mobile comparison grip should be a visible touch target');
await hasText(mobile.locator('.comparison-side-labels'), 'Before 7 Apr', 'Mobile before label did not render');
await hasText(mobile.locator('.comparison-side-labels'), 'After 27 Jun', 'Mobile after label did not render');
await mobile.waitForFunction(() => document.querySelectorAll('.named-place-label').length > 0, null, { timeout: 12000 });
const mobileNamedLabelState = await mobile.evaluate(() => {
  const labels = [...document.querySelectorAll('.named-place-label')].map((label) => ({
    text: label.textContent?.trim() || '',
    sourceUrl: label.getAttribute('data-source-url') || '',
    kind: label.getAttribute('data-kind') || ''
  }));
  return {
    count: labels.length,
    sourcedCount: labels.filter((label) => label.sourceUrl.startsWith('https://www.openstreetmap.org/')).length
  };
});
assert(mobileNamedLabelState.count > 0 && mobileNamedLabelState.sourcedCount === mobileNamedLabelState.count, `Mobile OSM labels should render with source URLs ${JSON.stringify(mobileNamedLabelState)}`);
const mobileComparisonChrome = await mobile.evaluate(() => {
  const rect = (selector) => {
    const element = document.querySelector(selector);
    if (!element) return null;
    const bounds = element.getBoundingClientRect();
    return {
      x: bounds.x,
      y: bounds.y,
      width: bounds.width,
      height: bounds.height,
      display: getComputedStyle(element).display
    };
  };
  const overlaps = (a, b) => Boolean(a && b && a.display !== 'none' && b.display !== 'none' && !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  ));
  const search = rect('.address-search');
  const tools = rect('.map-tool-cluster');
  const labels = rect('.comparison-side-labels');
  const grip = rect('.comparison-grip');
  return {
    searchToolsOverlap: overlaps(search, tools),
    labelsToolsOverlap: overlaps(labels, tools),
    labelsSearchOverlap: overlaps(labels, search),
    gripSearchOverlap: overlaps(grip, search),
    gripToolsOverlap: overlaps(grip, tools)
  };
});
assert(!mobileComparisonChrome.searchToolsOverlap, 'Mobile comparison search should not overlap map tools');
assert(!mobileComparisonChrome.labelsToolsOverlap, 'Mobile comparison labels should not overlap map tools');
assert(!mobileComparisonChrome.labelsSearchOverlap, 'Mobile comparison labels should not overlap search');
assert(!mobileComparisonChrome.gripSearchOverlap, 'Mobile comparison grip should not overlap search');
assert(!mobileComparisonChrome.gripToolsOverlap, 'Mobile comparison grip should not overlap map tools');
assert(!(await mobile.locator('.damage-legend').isVisible()), 'Mobile damage legend should stay hidden in clean satellite comparison mode');
await waitForComparisonTiles(mobile);
await assertComparisonAlignment(mobile, 'initial mobile comparison');
await touchDragComparisonSliderTo(mobile, mobileSlider, 18);
const mobileComparisonAt18 = await withMapChromeHidden(mobile, () => captureMapCanvas(mobile, `${outputDir}/mobile-comparison-18.png`));
await touchDragComparisonSliderTo(mobile, mobileSlider, 82);
const mobileComparisonAt82 = await withMapChromeHidden(mobile, () => captureMapCanvas(mobile, `${outputDir}/mobile-comparison-82.png`));
const mobileComparisonDiff = byteDifferenceRatio(mobileComparisonAt18, mobileComparisonAt82);
assert(mobileComparisonDiff > 0.002, `Mobile touch slider did not visibly change map pixels; screenshot byte diff ratio ${mobileComparisonDiff}`);
const mobileViewBeforeZoom = await mapView(mobile);
await mobile.getByRole('button', { name: 'Zoom in map' }).click();
await mobile.waitForFunction((previousZoom) => Number(document.querySelector('.map-shell')?.getAttribute('data-map-zoom') || 0) > previousZoom, mobileViewBeforeZoom.zoom, { timeout: 5000 });
await assertComparisonAlignment(mobile, 'mobile comparison after zoom in');
const mobileViewAfterZoomIn = await mapView(mobile);
await mobile.getByRole('button', { name: 'Zoom out map' }).click();
await mobile.waitForFunction((previousZoom) => Number(document.querySelector('.map-shell')?.getAttribute('data-map-zoom') || 0) < previousZoom, mobileViewAfterZoomIn.zoom, { timeout: 5000 });
await assertComparisonAlignment(mobile, 'mobile comparison after zoom out');
const mobileViewBeforePan = await mapView(mobile);
const mobilePanGesture = await mobile.evaluate(() => {
  const mapRect = document.querySelector('.map-canvas')?.getBoundingClientRect();
  const sliderRect = document.querySelector('.comparison-control')?.getBoundingClientRect();
  if (!mapRect || !sliderRect) return null;
  const y = Math.min(mapRect.bottom - 120, Math.max(sliderRect.bottom + 90, mapRect.top + 180));
  const defaultStartX = mapRect.right - 40;
  const startOnSlider = defaultStartX >= sliderRect.left - 8 && defaultStartX <= sliderRect.right + 8;
  return {
    start: { x: startOnSlider ? mapRect.left + 40 : defaultStartX, y },
    end: { x: startOnSlider ? mapRect.right - 40 : mapRect.left + 40, y }
  };
});
assert(mobilePanGesture, 'Mobile pan gesture could not find a clear map area');
await touchPanMap(mobile, mobilePanGesture.start, mobilePanGesture.end);
await mobile.waitForFunction((previousCenter) => document.querySelector('.map-shell')?.getAttribute('data-map-center') !== previousCenter, mobileViewBeforePan.center, { timeout: 5000 });
const mobilePreDamageResources = await mobile.evaluate(() => {
  const entries = performance.getEntriesByType('resource').map((entry) => entry.name);
  const imageUrls = [...document.querySelectorAll('.comparison-before-tile-layer img, .comparison-after-tile-layer img')].map(
    (image) => image.currentSrc
  );
  const nationalOpenImageryImages = [...document.querySelectorAll('.national-open-imagery-tile img')].map((image) => image.currentSrc);
  const urls = [...entries, ...imageUrls];
  return {
    localDamageTiles: urls.filter((name) => name.includes('/data/damage-tiles/')).length,
    localEnhancedAfterTiles: urls.filter((name) => name.includes('/data/enhanced-satellite-tiles/after/')).length,
    localEnhancedBeforeTiles: urls.filter((name) => name.includes('/data/enhanced-satellite-tiles/before/')).length,
    postEventVantorTiles: urls.filter((name) => name.includes('B15000110186C610.tif')).length,
    preEventVantorTiles: urls.filter((name) => name.includes('B120001100513B10.tif')).length,
    nationalOpenImageryTilesVisible: nationalOpenImageryImages.length
  };
});
assert(mobilePreDamageResources.localDamageTiles === 0, 'Mobile comparison should not load damage raster tiles before damage opt-in');
assert(
  mobilePreDamageResources.postEventVantorTiles + mobilePreDamageResources.localEnhancedAfterTiles > 0,
  'Mobile comparison did not request post-event Vantor or enhanced after tiles'
);
assert(
  mobilePreDamageResources.preEventVantorTiles + mobilePreDamageResources.localEnhancedBeforeTiles > 0,
  'Mobile comparison did not request pre-event Vantor or enhanced before tiles'
);
assert(mobilePreDamageResources.nationalOpenImageryTilesVisible > 0, 'Mobile comparison should keep open national imagery available as a low-priority underlay');
await mobileMapLayers.click();
assert(await hasClass(mobileMapLayers, 'active'), 'Mobile map layers drawer did not reopen for damage opt-in');
await mobileDamageLayer.click();
assert(await hasClass(mobileDamageLayer, 'selected'), 'Mobile damage layer did not enable after opt-in');
await mobile.waitForFunction(() => document.querySelector('.damage-legend')?.textContent?.includes('building footprints'), null, { timeout: 20000 });
await mobile.waitForFunction(() => !document.querySelector('.mobile-map-controls.open'), null, { timeout: 5000 });
assert(!(await mobile.locator('.mobile-map-controls').isVisible()), 'Mobile layers drawer should close after enabling damage');
assert((await mobile.getByRole('slider', { name: 'Move before and after satellite comparison' }).count()) === 1, 'Mobile comparison slider should stay visible with damage enabled');
await assertComparisonAlignment(mobile, 'mobile comparison with damage');
await mobile.screenshot({ path: `${outputDir}/mobile-map.png`, fullPage: true });
log('mobile touch comparison and damage opt-in', { mobileComparisonDiff, mobilePreDamageResources });

await mobileMapLayers.click();
assert(await hasClass(mobileMapLayers, 'active'), 'Mobile map layers drawer did not reopen for SR regression check');
await mobileSrLayer.click();
await mobile.waitForSelector('.super-resolution-panel', { state: 'visible', timeout: 15000 });
assert(!(await mobile.locator('.mobile-map-controls').isVisible()), 'Mobile layers drawer should close after enabling SR review');
assert((await mobile.locator('.worst-experience-panel').count()) === 0, 'Key affected areas panel should not be visible when SR review is enabled');
await mobile.getByRole('button', { name: 'View key affected areas' }).click();
await mobile.waitForSelector('.worst-experience-panel', { state: 'visible', timeout: 15000 });
await mobile.waitForFunction(() => !document.querySelector('.super-resolution-panel'), null, { timeout: 5000 });
await assertWorstPanelViewport(mobile, 'mobile key affected areas');
const mobileOverlayExclusion = await mobile.evaluate(() => {
  const visible = (selector) => {
    const element = document.querySelector(selector);
    if (!element) return false;
    const style = getComputedStyle(element);
    const bounds = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && bounds.width > 0 && bounds.height > 0;
  };
  return {
    srVisible: visible('.super-resolution-panel'),
    worstVisible: visible('.worst-experience-panel'),
    drawerVisible: visible('.mobile-map-controls.open'),
    visiblePrimaryOverlays: [
      '.super-resolution-panel',
      '.worst-experience-panel',
      '.mobile-map-controls.open'
    ].filter(visible).length
  };
});
assert(!mobileOverlayExclusion.srVisible, 'SR review panel should close when key affected areas opens');
assert(mobileOverlayExclusion.worstVisible, 'Key affected areas panel should be visible after selecting the mode');
assert(!mobileOverlayExclusion.drawerVisible, 'Mobile layers drawer should stay closed after switching modes');
assert(mobileOverlayExclusion.visiblePrimaryOverlays === 1, `Mobile should show exactly one primary overlay, saw ${mobileOverlayExclusion.visiblePrimaryOverlays}`);
await mobile.screenshot({ path: `${outputDir}/mobile-sr-affected-overlay-fixed.png`, fullPage: true });
log('mobile sr/affected overlay exclusion', mobileOverlayExclusion);

const summary = {
  observations,
  desktopButtons: await page.locator('button').count(),
  desktopComboboxes: await page.locator('select').count(),
  desktopTextInputs: await page.locator('textarea,input').count(),
  mobileButtons: await mobile.locator('button').count(),
  warnings,
  consoleIssues: errors
};

await browser.close();

if (errors.length) {
  console.error(JSON.stringify(summary, null, 2));
  process.exitCode = 1;
} else {
  console.log(JSON.stringify(summary, null, 2));
}
