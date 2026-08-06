import { useCallback, useEffect, useRef, useState, type CSSProperties, type RefObject } from 'react';
import L from 'leaflet';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock,
  Check,
  Clipboard,
  Crosshair,
  ExternalLink,
  Layers,
  Menu,
  Minus,
  MapPin,
  Phone,
  Plus,
  RotateCcw,
  Search,
  Shield,
  X
} from 'lucide-react';
import { MapContainer, useMap } from 'react-leaflet';
import {
  microsoftDamageSource,
  type DamageSeverity
} from './data/microsoftDamageData';
import { copy } from './lib/i18n';
import {
  initialDamageViewport,
  summarizeDamageViewport,
  type DamageViewportState,
  type DamageViewportSummary
} from './lib/damageViewport';
import { fetchTrustedDataSnapshot, formatSnapshotAge, type TrustedDataSnapshot } from './lib/trustedData';
import type { Language } from './lib/language';

type Copy = (typeof copy)['en'];

const mapCenter: [number, number] = [7.2, -66.2];
const mapZoom = 6;
const maxMapZoom = 21;
const nationalMaxUsefulZoom = 14;
const damageMaxUsefulZoom = 18;
const nationalFocusZoom = 13;
const comparisonMinZoom = 19;
const worstComparisonFocusZoom = 20;
const venezuelaBounds: L.LatLngBoundsExpression = [[0.45, -73.45], [12.35, -59.75]];
const explorationBounds: L.LatLngBoundsExpression = [[0.45, -73.45], [12.35, -59.75]];
const venezuelaSearchViewbox = '-73.45,12.35,-59.75,0.45';
const damageBounds: L.LatLngBoundsExpression = [[10.54, -67.14], [10.65, -66.96]];
const preEventComparisonBounds: L.LatLngBoundsExpression = [[10.518145, -67.085575], [10.679827, -66.967422]];
const postEventComparisonBounds: L.LatLngBoundsExpression = [[10.524025, -67.043108], [10.642557, -66.942944]];
const strictComparisonBounds: L.LatLngBoundsExpression = [[10.524025, -67.043108], [10.642557, -66.967422]];
const strictComparisonLatLngBounds = L.latLngBounds(strictComparisonBounds);
const preEventComparisonCogUrl =
  'https://vantor-opendata.s3.amazonaws.com/events/Venezuela-Earthquake-Jun-2026/B120001100513B10.tif';
const postEventComparisonCogUrl =
  'https://vantor-opendata.s3.amazonaws.com/events/Venezuela-Earthquake-Jun-2026/B15000110186C610.tif';
const comparisonTileScale = 2;
const useEnhancedSatelliteOverlay = false;
const enhancedSatelliteManifestUrl = '/data/enhanced-satellite-tiles/manifest.json';
const ownerToolsEnabled = ['1', 'true'].includes(import.meta.env.VITE_OWNER_TOOLS || '');
const nationalImageryAttribution =
  'EOxCloudless 2024 by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2024), 10 m national context';
const nationalImageryTileUrl =
  'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg';
const preEventSatelliteAttribution =
  'Vantor pre-event imagery via Vantor Open Data STAC, 7 Apr 2026, CC BY-NC 4.0';
const postEventSatelliteAttribution =
  'Vantor post-event imagery via Vantor Open Data STAC, 27 Jun 2026, CC BY-NC 4.0';
const transparentTileDataUri =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAEElEQVR42mNgYGD4DwABBAEAghzLJwAAAABJRU5ErkJggg==';
let enhancedTileManifestPromise: Promise<EnhancedTileManifest | null> | null = null;

const donationLinks = [
  {
    name: 'DEC Venezuela Earthquake Appeal',
    tag: { en: 'Appeal', es: 'Campana' },
    logoSrc: '/logos/donations/dec.svg',
    logoAlt: 'DEC logo',
    url: 'https://donation.dec.org.uk/venezuela-earthquake-appeal'
  },
  {
    name: 'Hogar Bambi',
    tag: { en: 'Children', es: 'Ninez' },
    logoSrc: '/logos/donations/hogar-bambi.svg',
    logoAlt: 'Hogar Bambi logo',
    url: 'https://hogarbambi.org/donar-ahora/'
  },
  {
    name: 'We Love Foundation',
    tag: { en: 'Foundation', es: 'Fundacion' },
    logoSrc: '/logos/donations/we-love-foundation.svg',
    logoAlt: 'We Love Foundation logo',
    url: 'https://www.welove.foundation/'
  },
  {
    name: 'UNICEF UK Venezuela Earthquake Appeal',
    tag: { en: 'UNICEF', es: 'UNICEF' },
    logoSrc: '/logos/donations/unicef-uk.svg',
    logoAlt: 'UNICEF UK logo',
    url: 'https://www.unicef.org.uk/donate/donate-to-our-venezuela-earthquake-appeal/'
  }
];

interface SatelliteSceneLayer {
  key: string;
  url: string;
  attribution: string;
  bounds: L.LatLngBoundsExpression;
  className: string;
}

interface SuperResolutionRecord {
  id: string;
  lon: number;
  lat: number;
  severity?: string;
  interpretive?: boolean;
}

interface SuperResolutionIndex {
  generatedAt?: string;
  model?: {
    name?: string;
    scale?: number;
    hallucinationRisk?: string;
  };
  zoom?: number;
  completedAois?: number;
  requestedAois?: number;
  records?: SuperResolutionRecord[];
  contactSheet?: {
    localPath?: string;
    url?: string;
  };
  archive?: {
    name?: string;
    url?: string;
  };
  useGuidance?: string;
}

interface AddressSearchResult {
  place_id: number;
  osm_type?: string;
  osm_id?: number;
  display_name: string;
  lat: string;
  lon: string;
  type?: string;
  class?: string;
  importance?: number;
  boundingbox?: [string, string, string, string];
  address?: Record<string, string>;
}

type AddressSearchStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error';

interface WorstDamageHotspot {
  id: string;
  rank: number;
  lat: number;
  lng: number;
  labels: Record<Language, string>;
  context: Record<Language, string>;
  total: number;
  high: number;
  moderate: number;
  observed: number;
  uncertain: number;
  score: number;
}

interface WorstDamageHotspotIndex {
  hotspots?: WorstDamageHotspot[];
}

interface WorstAreaPin {
  rank: number;
  lat: number;
  lng: number;
}

interface EnhancedTileManifest {
  bounds?: {
    west?: number;
    south?: number;
    east?: number;
    north?: number;
  };
  zoomLevels?: number[];
  tilePixelSize?: number;
  counts?: Record<string, { written?: number }>;
}

interface NamedPlaceFeature {
  type: 'Feature';
  geometry: {
    type: 'Point';
    coordinates: [number, number];
  };
  properties: {
    id: string;
    name: string;
    category: string;
    kind: string;
    sourceUrl: string;
  };
}

interface NamedPlaceCollection {
  features?: NamedPlaceFeature[];
}

interface AddressSearchOptions {
  signal?: AbortSignal;
  showMinLengthError?: boolean;
}

const comparisonScenes: {
  before: SatelliteSceneLayer[];
  after: SatelliteSceneLayer[];
} = {
  before: [
    {
      key: 'pre-event-fallback',
      url: preEventSatelliteTileUrl(),
      attribution: preEventSatelliteAttribution,
      bounds: strictComparisonBounds,
      className: 'comparison-tile-layer comparison-before-tile-layer comparison-before-fallback-tile-layer'
    }
  ],
  after: [
    {
      key: 'post-event-fallback',
      url: postEventSatelliteTileUrl(),
      attribution: postEventSatelliteAttribution,
      bounds: strictComparisonBounds,
      className: 'comparison-tile-layer comparison-after-tile-layer comparison-after-fallback-tile-layer'
    }
  ]
};

const worstAreaPinningAddressResult: AddressSearchResult = {
  place_id: -2026070603,
  display_name: 'Catia La Mar affected-area pinning workspace, La Guaira, Venezuela',
  lat: '10.600196',
  lon: '-67.038724',
  type: 'manual-pin-workspace',
  class: 'place',
  address: {
    town: 'Catia La Mar',
    state: 'La Guaira',
    country: 'Venezuela'
  }
};

function enhancedComparisonScenes(bounds: L.LatLngBoundsExpression): {
  before: SatelliteSceneLayer[];
  after: SatelliteSceneLayer[];
} {
  return {
    before: [
      {
        key: 'pre-event-enhanced',
        url: '/data/enhanced-satellite-tiles/before/{z}/{x}/{y}.jpg',
        attribution: `${preEventSatelliteAttribution}; deterministic enhanced visualization from original Vantor COG`,
        bounds,
        className: 'comparison-tile-layer comparison-before-tile-layer comparison-before-enhanced-tile-layer'
      }
    ],
    after: [
      {
        key: 'post-event-enhanced',
        url: '/data/enhanced-satellite-tiles/after/{z}/{x}/{y}.jpg',
        attribution: `${postEventSatelliteAttribution}; deterministic enhanced visualization from original Vantor COG`,
        bounds,
        className: 'comparison-tile-layer comparison-after-tile-layer comparison-after-enhanced-tile-layer'
      }
    ]
  };
}

function enhancedManifestBounds(manifest: EnhancedTileManifest | null): L.LatLngBoundsExpression | null {
  const bounds = manifest?.bounds;
  const zoomLevels = manifest?.zoomLevels || [];
  const hasEnoughTiles = Boolean(
    manifest?.counts?.before?.written &&
      manifest.counts.after?.written &&
      (zoomLevels.includes(20) || (zoomLevels.includes(18) && zoomLevels.includes(19))) &&
      Number(manifest.tilePixelSize) >= 512
  );

  if (
    !hasEnoughTiles ||
    !bounds ||
    !Number.isFinite(bounds.west) ||
    !Number.isFinite(bounds.south) ||
    !Number.isFinite(bounds.east) ||
    !Number.isFinite(bounds.north) ||
    Number(bounds.west) >= Number(bounds.east) ||
    Number(bounds.south) >= Number(bounds.north)
  ) {
    return null;
  }

  return [[Number(bounds.south), Number(bounds.west)], [Number(bounds.north), Number(bounds.east)]];
}

function loadEnhancedTileManifest() {
  if (!useEnhancedSatelliteOverlay) return Promise.resolve(null);
  if (!enhancedTileManifestPromise) {
    enhancedTileManifestPromise = fetch(enhancedSatelliteManifestUrl, { cache: 'force-cache' })
      .then((response) => {
        const contentType = response.headers.get('content-type') || '';
        if (!response.ok || !contentType.includes('application/json')) return null;
        return response.json() as Promise<EnhancedTileManifest>;
      })
      .catch(() => null);
  }
  return enhancedTileManifestPromise;
}

function tileXY(lat: number, lng: number, zoom: number) {
  const radians = (lat * Math.PI) / 180;
  return {
    x: Math.floor(((lng + 180) / 360) * 2 ** zoom),
    y: Math.floor(((1 - Math.log(Math.tan(radians) + 1 / Math.cos(radians)) / Math.PI) / 2) * 2 ** zoom)
  };
}

function preloadImage(url: string) {
  const image = new Image();
  image.decoding = 'async';
  image.src = url;
}

function preloadEnhancedHotspotTiles(hotspots: WorstDamageHotspot[]) {
  if (!useEnhancedSatelliteOverlay || typeof Image === 'undefined') return;
  const hotspot = hotspots[0];
  if (!hotspot) return;
  const { x, y } = tileXY(hotspot.lat, hotspot.lng, 20);
  for (const side of ['before', 'after']) {
    for (const dx of [-1, 0, 1]) {
      for (const dy of [-1, 0, 1]) {
        preloadImage(`/data/enhanced-satellite-tiles/${side}/20/${x + dx}/${y + dy}.jpg`);
      }
    }
  }
}

const defaultWorstDamageHotspots: WorstDamageHotspot[] = [
  {
    id: 'verified-hotspot-1',
    rank: 1,
    lat: 10.610353,
    lng: -67.012348,
    labels: {
      es: 'Edificio Arnedillo / Residencias Marena',
      en: 'Edificio Arnedillo / Residencias Marena'
    },
    context: {
      es: 'punto clave seleccionado junto a nombres OSM verificados en Playa Grande',
      en: 'selected key point beside verified OSM names in Playa Grande'
    },
    total: 70,
    high: 34,
    moderate: 16,
    observed: 20,
    uncertain: 0,
    score: 196
  },
  {
    id: 'verified-hotspot-2',
    rank: 2,
    lat: 10.609699,
    lng: -67.014644,
    labels: {
      es: 'Residencias Palmilla / Sol Marina Garden 2',
      en: 'Residencias Palmilla / Sol Marina Garden 2'
    },
    context: {
      es: 'punto clave seleccionado cerca de residencias y hotel OSM verificados',
      en: 'selected key point near verified OSM residences and hotel names'
    },
    total: 49,
    high: 22,
    moderate: 11,
    observed: 16,
    uncertain: 0,
    score: 131
  },
  {
    id: 'verified-hotspot-3',
    rank: 3,
    lat: 10.612984,
    lng: -67.022674,
    labels: {
      es: 'Playa Mar / Playa Grande este',
      en: 'Playa Mar / East Playa Grande'
    },
    context: {
      es: 'punto clave seleccionado en edificios residenciales nombrados por OSM',
      en: 'selected key point in OSM-named residential buildings'
    },
    total: 23,
    high: 8,
    moderate: 4,
    observed: 11,
    uncertain: 0,
    score: 52.3
  }
];

function preEventSatelliteTileUrl() {
  return vantorCogTileUrl(preEventComparisonCogUrl);
}

