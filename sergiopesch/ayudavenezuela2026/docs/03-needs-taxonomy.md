# Needs Taxonomy

This taxonomy is a starter for intake, triage, routing, analytics, and public communication. It should be localized with field partners.

## Top-Level Categories

| Code | Category | Description | Public by default? |
| --- | --- | --- | --- |
| SAR | Search and rescue | Trapped people, collapsed buildings, extraction needs, rescue assets | No |
| MED | Medical | Trauma, injury, chronic care, ambulance, hospital capacity | No |
| MISSING | Missing/found persons | Family tracing, last contact, sightings, reunification | No |
| SHELTER | Shelter/NFI | Displacement, tents, tarps, blankets, household items | Aggregate only |
| WASH | Water/sanitation/hygiene | Safe water, sanitation, hygiene kits, diapers, menstrual hygiene | Aggregate/service points |
| FOOD | Food/nutrition | Meals, nonperishables, baby formula, cooking capacity | Aggregate/service points |
| POWER_COMMS | Power and communications | Electricity, phone signal, internet, charging, radios | Aggregate/infrastructure |
| CONNECTIVITY | Connectivity/support location | Starlink or other hotspots, phone charging, support centers, shelters, clinics, food/water points | Public if verified and safe |
| LOGISTICS | Transport/logistics | Roads, bridges, port, airport, fuel, warehouse, supply chain | Role-gated |
| PROTECTION | Protection/MHPSS | children, older adults, disability, GBV risk, psychosocial support | No |
| CASH | Cash/donations | cash/voucher needs, vetted donation channels, fraud reports | Aggregate/public guidance |
| INFRA | Infrastructure damage | buildings, schools, hospitals, utilities, water systems | Depends |
| RUMOR | Rumor/info request | repeated public claim needing verification or response | Public response only |
| OFFER | Available resource | volunteers, supplies, equipment, transport, shelter capacity | Role-gated |

## Urgency Levels

| Code | Level | Use when |
| --- | --- | --- |
| U0 | Immediate life safety | trapped, severe injury, active danger, urgent medical evacuation |
| U1 | Same day | needs action within 24 hours to prevent serious harm |
| U2 | 1-3 days | important but not immediate life threat |
| U3 | Monitor | information useful for planning or trend tracking |
| U4 | Resolved/stale | no action needed, duplicate, outdated, or closed |

## Report Lifecycle

1. `received`
2. `needs_review`
3. `duplicate_candidate`
4. `contact_attempted`
5. `plausible`
6. `confirmed`
7. `routed`
8. `in_progress`
9. `resolved`
10. `stale`
11. `unsafe_to_publish`
12. `rejected`

## Minimum Data For A Report

Required:

- category;
- free-text description;
- location text or admin area;
- observed time or received time;
- source type;
- consent/publication preference;
- verification status.

Optional but important:

- GPS coordinate;
- landmark;
- contact method;
- number of people affected;
- vulnerability flags;
- attachment;
- partner organization;
- route/cluster assignment;
- confidence score;
- linked duplicate IDs.

## Sensitive Fields

Treat these as private by default:

- names;
- phone numbers;
- exact home locations;
- photos of people;
- medical details;
- child protection details;
- GBV or exploitation reports;
- migration or documentation status;
- political affiliation;
- ethnicity or Indigenous identity;
- shelter locations that could expose vulnerable groups.

## Public Output Rules

Safe public outputs:

- verified service points approved for publication;
- aggregate needs by municipality/parish/neighborhood;
- donation guidance through vetted organizations;
- official or partner-approved instructions;
- rumor corrections without exposing the original reporter.

Unsafe public outputs:

- exact location of trapped, missing, injured, or displaced people;
- identifiable medical/protection records;
- unverified donation accounts;
- unverified building-collapse reports linked to named people;
- operational routes for sensitive aid movement;
- shelter locations where public visibility creates protection risk.
