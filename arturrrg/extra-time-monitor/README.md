---
title: Extratimemonitor
emoji: ⚽
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
---

# Extra Time Monitor

An API-only, live endgame soccer tracker that monitors live matches on 1win from the **62nd minute onward** (until the full-time whistle). It is designed to identify stoppage-time betting opportunities and capture real-time odds fluctuations.

Rather than relying on browser automation (e.g., Puppeteer/Selenium), this system connects directly to the 1win WebSockets gateway and REST APIs to fetch real-time game logs, timeline events, and market prices in near-real-time (~100ms latency).

---

## Key Features & Betting Signals

### 1. The "Bet Ready" Signal
The dashboard monitors market counts on active fixtures. When both the **Full Time Result (1/X/2)** and **Next Goal** markets are active, and the **"Other Markets" count reaches 0**, it signals an actionable entry point for a late-stage bet.

### 2. Stoppage-time Board Detection
Captures the referee's official announced 2nd-half added-time board ("+X" injury time, sportcast event 1104) to monitor game progress and validate stoppage length.

### 3. Actionable Exclusions & Filtering
To ensure quality data and protect against high-risk situations, the backend automatically filters out matches:
* **Goal Scored:** Any goal scored in the late stage (62'–90') immediately evicts the match from the active dashboard.
* **Long Stoppage Time:** If the referee's board announces added time exceeding **5 minutes** (e.g., due to severe injuries/VAR delays), the match is retired as it represents an atypical, drawn-out finish.
* **Esports & Simulated Matches:** Filters out virtual matches, penalty shootouts, cyber leagues, and short-format games (e.g., "(V)", "replays", "gg-league").
* **Under-age Matches:** Excludes youth matches (e.g., U17, U20, Under-19) to maintain consistency.
* **Market Absence:** If both Full Time Result and Next Goal markets are absent/suspended for more than 5 minutes, the card is retired.

---

## Data Persistence & Logging

All persistent logs and subscription keys are stored in `DATA_DIR` (which defaults to the repository folder on local runs, and should be set to `/data` in persistent Docker mounts).

1. **System Log (`system-log.json`):** A permanent, append-only record of every match filtered or excluded by the system (e.g., match finished, goal scored, long added time). It includes full end-state telemetry and direct 1win links. Accessible via the frontend "System Logs" terminal or `/api/system-log.json`.
2. **Odds Log (`odds-log.jsonl`):** A real-time, high-resolution JSON Lines capture recording every odds change, suspension, and resumption for Full Time Result and Next Goal markets starting at 90'+.
3. **Web Push Subscriptions (`push-subscriptions.json`):** Contains keys for active browser alerts.

---

## Alert System

The system notifies users the moment the 2nd-half added-time board (+X minutes) is officially announced on eligible matches:

* **Tab Open (Active Audio):** Plays a Web Audio chime in the browser. Volume/mute controls are managed in the navbar and saved to `localStorage`.
* **Tab Closed (Web Push):** Dispatches a high-priority background Web Push notification using the VAPID keys (`vapid.json`). This wakes the device (Android/iOS) to display an OS-level notification.
  * *Note: On iPhones, the user must add the web app to their Home Screen (as a PWA) to enable background Web Push (iOS 16.4+).*

---

## Environment Configuration

Customize system behaviors by passing these environment variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `7860` | The port the web server listens on. |
| `DATA_DIR` | *Repo Dir* | Directory where `vapid.json`, logs, and subscriptions are saved. |
| `TEMP_MIN_MINUTE` | `62` | The minute threshold when a match enters the active tracking dashboard. |
| `LATE_APPEARANCE_MINUTE` | `85` | Fixtures first discovered after this minute are skipped (grace period applies on startup). |
| `MAX_ANNOUNCED_ADDED_MINUTES` | `5` | Excludes matches where announced stoppage time is greater than this value. |
| `BOTH_MARKETS_LAPSE_MS` | `300000` | Eviction timeout (5 mins) if both FTR and Next Goal markets stay absent. |
| `MARKET_ODD_FRESH_MS` | `45000` | Freshness check window (45s) to confirm silent market removals. |
| `MARKET_ACTIVE_GRACE_MS` | `60000` | Anti-flicker delay (1 min) to ride out brief market suspends. |
| `VAPID_SUBJECT` | `mailto:alerts@...` | Email contact string bundled with Web Push notifications. |

---

## Quick Start (Local Run)

1. Ensure [Node.js](https://nodejs.org/) is installed.
2. Install dependencies:
   ```bash
   npm install
   ```
3. Boot the environment using the provided batch script:
   ```bash
   start.bat
   ```
   This will start the server and open the web dashboard in your default browser at `http://localhost:7860`.
