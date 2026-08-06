import type { Language } from './language';

type UiCopy = {
  mapLayers: string;
  microsoftDamageLayer: string;
  damageLegendTitle: string;
  damageFootprints: string;
  damageHigh: string;
  damageModerate: string;
  damageObserved: string;
  damageUncertain: string;
  damageAttribution: string;
  damageLayerOff: string;
  noTrustedData: string;
  footerChannels: string;
  footerPrivacy: string;
  footerProxy: string;
  footerSync: string;
};

export const copy: Record<Language, UiCopy> = {
  es: {
    mapLayers: 'Capas del mapa',
    microsoftDamageLayer: 'Microsoft AI edificios afectados',
    damageLegendTitle: 'Dano estimado',
    damageFootprints: 'huellas de edificios',
    damageHigh: 'Alto',
    damageModerate: 'Moderado',
    damageObserved: 'Observado',
    damageUncertain: 'Incierto',
    damageAttribution: 'Microsoft AI for Good Lab via HDX, CC BY. No es una decision automatica de rescate.',
    damageLayerOff: 'Dano edificios oculto',
    noTrustedData: 'Snapshot de fuentes no disponible.',
    footerChannels: 'Fuentes: HDX, HOT/OSM, Microsoft AI for Good Lab, USGS, UNEP/OCHA',
    footerPrivacy: 'Vista publica: datos agregados o redactados',
    footerProxy: 'HF Assist: clasificacion local de contexto publico',
    footerSync: 'Sincronizacion publica diaria'
  },
  en: {
    mapLayers: 'Map layers',
    microsoftDamageLayer: 'Microsoft AI affected buildings',
    damageLegendTitle: 'Estimated damage',
    damageFootprints: 'building footprints',
    damageHigh: 'High',
    damageModerate: 'Moderate',
    damageObserved: 'Observed',
    damageUncertain: 'Uncertain',
    damageAttribution: 'Microsoft AI for Good Lab via HDX, CC BY. Not an automated rescue decision.',
    damageLayerOff: 'Building damage hidden',
    noTrustedData: 'Trusted-source snapshot unavailable.',
    footerChannels: 'Sources: HDX, HOT/OSM, Microsoft AI for Good Lab, USGS, UNEP/OCHA',
    footerPrivacy: 'Public view: aggregated or redacted data',
    footerProxy: 'HF Assist: local classification of public context',
    footerSync: 'Daily public sync'
  }
};
