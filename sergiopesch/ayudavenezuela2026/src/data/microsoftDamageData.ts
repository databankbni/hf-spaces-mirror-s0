export type DamageSeverity = 'high' | 'moderate' | 'observed' | 'uncertain';

export const microsoftDamageSource = {
  organization: 'Microsoft AI for Good Lab',
  hdxDatasetUrl: 'https://data.humdata.org/dataset/venezuela-earthquakes-catia-la-mar',
  webSceneUrl:
    'https://www.arcgis.com/home/webscene/viewer.html?webscene=c01ef4b6b74b4d25a39f7a1e4865be58',
  imageMapUrl:
    'https://data.humdata.org/dataset/029efb88-3a8a-40d9-8aea-65477e6eb744/resource/ac4ec923-02c2-43c2-92b9-50c439608e90/download/venezuela-2026-page-2-updated.jpg',
  geopackageUrl:
    'https://data.humdata.org/dataset/029efb88-3a8a-40d9-8aea-65477e6eb744/resource/684fdeab-e4ac-4029-9ec9-891676b2ebfc/download/predicted_damage_catia_la_mar_footprints.gpkg'
} as const;
