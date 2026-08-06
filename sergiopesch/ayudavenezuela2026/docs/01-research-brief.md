# Research Brief: Venezuela Earthquake Response Context

Date of brief: 2026-06-26

## High-Confidence Situation Framing

The project should be oriented around the June 24, 2026 north-central Venezuela earthquake emergency. Public and humanitarian reporting points to severe impacts around La Guaira and Greater Caracas, with wider effects reported across Caracas, Miranda, Aragua, Carabobo, Falcon, Yaracuy, and nearby areas.

Because the event is unfolding, casualty, injury, missing-person, displacement, and damage numbers should be treated as provisional. The product should store source, timestamp, confidence, and verification status for every number or claim.

## Timeline

- **2026-06-24, evening local time:** strong earthquake sequence affects north-central Venezuela. Several sources describe a M7.2 foreshock followed seconds later by a M7.5 mainshock.
- **2026-06-24 to 2026-06-25:** national emergency measures, search and rescue activation, reception centers, class/work suspensions, and emergency coordination are reported.
- **2026-06-25 to 2026-06-26:** international humanitarian actors begin appeals, logistics assessments, search and rescue support, cargo movement, and rapid mapping.

## Most Affected Areas To Model First

Initial geographic focus:

- La Guaira state: Los Corales, Caraballeda, Macuto, Catia La Mar, Maiquetia, port and coastal access routes.
- Greater Caracas: Libertador and surrounding municipalities, especially dense hillside and informal-settlement areas.
- Miranda, Aragua, Carabobo, Falcon, and Yaracuy as wider affected or exposed areas.

The platform should avoid depending on formal street addresses only. In Venezuela, disaster reports may use landmarks, barrios, sectors, parish names, road references, nearby businesses, churches, schools, or informal local names.

## Current Constraints

### Search And Rescue

Collapsed structures, aftershocks, blocked access, and incomplete building-damage visibility make SAR triage urgent. Reports may be duplicated across family posts, WhatsApp chains, citizen registries, and media.

### Connectivity And Power

Power, telecommunications, internet, and transport disruption are repeatedly reported. Firsthand diaspora/frontline context says La Guaira is currently without power, internet access is intermittent, and Starlink connectivity hotspots may exist but are hard for people to locate. This means a social-media-only map will underrepresent the most affected people. Offline and low-bandwidth intake are not optional.

The first operational map should include connectivity hotspots, phone-charging points, support centers, shelters, clinics, food/water points, and collection centers.

### Device Access And Proxy Reporting

Most people in the worst-affected areas may not have smartphones, while many people providing assistance on the ground do. The platform should therefore support proxy reporting: responders, volunteers, family members, and trusted community focal points can submit or update reports on behalf of affected people.

Proxy reports need clear source tracking, consent notes where possible, and a validation status that distinguishes direct observation from secondhand forwarding.

### Health

Likely needs include trauma care, crush injury treatment, surgery, wound care, antibiotics, IV supplies, chronic-disease medication continuity, ambulance routing, and field-health referrals.

### Logistics

Road access, airport/port status, fuel, warehouse capacity, customs/visa movement, and last-mile distribution are likely bottlenecks. Maiquetia/Simon Bolivar airport and La Guaira port are strategically important and should be tracked as infrastructure layers.

### Information Disorder

Public posts and citizen registries can surface urgent needs faster than official channels, but they can also contain duplicates, outdated reports, wrong locations, scams, and rumors. The platform should create workflows for validation and public corrections.

Family-location information is also being shared through handwritten wall lists and WhatsApp, Instagram, Facebook, SMS, and X. These are useful signals, but they require duplicate matching, careful redaction, and family-contact workflows before publication.

## Repeated Needs From Public Sources

The following categories appear repeatedly across public humanitarian, news, NGO, and community-facing sources:

| Need category | Concrete signals to capture |
| --- | --- |
| Search and rescue | trapped persons, collapsed buildings, heavy machinery, shovels, helmets, PPE, flashlights, rescue dogs, urgent extraction |
| Medical | trauma care, crush injuries, surgery, wounds, antibiotics, first aid, chronic medicines, blood donation, ambulances |
| Missing/found persons | name, age, last location, last contact time, family contact, hospital/shelter sightings, photo consent status |
| Shelter | temporary shelters, tents, tarps, mats, blankets, safe sleeping space, household registration |
| WASH | safe water, purification, hygiene kits, soap, diapers, menstrual hygiene, sanitation, latrines |
| Food | ready-to-eat food, hot meals, baby formula, nonperishables, cooking capacity |
| Communications and power | power banks, batteries, solar chargers, radios, phone charging, connectivity restoration |
| Connectivity/support locations | Starlink or other hotspots, charging points, shelters, support centers, clinics, food/water points, collection centers |
| Transport and logistics | road blockages, bridge damage, airport/port status, fuel, warehouse space, supply routes |
| Cash and donations | vetted cash channels, voucher assistance, collection points, fraud/scam warnings |
| Protection and psychosocial support | separated children, older adults, people with disabilities, bereavement, safe spaces, referral needs |

## Product Implications

1. **Geospatial spine:** use OCHA Common Operational Datasets, P-codes, OSM, health facility data, shelter locations, roads, ports, airports, and administrative boundaries.
2. **Report lifecycle:** unverified -> duplicate candidate -> contacted -> confirmed -> routed -> in progress -> resolved -> stale/unreachable -> unsafe to publish.
3. **Public/private split:** publish aggregate needs and verified services publicly; keep exact person-level data private.
4. **Diaspora workflow:** enable relatives outside Venezuela to submit missing-person reports, update sightings, and receive verified instructions.
5. **Field-ready design:** support offline PWA/Android collection, KoBo/ODK import/export, cached map tiles, CSV fallback, call-center entry, and proxy reporting.
6. **Connectivity-first layer:** map verified connectivity hotspots and charging points as first-class relief infrastructure.

## Confidence Boundaries

High confidence:

- The June 24 earthquake emergency is the dominant current catastrophe.
- La Guaira and Greater Caracas are priority areas.
- Connectivity, power, health, shelter, WASH, tracing, and logistics are central needs.
- Counts are volatile and should be timestamped.

Medium confidence:

- Specific neighborhood-level severity rankings.
- Exact state-by-state displacement.
- Exact airport/port damage and operational status without current logistics confirmation.

Low confidence:

- Unverified social posts naming individual missing persons, collapsed addresses, or donation accounts.
- Any single casualty/missing figure repeated without timestamp and source.
