import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const rootDir = process.cwd();
const registryPath = path.join(rootDir, 'data/trusted-source-registry.json');
const outputPath = path.join(rootDir, 'public/data/trusted-data.json');
const localDamageSnapshotPath = path.join(rootDir, 'public/data/microsoft-damage-catia-lite.geojson');
const hdxApi = 'https://data.humdata.org/api/3/action/package_show';
const usgsApi = 'https://earthquake.usgs.gov/fdsnws/event/1/query';

function nowIso() {
  return new Date().toISOString();
}

function sourceStatus(source, status, details = {}) {
  return {
    id: source.id,
    name: source.name,
    owner: source.owner,
    tier: source.tier,
    kind: source.kind,
    visibility: source.visibility,
    recommendedUse: source.recommendedUse,
    licenseReview: source.licenseReview,
    url: source.url,
    refreshCadenceHours: source.refreshCadenceHours,
    status,
    ...details
  };
}

async function fetchJson(url, timeoutMs = 12000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        accept: 'application/json',
        'user-agent': 'AyudaVenezuela2026 trusted data pipeline'
      }
    });

    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }

    return response.json();
  } finally {
    clearTimeout(timeout);
  }
}

function hdxPackageUrl(packageId) {
  const url = new URL(hdxApi);
  url.searchParams.set('id', packageId);
  return url.toString();
}

async function fetchHdxPackage(source) {
  const payload = await fetchJson(hdxPackageUrl(source.packageId));
  if (!payload.success || !payload.result) {
    throw new Error('HDX package_show returned no result');
  }

  const result = payload.result;
  const resources = Array.isArray(result.resources) ? result.resources : [];
  const formats = [...new Set(resources.map((resource) => resource.format).filter(Boolean))].sort();

  return sourceStatus(source, 'ok', {
    title: result.title,
    organization: result.organization?.title || source.owner,
    license: result.license_title || result.license_id || 'Unknown',
    metadataModified: result.metadata_modified,
    datasetDate: result.dataset_date || null,
    resourceCount: resources.length,
    formats,
    resources: resources.map((resource) => ({
      name: resource.name,
      format: resource.format,
      url: resource.url,
      lastModified: resource.last_modified || resource.metadata_modified || null,
      size: resource.size || null
    }))
  });
}

async function fetchArcgisLayer(source) {
  const layerMetadata = await fetchJson(`${source.url}?f=json`);
  const statsUrl = new URL(`${source.url}/query`);
  statsUrl.searchParams.set('f', 'json');
  statsUrl.searchParams.set('where', '1=1');
  statsUrl.searchParams.set('returnGeometry', 'false');
  statsUrl.searchParams.set('outFields', 'damaged,damage_pct_0m,unknown_pct');
  statsUrl.searchParams.set(
    'outStatistics',
    JSON.stringify([
      { statisticType: 'count', onStatisticField: 'OBJECTID', outStatisticFieldName: 'footprint_count' },
      { statisticType: 'avg', onStatisticField: 'damage_pct_0m', outStatisticFieldName: 'avg_damage_0m' },
      { statisticType: 'avg', onStatisticField: 'unknown_pct', outStatisticFieldName: 'avg_unknown_pct' }
    ])
  );

  const statsPayload = await fetchJson(statsUrl.toString());
  const stats = statsPayload.features?.[0]?.attributes || {};

  return sourceStatus(source, 'ok', {
    title: layerMetadata.name || source.name,
    geometryType: layerMetadata.geometryType,
    capabilities: layerMetadata.capabilities,
    maxRecordCount: layerMetadata.maxRecordCount,
    fields: (layerMetadata.fields || []).map((field) => ({
      name: field.name,
      type: field.type,
      alias: field.alias
    })),
    extent: layerMetadata.extent || null,
    stats: {
      footprintCount: stats.footprint_count || 0,
      averageDamage0m: stats.avg_damage_0m ?? null,
      averageUnknownPct: stats.avg_unknown_pct ?? null
    }
  });
}

async function fetchUsgsEvents(source, incident) {
  const [minLon, minLat, maxLon, maxLat] = incident.bbox;
  const url = new URL(usgsApi);
  url.searchParams.set('format', 'geojson');
  url.searchParams.set('starttime', incident.startDate);
  url.searchParams.set('endtime', new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10));
  url.searchParams.set('minlatitude', String(minLat));
  url.searchParams.set('maxlatitude', String(maxLat));
  url.searchParams.set('minlongitude', String(minLon));
  url.searchParams.set('maxlongitude', String(maxLon));
  url.searchParams.set('minmagnitude', '4.5');
  url.searchParams.set('orderby', 'time');

  const payload = await fetchJson(url.toString());
  const features = Array.isArray(payload.features) ? payload.features : [];

  return sourceStatus(source, 'ok', {
    queryUrl: url.toString(),
    generated: payload.metadata?.generated ? new Date(payload.metadata.generated).toISOString() : null,
    eventCount: payload.metadata?.count ?? features.length,
    maxMagnitude: features.reduce((max, feature) => Math.max(max, feature.properties?.mag || 0), 0),
    events: features.slice(0, 12).map((feature) => ({
      id: feature.id,
      magnitude: feature.properties?.mag,
      place: feature.properties?.place,
      time: feature.properties?.time ? new Date(feature.properties.time).toISOString() : null,
      url: feature.properties?.url,
      coordinates: feature.geometry?.coordinates || null
    }))
  });
}

