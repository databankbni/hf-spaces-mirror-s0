# AI Scam Detector — Product Architecture & Technical Specifications

This document provides a comprehensive overview of the **AI Scam Detector** ecosystem, detailing the features built, the technical stack chosen, architecture decisions, and third-party integrations.

---

## 1. Executive Summary & Brand Identity

*   **Official Brand Name:** AI Scam Detector
*   **Target Core Product:** A secure, AI-powered system designed to protect citizens from financial cyber-scams (UPI fraud, phishing links, job scams) directly over WhatsApp, supported by a conversion-optimized web landing page and admin monitoring suite.
*   **Monetization Model:** Freemium model. Users get 1 anonymous scan on the website or 3 free checks on WhatsApp. Paid users buy **Premium Access** at ₹199/month for unlimited scans, priority processing, and access to a personal web scanning history timeline.

---

## 2. Product Features & Capability Map

The platform is split into three main layers: the WhatsApp Bot, the Web Landing Page, and the Admin Control Center.

```
                  ┌─────────────────────────────────┐
                  │        AI Scam Detector         │
                  └────────────────┬────────────────┘
                                   │
         ┌─────────────────────────┼────────────────────────┐
         ▼                         ▼                        ▼
┌─────────────────┐       ┌─────────────────┐      ┌─────────────────┐
│  WhatsApp Bot   │       │  Landing Page   │      │   Admin Portal  │
├─────────────────┤       ├─────────────────┤      ├─────────────────┤
│ • Scam Checks   │       │ • Scan Widget   │      │ • Analytics     │
│ • Link Scraper  │       │ • Conversion    │      │ • Transaction   │
│ • Vision AI     │       │ • Razorpay Live │      │ • Status Monitor│
│ • Quota Manager │       │ • User Timeline │      │ • Pattern Editor│
└─────────────────┘       └─────────────────┘      └─────────────────┘
```

### A. Real-Time WhatsApp Protection Bot
*   **Link & URL Analysis:** Automatically extracts domains from incoming text and performs validation checks against OpenPhish threat intelligence feeds.
*   **Visual Vision AI Scanning:** Allows users to forward screenshots of QR codes, suspicious SMS headers, or payment slips. The bot uses Gemini Vision to inspect text elements embedded in images.
*   **Automatic Account Quotas:** Tracks user quotas (3 free scans per phone number). Once exhausted, it instructs the user to upgrade to premium.
*   **Interactive Menu Controls:** Supports interactive list options and quick-replies (e.g. "Check a Link", "Check a Message", "My Status").

### B. Conversion-Optimized Web Funnel
*   **"Hook & Lock" Landing Page:** Contains a free scam scanner card. Anonymous users are limited to **1 scan per 24 hours** (tracked via IP rate-limiting) to prevent AI abuse.
*   **Lockout Overlay Modal:** Once the free scan is exhausted, the scanner container blurs and locks, displaying a dynamic CTA pointing users directly to the WhatsApp bot.
*   **Live Service Status Dot:** A pulsing status indicator in the footer querying the backend `/health` status in real time to build customer trust.
*   **Razorpay Live Checkout:** Clicking "Upgrade to Premium" opens a checkout popup where users can buy premium access using UPI or card payments.
*   **Personal Scan History Timeline:** Users request a 4-digit OTP via their phone number on the website to securely log in and view their historical scans.

### C. Admin Control Dashboard
*   **Threat Analytics Trend Chart:** Displays historical daily check counts and flagged threats using Chart.js.
*   **Scam Distribution Analysis:** A circular doughnut chart illustrating the breakdown of flagged scam categories.
*   **Recent Scans Audit Log:** A chronological log detailing scanned messages, risk scores, and client confidence levels.
*   **Recent Transactions & Earnings Log:** Calculates total gathered revenue and lists all recent payments.
*   **Scam Heuristics Blacklist Manager:** An interactive interface to view, search, add, or delete regex patterns and threat indicators in real time.
*   **Global Connection Badge & Kill Switch:** Shows live Meta API connection statuses and includes a toggle to pause or resume the WhatsApp bot.

---

## 3. Technology Stack & Rationale

| Layer | Technology | Rationale |
| :--- | :--- | :--- |
| **Backend Engine** | **Node.js (Express)** | Lightweight, highly asynchronous event-driven loop ideal for processing webhooks and fast API responses. |
| **Realtime Database** | **Firebase Realtime DB** | NoSQL database offering low-latency reads/writes, hierarchical tree nodes for user limits, and instant updates. |
| **AI Processing** | **Gemini API (Flash 1.5)** | Selected for state-of-the-art token speeds, multi-modal vision capabilities, and cost efficiency. |
| **Frontend Styling** | **Vanilla HTML5 & CSS3** | Custom glassmorphism, responsive grids, and micro-animations styled natively to avoid dependency bloat. |
| **Charts Engine** | **Chart.js** | Canvas-based rendering engine providing elegant, animations-ready charts for admin dashboard panels. |

---

## 4. Platform Integrations & Topology

