export type TrustedSourceStatus = 'ok' | 'error' | 'manual_review';
export type TrustedSourceTier = 'reference' | 'hazard' | 'logistics' | 'situation';

export interface TrustedSourceSnapshot {
  id: string;
  name: string;
  owner: string;
  tier: TrustedSourceTier;
  kind: string;
  visibility: string;
  recommendedUse: string;
  licenseReview: string;
  url: string;
  refreshCadenceHours: number;
  status: TrustedSourceStatus;
  resourceCount?: number;
  license?: string;
  metadataModified?: string;
  datasetId?: string;
  coverage?: string;
  access?: string;
  beforeScene?: string;
  afterScene?: string;
  eventCount?: number;
  maxMagnitude?: number;
  stats?: {
    footprintCount?: number;
    averageDamage0m?: number | null;
    averageUnknownPct?: number | null;
  };
  error?: string;
  note?: string;
}

export interface TrustedDataSnapshot {
  schemaVersion: number;
  generatedAt: string;
  generatedBy: string;
  incident: {
    id: string;
    name: string;
    admin0: string;
    startDate: string;
    bbox: [number, number, number, number];
  };
  policy: {
    publicRule: string;
    privateRule: string;
    aiRule: string;
  };
  summary: {
    okSourceCount: number;
    errorSourceCount: number;
    hdxPackageCount: number;
    googleDatasetCount: number;
    satelliteImageryCount: number;
    resourceCount: number;
    trustedAssetLayers: number;
    microsoftDamageFootprints: number;
    averageDamage0m: number | null;
    usgsEventCount: number;
    usgsMaxMagnitude: number;
  };
  sources: TrustedSourceSnapshot[];
}

export async function fetchTrustedDataSnapshot(): Promise<TrustedDataSnapshot | null> {
  try {
    const response = await fetch('/data/trusted-data.json');
    if (!response.ok) return null;
    return (await response.json()) as TrustedDataSnapshot;
  } catch {
    return null;
  }
}

export function formatSnapshotAge(generatedAt: string, now = Date.now()) {
  const generated = new Date(generatedAt).getTime();
  if (!Number.isFinite(generated)) return 'unknown';
  const minutes = Math.max(0, Math.round((now - generated) / 60_000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}