async function fetchReliefWebReports(source) {
  const url = new URL(source.url);
  url.searchParams.set('appname', 'ayuda-venezuela-2026');
  url.searchParams.set('query[value]', 'Venezuela earthquake');
  url.searchParams.set('limit', '8');
  url.searchParams.set('profile', 'list');
  url.searchParams.set('preset', 'latest');

  const payload = await fetchJson(url.toString());
  const rows = Array.isArray(payload.data) ? payload.data : [];

  return sourceStatus(source, 'ok', {
    queryUrl: url.toString(),
    resultCount: payload.count ?? rows.length,
    totalCount: payload.totalCount ?? null,
    reports: rows.map((row) => ({
      id: row.id,
      title: row.fields?.title,
      created: row.fields?.date?.created || null,
      source: row.fields?.source?.[0]?.name || null,
      url: row.fields?.url || row.href || null
    }))
  });
}

function summarizeGooglePublicDataset(source) {
  return sourceStatus(source, 'ok', {
    datasetId: source.datasetId,
    coverage: source.coverage,
    access: source.access,
    note: 'Public Google dataset registered for trusted context. Area-specific Earth Engine export is a downstream pipeline step.'
  });
}

function summarizePublicSatelliteImagery(source) {
  return sourceStatus(source, 'ok', {
    beforeScene: source.beforeScene,
    afterScene: source.afterScene,
    access: source.access,
    note: 'Public satellite imagery or derived public remote-sensing layer registered for visualization. Individual building damage is interpreted from the Microsoft/HDX damage assessment and human validation, not directly from context imagery.'
  });
}

function summarizeHuggingFaceDataset(source) {
  return sourceStatus(source, 'ok', {
    datasetId: source.datasetId,
    coverage: source.coverage,
    access: source.access,
    note: 'Hugging Face dataset registered for public visualization and local static cache generation. Verify source-specific limitations before operational use.'
  });
}

async function loadLocalDamageSummary() {
  try {
    const payload = JSON.parse(await readFile(localDamageSnapshotPath, 'utf8'));
    const features = Array.isArray(payload.features) ? payload.features : [];
    return {
      footprintCount: features.length
    };
  } catch {
    return {
      footprintCount: 0
    };
  }
}

async function buildSource(source, registry) {
  try {
    if (source.kind === 'hdx_package') return await fetchHdxPackage(source);
    if (source.kind === 'arcgis_feature_layer') return await fetchArcgisLayer(source);
    if (source.kind === 'google_public_dataset') return summarizeGooglePublicDataset(source);
    if (source.kind === 'public_satellite_imagery') return summarizePublicSatelliteImagery(source);
    if (source.kind === 'hf_dataset') return summarizeHuggingFaceDataset(source);
    if (source.kind === 'usgs_geojson') return await fetchUsgsEvents(source, registry.incident);
    if (source.kind === 'reliefweb_reports') {
      return sourceStatus(source, 'manual_review', {
        note: 'Configured for situation monitoring. Automated ingestion is disabled until an event-specific ReliefWeb query is validated.'
      });
    }
    return sourceStatus(source, 'manual_review', { error: 'No automated fetcher configured for source kind.' });
  } catch (error) {
    return sourceStatus(source, 'error', {
      error: error instanceof Error ? error.message : 'Unknown fetch error'
    });
  }
}

function summarize(sources, localDamageSummary) {
  const okSources = sources.filter((source) => source.status === 'ok');
  const errorSources = sources.filter((source) => source.status === 'error');
  const hdxSources = okSources.filter((source) => source.kind === 'hdx_package');
  const googleSources = okSources.filter((source) => source.kind === 'google_public_dataset');
  const satelliteSources = okSources.filter((source) => source.kind === 'public_satellite_imagery');
  const resourceCount = hdxSources.reduce((total, source) => total + (source.resourceCount || 0), 0);
  const microsoftLayer = sources.find((source) => source.id === 'arcgis-microsoft-catia-damage');
  const usgsLayer = sources.find((source) => source.id === 'usgs-earthquake-events');
  const microsoftDamageFootprints =
    microsoftLayer?.stats?.footprintCount ||
    localDamageSummary.footprintCount ||
    0;

  return {
    okSourceCount: okSources.length,
    errorSourceCount: errorSources.length,
    hdxPackageCount: hdxSources.length,
    googleDatasetCount: googleSources.length,
    satelliteImageryCount: satelliteSources.length,
    resourceCount,
    trustedAssetLayers: hdxSources.reduce((count, source) => {
      const name = source.name.toLowerCase();
      return count + (/(road|health|port|airport|building|facility|populated)/.test(name) ? 1 : 0);
    }, googleSources.length + satelliteSources.length),
    microsoftDamageFootprints,
    averageDamage0m: microsoftLayer?.stats?.averageDamage0m ?? null,
    usgsEventCount: usgsLayer?.eventCount || 0,
    usgsMaxMagnitude: usgsLayer?.maxMagnitude || 0
  };
}

async function main() {
  const registry = JSON.parse(await readFile(registryPath, 'utf8'));
  const generatedAt = nowIso();
  const [sources, localDamageSummary] = await Promise.all([
    Promise.all(registry.sources.map((source) => buildSource(source, registry))),
    loadLocalDamageSummary()
  ]);
  const output = {
    schemaVersion: 1,
    generatedAt,
    generatedBy: 'scripts/build-trusted-data.mjs',
    incident: registry.incident,
    policy: registry.policy,
    summary: summarize(sources, localDamageSummary),
    sources
  };

  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(output, null, 2)}\n`);
  console.log(`trusted data snapshot: ${outputPath}`);
  console.log(JSON.stringify(output.summary, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