To bypass firewalls and implement secure payments, the application integrates multiple platforms:

```
┌─────────────────┐       ┌─────────────────┐       ┌──────────────────┐
│  Hugging Face   ├──────►│   Google Apps   ├──────►│   Meta Graph     │
│  Spaces Host    │       │   Script Proxy  │       │   API Gateway    │
└────────┬────────┘       └─────────────────┘       └──────────────────┘
         │
         ├────────────────► Firebase Realtime Database
         │
         └────────────────► Razorpay Payment Gateway
```

### A. Hugging Face Spaces (Hosting Platform)
*   **What it does:** Hosts the running Docker Node.js container.
*   **Client IP Resolution:** Hugging Face acts as a reverse proxy. To track individual client IPs for rate-limiting, the server parses the first index of the comma-separated `x-forwarded-for` request header.
*   **Git LFS Configuration:** Git LFS is configured in the repository to bypass Hugging Face's strict binary push restrictions, enabling version control of logo PNGs.

### B. Google Apps Script Web App (Egress Proxy)
*   **Why it is used:** Hugging Face Spaces restrict outbound network requests to certain external APIs (including the Meta Graph API domain `graph.facebook.com`) via a strict internal egress firewall.
*   **How it works:** A secure Google Apps Script serves as a bridge. Outbound WhatsApp messages from the node server are sent to the Apps Script endpoint, which forwards the request to Meta using Google's whitelisted network routes.
*   **Header Mapping Bypass:** The authorization token is forwarded as a query parameter (`?token=...`) to avoid Google's default behavior of stripping authorization headers.

### C. Meta Developer Platform (WhatsApp Business Cloud API)
*   **What it does:** Replaced the legacy Gupshup integration.
*   **Inbound Messages (Webhook):** Meta routes customer messages to our `/webhook` endpoint. The server verifies payloads using a secure verify token handshaking check.
*   **Outbound Messages:** Sends templates, interactive list buttons, and quick-replies to users.

### D. Razorpay (Payment Gateway)
*   **Standard Orders API:** Implements `/payments/create-order` to generate standard ₹199 orders directly on the live account.
*   **HMAC Signature Verification:** Implements `/payments/verify-order` signature validation. It hashes `orderId` and `paymentId` with the `RAZORPAY_KEY_SECRET` using a secure SHA-256 HMAC algorithm to ensure authenticity before upgrading accounts.

---

## 5. Security & Privacy Safeguards

1.  **PII Hashing:** To maintain absolute user privacy, phone numbers are never stored in plain text inside the database check logs or transaction records. They are hashed using a secure **SHA-256** hash algorithm immediately upon receipt.
2.  **Encryption of Messages:** Raw user messages submitted to database logs are encrypted using **AES-256-CBC** symmetric encryption with a rotating secret key.
3.  **JSON Parser DoS Protection:** Custom Express middleware intercepts syntax errors during JSON parsing, returning structured `400 Bad Request` payloads instead of triggering process crashes.
4.  **IP Rate Limiting:** Restricts anonymous web scans to 1 per 24 hours per IP address, preventing bot exhaustion and API billing inflation.
5.  **Automated Background Cron Sync:** Runs a background scraper thread every 12 hours (and 10 seconds post-startup) to synchronize threat vectors natively inside the Node process container, securing zero-day protection coverage at no extra hosting costs.
6.  **Crowdsourced Scam Reporting Flow:** Enables users to submit suspicious text, links, or screenshot images via WhatsApp using the `REPORT` command. Detections are evaluated via Gemini Flash. High-confidence results (>=85%) are automatically whitelisted into the global blacklist databases, notifying the admin via Telegram alerts and immediately shielding all active users.
7.  **WhatsApp-to-Web Auto-Checkout Bridge:** Converts static payment templates inside WhatsApp messages to parameterized web redirects (`/?phone=xyz`). When a user visits this URL, the landing page detects the query parameter, auto-prefills their phone details, and instantly triggers the live Razorpay billing modal overlay, eliminating user checkout friction.
8.  **Razorpay Webhook Recovery Endpoint:** Implements `/payments/webhook` listening for `payment.captured` and `order.paid` events. This ensures 100% upgrade reliability (granting premium, logging transactions, and dispatching WhatsApp confirmations) even if the customer closes their browser tab mid-upgrade.
9.  **Accumulative Expiry Stacking:** Implements dynamic subscription duration addition inside the database. When an active premium user pays for an upgrade early, the new month duration stacks on top of their remaining validity instead of overwriting it, protecting user paid time.
10. **Egress Evasion Proxy:** Automatically routes outgoing Telegram Alert API calls through the custom Google Apps Script Web App proxy (`META_API_BASE_URL`). This bypasses Hugging Face's egress container firewall which blocks direct connections to `api.telegram.org`.
11. **Hourly Memory Sweep Daemon:** Runs an automated memory sweep once per hour in the API router container, deleting visitor rate limit IP logs older than 24 hours to prevent memory leaks and container downtime.