function postEventSatelliteTileUrl() {
  return vantorCogTileUrl(postEventComparisonCogUrl);
}

function vantorCogTileUrl(cogUrl: string) {
  const params = new URLSearchParams({
    url: cogUrl,
    resampling: 'bilinear',
    reproject: 'bilinear'
  });
  return `https://titiler.hotosm.org/cog/tiles/WebMercatorQuad/{z}/{x}/{y}@${comparisonTileScale}x?${params.toString()}`;
}

async function fetchSuperResolutionIndex() {
  for (const path of [
    '/data/super-resolution/swin2sr-pilot/index.json',
    '/data/super-resolution/real-esrgan-pilot/index.json'
  ]) {
    const response = await fetch(path);
    if (!response.ok) continue;
    return normalizeSuperResolutionIndex((await response.json()) as SuperResolutionIndex);
  }
  return null;
}

async function fetchWorstDamageHotspots() {
  const response = await fetch('/data/worst-damage-hotspots.json');
  if (!response.ok) return defaultWorstDamageHotspots;
  const index = (await response.json()) as WorstDamageHotspotIndex;
  const hotspots = index.hotspots?.filter((hotspot) => (
    Number.isFinite(hotspot.lat) &&
    Number.isFinite(hotspot.lng) &&
    Number.isFinite(hotspot.rank)
  ));
  return hotspots?.length ? hotspots.slice(0, 3) : defaultWorstDamageHotspots;
}

async function fetchNamedPlaces() {
  const response = await fetch('/data/osm-named-places-catia.geojson', { cache: 'force-cache' });
  if (!response.ok) return [];
  const collection = (await response.json()) as NamedPlaceCollection;

  return (collection.features || []).filter((feature) => {
    const [lng, lat] = feature.geometry?.coordinates || [];
    return (
      feature.type === 'Feature' &&
      feature.geometry?.type === 'Point' &&
      Number.isFinite(lat) &&
      Number.isFinite(lng) &&
      Boolean(feature.properties?.name) &&
      Boolean(feature.properties?.sourceUrl)
    );
  });
}

function damageTileUrl() {
  return '/data/damage-tiles/{z}/{x}/{y}.png';
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function addressResultCoordinate(result: AddressSearchResult): [number, number] {
  return [Number(result.lat), Number(result.lon)];
}

function addressResultShortLabel(result: AddressSearchResult) {
  const address = result.address || {};
  return address.road || address.neighbourhood || address.suburb || address.city || address.town || address.village || result.type || 'Venezuela';
}

function hotspotToAddressResult(hotspot: WorstDamageHotspot): AddressSearchResult {
  return {
    place_id: -hotspot.rank,
    display_name: `${hotspot.labels.en}, Catia La Mar, La Guaira, Venezuela`,
    lat: hotspot.lat.toFixed(6),
    lon: hotspot.lng.toFixed(6),
    type: 'damage hotspot',
    class: 'verified-damage',
    importance: 1,
    address: {
      neighbourhood: hotspot.labels.en,
      city: 'Catia La Mar',
      state: 'La Guaira',
      country: 'Venezuela'
    }
  };
}

function formatPinnedCoordinate(value: number) {
  return value.toFixed(6);
}

function worstAreaPinExport(pins: WorstAreaPin[]) {
  return JSON.stringify(
    {
      type: 'AyudaVenezuela2026 key affected-area pins',
      source: 'manual-map-pins',
      usage: 'Paste this block back into Codex to update the published key affected areas.',
      pins: pins.map((pin) => ({
        rank: pin.rank,
        lat: Number(formatPinnedCoordinate(pin.lat)),
        lng: Number(formatPinnedCoordinate(pin.lng))
      }))
    },
    null,
    2
  );
}

function addressSupportsComparison(result: AddressSearchResult | null) {
  if (!result) return false;
  const [lat, lng] = addressResultCoordinate(result);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;

  const point = L.latLng(lat, lng);
  return L.latLngBounds(strictComparisonBounds as L.LatLngBoundsLiteral).contains(point);
}

function comparisonFocusZoomForResult(result: AddressSearchResult) {
  return result.place_id < 0 ? worstComparisonFocusZoom : comparisonMinZoom;
}

function focusZoomForResult(result: AddressSearchResult) {
  return addressSupportsComparison(result) ? comparisonFocusZoomForResult(result) : nationalFocusZoom;
}

function focusMapOnAddress(map: L.Map, result: AddressSearchResult, animate = true, zoom = 18) {
  const [lat, lng] = addressResultCoordinate(result);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

  if (!animate) {
    map.setView(L.latLng(lat, lng), zoom, { animate: false });
    return;
  }

  map.flyTo(L.latLng(lat, lng), zoom, { duration: animate ? 0.7 : 0 });
}

function normalizeSuperResolutionIndex(index: SuperResolutionIndex): SuperResolutionIndex {
  const records = index.records?.filter((record) => Number.isFinite(record.lat) && Number.isFinite(record.lon));
  return {
    ...index,
    records
  };
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  })[character] || character);
}

function namedPlaceCategoryWeight(category: string) {
  const weights: Record<string, number> = {
    safety: 0,
    health: 1,
    education: 2,
    building: 3,
    amenity: 4,
    finance: 5,
    shop: 6,
    food: 7,
    lodging: 8,
    office: 9,
    leisure: 10,
    historic: 11
  };
  return weights[category] ?? 99;
}

function OpenNationalImageryLayer({ highResolutionVisible }: { highResolutionVisible: boolean }) {
  const map = useMap();
  const layerRef = useRef<L.TileLayer | null>(null);

  useEffect(() => {
    const imagery = L.tileLayer(
      nationalImageryTileUrl,
      {
        attribution: nationalImageryAttribution,
        className: 'earth-imagery-tile national-open-imagery-tile',
        keepBuffer: 2,
        maxNativeZoom: 14,
        maxZoom: maxMapZoom,
        minZoom: 0,
        updateWhenIdle: true,
        updateWhenZooming: false,
        zIndex: 80
      }
    );

    layerRef.current = imagery;
    imagery.addTo(map);
    return () => {
      imagery.remove();
      layerRef.current = null;
    };
  }, [map]);

  useEffect(() => {
    layerRef.current?.setZIndex(highResolutionVisible ? 60 : 80);
  }, [highResolutionVisible]);

  return null;
}

function damageSeverityLabel(severity: DamageSeverity, c: Copy) {
  const labels: Record<DamageSeverity, string> = {
    high: c.damageHigh,
    moderate: c.damageModerate,
    observed: c.damageObserved,
    uncertain: c.damageUncertain
  };
  return labels[severity];
}

function MapRecenter({
  tick,
  addressResult
}: {
  tick: number;
  addressResult: AddressSearchResult | null;
}) {
  const map = useMap();

  useEffect(() => {
    if (!tick) return;
    if (addressResult) {
      focusMapOnAddress(map, addressResult, true, focusZoomForResult(addressResult));
      return;
    }
    map.flyToBounds(venezuelaBounds, { duration: 0.65, padding: [36, 36] });
  }, [addressResult, map, tick]);

  return null;
}

function MapHandle({ onReady }: { onReady: (map: L.Map | null) => void }) {
  const map = useMap();

  useEffect(() => {
    onReady(map);
    return () => onReady(null);
  }, [map, onReady]);

  return null;
}

function MapSizeInvalidator() {
  const map = useMap();

  useEffect(() => {
    const container = map.getContainer();
    let frame = window.requestAnimationFrame(() => {
      map.invalidateSize({ pan: false });
    });
    const timeout = window.setTimeout(() => {
      map.invalidateSize({ pan: false });
    }, 250);
    const observer = new ResizeObserver(() => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        map.invalidateSize({ pan: false });
      });
    });

    observer.observe(container);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timeout);
      observer.disconnect();
    };
  }, [map]);

  return null;
}

function MapZoomBounds({ maxZoom }: { maxZoom: number }) {
  const map = useMap();

  useEffect(() => {
    map.setMinZoom(mapZoom);
    map.setMaxZoom(maxZoom);
    const currentZoom = map.getZoom();
    const nextZoom = Math.min(maxZoom, Math.max(mapZoom, currentZoom));
    if (nextZoom !== currentZoom) {
      map.setZoom(nextZoom, { animate: false });
    }
  }, [map, maxZoom]);

  return null;
}

function MapViewportReporter({
  onComparisonIntersectionChange
}: {
  onComparisonIntersectionChange: (intersects: boolean) => void;
}) {
  const map = useMap();

  useEffect(() => {
    let previous: boolean | null = null;
    const updateViewport = () => {
      const intersects = map.getBounds().intersects(strictComparisonLatLngBounds);
      if (intersects === previous) return;
      previous = intersects;
      onComparisonIntersectionChange(intersects);
    };

    updateViewport();
    map.on('moveend zoomend resize', updateViewport);
    return () => {
      map.off('moveend zoomend resize', updateViewport);
    };
  }, [map, onComparisonIntersectionChange]);

  return null;
}

function MapViewDataAttributes({ targetRef }: { targetRef: RefObject<HTMLElement | null> }) {
  const map = useMap();

  useEffect(() => {
    const updateViewAttributes = () => {
      const target = targetRef.current;
      if (!target) return;
      const center = map.getCenter();
      target.dataset.mapZoom = String(map.getZoom());
      target.dataset.mapCenter = `${center.lat.toFixed(6)},${center.lng.toFixed(6)}`;
    };

    updateViewAttributes();
    map.on('moveend zoomend', updateViewAttributes);
    return () => {
      map.off('moveend zoomend', updateViewAttributes);
    };
  }, [map, targetRef]);

  return null;
}

function AddressSearchMarker({ result }: { result: AddressSearchResult | null }) {
  const map = useMap();

  useEffect(() => {
    if (!result) return undefined;

    const [lat, lng] = addressResultCoordinate(result);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return undefined;

    const popupContent = document.createElement('span');
    popupContent.textContent = result.display_name;
    const marker = L.marker([lat, lng], {
      icon: L.divIcon({
        className: 'address-search-marker-icon',
        html: '<span class="address-search-marker" aria-hidden="true"></span>',
        iconSize: [22, 22],
        iconAnchor: [11, 11]
      }),
      keyboard: false,
      pane: 'markerPane'
    })
      .bindPopup(popupContent)
      .addTo(map);

    return () => {
      marker.remove();
    };
  }, [map, result]);

  return null;
}

function WorstHotspotMarkers({
  hotspots,
  selectedId,
  onSelect,
  language
}: {
  hotspots: WorstDamageHotspot[];
  selectedId: string | null;
  onSelect: (hotspot: WorstDamageHotspot) => void;
  language: Language;
}) {
  const map = useMap();

  useEffect(() => {
    const markers = hotspots.map((hotspot) => {
      const icon = L.divIcon({
        className: `hotspot-map-marker ${selectedId === hotspot.id ? 'selected' : ''}`,
        html: `<span>${hotspot.rank}</span>`,
        iconSize: [34, 34],
        iconAnchor: [17, 17]
      });
      const marker = L.marker([hotspot.lat, hotspot.lng], {
        icon,
        pane: 'markerPane',
        keyboard: true,
        title: `${hotspot.rank}. ${hotspot.labels[language]}`
      }).addTo(map);
      marker.on('click', () => onSelect(hotspot));
      return marker;
    });

    return () => {
      markers.forEach((marker) => marker.remove());
    };
  }, [hotspots, language, map, onSelect, selectedId]);

  return null;
}

function WorstAreaPinCaptureLayer({
  active,
  pins,
  onAddPin
}: {
  active: boolean;
  pins: WorstAreaPin[];
  onAddPin: (latlng: L.LatLng) => void;
}) {
  const map = useMap();
  const markersRef = useRef<L.Marker[]>([]);

  useEffect(() => {
    const clearMarkers = () => {
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
    };

    clearMarkers();
    const pane = map.getPane('worst-area-pin-pane') || map.createPane('worst-area-pin-pane');
    pane.style.zIndex = '690';

    markersRef.current = pins.map((pin) => {
      const icon = L.divIcon({
        className: 'worst-area-draft-pin-icon',
        html: `<span><b>${pin.rank}</b></span>`,
        iconSize: [38, 38],
        iconAnchor: [19, 38]
      });
      return L.marker([pin.lat, pin.lng], {
        icon,
        keyboard: false,
        pane: 'worst-area-pin-pane',
        title: `Draft key affected area ${pin.rank}`
      }).addTo(map);
    });

    return clearMarkers;
  }, [map, pins]);

  useEffect(() => {
    const container = map.getContainer();
    container.classList.toggle('pinning-active', active);

    if (!active) {
      return () => {
        container.classList.remove('pinning-active');
      };
    }

    const handleMapClick = (event: L.LeafletMouseEvent) => {
      if (pins.length >= 3) return;
      onAddPin(event.latlng);
    };

    map.on('click', handleMapClick);
    return () => {
      map.off('click', handleMapClick);
      container.classList.remove('pinning-active');
    };
  }, [active, map, onAddPin, pins.length]);

  return null;
}

