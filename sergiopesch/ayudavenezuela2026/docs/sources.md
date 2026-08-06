# Sources

This file records the source base for the initial project foundation. Because the situation is active as of 2026-06-26, operational facts should be rechecked before public use.

## Original Reference Project

- Hugging Face: [Using ML for Disasters](https://huggingface.co/blog/using-ml-for-disasters)
- afet-org GitHub repository: [afet-org](https://github.com/acikyazilimagi/afet-org)
- DEV Community writeup: [How an open-source disaster map helped thousands of earthquake survivors](https://dev.to/erayg/how-an-open-source-disaster-map-helped-thousands-of-earthquake-survivors-afetharitacom-440)
- arXiv paper on Turkish earthquake help-request classification/extraction: [arXiv:2302.13403](https://arxiv.org/abs/2302.13403)

## Venezuela 2026 Earthquake Context

- OCHA Venezuela: [Venezuela](https://www.unocha.org/venezuela)
- ReliefWeb disaster page: [Venezuela Earthquake 2026](https://reliefweb.int/disaster/eq-2026-000093-ven)
- IFRC: Venezuela earthquake emergency appeal and operational updates, including La Guaira/Greater Caracas focus and emergency assistance. Use the IFRC site search and ReliefWeb mirrors if a direct appeal URL changes.
- USGS event references from public earthquake reporting:
  - [M7.2 event](https://earthquake.usgs.gov/earthquakes/eventpage/us6000t7zc/executive)
  - [M7.5 event](https://earthquake.usgs.gov/earthquakes/eventpage/us6000t7zp/oaf/overview)
- GDACS: [Global Disaster Alert and Coordination System](https://gdacs.org/)
- Copernicus EMS: [Emergency Management Service Mapping](https://mapping.emergency.copernicus.eu/)
- Logistics Cluster: [Earthquake 2026 activity page](https://logcluster.org/en/activities/earthquake-2026)
- European Civil Protection and Humanitarian Aid Operations: [Venezuela country page](https://civil-protection-humanitarian-aid.ec.europa.eu/where/latin-america-and-caribbean/venezuela_en)

## Needs And Public Signals

- Caracas Chronicles: [Key information about Venezuela's state of emergency](https://www.caracaschronicles.com/2026/06/25/key-information-about-venezuelas-state-of-emergency/)
- Associated Press: [international response and urgent needs](https://apnews.com/article/fc64bb65cd2da3c9206a37b74e89d3f7)
- Associated Press: [missing-person registries and online family tracing](https://apnews.com/article/ac6117e7a9ad3095d50e3535e991df12)
- Direct Relief: [Venezuela earthquake medical response reporting](https://www.directrelief.org/2026/06/venezuela-earthquake-caracas-damage/)
- World Vision: [Venezuela earthquake updates and relief needs](https://www.worldvision.org/disaster-relief-news-stories/venezuela-earthquake-latest-updates-fast-facts-and-how-to-help)
- Action Against Hunger: [Venezuela earthquake appeal](https://www.actionagainsthunger.org.uk/venezuela-earthquake-appeal)
- ACT Alliance: [Venezuela earthquake alert](https://actalliance.org/wp-content/uploads/2026/06/ACT_Alert_Venezuela_Earthquakes.pdf)
- El Pais Colombia: [collection centers and donation needs in Bogota](https://www.elpais.com.co/amp/mundo/habilitan-centro-de-acopio-en-bogota-para-ayudar-a-afectados-tras-sismos-en-venezuela-2543.html)
- RTVE: [donation guidance and NGO channels](https://www.rtve.es/noticias/20260626/claves-ayudar-venezuela-terremoto-donaciones-ong-aecid-espana/17133659.shtml)
- Vogue Mexico: [how to help after the June 24 earthquakes](https://www.vogue.mx/articulo/como-ayudar-a-venezuela-terremotos-del-24-de-junio-2026)

## Humanitarian Data, Safety, And Coordination

- OCHA Centre for Humanitarian Data: [Data responsibility](https://centre.humdata.org/data-responsibility/)
- ICRC: [Handbook on Data Protection in Humanitarian Action](https://www.icrc.org/en/data-protection-humanitarian-action-handbook)
- OCHA Knowledge Base: [Common Operational Datasets and P-codes](https://knowledge.base.unocha.org/wiki/spaces/imtoolbox/pages/4099440644/COD%2BGlobal%2BInformation%2BDashboard)
- HDX Venezuela: [Humanitarian Data Exchange - Venezuela](https://data.humdata.org/group/ven)
- Google Research Open Buildings: [Open Buildings V3 Polygons in Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings_v3_polygons). Public building-footprint dataset covering Latin America and the Caribbean, including Venezuela; useful for aggregate exposure context.
- Google Research Open Buildings: [Open Buildings 2.5D Temporal Dataset in Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings-temporal_v1). Public annual building presence/count/height dataset for 2016-2023; useful for exposure and settlement-change context.
- EOX: [Sentinel-2 Cloudless](https://s2maps.eu/) and [EOxCloudless](https://cloudless.eox.at/) for open, shareable Venezuela-wide optical context at 10 m resolution.
- HOTOSM / Hugging Face: [hotosm/venezuela_eq_2026](https://huggingface.co/datasets/hotosm/venezuela_eq_2026) for earthquake damage AOI context across Caracas, Caraballeda, Catia La Mar, La Guaira, Moron, and Naiguata. Use as prioritization context, not household-level verification.
- Element 84 Earth Search: [STAC API](https://earth-search.aws.element84.com/v1) for Sentinel-2 L2A Cloud-Optimized GeoTIFF visual assets used in the public before/after satellite slider.
- TiTiler: [Cloud-Optimized GeoTIFF tile rendering](https://developmentseed.org/titiler/) used to render Sentinel-2 COG visual assets as web map tiles.
- Microsoft AI for Good Lab / HDX: [Venezuela Earthquakes: Building Damage Assessment in Catia La Mar](https://data.humdata.org/dataset/venezuela-earthquakes-catia-la-mar). Dataset date 2026-06-25, license CC BY. Resources include predicted damage building footprints as GeoPackage, a valid-area mask GeoJSON, and an updated JPEG map.
- ArcGIS Web Scene: [Catia La Mar 3D](https://www.arcgis.com/home/webscene/viewer.html?webscene=c01ef4b6b74b4d25a39f7a1e4865be58), with public FeatureServer layer [Edificios_Afectados](https://services8.arcgis.com/w0z3NDBGLWwOLx2y/arcgis/rest/services/Catia_La_Mar_3D_WFL1/FeatureServer/0) used by the prototype for interactive affected-building polygons.
- KoBoToolbox: [KoBoToolbox](https://www.kobotoolbox.org/)
- CLEAR Global: [Language data for Venezuela](https://clearglobal.org/language-data-for-venezuela/)
- CLEAR Global: [Language technology for humanitarian action](https://clearglobal.org/wp-content/uploads/2024/04/Language-technology-for-humanitarian-action-CLEAR-Global-April-2024.pdf)
- CARE Principles for Indigenous Data Governance: [CARE Principles](https://www.gida-global.org/care-principles-copy)
- Internews: [Humanitarian rumor tracking](https://internews.org/areas-of-expertise/humanitarian/approaches/rumour-tracking/)
- WHO: [Ethical social listening guidance](https://www.who.int/publications/i/item/9789240108202)
- NASA Disasters Mapping Portal: [Practitioner resources](https://appliedsciences.nasa.gov/what-we-do/disasters/practitioner-resources)
- OCHA Centre for Humanitarian Data: [Retiring HXL services](https://centre.humdata.org/retiring-hxl-services/)
