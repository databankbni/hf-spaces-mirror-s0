import type { DamageSeverity } from '../data/microsoftDamageData';
import type { Language } from './language';

export type DamageViewportSummary = { total: number } & Record<DamageSeverity, number>;

export interface DamageViewportState {
  summary: DamageViewportSummary;
  areaTitle: string;
  description: string;
  coordinateText: string;
  isIndexed: boolean;
}

type DamagePoint = [number, number, 0 | 1 | 2 | 3];

interface DamageViewIndex {
  schemaVersion: number;
  total: number;
  bounds?: DamageBounds;
  points: DamagePoint[];
}

export interface DamageBounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

const severityByCode: Record<DamagePoint[2], DamageSeverity> = {
  0: 'high',
  1: 'moderate',
  2: 'observed',
  3: 'uncertain'
};

export const fullDamageSummary: DamageViewportSummary = {
  total: 9128,
  high: 4274,
  moderate: 1459,
  observed: 3300,
  uncertain: 95
};

const emptyDamageSummary: DamageViewportSummary = {
  total: 0,
  high: 0,
  moderate: 0,
  observed: 0,
  uncertain: 0
};

const nationalCoverageCenter = { lat: 7.2, lng: -66.2 };

let damageIndexPromise: Promise<DamageViewIndex> | null = null;

function fetchDamageViewIndex() {
  if (!damageIndexPromise) {
    damageIndexPromise = fetch('/data/damage-view-index.json')
      .then((response) => {
        if (!response.ok) throw new Error(`Damage view index failed with ${response.status}`);
        return response.json() as Promise<DamageViewIndex>;
      })
      .catch((error: unknown) => {
        damageIndexPromise = null;
        throw error;
      });
  }
  return damageIndexPromise;
}