function SatelliteBeforeAfterLayer({
  damageLayerVisible,
  split,
  preferEnhancedOnly
}: {
  damageLayerVisible: boolean;
  split: number;
  preferEnhancedOnly: boolean;
}) {
  const map = useMap();
  const [enhancedBounds, setEnhancedBounds] = useState<L.LatLngBoundsExpression | null>(null);
  const splitRef = useRef(split);
  const layerEntriesRef = useRef<Array<{ layer: L.TileLayer; side: 'before' | 'after' }>>([]);
  const damageLayerRef = useRef<L.TileLayer | null>(null);
  const clipFrameRef = useRef<number | null>(null);

  const createComparisonLayer = useCallback((scene: SatelliteSceneLayer, pane: string) => {
    const isEnhanced = scene.key.includes('enhanced');
    return L.tileLayer(scene.url, {
      attribution: scene.attribution,
      bounds: scene.bounds,
      className: scene.className,
      errorTileUrl: transparentTileDataUri,
      keepBuffer: 2,
      maxNativeZoom: isEnhanced ? 20 : maxMapZoom,
      maxZoom: maxMapZoom,
      minNativeZoom: isEnhanced ? 20 : 14,
      minZoom: isEnhanced ? 20 : 14,
      noWrap: true,
      opacity: 1,
      pane,
      updateWhenIdle: false,
      updateWhenZooming: false
    });
  }, []);

  useEffect(() => {
    if (!useEnhancedSatelliteOverlay) return undefined;

    let cancelled = false;
    loadEnhancedTileManifest()
      .then((manifest) => {
        if (!cancelled) setEnhancedBounds(enhancedManifestBounds(manifest));
      })
      .catch(() => {
        if (!cancelled) setEnhancedBounds(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const applyLayerClip = useCallback(() => {
    const mapRect = map.getContainer().getBoundingClientRect();
    const mapPaneRect = map.getPane('mapPane')?.getBoundingClientRect();
    if (!mapPaneRect) return;
    const splitX = mapRect.left + mapRect.width * (splitRef.current / 100);
    const top = mapRect.top - mapPaneRect.top;
    const bottom = mapRect.bottom - mapPaneRect.top;
    const left = mapRect.left - mapPaneRect.left;
    const split = splitX - mapPaneRect.left;
    const right = mapRect.right - mapPaneRect.left;
    const beforeClip = `rect(${top}px, ${split}px, ${bottom}px, ${left}px)`;
    const afterClip = `rect(${top}px, ${right}px, ${bottom}px, ${split}px)`;

    const applyClip = (layer: L.TileLayer, side: 'before' | 'after') => {
      const container = layer.getContainer();
      if (!container) return;
      container.style.clip = side === 'before' ? beforeClip : afterClip;
    };

    layerEntriesRef.current.forEach(({ layer, side }) => {
      applyClip(layer, side);
    });
    if (damageLayerRef.current) applyClip(damageLayerRef.current, 'after');
  }, [map]);

  const scheduleLayerClip = useCallback(() => {
    if (clipFrameRef.current !== null) return;
    clipFrameRef.current = L.Util.requestAnimFrame(() => {
      clipFrameRef.current = null;
      applyLayerClip();
    });
  }, [applyLayerClip]);

  useEffect(() => {
    splitRef.current = split;
    scheduleLayerClip();
  }, [scheduleLayerClip, split]);

  useEffect(() => {
    const beforePane = map.getPane('comparison-before-pane') || map.createPane('comparison-before-pane');
    const afterPane = map.getPane('comparison-after-pane') || map.createPane('comparison-after-pane');
    const damagePane = map.getPane('comparison-damage-pane') || map.createPane('comparison-damage-pane');

    for (const [pane, zIndex] of [[beforePane, '320'], [afterPane, '330'], [damagePane, '340']] as const) {
      pane.style.zIndex = zIndex;
      pane.style.pointerEvents = 'none';
    }

    const enhancedScenes = enhancedBounds ? enhancedComparisonScenes(enhancedBounds) : null;
    const activeScenes = {
      before: enhancedScenes
        ? (preferEnhancedOnly ? enhancedScenes.before : [...comparisonScenes.before, ...enhancedScenes.before])
        : (preferEnhancedOnly ? [] : comparisonScenes.before),
      after: enhancedScenes
        ? (preferEnhancedOnly ? enhancedScenes.after : [...comparisonScenes.after, ...enhancedScenes.after])
        : (preferEnhancedOnly ? [] : comparisonScenes.after)
    };
    const beforeLayers = activeScenes.before.map((scene) => createComparisonLayer(scene, 'comparison-before-pane'));
    const afterLayers = activeScenes.after.map((scene) => createComparisonLayer(scene, 'comparison-after-pane'));
    const layers = [...beforeLayers, ...afterLayers];
    layerEntriesRef.current = [
      ...beforeLayers.map((layer) => ({ layer, side: 'before' as const })),
      ...afterLayers.map((layer) => ({ layer, side: 'after' as const }))
    ];

    layers.forEach((layer) => layer.addTo(map));
    scheduleLayerClip();
    map.on('move zoom moveend zoomend viewreset resize', scheduleLayerClip);

    return () => {
      map.off('move zoom moveend zoomend viewreset resize', scheduleLayerClip);
      if (clipFrameRef.current !== null) {
        L.Util.cancelAnimFrame(clipFrameRef.current);
        clipFrameRef.current = null;
      }
      layers.forEach((layer) => {
        const container = layer.getContainer();
        if (container) container.style.clip = '';
        layer.remove();
      });
      layerEntriesRef.current = [];
    };
  }, [createComparisonLayer, enhancedBounds, map, preferEnhancedOnly, scheduleLayerClip]);

  useEffect(() => {
    if (!damageLayerVisible) return undefined;

    const layer = L.tileLayer(damageTileUrl(), {
      bounds: damageBounds,
      className: 'damage-raster-layer comparison-damage-raster-layer',
      errorTileUrl: transparentTileDataUri,
      keepBuffer: 0,
      maxNativeZoom: damageMaxUsefulZoom,
      maxZoom: maxMapZoom,
      minNativeZoom: 14,
      minZoom: 14,
      noWrap: true,
      opacity: 0.88,
      pane: 'comparison-damage-pane',
      updateWhenIdle: true,
      updateWhenZooming: false
    });

    damageLayerRef.current = layer;
    layer.addTo(map);
    scheduleLayerClip();
    return () => {
      const container = layer.getContainer();
      if (container) container.style.clip = '';
      layer.remove();
      if (damageLayerRef.current === layer) damageLayerRef.current = null;
    };
  }, [damageLayerVisible, map, scheduleLayerClip]);

  return null;
}

function HighResolutionFocusLayer() {
  const map = useMap();
  const [enhancedBounds, setEnhancedBounds] = useState<L.LatLngBoundsExpression | null>(null);

  useEffect(() => {
    if (!useEnhancedSatelliteOverlay) return undefined;

    let cancelled = false;
    loadEnhancedTileManifest()
      .then((manifest) => {
        if (!cancelled) setEnhancedBounds(enhancedManifestBounds(manifest));
      })
      .catch(() => {
        if (!cancelled) setEnhancedBounds(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const pane = map.getPane('high-resolution-focus-pane') || map.createPane('high-resolution-focus-pane');
    pane.style.zIndex = '300';
    pane.style.pointerEvents = 'none';

    const enhancedScenes = enhancedBounds ? enhancedComparisonScenes(enhancedBounds).after : [];
    const scenes = [...comparisonScenes.after, ...enhancedScenes];
    const layers = scenes.map((scene) => {
      const isEnhanced = scene.key.includes('enhanced');
      return L.tileLayer(scene.url, {
        attribution: scene.attribution,
        bounds: scene.bounds,
        className: `high-resolution-focus-tile-layer ${isEnhanced ? 'high-resolution-focus-enhanced-tile-layer' : 'high-resolution-focus-fallback-tile-layer'}`,
        errorTileUrl: transparentTileDataUri,
        keepBuffer: 1,
        maxNativeZoom: isEnhanced ? 20 : maxMapZoom,
        maxZoom: maxMapZoom,
        minNativeZoom: isEnhanced ? 20 : 14,
        minZoom: isEnhanced ? 20 : 14,
        noWrap: true,
        opacity: 1,
        pane: 'high-resolution-focus-pane',
        updateWhenIdle: true,
        updateWhenZooming: false
      });
    });

    layers.forEach((layer) => layer.addTo(map));
    return () => {
      layers.forEach((layer) => layer.remove());
    };
  }, [enhancedBounds, map]);

  return null;
}

function DamageViewportReporter({
  language,
  onChange
}: {
  language: Language;
  onChange: (state: DamageViewportState) => void;
}) {
  const map = useMap();
  const updateIdRef = useRef(0);

  useEffect(() => {
    let cancelled = false;

    const updateVisibleDamage = () => {
      const updateId = ++updateIdRef.current;
      const bounds = map.getBounds();
      const center = map.getCenter();
      summarizeDamageViewport(
        {
          west: bounds.getWest(),
          south: bounds.getSouth(),
          east: bounds.getEast(),
          north: bounds.getNorth()
        },
        { lat: center.lat, lng: center.lng },
        language
      )
        .then((state) => {
          if (!cancelled && updateId === updateIdRef.current) onChange(state);
        })
        .catch(() => {
          if (!cancelled && updateId === updateIdRef.current) onChange(initialDamageViewport(language));
        });
    };

    updateVisibleDamage();
    map.on('moveend zoomend', updateVisibleDamage);
    return () => {
      cancelled = true;
      map.off('moveend zoomend', updateVisibleDamage);
    };
  }, [language, map, onChange]);

  return null;
}

function DamageRasterLayer() {
  const map = useMap();

  useEffect(() => {
    const layer = L.tileLayer(damageTileUrl(), {
      bounds: damageBounds,
      className: 'damage-raster-layer',
      errorTileUrl: transparentTileDataUri,
      keepBuffer: 0,
      maxNativeZoom: 18,
      maxZoom: maxMapZoom,
      minNativeZoom: 14,
      minZoom: 14,
      noWrap: true,
      opacity: 0.92,
      updateWhenIdle: true,
      updateWhenZooming: false,
      zIndex: 430
    });

    layer.addTo(map);
    return () => {
      layer.remove();
    };
  }, [map]);

  return null;
}

function SuperResolutionMarkers({
  visible,
  srIndex,
  language
}: {
  visible: boolean;
  srIndex: SuperResolutionIndex | null;
  language: Language;
}) {
  const map = useMap();

  useEffect(() => {
    const records = srIndex?.records || [];
    if (!visible || !records.length) return undefined;

    const pane = map.getPane('super-resolution-pane') || map.createPane('super-resolution-pane');
    pane.style.zIndex = '520';
    pane.style.pointerEvents = 'auto';
    pane.dataset.aoiCount = String(records.length);

    const markers = records.map((record) => {
      const marker = L.circleMarker([record.lat, record.lon], {
        className: 'super-resolution-marker',
        color: '#0f766e',
        fillColor: '#67e8f9',
        fillOpacity: 0.78,
        pane: 'super-resolution-pane',
        radius: 5,
        weight: 2
      }).addTo(map);
      marker.bindTooltip(
        `<strong>${record.id}</strong><br>` +
          `${srIndex?.model?.name || 'Real-ESRGAN'} x${srIndex?.model?.scale || 4}<br>` +
          `${language === 'es' ? 'Ayuda visual; no reemplaza evidencia' : 'Visual aid; not evidence replacement'}`,
        { sticky: true, opacity: 0.95 }
      );
      return marker;
    });

    return () => {
      markers.forEach((marker) => marker.remove());
      pane.dataset.aoiCount = '0';
    };
  }, [language, map, srIndex, visible]);

  return null;
}

function NamedPlaceLabelsLayer({
  visible,
  language,
  addressSearchResult,
  onVisibleCountChange
}: {
  visible: boolean;
  language: Language;
  addressSearchResult: AddressSearchResult | null;
  onVisibleCountChange: (count: number) => void;
}) {
  const map = useMap();
  const [places, setPlaces] = useState<NamedPlaceFeature[] | null>(null);
  const markersRef = useRef<L.Marker[]>([]);

  useEffect(() => {
    if (!visible || places !== null) return undefined;

    let cancelled = false;
    fetchNamedPlaces()
      .then((features) => {
        if (!cancelled) setPlaces(features);
      })
      .catch(() => {
        if (!cancelled) setPlaces([]);
      });

    return () => {
      cancelled = true;
    };
  }, [places, visible]);

  useEffect(() => {
    const clearMarkers = () => {
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      onVisibleCountChange(0);
    };

    if (!visible || !places?.length) {
      clearMarkers();
      return undefined;
    }

    const pane = map.getPane('named-place-label-pane') || map.createPane('named-place-label-pane');
    pane.style.zIndex = '545';
    pane.style.pointerEvents = 'none';

    const renderLabels = () => {
      clearMarkers();
      if (map.getZoom() < 18) return;

      const bounds = map.getBounds().pad(0.08);
      const center = map.getCenter();
      const mapSize = map.getSize();
      const isMobile = mapSize.x < 700;
      const maxLabels = mapSize.x < 430 ? 4 : isMobile ? 7 : 18;
      const searchedPoint = addressSearchResult
        ? map.latLngToContainerPoint(addressResultCoordinate(addressSearchResult))
        : null;
      const selectedRects = searchedPoint && isMobile
        ? [{
            left: searchedPoint.x - 112,
            right: searchedPoint.x + 112,
            top: searchedPoint.y - 42,
            bottom: searchedPoint.y + 42
          }]
        : [];
      const collides = (rect: { left: number; right: number; top: number; bottom: number }) =>
        selectedRects.some((selectedRect) => !(
          rect.right <= selectedRect.left ||
          selectedRect.right <= rect.left ||
          rect.bottom <= selectedRect.top ||
          selectedRect.bottom <= rect.top
        ));
      const labelRect = (feature: NamedPlaceFeature) => {
        const [lng, lat] = feature.geometry.coordinates;
        const point = map.latLngToContainerPoint([lat, lng]);
        const width = Math.min(isMobile ? 142 : 168, Math.max(58, 34 + feature.properties.name.length * 6));
        const height = isMobile ? 24 : 26;
        return {
          left: point.x - width / 2,
          right: point.x + width / 2,
          top: point.y - height / 2,
          bottom: point.y + height / 2
        };
      };
      const visiblePlaces: NamedPlaceFeature[] = [];
      const candidates = places
        .filter((feature) => {
          const [lng, lat] = feature.geometry.coordinates;
          return bounds.contains(L.latLng(lat, lng));
        })
        .sort((left, right) => {
          const categoryDelta =
            namedPlaceCategoryWeight(left.properties.category) -
            namedPlaceCategoryWeight(right.properties.category);
          if (categoryDelta) return categoryDelta;

          const [leftLng, leftLat] = left.geometry.coordinates;
          const [rightLng, rightLat] = right.geometry.coordinates;
          return center.distanceTo([leftLat, leftLng]) - center.distanceTo([rightLat, rightLng]);
        });

      for (const feature of candidates) {
        const rect = labelRect(feature);
        if (isMobile && (
          rect.left < 8 ||
          rect.right > mapSize.x - 8 ||
          rect.top < 120 ||
          rect.bottom > mapSize.y - 96
        )) continue;
        if (collides(rect)) continue;
        visiblePlaces.push(feature);
        selectedRects.push(rect);
        if (visiblePlaces.length >= maxLabels) break;
      }

      onVisibleCountChange(visiblePlaces.length);

      markersRef.current = visiblePlaces.map((feature) => {
        const [lng, lat] = feature.geometry.coordinates;
        const name = escapeHtml(feature.properties.name);
        const kind = escapeHtml(feature.properties.kind);
        const category = escapeHtml(feature.properties.category);
        const sourceUrl = escapeHtml(feature.properties.sourceUrl);
        const label = language === 'es' ? 'Nombre OSM verificado' : 'Verified OSM name';
        const marker = L.marker([lat, lng], {
          icon: L.divIcon({
            className: 'named-place-label-icon',
            iconAnchor: [0, 0],
            html:
              `<span class="named-place-label named-place-label-${category}" ` +
              `data-source-url="${sourceUrl}" data-kind="${kind}" title="${label}: ${name}">` +
              `<span class="named-place-dot" aria-hidden="true"></span>${name}</span>`
          }),
          interactive: false,
          keyboard: false,
          pane: 'named-place-label-pane'
        }).addTo(map);
        return marker;
      });
    };

    renderLabels();
    map.on('moveend zoomend resize', renderLabels);

    return () => {
      map.off('moveend zoomend resize', renderLabels);
      clearMarkers();
    };
  }, [addressSearchResult, language, map, onVisibleCountChange, places, visible]);

  return null;
}

function DamageLayerLegend({
  status,
  summary,
  c
}: {
  status: 'ready' | 'hidden';
  summary: DamageViewportSummary | null;
  c: Copy;
}) {
  const rows: DamageSeverity[] = ['high', 'moderate', 'observed', 'uncertain'];

  return (
    <aside className="damage-legend" aria-label={c.damageLegendTitle}>
      <div className="damage-legend-top">
        <strong>{c.damageLegendTitle}</strong>
        <span>{microsoftDamageSource.organization}</span>
      </div>
      <div className="damage-legend-status">
        {status === 'ready' && summary ? `${summary.total.toLocaleString()} ${c.damageFootprints}` : null}
        {status === 'hidden' ? c.damageLayerOff : null}
      </div>
      <div className="damage-legend-rows">
        {rows.map((severity) => (
          <span key={severity}>
            <span className={`damage-swatch damage-${severity}`} />
            {damageSeverityLabel(severity, c)}
            {summary ? ` ${summary[severity].toLocaleString()}` : ''}
          </span>
        ))}
      </div>
      <div className="damage-links">
        <a href={microsoftDamageSource.hdxDatasetUrl} target="_blank" rel="noreferrer">HDX</a>
        <a href={microsoftDamageSource.webSceneUrl} target="_blank" rel="noreferrer">3D</a>
        <a href={microsoftDamageSource.geopackageUrl} target="_blank" rel="noreferrer">GPKG</a>
        <a href={microsoftDamageSource.imageMapUrl} target="_blank" rel="noreferrer">JPG</a>
      </div>
      <p>{c.damageAttribution}</p>
    </aside>
  );
}

function DamageComparisonControl({
  value,
  onChange,
  language
}: {
  value: number;
  onChange: (value: number) => void;
  language: Language;
}) {
  const handleRef = useRef<HTMLDivElement>(null);
  const activePointerIdRef = useRef<number | null>(null);
  const activeTouchIdRef = useRef<number | null>(null);
  const touchDragActiveRef = useRef(false);
  const mouseDragActiveRef = useRef(false);
  const label = language === 'es' ? 'Mover comparador satelital antes y despues' : 'Move before and after satellite comparison';

  const setComparisonDragging = useCallback((active: boolean) => {
    handleRef.current?.closest('.map-shell')?.classList.toggle('comparison-dragging', active);
  }, []);

  const updateFromClientX = useCallback((clientX: number) => {
    const mapShell = handleRef.current?.closest('.map-shell') || handleRef.current?.parentElement;
    if (!mapShell) return;
    const rect = mapShell.getBoundingClientRect();
    const nextValue = Math.round(((clientX - rect.left) / rect.width) * 100);
    onChange(Math.min(92, Math.max(8, nextValue)));
  }, [onChange]);

  useEffect(() => {
    const stopMapGesture = (event: Event) => {
      event.preventDefault();
      event.stopPropagation();
    };

    const startPointerDrag = (event: PointerEvent) => {
      stopMapGesture(event);
      activePointerIdRef.current = event.pointerId;
      setComparisonDragging(true);
      try {
        if (handleRef.current && !handleRef.current.hasPointerCapture(event.pointerId)) {
          handleRef.current.setPointerCapture(event.pointerId);
        }
      } catch {
        // Embedded webviews can reject pointer capture while still sending pointer moves.
      }
      updateFromClientX(event.clientX);
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (activePointerIdRef.current !== event.pointerId) return;
      stopMapGesture(event);
      updateFromClientX(event.clientX);
    };

    const handlePointerEnd = (event: PointerEvent) => {
      if (activePointerIdRef.current !== event.pointerId) return;
      stopMapGesture(event);
      activePointerIdRef.current = null;
      setComparisonDragging(false);
      try {
        if (handleRef.current?.hasPointerCapture(event.pointerId)) {
          handleRef.current.releasePointerCapture(event.pointerId);
        }
      } catch {
        // Pointer capture may already be gone on some touch cancellation paths.
      }
    };

    const activeTouch = (touches: TouchList) => {
      if (activeTouchIdRef.current === null) return touches[0] || null;
      for (let index = 0; index < touches.length; index += 1) {
        if (touches[index].identifier === activeTouchIdRef.current) return touches[index];
      }
      return null;
    };

    const handleTouchMove = (event: TouchEvent) => {
      if (!touchDragActiveRef.current) return;
      const touch = activeTouch(event.touches) || activeTouch(event.changedTouches);
      if (!touch) return;
      stopMapGesture(event);
      updateFromClientX(touch.clientX);
    };

    const handleTouchStart = (event: TouchEvent) => {
      if (activePointerIdRef.current !== null || event.touches.length !== 1) return;
      const touch = event.touches[0];
      if (!touch) return;
      stopMapGesture(event);
      activeTouchIdRef.current = touch.identifier;
      touchDragActiveRef.current = true;
      setComparisonDragging(true);
      updateFromClientX(touch.clientX);
    };

    const handleTouchEnd = (event: TouchEvent) => {
      if (!touchDragActiveRef.current) return;
      if (activeTouchIdRef.current !== null && activeTouch(event.touches)) return;
      stopMapGesture(event);
      activeTouchIdRef.current = null;
      touchDragActiveRef.current = false;
      setComparisonDragging(false);
    };

    const handleMouseStart = (event: MouseEvent) => {
      stopMapGesture(event);
      mouseDragActiveRef.current = true;
      setComparisonDragging(true);
      updateFromClientX(event.clientX);
    };

    const handleMouseMove = (event: MouseEvent) => {
      if (!mouseDragActiveRef.current) return;
      stopMapGesture(event);
      updateFromClientX(event.clientX);
    };

    const handleMouseEnd = (event: MouseEvent) => {
      if (!mouseDragActiveRef.current) return;
      stopMapGesture(event);
      mouseDragActiveRef.current = false;
      setComparisonDragging(false);
    };

    const control = handleRef.current;
    const ownerDocument = control?.ownerDocument || document;
    ownerDocument.addEventListener('pointermove', handlePointerMove, { capture: true, passive: false });
    ownerDocument.addEventListener('pointerup', handlePointerEnd, { capture: true, passive: false });
    ownerDocument.addEventListener('pointercancel', handlePointerEnd, { capture: true, passive: false });
    ownerDocument.addEventListener('touchmove', handleTouchMove, { capture: true, passive: false });
    ownerDocument.addEventListener('touchend', handleTouchEnd, { capture: true, passive: false });
    ownerDocument.addEventListener('touchcancel', handleTouchEnd, { capture: true, passive: false });
    ownerDocument.addEventListener('mousemove', handleMouseMove, { capture: true, passive: false });
    ownerDocument.addEventListener('mouseup', handleMouseEnd, { capture: true, passive: false });
    control?.addEventListener('pointerdown', startPointerDrag, { capture: true, passive: false });
    control?.addEventListener('touchstart', handleTouchStart, { capture: true, passive: false });
    control?.addEventListener('mousedown', handleMouseStart, { capture: true, passive: false });

    return () => {
      ownerDocument.removeEventListener('pointermove', handlePointerMove, true);
      ownerDocument.removeEventListener('pointerup', handlePointerEnd, true);
      ownerDocument.removeEventListener('pointercancel', handlePointerEnd, true);
      ownerDocument.removeEventListener('touchmove', handleTouchMove, true);
      ownerDocument.removeEventListener('touchend', handleTouchEnd, true);
      ownerDocument.removeEventListener('touchcancel', handleTouchEnd, true);
      ownerDocument.removeEventListener('mousemove', handleMouseMove, true);
      ownerDocument.removeEventListener('mouseup', handleMouseEnd, true);
      control?.removeEventListener('pointerdown', startPointerDrag, true);
      control?.removeEventListener('touchstart', handleTouchStart, true);
      control?.removeEventListener('mousedown', handleMouseStart, true);
      setComparisonDragging(false);
    };
  }, [setComparisonDragging, updateFromClientX]);

  return (
    <div
      ref={handleRef}
      className="comparison-control"
      data-testid="comparison-slider"
      style={{ left: `${value}%` }}
      role="slider"
      aria-label={label}
      aria-valuemin={8}
      aria-valuemax={92}
      aria-valuenow={value}
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'ArrowLeft') {
          event.preventDefault();
          onChange(Math.max(8, value - 2));
        }
        if (event.key === 'ArrowRight') {
          event.preventDefault();
          onChange(Math.min(92, value + 2));
        }
      }}
      onLostPointerCapture={(event) => {
        event.stopPropagation();
      }}
      onWheel={(event) => {
        event.preventDefault();
        event.stopPropagation();
        const control = event.currentTarget;
        const previousPointerEvents = control.style.pointerEvents;
        control.style.pointerEvents = 'none';
        const mapTarget = document.elementFromPoint(event.clientX, event.clientY);
        control.style.pointerEvents = previousPointerEvents;
        mapTarget?.dispatchEvent(
          new WheelEvent('wheel', {
            bubbles: true,
            cancelable: true,
            clientX: event.clientX,
            clientY: event.clientY,
            deltaMode: event.deltaMode,
            deltaX: event.deltaX,
            deltaY: event.deltaY,
            deltaZ: event.deltaZ
          })
        );
      }}
    >
      <span className="comparison-grip" aria-hidden="true" />
    </div>
  );
}

function SatelliteComparisonControls({
  split,
  onSplitChange,
  language
}: {
  split: number;
  onSplitChange: (value: number) => void;
  language: Language;
}) {
  return (
    <section
      className="satellite-comparison-controls"
      data-testid="comparison-drag-surface"
      aria-label={language === 'es' ? 'Comparacion satelital antes y despues' : 'Before and after satellite comparison'}
    >
      <div className="comparison-side-labels" aria-hidden="true">
        <span>{language === 'es' ? 'Antes 7 Abr' : 'Before 7 Apr'}</span>
        <span>{language === 'es' ? 'Despues 27 Jun' : 'After 27 Jun'}</span>
      </div>
      <div className="comparison-divider" style={{ left: `${split}%` }} aria-hidden="true" />
      <DamageComparisonControl
        value={split}
        onChange={onSplitChange}
        language={language}
      />
      <div className="comparison-context">
        {language === 'es'
          ? 'Vantor 7 Apr / 27 Jun'
          : 'Vantor 7 Apr / 27 Jun'}
      </div>
    </section>
  );
}

function SuperResolutionReviewPanel({
  srIndex,
  onClose,
  language
}: {
  srIndex: SuperResolutionIndex;
  onClose: () => void;
  language: Language;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const completed = srIndex.completedAois || srIndex.records?.length || 0;
  const generated = srIndex.generatedAt ? new Date(srIndex.generatedAt) : null;
  const generatedLabel = generated && Number.isFinite(generated.getTime())
    ? generated.toLocaleDateString(language === 'es' ? 'es-VE' : 'en-US', { day: '2-digit', month: 'short', year: 'numeric' })
    : '2026';

  return (
    <aside className="super-resolution-panel" aria-label={language === 'es' ? 'Revision de super resolucion' : 'Super-resolution review'}>
      <div className="super-resolution-top">
        <div>
          <span>{language === 'es' ? 'Ayuda visual AI' : 'AI visual aid'}</span>
          <strong>{srIndex.model?.name || 'Real-ESRGAN'} x{srIndex.model?.scale || 4}</strong>
        </div>
        <button
          className="icon-button"
          type="button"
          onClick={onClose}
          aria-label={language === 'es' ? 'Cerrar super resolucion' : 'Close super-resolution'}
        >
          <X size={15} />
        </button>
      </div>
      <div className="super-resolution-metrics">
        <span><strong>{completed.toLocaleString()}</strong>{language === 'es' ? 'AOIs' : 'AOIs'}</span>
        <span><strong>z{srIndex.zoom || 19}</strong>{generatedLabel}</span>
      </div>
      {srIndex.contactSheet?.localPath && !imageFailed ? (
        <a className="super-resolution-preview" href={srIndex.contactSheet.url || srIndex.contactSheet.localPath} target="_blank" rel="noreferrer">
          <img
            src={srIndex.contactSheet.localPath}
            alt={language === 'es' ? 'Mosaico de super resolucion' : 'Super-resolution contact sheet'}
            onError={() => setImageFailed(true)}
          />
        </a>
      ) : null}
      <p>
        {language === 'es'
          ? 'Interpretativo: comparar con Vantor crudo antes/despues antes de tomar decisiones.'
          : 'Interpretive: compare against raw Vantor before/after imagery before decisions.'}
      </p>
      {srIndex.archive?.url ? (
        <a className="super-resolution-archive" href={srIndex.archive.url} target="_blank" rel="noreferrer">
          {language === 'es' ? 'Archivo completo HF' : 'Full HF archive'}
        </a>
      ) : null}
    </aside>
  );
}

function TrustedDataPanel({
  trustedData,
  language,
  c
}: {
  trustedData: TrustedDataSnapshot | null;
  language: Language;
  c: Copy;
}) {
  const manualCount = trustedData?.sources.filter((source) => source.status === 'manual_review').length || 0;
  const errorCount = trustedData?.summary.errorSourceCount || 0;
  const updateAge = trustedData ? formatSnapshotAge(trustedData.generatedAt) : '--';

  return (
    <section className="sidebar-section trusted-panel compact-panel">
      <div className="section-title">
        <span>{language === 'es' ? 'Estado' : 'Status'}</span>
        <Shield size={15} />
      </div>
      {!trustedData ? (
        <p className="trusted-empty">{c.noTrustedData}</p>
      ) : (
        <>
          <div className="status-stack" aria-label={language === 'es' ? 'Estado de fuentes' : 'Source status'}>
            <div className="status-row">
              <span className={errorCount ? 'status-dot bad' : 'status-dot good'} />
              <strong>{errorCount ? `${errorCount} ${language === 'es' ? 'errores' : 'errors'}` : (language === 'es' ? 'Salud OK' : 'Healthy')}</strong>
            </div>
            <div className="status-row muted">
              <Clock size={14} />
              <span>{updateAge} {language === 'es' ? 'sync' : 'sync'}</span>
            </div>
            {manualCount ? (
              <div className="status-row muted">
                <span className="status-dot neutral" />
                <span>{manualCount} {language === 'es' ? 'revision' : 'review'}</span>
              </div>
            ) : null}
          </div>
          <p className="source-line">Microsoft/HDX · NASA · Vantor · USGS</p>
        </>
      )}
    </section>
  );
}

function WorstHotspotExperience({
  hotspots,
  activeHotspot,
  activeIndex,
  damageLayerVisible,
  onDamageLayerToggle,
  onSelectIndex,
  onClose,
  language
}: {
  hotspots: WorstDamageHotspot[];
  activeHotspot: WorstDamageHotspot;
  activeIndex: number;
  damageLayerVisible: boolean;
  onDamageLayerToggle: () => void;
  onSelectIndex: (index: number) => void;
  onClose: () => void;
  language: Language;
}) {
  const [mobilePanelExpanded, setMobilePanelExpanded] = useState(false);
  const panelRef = useRef<HTMLElement>(null);
  const previousIndex = (activeIndex + hotspots.length - 1) % hotspots.length;
  const nextIndex = (activeIndex + 1) % hotspots.length;
  const highLabel = language === 'es' ? 'alto dano' : 'high damage';
  const footprintLabel = language === 'es' ? 'huellas' : 'footprints';
  const drawerLabel = language === 'es' ? 'Zonas clave afectadas' : 'Key affected areas';

  useEffect(() => {
    const shell = panelRef.current?.closest('.map-shell');
    shell?.classList.toggle('worst-panel-mobile-expanded', mobilePanelExpanded);
    shell?.classList.toggle('worst-panel-mobile-collapsed', !mobilePanelExpanded);

    return () => {
      shell?.classList.remove('worst-panel-mobile-expanded', 'worst-panel-mobile-collapsed');
    };
  }, [mobilePanelExpanded]);

  return (
    <section
      ref={panelRef}
      className={`worst-experience-panel ${mobilePanelExpanded ? 'mobile-expanded' : 'mobile-collapsed'}`}
      aria-label={drawerLabel}
      aria-live="polite"
    >
      <button
        className="worst-drawer-toggle"
        type="button"
        onClick={() => setMobilePanelExpanded((expanded) => !expanded)}
        aria-expanded={mobilePanelExpanded}
        aria-label={mobilePanelExpanded
          ? (language === 'es' ? 'Contraer zonas clave afectadas' : 'Collapse key affected areas')
          : (language === 'es' ? 'Expandir zonas clave afectadas' : 'Expand key affected areas')}
      >
        <AlertTriangle size={14} />
        <Menu className="drawer-menu-icon" size={16} />
        <span>{language === 'es' ? 'Zonas clave' : 'Key areas'}</span>
        <strong>{activeIndex + 1}/{hotspots.length}</strong>
        <ChevronRight size={15} />
      </button>
      <div className="worst-panel-content">
        <div className="worst-experience-top">
          <span className="worst-eyebrow">
            <AlertTriangle size={14} />
            {language === 'es' ? 'Zonas clave' : 'Key affected areas'}
          </span>
          <span className="worst-step">{activeIndex + 1}/{hotspots.length}</span>
          <button
            className="worst-close-button"
            type="button"
            onClick={onClose}
            aria-label={language === 'es' ? 'Cerrar zonas clave afectadas' : 'Close key affected areas'}
          >
            <X size={16} />
          </button>
        </div>
        <div className="worst-experience-copy">
          <h2>#{activeHotspot.rank} {activeHotspot.labels[language]}</h2>
          <p>{activeHotspot.context[language]}</p>
        </div>
        <div className="worst-metrics" aria-label={language === 'es' ? 'Dano verificado' : 'Verified damage'}>
          <span><strong>{activeHotspot.high.toLocaleString()}</strong>{highLabel}</span>
          <span><strong>{activeHotspot.total.toLocaleString()}</strong>{footprintLabel}</span>
        </div>
        <button
          className={`worst-damage-toggle ${damageLayerVisible ? 'selected' : ''}`}
          type="button"
          onClick={onDamageLayerToggle}
          aria-pressed={damageLayerVisible}
        >
          <span className="damage-swatch damage-high" aria-hidden="true" />
          <span>
            {damageLayerVisible
              ? (language === 'es' ? 'Ocultar dano' : 'Hide damage')
              : (language === 'es' ? 'Mostrar dano' : 'Show damage')}
          </span>
          <span className="switch" aria-hidden="true" />
        </button>
        <div className="worst-progress" aria-label={language === 'es' ? 'Seleccionar zona' : 'Select area'}>
          {hotspots.map((hotspot, index) => (
            <button
              key={hotspot.id}
              type="button"
              className={index === activeIndex ? 'active' : ''}
              onClick={() => onSelectIndex(index)}
              aria-label={`${language === 'es' ? 'Zona' : 'Area'} ${hotspot.rank}: ${hotspot.labels[language]}`}
              aria-pressed={index === activeIndex}
            >
              {hotspot.rank}
            </button>
          ))}
        </div>
        <div className="worst-navigation">
          <button
            type="button"
            className="secondary-button"
            onClick={() => onSelectIndex(previousIndex)}
            aria-label={language === 'es' ? 'Zona anterior' : 'Previous area'}
          >
            <ChevronLeft size={16} />
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={() => onSelectIndex(nextIndex)}
          >
            <span>{language === 'es' ? 'Siguiente' : 'Next'}</span>
            <ChevronRight size={16} />
          </button>
        </div>
        <small>{language === 'es' ? 'Microsoft/HDX verificado · Vantor antes/despues' : 'Verified Microsoft/HDX · Vantor before/after'}</small>
      </div>
    </section>
  );
}

function WorstAreaPinningPanel({
  pins,
  onRemovePin,
  onClearPins,
  onClose,
  language
}: {
  pins: WorstAreaPin[];
  onRemovePin: (index: number) => void;
  onClearPins: () => void;
  onClose: () => void;
  language: Language;
}) {
  const [copied, setCopied] = useState(false);
  const exportText = worstAreaPinExport(pins);

  useEffect(() => {
    setCopied(false);
  }, [exportText]);

  const handleCopy = async () => {
    if (!pins.length) return;
    await navigator.clipboard.writeText(exportText);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <section className="worst-pin-panel" aria-label={language === 'es' ? 'Fijar tres zonas clave afectadas' : 'Pin three key affected areas'}>
      <div className="worst-pin-top">
        <span className="worst-pin-title">
          <MapPin size={15} />
          {language === 'es' ? 'Fijar claves' : 'Key area pins'}
        </span>
        <span className="worst-step">{pins.length}/3</span>
        <button
          className="worst-close-button"
          type="button"
          onClick={onClose}
          aria-label={language === 'es' ? 'Cerrar fijacion de zonas' : 'Close area pinning'}
        >
          <X size={16} />
        </button>
      </div>
      <div className="worst-pin-list">
        {[0, 1, 2].map((index) => {
          const pin = pins[index];
          return (
            <div key={index} className={`worst-pin-row ${pin ? 'filled' : ''}`}>
              <strong>{index + 1}</strong>
              <span>
                {pin
                  ? `${formatPinnedCoordinate(pin.lat)}, ${formatPinnedCoordinate(pin.lng)}`
                  : (language === 'es' ? 'Toca el mapa' : 'Tap map')}
              </span>
              {pin ? (
                <button
                  type="button"
                  onClick={() => onRemovePin(index)}
                  aria-label={`${language === 'es' ? 'Eliminar pin' : 'Remove pin'} ${index + 1}`}
                >
                  <X size={13} />
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
      <div className="worst-pin-actions">
        <button
          type="button"
          className="secondary-button"
          onClick={onClearPins}
          disabled={!pins.length}
        >
          <RotateCcw size={15} />
          <span>{language === 'es' ? 'Reiniciar' : 'Reset'}</span>
        </button>
        <button
          type="button"
          className="primary-button"
          onClick={handleCopy}
          disabled={!pins.length}
        >
          {copied ? <Check size={15} /> : <Clipboard size={15} />}
          <span>{copied ? (language === 'es' ? 'Copiado' : 'Copied') : (language === 'es' ? 'Copiar' : 'Copy')}</span>
        </button>
      </div>
      <small>{language === 'es' ? 'Manual, no evidencia publicada todavia.' : 'Manual draft; not published evidence yet.'}</small>
    </section>
  );
}

function MapLayerControls({
  damageLayerVisible,
  setDamageLayerVisible,
  superResolutionVisible,
  setSuperResolutionVisible,
  srIndex,
  comparisonVisible,
  setComparisonVisible,
  comparisonAvailable,
  hasSearchedAddress,
  language,
  c
}: {
  damageLayerVisible: boolean;
  setDamageLayerVisible: (value: boolean) => void;
  superResolutionVisible: boolean;
  setSuperResolutionVisible: (value: boolean) => void;
  srIndex: SuperResolutionIndex | null;
  comparisonVisible: boolean;
  setComparisonVisible: (value: boolean) => void;
  comparisonAvailable: boolean;
  hasSearchedAddress: boolean;
  language: Language;
  c: Copy;
}) {
  const comparisonButtonText = comparisonVisible
    ? (language === 'es' ? 'Ocultar' : 'Hide')
    : comparisonAvailable
      ? (language === 'es' ? 'Comparar' : 'Compare')
      : hasSearchedAddress
        ? (language === 'es' ? 'No disponible' : 'Unavailable')
        : (language === 'es' ? 'Busca primero' : 'Search first');

  return (
    <>
      <section className="sidebar-section imagery-panel">
        <div className="section-title">
          <span>{language === 'es' ? 'Imagenes' : 'Imagery'}</span>
          <Layers size={15} />
        </div>
        <div className="satellite-pair-card">
          <div className="imagery-row">
            <span>{language === 'es' ? 'Nacional' : 'National'}</span>
            <strong>Sentinel-2 Cloudless 2024</strong>
          </div>
          <div className="imagery-row imagery-dates">
            <span>{language === 'es' ? 'Resolucion' : 'Resolution'}</span>
            <strong>{language === 'es' ? '10 m, abierto' : '10 m, open'}</strong>
          </div>
          <div className="imagery-row imagery-dates">
            <span>{language === 'es' ? 'Antes' : 'Before'}</span>
            <strong>7 Apr 2026</strong>
          </div>
          <div className="imagery-row imagery-dates">
            <span>{language === 'es' ? 'Despues' : 'After'}</span>
            <strong>27 Jun 2026</strong>
          </div>
          <div className="imagery-row imagery-dates">
            <span>{language === 'es' ? 'Nombres' : 'Labels'}</span>
            <strong>{language === 'es' ? 'OSM verificado' : 'Verified OSM'}</strong>
          </div>
          <button
            className={`satellite-toggle ${comparisonVisible ? 'selected' : ''}`}
            onClick={() => {
              if (comparisonAvailable) setComparisonVisible(!comparisonVisible);
            }}
            type="button"
            disabled={!comparisonAvailable}
            aria-pressed={comparisonVisible}
          >
            <span>{comparisonButtonText}</span>
            <span className="switch" aria-hidden="true" />
          </button>
        </div>
      </section>

      <section className="sidebar-section layers-panel">
        <div className="section-title">
          <span>{language === 'es' ? 'Capas' : 'Layers'}</span>
          <Layers size={15} />
        </div>
        <button
          className={`layer-row ${damageLayerVisible ? 'selected' : ''}`}
          onClick={() => setDamageLayerVisible(!damageLayerVisible)}
          type="button"
          aria-pressed={damageLayerVisible}
          aria-label={c.microsoftDamageLayer}
        >
          <span className="layer-left">
            <span className="damage-swatch damage-high" />
            {language === 'es' ? 'Dano' : 'Damage'}
          </span>
          <span className="switch" aria-hidden="true" />
        </button>
        {srIndex ? (
          <button
            className={`layer-row ${superResolutionVisible ? 'selected' : ''}`}
            onClick={() => setSuperResolutionVisible(!superResolutionVisible)}
            type="button"
            aria-pressed={superResolutionVisible}
            aria-label={language === 'es' ? 'Super resolucion AI' : 'AI super-resolution'}
          >
            <span className="layer-left">
              <span className="super-resolution-swatch" />
              {language === 'es' ? 'SR visual' : 'SR review'}
            </span>
            <span className="switch" aria-hidden="true" />
          </button>
        ) : null}
      </section>
    </>
  );
}

function AddressSearchControl({
  language,
  map,
  onSelect
}: {
  language: Language;
  map: L.Map | null;
  onSelect: (result: AddressSearchResult) => void;
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<AddressSearchResult[]>([]);
  const [status, setStatus] = useState<AddressSearchStatus>('idle');
  const [message, setMessage] = useState('');
  const cacheRef = useRef<Map<string, AddressSearchResult[]>>(new Map());
  const lastSearchAtRef = useRef(0);
  const latestSearchIdRef = useRef(0);
  const skipNextSuggestRef = useRef(false);

  const searchLabel = language === 'es' ? 'Buscar direccion o lugar en Venezuela' : 'Search address or place in Venezuela';
  const placeholder = language === 'es' ? 'Calle, edificio, casa, ciudad...' : 'Street, building, house, city...';

  const runSearch = useCallback(async (searchQuery: string, options: AddressSearchOptions = {}) => {
    const normalizedQuery = searchQuery.trim();
    if (normalizedQuery.length < 3) {
      setResults([]);
      setStatus(options.showMinLengthError ? 'error' : 'idle');
      setMessage(options.showMinLengthError ? (language === 'es' ? 'Escribe al menos 3 caracteres.' : 'Enter at least 3 characters.') : '');
      return;
    }

    const cacheKey = `${language}:${normalizedQuery.toLocaleLowerCase('es-VE')}`;
    const cached = cacheRef.current.get(cacheKey);
    if (cached) {
      setResults(cached);
      setStatus(cached.length ? 'ready' : 'empty');
      setMessage(cached.length ? '' : (language === 'es' ? 'Sin resultados en Venezuela.' : 'No Venezuela results found.'));
      return;
    }

    const searchId = ++latestSearchIdRef.current;
    setStatus('loading');
    setMessage('');

    try {
      const elapsed = Date.now() - lastSearchAtRef.current;
      if (elapsed < 1100) await sleep(1100 - elapsed);
      if (options.signal?.aborted || searchId !== latestSearchIdRef.current) return;
      lastSearchAtRef.current = Date.now();

      const params = new URLSearchParams({
        q: normalizedQuery,
        format: 'jsonv2',
        addressdetails: '1',
        namedetails: '1',
        countrycodes: 've',
        viewbox: venezuelaSearchViewbox,
        bounded: '1',
        limit: '7',
        'accept-language': language === 'es' ? 'es,en' : 'en,es'
      });
      const response = await fetch(`https://nominatim.openstreetmap.org/search?${params.toString()}`, {
        headers: {
          Accept: 'application/json'
        },
        signal: options.signal
      });
      if (!response.ok) throw new Error(`Nominatim search failed with ${response.status}`);
      if (options.signal?.aborted || searchId !== latestSearchIdRef.current) return;

      const payload = (await response.json()) as AddressSearchResult[];
      if (options.signal?.aborted || searchId !== latestSearchIdRef.current) return;
      const safeResults = payload
        .filter((result) => Number.isFinite(Number(result.lat)) && Number.isFinite(Number(result.lon)))
        .slice(0, 7);
      cacheRef.current.set(cacheKey, safeResults);
      setResults(safeResults);
      setStatus(safeResults.length ? 'ready' : 'empty');
      setMessage(safeResults.length ? '' : (language === 'es' ? 'Sin resultados en Venezuela.' : 'No Venezuela results found.'));
    } catch (error) {
      if (options.signal?.aborted || (error instanceof DOMException && error.name === 'AbortError')) return;
      setResults([]);
      setStatus('error');
      setMessage(language === 'es' ? 'No se pudo buscar ahora. Intenta de nuevo.' : 'Search is unavailable right now. Try again.');
    }
  }, [language]);

  useEffect(() => {
    if (skipNextSuggestRef.current) {
      skipNextSuggestRef.current = false;
      return undefined;
    }

    const normalizedQuery = query.trim();
    if (normalizedQuery.length < 3) {
      latestSearchIdRef.current += 1;
      setResults([]);
      setStatus('idle');
      setMessage('');
      return undefined;
    }

    const controller = new AbortController();
    const debounce = window.setTimeout(() => {
      void runSearch(normalizedQuery, { signal: controller.signal });
    }, 420);

    return () => {
      window.clearTimeout(debounce);
      controller.abort();
    };
  }, [query, runSearch]);

  const selectResult = useCallback((result: AddressSearchResult) => {
    skipNextSuggestRef.current = true;
    setQuery(addressResultShortLabel(result));
    onSelect(result);
    setStatus('idle');
    setResults([]);
  }, [onSelect]);

  return (
    <form
      className={`address-search ${status === 'ready' ? 'has-results' : ''}`}
      role="search"
      aria-label={searchLabel}
      onSubmit={(event) => {
        event.preventDefault();
        if (results.length) {
          selectResult(results[0]);
          return;
        }
        void runSearch(query, { showMinLengthError: true });
      }}
    >
      <div className="address-search-input-wrap">
        <Search size={16} aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={placeholder}
          title={query}
          aria-label={searchLabel}
          aria-autocomplete="list"
          aria-expanded={results.length > 0}
          aria-controls="address-search-results"
          autoComplete="street-address"
        />
        <button className="address-search-submit" type="submit" disabled={!map || status === 'loading'}>
          {status === 'loading' ? (language === 'es' ? 'Buscando' : 'Searching') : (language === 'es' ? 'Ir' : 'Go')}
        </button>
      </div>
      {message ? <p className="address-search-message">{message}</p> : null}
      {results.length ? (
        <div id="address-search-results" className="address-results" role="listbox" aria-label={language === 'es' ? 'Resultados de direccion' : 'Address results'}>
          {results.map((result) => (
            <button
              key={`${result.osm_type || 'place'}-${result.osm_id || result.place_id}`}
              type="button"
              role="option"
              onClick={() => selectResult(result)}
            >
              <strong>{addressResultShortLabel(result)}</strong>
              <span>{result.display_name}</span>
            </button>
          ))}
          <small>
            {language === 'es'
              ? 'OpenStreetMap/Nominatim'
              : 'OpenStreetMap/Nominatim'}
          </small>
        </div>
      ) : null}
    </form>
  );
}

function AppHeader({
  language,
  setLanguage,
  worstExperienceOpen,
  onToggleWorstExperience,
  ownerToolsEnabled,
  worstAreaPinningActive,
  onToggleWorstAreaPinning,
  onOpenDonationModal,
  c
}: {
  language: Language;
  setLanguage: (language: Language) => void;
  worstExperienceOpen: boolean;
  onToggleWorstExperience: () => void;
  ownerToolsEnabled: boolean;
  worstAreaPinningActive: boolean;
  onToggleWorstAreaPinning: () => void;
  onOpenDonationModal: () => void;
  c: Copy;
}) {
  return (
    <header className="topbar">
      <div className="brand" aria-label="Ayuda Venezuela 2026">
        <div className="brand-mark" aria-hidden="true">
          <span className="flag-stroke yellow" />
          <span className="flag-stroke blue" />
          <span className="flag-stars">
            <span style={{ '--x': '6px', '--y': '7px', '--r': '-18deg' } as CSSProperties} />
            <span style={{ '--x': '10px', '--y': '4px', '--r': '-13deg' } as CSSProperties} />
            <span style={{ '--x': '14px', '--y': '2px', '--r': '-7deg' } as CSSProperties} />
            <span style={{ '--x': '18px', '--y': '1px', '--r': '-2deg' } as CSSProperties} />
            <span style={{ '--x': '22px', '--y': '1px', '--r': '2deg' } as CSSProperties} />
            <span style={{ '--x': '26px', '--y': '2px', '--r': '7deg' } as CSSProperties} />
            <span style={{ '--x': '30px', '--y': '4px', '--r': '13deg' } as CSSProperties} />
            <span style={{ '--x': '34px', '--y': '7px', '--r': '18deg' } as CSSProperties} />
          </span>
          <span className="flag-stroke red" />
        </div>
        <div className="brand-copy">
          <h1>AYUDA</h1>
          <p>VENEZUELA 2026</p>
          <span className="sr-only">Ayuda Venezuela 2026</span>
        </div>
      </div>
      <div className="viewer-title">
        <span>{language === 'es' ? 'Visualizador publico de dano' : 'Public damage visualization'}</span>
          <strong>{language === 'es' ? 'Venezuela: vista nacional' : 'Venezuela nationwide view'}</strong>
      </div>

      <div className="topbar-actions">
        <div className="public-mode-badge">
          <Shield size={15} />
          <span>{language === 'es' ? 'Vista publica' : 'Public view'}</span>
        </div>
        <button
          className={`worst-mode-button ${worstExperienceOpen ? 'active' : ''}`}
          type="button"
          onClick={onToggleWorstExperience}
          aria-pressed={worstExperienceOpen}
          aria-label={language === 'es' ? 'Ver zonas clave afectadas' : 'View key affected areas'}
        >
          <AlertTriangle size={15} />
          <span>{language === 'es' ? 'Zonas clave' : 'Key areas'}</span>
        </button>
        {!worstExperienceOpen ? (
          <button
            className="compare-nudge-button"
            type="button"
            onClick={onToggleWorstExperience}
            aria-label={language === 'es' ? 'Ver y comparar zonas afectadas' : 'View and compare affected areas'}
          >
            <span>{language === 'es' ? 'Ver y comparar' : 'View & compare'}</span>
            <ChevronRight size={13} />
          </button>
        ) : null}
        {ownerToolsEnabled ? (
          <button
            className={`area-pin-button ${worstAreaPinningActive ? 'active' : ''}`}
            type="button"
            onClick={onToggleWorstAreaPinning}
            aria-pressed={worstAreaPinningActive}
            aria-label={language === 'es' ? 'Fijar tres zonas clave afectadas' : 'Pin three key affected areas'}
          >
            <MapPin size={15} />
            <span>{language === 'es' ? 'Fijar' : 'Key pins'}</span>
          </button>
        ) : null}
        <button
          className="donation-help-button"
          type="button"
          onClick={onOpenDonationModal}
          aria-label={language === 'es' ? 'Abrir opciones de ayuda y donacion' : 'Open help and donation options'}
        >
          <CircleHelp size={15} />
          <span>{language === 'es' ? 'Ayuda' : 'Help'}</span>
        </button>
        <div className="language-switch" aria-label="Language selector">
          <button className={language === 'en' ? 'active' : ''} onClick={() => setLanguage('en')} type="button">
            <span aria-hidden="true">🇬🇧</span>
            English
          </button>
          <button className={language === 'es' ? 'active' : ''} onClick={() => setLanguage('es')} type="button">
            <span aria-hidden="true">🇻🇪</span>
            ES
          </button>
        </div>
      </div>
    </header>
  );
}

function DonationModal({
  language,
  onClose
}: {
  language: Language;
  onClose: () => void;
}) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div className="donation-modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section
        className="donation-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="donation-modal-title"
      >
        <div className="donation-modal-header">
          <div>
            <h2 id="donation-modal-title">{language === 'es' ? 'Dona directamente' : 'Donate directly'}</h2>
          </div>
          <button
            className="donation-modal-close"
            type="button"
            onClick={onClose}
            aria-label={language === 'es' ? 'Cerrar opciones de donacion' : 'Close donation options'}
          >
            <X size={18} />
          </button>
        </div>
        <div className="donation-link-list">
          {donationLinks.map((link) => (
            <a key={link.url} href={link.url} target="_blank" rel="noreferrer" className="donation-link-card">
              <span className="donation-org-logo">
                <img src={link.logoSrc} alt={link.logoAlt} />
              </span>
              <span>
                <strong>{link.name}</strong>
                <small>{link.tag[language]}</small>
              </span>
              <ExternalLink size={17} aria-hidden="true" />
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}

function Sidebar({
  damageLayerVisible,
  setDamageLayerVisible,
  superResolutionVisible,
  setSuperResolutionVisible,
  srIndex,
  comparisonVisible,
  setComparisonVisible,
  comparisonAvailable,
  hasSearchedAddress,
  damageViewport,
  trustedData,
  language,
  c
}: {
  damageLayerVisible: boolean;
  setDamageLayerVisible: (value: boolean) => void;
  superResolutionVisible: boolean;
  setSuperResolutionVisible: (value: boolean) => void;
  srIndex: SuperResolutionIndex | null;
  comparisonVisible: boolean;
  setComparisonVisible: (value: boolean) => void;
  comparisonAvailable: boolean;
  hasSearchedAddress: boolean;
  damageViewport: DamageViewportState;
  trustedData: TrustedDataSnapshot | null;
  language: Language;
  c: Copy;
}) {
  const damageFootprints = damageViewport.summary.total.toLocaleString();
  const highDamage = damageViewport.summary.high.toLocaleString();

  return (
    <aside className="sidebar">
      <section className="sidebar-section impact-summary-panel">
        <div className="section-title">
          <span>{language === 'es' ? 'Dano verificado' : 'Verified damage'}</span>
          <MapPin size={15} />
        </div>
        <div className="focus-area-card impact">
          <span>{damageViewport.isIndexed ? (language === 'es' ? 'Vista actual' : 'Current view') : (language === 'es' ? 'Vista inicial' : 'Initial view')}</span>
          <strong>{damageViewport.areaTitle}</strong>
          <em>{damageViewport.coordinateText}</em>
          <small>{language === 'es' ? 'Huellas Microsoft/HDX verificadas' : 'Verified Microsoft/HDX footprints'}</small>
        </div>
        <div className="impact-stats">
          <div><strong>{damageFootprints}</strong><span>{c.damageFootprints}</span></div>
          <div><strong>{highDamage}</strong><span>{language === 'es' ? 'alto dano' : 'high damage'}</span></div>
        </div>
      </section>

      <TrustedDataPanel trustedData={trustedData} language={language} c={c} />

      <MapLayerControls
        damageLayerVisible={damageLayerVisible}
        setDamageLayerVisible={setDamageLayerVisible}
        superResolutionVisible={superResolutionVisible}
        setSuperResolutionVisible={setSuperResolutionVisible}
        srIndex={srIndex}
        comparisonVisible={comparisonVisible}
        setComparisonVisible={setComparisonVisible}
        comparisonAvailable={comparisonAvailable}
        hasSearchedAddress={hasSearchedAddress}
        language={language}
        c={c}
      />

    </aside>
  );
}

function OpsMap({
  damageLayerVisible,
  setDamageLayerVisible,
  superResolutionVisible,
  setSuperResolutionVisible,
  srIndex,
  comparisonVisible,
  setComparisonVisible,
  comparisonAvailable,
  addressSearchResult,
  setAddressSearchResult,
  worstDamageHotspots,
  worstExperienceOpen,
  activeWorstIndex,
  activeWorstHotspot,
  onWorstHotspotSelect,
  onWorstHotspotIndexSelect,
  onWorstExperienceClose,
  ownerToolsEnabled,
  worstAreaPinningActive,
  worstAreaPins,
  onWorstAreaPinAdd,
  onWorstAreaPinRemove,
  onWorstAreaPinsClear,
  onWorstAreaPinningClose,
  damageViewport,
  setDamageViewport,
  language,
  c
}: {
  damageLayerVisible: boolean;
  setDamageLayerVisible: (value: boolean) => void;
  superResolutionVisible: boolean;
  setSuperResolutionVisible: (value: boolean) => void;
  srIndex: SuperResolutionIndex | null;
  comparisonVisible: boolean;
  setComparisonVisible: (value: boolean) => void;
  comparisonAvailable: boolean;
  addressSearchResult: AddressSearchResult | null;
  setAddressSearchResult: (result: AddressSearchResult | null) => void;
  worstDamageHotspots: WorstDamageHotspot[];
  worstExperienceOpen: boolean;
  activeWorstIndex: number;
  activeWorstHotspot: WorstDamageHotspot;
  onWorstHotspotSelect: (hotspot: WorstDamageHotspot) => void;
  onWorstHotspotIndexSelect: (index: number) => void;
  onWorstExperienceClose: () => void;
  ownerToolsEnabled: boolean;
  worstAreaPinningActive: boolean;
  worstAreaPins: WorstAreaPin[];
  onWorstAreaPinAdd: (latlng: L.LatLng) => void;
  onWorstAreaPinRemove: (index: number) => void;
  onWorstAreaPinsClear: () => void;
  onWorstAreaPinningClose: () => void;
  damageViewport: DamageViewportState;
  setDamageViewport: (state: DamageViewportState) => void;
  language: Language;
  c: Copy;
}) {
  const [mobileMapControlsOpen, setMobileMapControlsOpen] = useState(false);
  const [mapFocusTick, setMapFocusTick] = useState(0);
  const [comparisonSplit, setComparisonSplit] = useState(50);
  const [mapInstance, setMapInstance] = useState<L.Map | null>(null);
  const [currentZoom, setCurrentZoom] = useState(mapZoom);
  const [viewportIntersectsComparisonBounds, setViewportIntersectsComparisonBounds] = useState(false);
  const [visibleNamedLabelCount, setVisibleNamedLabelCount] = useState(0);
  const mapShellRef = useRef<HTMLElement | null>(null);
  const focusedResultIdRef = useRef<number | null>(null);
  const comparisonRendered = comparisonVisible && comparisonAvailable;
  const effectiveWorstAreaPinningActive = ownerToolsEnabled && worstAreaPinningActive;
  const setMobileComparisonVisible = useCallback((value: boolean) => {
    if (value && !comparisonAvailable) return;
    setComparisonVisible(value);
    if (value) setMobileMapControlsOpen(false);
  }, [comparisonAvailable, setComparisonVisible]);
  const setMobileDamageLayerVisible = useCallback((value: boolean) => {
    setDamageLayerVisible(value);
    setMobileMapControlsOpen(false);
  }, [setDamageLayerVisible]);
  const setMobileSuperResolutionVisible = useCallback((value: boolean) => {
    setSuperResolutionVisible(value);
    if (value) setMobileMapControlsOpen(false);
  }, [setSuperResolutionVisible]);
  const setReadyMap = useCallback((map: L.Map | null) => {
    setMapInstance(map);
    if (map) setCurrentZoom(map.getZoom());
  }, []);
  const handleAddressSelect = useCallback((result: AddressSearchResult) => {
    const [lat, lng] = addressResultCoordinate(result);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    const supportsComparison = addressSupportsComparison(result);

    setAddressSearchResult(result);
    setComparisonVisible(supportsComparison);
    onWorstExperienceClose();
    onWorstAreaPinningClose();
    setMobileMapControlsOpen(false);

    if (!mapInstance) return;
    focusMapOnAddress(mapInstance, result, true, focusZoomForResult(result));
  }, [mapInstance, onWorstAreaPinningClose, onWorstExperienceClose, setAddressSearchResult, setComparisonVisible]);
  const handleWorstHotspotSelect = useCallback((hotspot: WorstDamageHotspot) => {
    onWorstHotspotSelect(hotspot);
    setMobileMapControlsOpen(false);
  }, [onWorstHotspotSelect]);

  useEffect(() => {
    if (!mapInstance || !addressSearchResult || worstExperienceOpen) return undefined;
    if (focusedResultIdRef.current === addressSearchResult.place_id) return;

    const focusAddress = () => {
      mapInstance.invalidateSize({ pan: false });
      focusedResultIdRef.current = addressSearchResult.place_id;
      focusMapOnAddress(
        mapInstance,
        addressSearchResult,
        true,
        focusZoomForResult(addressSearchResult)
      );
    };
    const frame = window.requestAnimationFrame(focusAddress);
    const timeout = window.setTimeout(focusAddress, 180);

    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timeout);
    };
  }, [addressSearchResult, mapInstance, worstExperienceOpen]);

  useEffect(() => {
    if (!mapInstance || !worstExperienceOpen) return undefined;

    const result = hotspotToAddressResult(activeWorstHotspot);
    const focusHotspot = () => {
      mapInstance.invalidateSize({ pan: false });
      focusedResultIdRef.current = result.place_id;
      focusMapOnAddress(mapInstance, result, false, worstComparisonFocusZoom);
    };
    const frame = window.requestAnimationFrame(focusHotspot);
    const timeout = window.setTimeout(focusHotspot, 180);

    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timeout);
    };
  }, [activeWorstHotspot, mapInstance, worstExperienceOpen]);
  useEffect(() => {
    const records = srIndex?.records || [];
    if (!mapInstance || !superResolutionVisible || !records.length) return;

    const bounds = L.latLngBounds(records.map((record) => [record.lat, record.lon] as [number, number]));
    mapInstance.flyToBounds(bounds.pad(0.3), {
      duration: 0.65,
      maxZoom: 16,
      padding: [44, 44]
    });
  }, [mapInstance, srIndex, superResolutionVisible]);
  useEffect(() => {
    if (!mapInstance) return undefined;

    const updateZoom = () => setCurrentZoom(mapInstance.getZoom());
    updateZoom();
    mapInstance.on('zoomend zoomlevelschange', updateZoom);
    return () => {
      mapInstance.off('zoomend zoomlevelschange', updateZoom);
    };
  }, [mapInstance]);

  const viewportHighResolutionAvailable = viewportIntersectsComparisonBounds && currentZoom >= nationalMaxUsefulZoom;
  const highResolutionFocusVisible = Boolean(
    !comparisonRendered &&
      ((addressSearchResult && comparisonAvailable) || viewportHighResolutionAvailable)
  );
  const highResolutionMapActive = comparisonRendered || highResolutionFocusVisible || damageLayerVisible || worstExperienceOpen || effectiveWorstAreaPinningActive;
  const namedLabelsVisible = highResolutionMapActive && currentZoom >= 18;
  const namedLabelsRendered = visibleNamedLabelCount > 0;
  const minimumZoomForMode = mapZoom;
  const highResolutionZoomAvailable = comparisonRendered || highResolutionFocusVisible || viewportIntersectsComparisonBounds || worstExperienceOpen || effectiveWorstAreaPinningActive;
  const maximumZoomForMode = highResolutionZoomAvailable
    ? maxMapZoom
    : damageLayerVisible
      ? damageMaxUsefulZoom
      : nationalMaxUsefulZoom;
  const canZoomIn = Boolean(mapInstance) && currentZoom < maximumZoomForMode;
  const canZoomOut = Boolean(mapInstance) && currentZoom > minimumZoomForMode;
  const zoomInMap = useCallback(() => {
    if (!mapInstance) return;
    mapInstance.setZoom(Math.min(maximumZoomForMode, mapInstance.getZoom() + 1));
  }, [mapInstance, maximumZoomForMode]);
  const zoomOutMap = useCallback(() => {
    if (!mapInstance) return;
    mapInstance.setZoom(Math.max(minimumZoomForMode, mapInstance.getZoom() - 1));
  }, [mapInstance, minimumZoomForMode]);

  const damageStatusText =
    damageLayerVisible
      ? `${damageViewport.summary.total.toLocaleString()} ${c.damageFootprints}`
      : c.damageLayerOff;
  const superResolutionRendered = superResolutionVisible && !worstExperienceOpen && Boolean(srIndex?.records?.length);
  const activeLayerCount =
    (damageLayerVisible ? 1 : 0) +
    (comparisonRendered ? 1 : 0) +
    (superResolutionRendered ? 1 : 0) +
    (namedLabelsRendered ? 1 : 0);

  return (
    <main
      ref={mapShellRef}
      className={`map-shell ${comparisonRendered ? 'comparison-active' : ''} ${worstExperienceOpen ? 'worst-experience-active' : ''}`}
    >
      <div className="map-toolbar">
        <AddressSearchControl
          language={language}
          map={mapInstance}
          onSelect={handleAddressSelect}
        />
        <div className="map-tool-cluster" aria-label={language === 'es' ? 'Herramientas de mapa' : 'Map tools'}>
          <button
            className="icon-button recenter-button"
            type="button"
            aria-label={
              addressSearchResult
                ? (language === 'es' ? 'Centrar direccion buscada' : 'Center searched address')
                : (language === 'es' ? 'Centrar vista nacional' : 'Center national view')
            }
            onClick={() => setMapFocusTick((tick) => tick + 1)}
          >
            <Crosshair size={17} />
          </button>
          <button
            className="icon-button"
            type="button"
            aria-label={language === 'es' ? 'Acercar mapa' : 'Zoom in map'}
            onClick={zoomInMap}
            disabled={!canZoomIn}
          >
            <Plus size={17} />
          </button>
          <button
            className="icon-button"
            type="button"
            aria-label={language === 'es' ? 'Alejar mapa' : 'Zoom out map'}
            onClick={zoomOutMap}
            disabled={!canZoomOut}
          >
            <Minus size={17} />
          </button>
          <button
            className={`icon-button map-controls-button ${mobileMapControlsOpen ? 'active' : ''}`}
            onClick={() => setMobileMapControlsOpen((open) => !open)}
            type="button"
            aria-expanded={mobileMapControlsOpen}
            aria-controls="mobile-map-controls"
            aria-label={c.mapLayers}
          >
            <Layers size={17} />
          </button>
        </div>
      </div>
      <div
        id="mobile-map-controls"
        className={`mobile-map-controls ${mobileMapControlsOpen ? 'open' : ''}`}
      >
        <MapLayerControls
          damageLayerVisible={damageLayerVisible}
          setDamageLayerVisible={setMobileDamageLayerVisible}
          superResolutionVisible={superResolutionVisible}
          setSuperResolutionVisible={setMobileSuperResolutionVisible}
          srIndex={srIndex}
          comparisonVisible={comparisonRendered}
          setComparisonVisible={setMobileComparisonVisible}
          comparisonAvailable={comparisonAvailable}
          hasSearchedAddress={Boolean(addressSearchResult)}
          language={language}
          c={c}
        />
      </div>
      <MapContainer
        center={mapCenter}
        zoom={mapZoom}
        minZoom={6}
        maxZoom={maxMapZoom}
        maxBounds={explorationBounds}
        maxBoundsViscosity={0.45}
        className="map-canvas"
        scrollWheelZoom
        doubleClickZoom
        touchZoom
        boxZoom
        zoomControl={false}
        fadeAnimation={false}
        preferCanvas
      >
        <MapHandle onReady={setReadyMap} />
        <MapSizeInvalidator />
        <MapZoomBounds maxZoom={maximumZoomForMode} />
        <MapViewportReporter onComparisonIntersectionChange={setViewportIntersectsComparisonBounds} />
        <MapViewDataAttributes targetRef={mapShellRef} />
        <MapRecenter tick={mapFocusTick} addressResult={addressSearchResult} />
        <DamageViewportReporter language={language} onChange={setDamageViewport} />
        <OpenNationalImageryLayer highResolutionVisible={highResolutionMapActive} />
        <NamedPlaceLabelsLayer
          visible={namedLabelsVisible}
          language={language}
          addressSearchResult={addressSearchResult}
          onVisibleCountChange={setVisibleNamedLabelCount}
        />
        <SuperResolutionMarkers visible={superResolutionRendered} srIndex={srIndex} language={language} />
        <AddressSearchMarker result={addressSearchResult} />
        {ownerToolsEnabled ? (
          <WorstAreaPinCaptureLayer
            active={effectiveWorstAreaPinningActive}
            pins={worstAreaPins}
            onAddPin={onWorstAreaPinAdd}
          />
        ) : null}
        {worstExperienceOpen ? (
          <WorstHotspotMarkers
            hotspots={worstDamageHotspots}
            selectedId={activeWorstHotspot.id}
            onSelect={handleWorstHotspotSelect}
            language={language}
          />
        ) : null}
        {comparisonRendered ? (
          <SatelliteBeforeAfterLayer
            damageLayerVisible={damageLayerVisible}
            split={comparisonSplit}
            preferEnhancedOnly={false}
          />
        ) : null}
        {highResolutionFocusVisible ? <HighResolutionFocusLayer /> : null}
        {damageLayerVisible && !comparisonRendered ? <DamageRasterLayer /> : null}
      </MapContainer>
      {comparisonRendered ? (
        <SatelliteComparisonControls
          split={comparisonSplit}
          onSplitChange={setComparisonSplit}
          language={language}
        />
      ) : null}
      {damageLayerVisible && !worstExperienceOpen ? (
        <DamageLayerLegend
          status="ready"
          summary={damageViewport.summary}
          c={c}
        />
      ) : null}
      {superResolutionRendered && srIndex ? (
        <SuperResolutionReviewPanel
          srIndex={srIndex}
          onClose={() => setSuperResolutionVisible(false)}
          language={language}
        />
      ) : null}
      {worstExperienceOpen ? (
        <WorstHotspotExperience
          hotspots={worstDamageHotspots}
          activeHotspot={activeWorstHotspot}
          activeIndex={activeWorstIndex}
          damageLayerVisible={damageLayerVisible}
          onDamageLayerToggle={() => setDamageLayerVisible(!damageLayerVisible)}
          onSelectIndex={onWorstHotspotIndexSelect}
          onClose={onWorstExperienceClose}
          language={language}
        />
      ) : null}
      {effectiveWorstAreaPinningActive ? (
        <WorstAreaPinningPanel
          pins={worstAreaPins}
          onRemovePin={onWorstAreaPinRemove}
          onClearPins={onWorstAreaPinsClear}
          onClose={onWorstAreaPinningClose}
          language={language}
        />
      ) : null}
      {!worstExperienceOpen ? (
        <div className="map-status">
          <span><span className="live-dot" /> {language === 'es' ? 'Vivo' : 'Live'}</span>
          <span>{highResolutionFocusVisible || comparisonRendered ? 'Vantor' : 'Sentinel-2'}</span>
          {addressSearchResult ? (
            <span>
              {addressResultShortLabel(addressSearchResult)}
            </span>
          ) : null}
          {damageLayerVisible ? <span>{language === 'es' ? 'Dano' : 'Damage'}</span> : null}
          {superResolutionRendered ? <span>SR</span> : null}
          {namedLabelsRendered ? <span>{language === 'es' ? 'Nombres OSM' : 'OSM names'}</span> : null}
          <span>
            {comparisonRendered
              ? (language === 'es' ? 'Comparando' : 'Compare')
              : (language === 'es' ? 'Actual' : 'Current')}
          </span>
          <span>{activeLayerCount}</span>
        </div>
      ) : null}
    </main>
  );
}

export function App() {
  const embeddedXWebView = typeof navigator !== 'undefined' && /\bTwitter\b|XWebView|XTwitter/i.test(navigator.userAgent);
  const [language, setLanguage] = useState<Language>('en');
  const [damageLayerVisible, setDamageLayerVisible] = useState(false);
  const [superResolutionVisible, setSuperResolutionVisible] = useState(false);
  const [comparisonVisible, setComparisonVisible] = useState(false);
  const [addressSearchResult, setAddressSearchResult] = useState<AddressSearchResult | null>(null);
  const [worstExperienceOpen, setWorstExperienceOpen] = useState(false);
  const [worstAreaPinningActive, setWorstAreaPinningActive] = useState(false);
  const [worstAreaPins, setWorstAreaPins] = useState<WorstAreaPin[]>([]);
  const [donationModalOpen, setDonationModalOpen] = useState(false);
  const [activeWorstIndex, setActiveWorstIndex] = useState(0);
  const [damageViewport, setDamageViewport] = useState<DamageViewportState>(() => initialDamageViewport('es'));
  const [trustedData, setTrustedData] = useState<TrustedDataSnapshot | null>(null);
  const [srIndex, setSrIndex] = useState<SuperResolutionIndex | null>(null);
  const [worstDamageHotspots, setWorstDamageHotspots] = useState<WorstDamageHotspot[]>(defaultWorstDamageHotspots);
  const activeWorstHotspot = worstDamageHotspots[activeWorstIndex] || worstDamageHotspots[0] || defaultWorstDamageHotspots[0];
  const comparisonAvailable = addressSupportsComparison(addressSearchResult);
  const c = copy[language];

  const setSuperResolutionMode = useCallback((value: boolean) => {
    setSuperResolutionVisible(value);
    if (value) {
      setWorstExperienceOpen(false);
      setWorstAreaPinningActive(false);
    }
  }, []);

  const selectWorstHotspot = useCallback((hotspot: WorstDamageHotspot) => {
    const nextIndex = worstDamageHotspots.findIndex((item) => item.id === hotspot.id);
    setActiveWorstIndex(nextIndex >= 0 ? nextIndex : 0);
    setWorstExperienceOpen(true);
    setWorstAreaPinningActive(false);
    setAddressSearchResult(hotspotToAddressResult(hotspot));
    setDamageLayerVisible(false);
    setSuperResolutionVisible(false);
    setComparisonVisible(true);
  }, [worstDamageHotspots]);

  const selectWorstHotspotIndex = useCallback((index: number) => {
    if (!worstDamageHotspots.length) return;
    const normalizedIndex = (index + worstDamageHotspots.length) % worstDamageHotspots.length;
    selectWorstHotspot(worstDamageHotspots[normalizedIndex]);
  }, [selectWorstHotspot, worstDamageHotspots]);

  const toggleWorstExperience = useCallback(() => {
    if (worstExperienceOpen) {
      setWorstExperienceOpen(false);
      return;
    }
    setWorstAreaPinningActive(false);
    selectWorstHotspot(worstDamageHotspots[activeWorstIndex] || worstDamageHotspots[0] || defaultWorstDamageHotspots[0]);
  }, [activeWorstIndex, selectWorstHotspot, worstDamageHotspots, worstExperienceOpen]);

  const toggleWorstAreaPinning = useCallback(() => {
    if (!ownerToolsEnabled) return;
    setWorstAreaPinningActive((active) => {
      const nextActive = !active;
      if (nextActive) {
        setWorstExperienceOpen(false);
        setSuperResolutionVisible(false);
        setDamageLayerVisible(false);
        setAddressSearchResult(worstAreaPinningAddressResult);
        setComparisonVisible(true);
      }
      return nextActive;
    });
  }, []);

  const addWorstAreaPin = useCallback((latlng: L.LatLng) => {
    setWorstAreaPins((pins) => {
      if (pins.length >= 3) return pins;
      return [
        ...pins,
        {
          rank: pins.length + 1,
          lat: Number(formatPinnedCoordinate(latlng.lat)),
          lng: Number(formatPinnedCoordinate(latlng.lng))
        }
      ];
    });
  }, []);

  const removeWorstAreaPin = useCallback((index: number) => {
    setWorstAreaPins((pins) => pins
      .filter((_, pinIndex) => pinIndex !== index)
      .map((pin, pinIndex) => ({ ...pin, rank: pinIndex + 1 })));
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchTrustedDataSnapshot().then((snapshot) => {
      if (!cancelled) setTrustedData(snapshot);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchSuperResolutionIndex()
      .then((index) => {
        if (!cancelled) setSrIndex(index);
      })
      .catch(() => {
        if (!cancelled) setSrIndex(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchWorstDamageHotspots()
      .then((hotspots) => {
        if (!cancelled) {
          setWorstDamageHotspots(hotspots);
          setActiveWorstIndex((index) => Math.min(index, Math.max(0, hotspots.length - 1)));
        }
      })
      .catch(() => {
        if (!cancelled) setWorstDamageHotspots(defaultWorstDamageHotspots);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!worstExperienceOpen && !worstAreaPinningActive) return;
    void loadEnhancedTileManifest().then(() => {
      preloadEnhancedHotspotTiles(worstDamageHotspots);
    });
  }, [worstAreaPinningActive, worstDamageHotspots, worstExperienceOpen]);

  return (
    <div
      className="app"
      data-active-panel="map"
      data-worst-experience={worstExperienceOpen ? 'true' : 'false'}
      data-x-webview={embeddedXWebView ? 'true' : 'false'}
    >
      <AppHeader
        language={language}
        setLanguage={setLanguage}
        worstExperienceOpen={worstExperienceOpen}
        onToggleWorstExperience={toggleWorstExperience}
        ownerToolsEnabled={ownerToolsEnabled}
        worstAreaPinningActive={worstAreaPinningActive}
        onToggleWorstAreaPinning={toggleWorstAreaPinning}
        onOpenDonationModal={() => setDonationModalOpen(true)}
        c={c}
      />
      <div className="workspace">
        <Sidebar
          damageLayerVisible={damageLayerVisible}
          setDamageLayerVisible={setDamageLayerVisible}
          superResolutionVisible={superResolutionVisible}
          setSuperResolutionVisible={setSuperResolutionMode}
          srIndex={srIndex}
          comparisonVisible={comparisonVisible && comparisonAvailable}
          setComparisonVisible={setComparisonVisible}
          comparisonAvailable={comparisonAvailable}
          hasSearchedAddress={Boolean(addressSearchResult)}
          damageViewport={damageViewport}
          trustedData={trustedData}
          language={language}
          c={c}
        />
        <OpsMap
          damageLayerVisible={damageLayerVisible}
          setDamageLayerVisible={setDamageLayerVisible}
          superResolutionVisible={superResolutionVisible}
          setSuperResolutionVisible={setSuperResolutionMode}
          srIndex={srIndex}
          comparisonVisible={comparisonVisible}
          setComparisonVisible={setComparisonVisible}
          comparisonAvailable={comparisonAvailable}
          addressSearchResult={addressSearchResult}
          setAddressSearchResult={setAddressSearchResult}
          worstDamageHotspots={worstDamageHotspots}
          worstExperienceOpen={worstExperienceOpen}
          activeWorstIndex={activeWorstIndex}
          activeWorstHotspot={activeWorstHotspot}
          onWorstHotspotSelect={selectWorstHotspot}
          onWorstHotspotIndexSelect={selectWorstHotspotIndex}
          onWorstExperienceClose={() => setWorstExperienceOpen(false)}
          ownerToolsEnabled={ownerToolsEnabled}
          worstAreaPinningActive={worstAreaPinningActive}
          worstAreaPins={worstAreaPins}
          onWorstAreaPinAdd={addWorstAreaPin}
          onWorstAreaPinRemove={removeWorstAreaPin}
          onWorstAreaPinsClear={() => setWorstAreaPins([])}
          onWorstAreaPinningClose={() => setWorstAreaPinningActive(false)}
          damageViewport={damageViewport}
          setDamageViewport={setDamageViewport}
          language={language}
          c={c}
        />
      </div>
      {donationModalOpen ? (
        <DonationModal language={language} onClose={() => setDonationModalOpen(false)} />
      ) : null}
      <footer className="footer">
        <span><Phone size={14} /> {c.footerChannels}</span>
        <span><Shield size={14} /> {c.footerPrivacy}</span>
        <span><CircleHelp size={14} /> {c.footerProxy}</span>
        <span><Clock size={14} /> {c.footerSync}</span>
      </footer>
    </div>
  );
}
