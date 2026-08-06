# Point Of View

## Summary

The next evolution of the Hugging Face/Turkey disaster ML project for Venezuela should not be a direct clone of a Twitter-driven rescue map. It should be a **human-validated disaster intelligence and communication platform** designed for low connectivity, Spanish-first and multilingual access, sensitive personal data, uncertain reports, and humanitarian coordination.

The Turkey project proved that volunteer ML can turn chaotic public messages into structured, geocoded, actionable records. Venezuela 2026 needs that same speed, but with stronger safeguards and more diverse channels:

- less dependence on X/Twitter firehose access;
- more first-party and partner intake through field forms, WhatsApp, Telegram, SMS, IVR, radio-room logs, call centers, and diaspora channels;
- offline-first workflows for power and telecom disruption;
- stricter verification and redaction before publishing;
- explicit integration with humanitarian coordination data, not only a public map;
- Spanish and Venezuela-specific geocoding, plus respectful Indigenous-language support where relevant.

## Why This Is Not Just "Afet Harita For Venezuela"

The original disaster ML project helped convert survivor posts, screenshots, forms, and social feeds into map records using OCR, entity extraction, need classification, and geocoding. That was right for the Turkey earthquake response because public social media carried a large share of rescue requests.

For Venezuela in June 2026, the immediate crisis appears to be the June 24 north-central earthquake doublet, with severe impact reported in La Guaira and Greater Caracas. But the response context is different:

- connectivity and power disruptions make online-only intake incomplete;
- many affected residents may not have smartphones, while frontline helpers often do and can submit reports on their behalf;
- people may be afraid to share identifiable data publicly;
- casualty, missing-person, and shelter information can be politically and personally sensitive;
- existing humanitarian need was already high before the earthquake;
- diaspora networks are essential for family tracing and donations;
- official, NGO, citizen, and media reports may conflict during the first days.

The product should therefore treat public reports as **signals to verify**, not as facts to publish.

## Operating Principle

Use AI to accelerate the repetitive work around crisis data, while keeping operational judgment with humans.

AI can help with:

- extracting names, phone numbers, addresses, landmarks, needs, and timestamps from messages;
- classifying needs such as search and rescue, medical, shelter, WASH, food, power, logistics, missing person, and protection;
- clustering duplicates and stale reports;
- suggesting geocodes using gazetteers, OSM, administrative boundaries, and local landmarks;
- translating or summarizing reports for validators;
- drafting situation updates with citations;
- flagging rumors that need public clarification.

AI must not:

- decide who receives aid;
- decide medical priority without clinical review;
- publish exact locations of vulnerable people;
- classify a report as true or false without human validation;
- share identifiable reports with actors outside the agreed humanitarian purpose;
- infer political affiliation, migration status, ethnicity, or vulnerability unless explicitly needed and consented for protection work.

## The Product Shape

AyudaVenezuela2026 should have four surfaces:

1. **Community intake**
   Lightweight forms and messaging workflows for people and proxy reporters to report urgent needs, missing people, infrastructure damage, connectivity hotspots, shelter needs, medical issues, or available resources.

2. **Validator workbench**
   A private queue where trained volunteers and partner staff merge duplicates, redact sensitive fields, verify sources, update status, and route cases.

3. **Operations map**
   A role-gated geospatial dashboard for responders showing verified or partner-visible layers: shelters, health points, WASH gaps, road access, supply points, damage reports, missing/found cases, and unresolved urgent needs.

4. **Public information layer**
   A safe, redacted public view: verified service points, donation guidance, rumor corrections, emergency instructions, and aggregate needs by area.

## Priority Use Cases

### First 72 Hours

- Search and rescue request triage.
- Missing/found person registry with family contact workflow.
- Starlink/connectivity hotspot and phone-charging map.
- Support center, shelter, clinic, food, and water point map.
- Proxy reporting by frontline smartphone users for people without smartphones.
- Collapsed/damaged building reports.
- Health referral routing.
- Power/telecom/road outage collection.
- Public correction of false donation links and rumors.

### Days 3-14

- Shelter and household registration.
- WASH, food, medicine, and cash-assistance gap mapping.
- Damage assessment aggregation.
- Health facility and ambulance availability.
- Supply-point and distribution monitoring.
- Diaspora family tracing and donation routing.

### Weeks 2-12

- Recovery needs monitoring.
- Protection and psychosocial referral workflows.
- School, health, and infrastructure restoration tracking.
- Community feedback and complaints.
- Risk monitoring for aftershocks, floods, landslides, and disease outbreaks.

## The Design Bet

The highest-leverage system is not the flashiest map. It is the trusted pipeline behind the map:

**messy report -> structured record -> dedupe -> risk redaction -> human validation -> operational routing -> safe publication -> feedback loop.**

That is the next evolution.