function formatCoordinate(lat: number, lng: number) {
  return `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
}

function isInsideBounds(bounds: DamageBounds | undefined, point: { lat: number; lng: number }) {
  return Boolean(
    bounds &&
      point.lng >= bounds.west &&
      point.lng <= bounds.east &&
      point.lat >= bounds.south &&
      point.lat <= bounds.north
  );
}

function doBoundsIntersect(source: DamageBounds | undefined, viewport: DamageBounds) {
  return Boolean(
    source &&
      viewport.east >= source.west &&
      viewport.west <= source.east &&
      viewport.north >= source.south &&
      viewport.south <= source.north
  );
}

function nationalAreaLabel(center: { lat: number; lng: number }, language: Language) {
  if (center.lat < 7.5) {
    return language === 'es' ? 'Venezuela sur / Guayana' : 'Southern Venezuela / Guayana';
  }

  if (center.lng <= -70.2) {
    return language === 'es' ? 'Venezuela occidental' : 'Western Venezuela';
  }

  if (center.lng <= -68.2) {
    return language === 'es' ? 'Venezuela centro-occidental' : 'Central-western Venezuela';
  }

  if (center.lng <= -66.0) {
    return language === 'es' ? 'Venezuela norte-central' : 'North-central Venezuela';
  }

  return language === 'es' ? 'Venezuela oriental' : 'Eastern Venezuela';
}

function areaLabel(lat: number, lng: number, language: Language, isMicrosoftCoverage: boolean) {
  if (!isMicrosoftCoverage) return nationalAreaLabel({ lat, lng }, language);

  if (lng <= -67.065) {
    return language === 'es' ? 'Catia La Mar oeste, La Guaira' : 'West Catia La Mar, La Guaira';
  }

  if (lng <= -67.043) {
    return language === 'es' ? 'Catia La Mar centro-oeste, La Guaira' : 'Central-west Catia La Mar, La Guaira';
  }

  if (lng <= -67.026) {
    return language === 'es' ? 'Catia La Mar centro, La Guaira' : 'Central Catia La Mar, La Guaira';
  }

  return language === 'es' ? 'Playa Grande / Catia La Mar este' : 'Playa Grande / East Catia La Mar';
}

function isBroadNationalViewport(bounds: DamageBounds) {
  return bounds.east - bounds.west > 5 || bounds.north - bounds.south > 4;
}

function describeSummary(
  summary: DamageViewportSummary,
  coordinateText: string,
  language: Language,
  isNearestFallback: boolean,
  isMicrosoftCoverage: boolean
) {
  if (!isMicrosoftCoverage) {
    return language === 'es'
      ? `Vista nacional: ${coordinateText}. No hay huellas Microsoft/HDX verificadas en este encuadre; valida con informacion local.`
      : `National view: ${coordinateText}. No verified Microsoft/HDX footprints are in this frame; validate with local information.`;
  }

  if (summary.total === 0) {
    return language === 'es'
      ? `Punto verificado mas cercano: ${coordinateText}. No hay huellas afectadas visibles en este encuadre.`
      : `Nearest verified point: ${coordinateText}. No affected footprints are visible in this view.`;
  }

  if (isNearestFallback) {
    return language === 'es'
      ? `Punto verificado mas cercano: ${coordinateText}. Las cifras se recalculan al volver sobre la huella visible.`
      : `Nearest verified point: ${coordinateText}. Counts recalculate when the view returns over visible footprints.`;
  }

  return language === 'es'
    ? `Centro de huellas visibles: ${coordinateText}. Las cifras usan solo edificios dentro del encuadre.`
    : `Visible-footprint center: ${coordinateText}. Counts use only buildings inside the current view.`;
}

export async function summarizeDamageViewport(
  bounds: DamageBounds,
  center: { lat: number; lng: number },
  language: Language
): Promise<DamageViewportState> {
  const index = await fetchDamageViewIndex();
  const summary = { ...emptyDamageSummary };
  const centerInsideMicrosoftCoverage = isInsideBounds(index.bounds, center);
  const focalPoint = { lat: 0, lng: 0 };
  let nearestPoint: { lat: number; lng: number } | null = null;
  let nearestDistance = Infinity;

  for (const [lng, lat, severityCode] of index.points) {
    const distance = (lat - center.lat) ** 2 + (lng - center.lng) ** 2;
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestPoint = { lat, lng };
    }

    if (lng >= bounds.west && lng <= bounds.east && lat >= bounds.south && lat <= bounds.north) {
      summary.total += 1;
      summary[severityByCode[severityCode]] += 1;
      focalPoint.lat += lat;
      focalPoint.lng += lng;
    }
  }

  const isMicrosoftCoverage =
    summary.total > 0 ||
    centerInsideMicrosoftCoverage ||
    doBoundsIntersect(index.bounds, bounds);
  let isNearestFallback = false;
  if (summary.total) {
    focalPoint.lat /= summary.total;
    focalPoint.lng /= summary.total;
  } else if (isMicrosoftCoverage && nearestPoint) {
    focalPoint.lat = nearestPoint.lat;
    focalPoint.lng = nearestPoint.lng;
    isNearestFallback = true;
  } else {
    focalPoint.lat = center.lat;
    focalPoint.lng = center.lng;
  }

  const coordinateText = formatCoordinate(focalPoint.lat, focalPoint.lng);
  const broadNational = isBroadNationalViewport(bounds);

  return {
    summary,
    areaTitle:
      broadNational
        ? (language === 'es' ? 'Venezuela: vista nacional' : 'Venezuela: national view')
        : areaLabel(focalPoint.lat, focalPoint.lng, language, isMicrosoftCoverage),
    description: broadNational
      ? (language === 'es'
          ? `Vista nacional: ${coordinateText}. Las cifras de edificios son huellas verificadas Microsoft/HDX disponibles, no toda el area afectada.`
          : `National view: ${coordinateText}. Building counts are available verified Microsoft/HDX footprints, not the full affected area.`)
      : describeSummary(summary, coordinateText, language, isNearestFallback, isMicrosoftCoverage),
    coordinateText,
    isIndexed: true
  };
}

export function initialDamageViewport(language: Language): DamageViewportState {
  return {
    summary: fullDamageSummary,
    areaTitle: language === 'es' ? 'Venezuela: vista nacional' : 'Venezuela: national view',
    description:
      language === 'es'
        ? `Vista inicial nacional: ${formatCoordinate(nationalCoverageCenter.lat, nationalCoverageCenter.lng)}. Las cifras de edificios son huellas verificadas Microsoft/HDX disponibles, no toda el area afectada.`
        : `Initial national view: ${formatCoordinate(nationalCoverageCenter.lat, nationalCoverageCenter.lng)}. Building counts are available verified Microsoft/HDX footprints, not the full affected area.`,
    coordinateText: formatCoordinate(nationalCoverageCenter.lat, nationalCoverageCenter.lng),
    isIndexed: false
  };
}
