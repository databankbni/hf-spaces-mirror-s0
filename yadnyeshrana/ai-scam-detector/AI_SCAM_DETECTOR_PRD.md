# PRODUCT REQUIREMENTS DOCUMENT (PRD)
## AI Scam Detector - WhatsApp Integration

**Version:** 1.0  
**Date:** June 24, 2026  
**Status:** MVP - Ready for Development  
**Owner:** Engineering Team  
**Target Launch:** Week 1 (July 2026)

---

## 1. EXECUTIVE SUMMARY

### 1.1 Product Vision
Build an AI-powered WhatsApp bot that detects scam messages in real-time, protecting Indian users from financial fraud.

### 1.2 Problem Statement
- **Scope:** 500M+ Indian WhatsApp users receive 5-10 scam messages daily
- **Impact:** 3M+ Indians lose ₹2000-50K annually to fraud
- **Cost to society:** ₹1000+ crore stolen yearly through scams
- **Current solution:** None exists specifically for India on WhatsApp

### 1.3 Solution Overview
A conversational WhatsApp bot that:
1. User forwards suspicious message
2. Bot analyzes using Claude AI + scam pattern database
3. Returns risk assessment in seconds
4. Stores data for learning

### 1.4 Market Opportunity
- **TAM (Total Addressable Market):** 500M WhatsApp users × ₹199/month = ₹1,000 Cr potential market
- **SAM (Serviceable Market):** 50M users willing to pay = ₹100 Cr
- **SOM (Serviceable Obtainable Market):** Year 1 target = 10K users = ₹2.4 Cr

---

## 2. TARGET USERS

### 2.1 Primary Users
**Profile: Indian WhatsApp Users**
- Age: 18-60 years old
- Tech literacy: Basic to intermediate
- Pain point: Receiving multiple scam messages daily
- Willingness to pay: ₹199/month for security
- Geography: All Indian states, focus on Tier 2/3 cities

### 2.2 Persona: Arun (Typical User)
- Age: 35, Small business owner
- Income: ₹5-10 Lakh/year
- Phone: Basic smartphone with WhatsApp
- Problem: Lost ₹15K to fake loan scam last year
- Motivation: Never lose money to scams again
- Frequency: Uses bot 10-20 times/month

### 2.3 Secondary Users
1. **Parents:** Protecting elderly parents from fraud
2. **Job seekers:** Detecting fake job scams
3. **Young adults:** Detecting romance/relationship scams
4. **Small business owners:** Detecting fake supplier/vendor scams

### 2.4 Enterprise Users (Future)
- Fintech companies (Razorpay, Paytm, PhonePe)
- Banks (HDFC, ICICI, SBI)
- Insurance companies
- Government agencies (Police, RBI)

---

## 3. PRODUCT FEATURES

### 3.1 MVP Features (Week 1-4)

#### **Feature 1: Message Analysis**
**Description:** User forwards suspicious message → Bot analyzes → Returns risk score

**User Flow:**
```
1. User opens WhatsApp
2. Forwards message to bot (+91-XXX-XXX-XXXX)
3. Bot receives message (1-2 seconds)
4. Claude AI analyzes (2-3 seconds)
5. Bot responds with risk assessment
```

**Output Format:**
```
🚨 HIGH Risk
Confidence: 95%

Reason: Uses urgency tactics and requests OTP, 
classic banking fraud pattern

What to do:
❌ Don't click link
❌ Don't share OTP
✅ Report to bank immediately
```

**Acceptance Criteria:**
- Response time < 5 seconds
- Risk classification: HIGH/MEDIUM/LOW/SAFE
- Confidence score: 0-100%
- 1-2 sentence explanation
- Actionable recommendations

---

#### **Feature 2: Freemium Model**
**Description:** Free tier with limited checks, paid unlimited

**Free Tier:**
- 5 checks per day
- Response time: Standard
- Basic explanation
- No history tracking

**Premium Tier (₹199/month):**
- Unlimited checks
- Priority response
- Detailed explanations
- Scam history tracking
- Personalized safety tips
- 7-day free trial

**Acceptance Criteria:**
- Freemium gate works without friction
- Payment processing <5 seconds
- Trial activation automatic
- Easy upgrade in-app

---

#### **Feature 3: Scam Database**
**Description:** Database of known scams, patterns, and links

**Data Sources:**
- PhishTank API (known bad links)
- URLhaus (malicious URLs)
- Internal user reports
- News article scraping
- Twitter/X monitoring
- Reddit mining
- Police databases

**Database Schema:**
```
{
  id: unique_id,
  message_pattern: "Your account suspended",
  scam_type: "banking_fraud",
  risk_level: "HIGH",
  confidence: 95,
  examples: 10,
  last_seen: timestamp,
  phone_numbers: [...],
  urls: [...],
  keywords: [...],
  region: "India",
  language: "English/Hindi/etc"
}
```

**Acceptance Criteria:**
- Minimum 1000 scam patterns at launch
- Database updates daily
- Search by pattern/link/phone possible
- Version control on database updates

---

#### **Feature 4: WhatsApp Integration**
**Description:** Native WhatsApp bot using Gupshup API

**Technical Stack:**
- Platform: Gupshup WhatsApp Business API
- Backend: Node.js + Express
- Hosting: Railway.app
- Database: Firebase Realtime DB
- AI: Claude Haiku API

**Endpoints:**
```
POST /gupshup-webhook
- Receives message from WhatsApp
- Triggers analysis
- Sends response back

POST /check-scam
- Internal API for message analysis
- Returns risk assessment

GET /stats
- Returns usage statistics
- User count, checks performed, scams detected
```

**Acceptance Criteria:**
- Message received in <1 second
- Analysis completes in 2-3 seconds
- Response sent in <4 seconds
- 99% uptime SLA
- Handles 1000+ concurrent users

---

#### **Feature 5: User Authentication**
**Description:** Track users for premium features and analytics

**User Data Stored:**
- WhatsApp phone number
- Subscription status (free/premium)
- Checks performed
- Scams detected
- Subscription expiry date
- Payment history

**Acceptance Criteria:**
- Phone number stored securely
- No sensitive data in logs
- GDPR/data privacy compliant
- User can request data deletion
- User can view their history

---

### 3.2 Phase 2 Features (Month 2-3)

#### **Feature 6: Scam Pattern Learning**
- User reports incorrect analysis
- Feedback stored
- AI model retrains weekly
- Accuracy improves over time

#### **Feature 7: Multiple Languages**
- Support Hindi, Marathi, Tamil, Telugu
- Localized explanations
- Regional scam patterns

#### **Feature 8: User Dashboard**
- Web portal (simple landing page)
- View check history
- See detected scams
- Manage subscription
- Safety tips feed

#### **Feature 9: Android App**
- Native Android app
- Same features as WhatsApp bot
- Offline scam database
- Integration with SMS detection

### 3.3 Phase 3 Features (Month 4-6)

#### **Feature 10: Enterprise API**
- White-label integration
- For banks/fintech apps
- Custom branding
- Advanced analytics

#### **Feature 11: Community Features**
- User forums (discuss scams)
- Scam bounty program
- Top reporters leaderboard
- Community reports

---

## 4. TECHNICAL ARCHITECTURE

### 4.1 System Architecture

```
User WhatsApp Message
        ↓
   Gupshup API
   (Webhook receives message)
        ↓
   Railway Backend
   (Node.js + Express)
        ↓
   Message Parser
   (Extract keywords, links, phone numbers)
        ↓
   Database Check
   (Query known scams)
        ↓
   Claude AI Analysis
   (Run detection prompt)
        ↓
   Result Formatter
   (Create user-friendly response)
        ↓
   Firebase Logger
   (Store for analytics)
        ↓
   Gupshup API
   (Send response to user)
        ↓
   User Receives Response
   (Risk assessment + recommendations)
```

### 4.2 Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Messaging** | Gupshup WhatsApp API | Free tier, easy integration |
| **Backend** | Node.js + Express | Fast, scalable, JavaScript |
| **Hosting** | Railway.app | Free tier, auto-deploy |
| **Database** | Firebase Realtime | Real-time, free tier adequate |
| **AI** | Claude Haiku API | Cheapest, best for reasoning |
| **Payments** | Razorpay | Indian focus, 2% fee |
| **Analytics** | Simple JSON logs | Start simple, scale later |
| **Auth** | Phone number + OTP | WhatsApp native |

### 4.3 API Endpoints

```
POST /gupshup-webhook
- Input: WhatsApp message (JSON)
- Output: Sends response via Gupshup
- Rate limit: Unlimited (Gupshup handles)

POST /check-scam
- Input: { message: string, phoneNumber: string }
- Output: { riskLevel, confidence, reason }
- Rate limit: 1000/minute per user

GET /stats
- Input: None
- Output: { totalUsers, totalChecks, scamsDetected }
- Rate limit: 10/minute

POST /create-subscription
- Input: { phoneNumber, planId }
- Output: { razorpayOrderId }
- Rate limit: 100/minute

POST /verify-payment
- Input: { phoneNumber, razorpayPaymentId }
- Output: { success, message }
- Rate limit: 100/minute

GET /user-history/:phoneNumber
- Input: phoneNumber
- Output: { history: [...] }
- Auth: Required
- Rate limit: 100/minute
```

### 4.4 Database Schema

**Firebase Structure:**

```
/users/{phoneNumber}
  /premium: boolean
  /premiumExpiry: timestamp
  /checksThisMonth: number
  /createdAt: timestamp
  /lastChecked: timestamp

/checks/{phoneNumber}/{checkId}
  /message: string
  /result: object
    /riskLevel: string
    /confidence: number
    /reason: string
  /timestamp: timestamp
  /userFeedback: string (optional)

/scams/{scamId}
  /pattern: string
  /type: string
  /riskLevel: string
  /examples: number
  /lastSeen: timestamp
  /keywords: array
  /urls: array
  /phoneNumbers: array

/analytics/daily/{date}
  /totalChecks: number
  /highRiskDetected: number
  /newUsers: number
  /premiumConversions: number
```

### 4.5 Data Flow

```
1. User → WhatsApp: Forwards message
2. WhatsApp → Gupshup: Message routed
3. Gupshup → Railway: Webhook call
4. Railway → Firebase: Store message + user
5. Railway → Claude: Send for analysis
6. Claude → Railway: Return analysis
7. Railway → Firebase: Store result
8. Railway → Gupshup: Send response
9. Gupshup → WhatsApp: Response delivered
10. Firebase → Analytics: Log event
```

---

## 5. SUCCESS METRICS

### 5.1 Key Performance Indicators (KPIs)

#### **User Metrics**
| Metric | Target Week 4 | Target Month 3 | Success Criteria |
|--------|---------------|----------------|------------------|
| Total Users | 500 | 10K | >50% MoM growth |
| Active Users | 200 | 5K | 50%+ daily active |
| Premium Users | 10 | 500 | 5%+ conversion |
| DAU (Daily Active) | 100 | 3K | Growing consistently |
| MAU (Monthly Active) | 200 | 5K | 60%+ retention |

#### **Product Metrics**
| Metric | Target | Success Criteria |
|--------|--------|------------------|
| Avg checks/user/month | 15 | >10 |
| Response time | <4 seconds | P95 latency <5s |
| Accuracy (correct risk assessment) | 90% | Improve by 2% monthly |
| False positives | <5% | Users can appeal |
| Uptime | 99% | <1 hour downtime/month |

#### **Revenue Metrics**
| Metric | Target Month 1 | Target Month 3 | Success Criteria |
|--------|----------------|----------------|------------------|
| Monthly Revenue | ₹2K-5K | ₹1L+ | Growing 100%+ MoM |
| ARPU | ₹199 | ₹199 | Consistent |
| Premium Conversion | 2% | 5% | Doubling quarterly |
| LTV (Lifetime Value) | ₹2000 | ₹3000 | Improving |
| CAC (Customer Acquisition Cost) | ₹0 | ₹100-200 | <20% of LTV |

#### **Viral Metrics**
| Metric | Target | Success Criteria |
|--------|--------|------------------|
| Viral coefficient | 0.3 | Each user brings 0.3 users |
| Share rate | 20% | 1 in 5 users share |
| Word-of-mouth signups | 30% | Growing over time |
| Social media mentions | 50+ | /month by month 3 |

### 5.2 Health Metrics

| Metric | Red (Bad) | Yellow (Caution) | Green (Good) |
|--------|-----------|-----------------|-------------|
| **Response Time** | >10s | 5-10s | <4s |
| **Uptime** | <95% | 95-99% | >99% |
| **Accuracy** | <80% | 80-90% | >90% |
| **Premium Conversion** | <1% | 1-3% | >5% |
| **Retention (1-month)** | <30% | 30-60% | >60% |
| **Refund Rate** | >10% | 5-10% | <5% |

### 5.3 Success Definition (Launch Success)

**Week 1 Launch Success:**
- ✅ 100+ beta users
- ✅ <4 second response time
- ✅ >85% accuracy
- ✅ >99% uptime
- ✅ Zero critical bugs

**Month 1 Success:**
- ✅ 1000+ users
- ✅ 10+ premium subscribers
- ✅ ₹2000+ MRR
- ✅ <5% churn rate
- ✅ 3-4 social media viral mentions

**Month 3 Success:**
- ✅ 10K+ users
- ✅ 500+ premium subscribers
- ✅ ₹1L+ MRR
- ✅ >90% accuracy
- ✅ First enterprise deal

---

## 6. MONETIZATION STRATEGY

### 6.1 Revenue Models

#### **Model 1: Freemium (Primary)**
- **Free tier:** 5 checks/day
- **Premium tier:** ₹199/month = unlimited
- **Free trial:** 7 days
- **Expected conversion:** 2-5%

**Revenue calculation:**
- 10K users × 3% conversion = 300 premium users
- 300 × ₹199 = ₹59,700/month

#### **Model 2: Enterprise (B2B)**
- **Fintech companies:** ₹25L-50L/month
- **Banks:** ₹50L-1Cr/month
- **Insurance companies:** ₹20L-50L/month
- **API access:** ₹0.50-1 per check

**Revenue calculation (Month 6):**
- 5 fintech clients × ₹35L = ₹1.75 Cr
- 100K API checks × ₹0.50 = ₹50K

#### **Model 3: Affiliate (Secondary)**
- Partner with: VPN, password managers, insurance
- Commission: 20-30%
- Expected revenue: ₹20K-50K/month by month 3

### 6.2 Pricing Strategy

**Consumer Pricing:**
```
Free Tier: ₹0/month
- 5 checks/day
- Standard response
- Basic explanation

Premium Tier: ₹199/month
- Unlimited checks
- Priority processing
- Detailed explanations
- Check history
- Personalized tips
- 7-day free trial
```

**Rationale:**
- ₹199 is sweet spot (accessible, profitable)
- 2-5% conversion is realistic for security tools
- Free trial removes purchase friction
- Annual option: ₹1999 (saves ₹390)

---

## 7. GO-TO-MARKET STRATEGY

### 7.1 Launch Phases

#### **Phase 1: Soft Launch (Week 1-2)**
**Goal:** Get first 200 beta users, validate product

**Activities:**
- Share bot with 20 close friends
- Gather feedback
- Fix bugs
- Refine messaging
- Prepare launch materials

**Channels:**
- WhatsApp status to friends
- Close community groups
- Discord servers

**Success metric:** 200 beta users, zero critical bugs

---

#### **Phase 2: Hard Launch (Week 3-4)**
**Goal:** Reach 1000 users, get viral traction

**Activities:**
- Post on Reddit: r/India, r/bangalore, r/IndianEnts
- Share in Facebook groups: Tech, security, complaints
- Tweet on Twitter: "Forward scam messages to our bot"
- Email outreach to cybersecurity enthusiasts
- Press release to tech blogs

**Channels:**
- **Reddit:** 5 posts in relevant subreddits
- **Twitter:** Daily tweets, thread about scams
- **Facebook:** 20 tech/security groups
- **WhatsApp:** Forward in security groups
- **Email:** Contact tech bloggers

**Success metric:** 1000+ users, 10+ news mentions

---

#### **Phase 3: Growth (Month 2)**
**Goal:** 5000+ users, get first enterprise interest

**Activities:**
- Content marketing: Blog posts on scam detection
- Influencer outreach (security YouTubers)
- Paid ads (Google, Facebook) if needed
- Partnerships with fintech companies
- University outreach (college groups)

**Channels:**
- YouTube: Feature in tech channels
- Blogs: Submit guest articles
- Partnerships: Security platforms
- Ads: Google Ads, Facebook (₹20K budget)

**Success metric:** 5000+ users, 100+ premium, 1 enterprise meeting

---

#### **Phase 4: Scale (Month 3-6)**
**Goal:** 10K+ users, 5+ enterprise clients, ₹1L+/month

**Activities:**
- Regional language support
- Android app launch
- Enterprise sales team
- PR campaign in major publications
- Government relations (RBI, police)

---

### 7.2 Marketing Channels (Priority)

| Channel | Effort | Cost | ROI | Timeline | Priority |
|---------|--------|------|-----|----------|----------|
| **Reddit** | Low | ₹0 | High | Week 1 | 🔴 P0 |
| **Twitter** | Low | ₹0 | Medium | Week 1 | 🔴 P0 |
| **WhatsApp Groups** | Medium | ₹0 | High | Week 1 | 🔴 P0 |
| **Facebook Groups** | Medium | ₹0 | Medium | Week 2 | 🟡 P1 |
| **YouTube Tech** | Medium | ₹0 | Medium | Week 2 | 🟡 P1 |
| **Google Ads** | Medium | ₹10K | Medium | Month 2 | 🟡 P1 |
| **Blog/Content** | High | ₹0 | High | Month 2 | 🟡 P1 |
| **Partnerships** | High | ₹0 | Very High | Month 3 | 🟢 P2 |

### 7.3 Key Messages

**For Users:**
```
"Protect yourself from ₹50K+ scams"
"Forward suspicious messages, get instant analysis"
"₹199/month for peace of mind"
"Used by 10K+ Indians"
```

**For Enterprises:**
```
"Protect your users from fraud"
"White-label scam detection for your platform"
"₹25L-1Cr/month for enterprise plans"
"Reduce fraud losses by 80%"
```

---

## 8. IMPLEMENTATION TIMELINE

### 8.1 Development Timeline

| Week | Task | Owner | Status |
|------|------|-------|--------|
| **Week 1** | Setup backend + Gupshup integration | Dev | 🟢 Ready |
| **Week 1** | Database setup + Firebase | Dev | 🟢 Ready |
| **Week 1** | Claude API integration | Dev | 🟢 Ready |
| **Week 1** | Landing page + legal docs | Design | 🟢 Ready |
| **Week 2** | Testing + bug fixes | QA | 📝 To-do |
| **Week 2** | Razorpay payment integration | Dev | 📝 To-do |
| **Week 2** | Premium tier implementation | Dev | 📝 To-do |
| **Week 3** | Beta launch + user onboarding | Marketing | 📝 To-do |
| **Week 3** | Analytics + monitoring setup | Dev | 📝 To-do |
| **Week 4** | Public launch + PR | Marketing | 📝 To-do |

### 8.2 Detailed Week 1 Checklist

**Day 1-2: Setup Infrastructure**
- [ ] Create GitHub repository
- [ ] Deploy to Railway.app
- [ ] Setup Firebase project
- [ ] Create Gupshup WhatsApp bot account

**Day 3-4: Implement Core Logic**
- [ ] Implement /check-scam endpoint
- [ ] Integrate Claude API
- [ ] Setup message parsing
- [ ] Create response formatter

**Day 5-6: Integration & Testing**
- [ ] Connect Gupshup webhook
- [ ] End-to-end testing
- [ ] Test with 10 sample messages
- [ ] Performance benchmarking

**Day 7: Prepare for Beta**
- [ ] Documentation
- [ ] Create landing page
- [ ] Prepare WhatsApp bot description
- [ ] Test with 5 friends

### 8.3 Month Timeline

```
Week 1: MVP launch (200 beta users)
Week 2-3: Growth phase (1000 users)
Week 4: Add payment (50 premium users)
Month 2: Enterprise outreach (5000 users)
Month 3: Scaling (10K users, 500 premium)
```

---

## 9. RISK ANALYSIS & MITIGATION

### 9.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| **Claude API rate limits** | Medium | High | Cache results, queue system |
| **Gupshup goes down** | Low | High | Build SMS fallback, build Android app |
| **False positives (accuracy)** | High | Medium | User feedback loop, continuous retraining |
| **Performance issues at scale** | Medium | High | Load testing, Redis caching |
| **Data privacy breach** | Low | Very High | Encryption, GDPR compliance, audits |

### 9.2 Market Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| **Competitor launches** | High | Medium | First-mover advantage, network effects |
| **WhatsApp API changes** | Medium | High | Build Android app parallel |
| **User adoption slow** | Medium | High | Aggressive marketing, referral program |
| **Low premium conversion** | Medium | Medium | Better onboarding, value demo |
| **Regulatory issues** | Low | Very High | Legal review, privacy focus |

### 9.3 Business Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| **Enterprise deals fall through** | Medium | Medium | Diversify revenue, focus on users |
| **Churn rate too high** | Low | Medium | Improve product, support |
| **CAC > LTV** | Low | High | Organic growth focus, referrals |
| **Difficult to find team members** | High | Medium | Build solo initially, hire later |

---

## 10. SUCCESS CRITERIA & EXIT STRATEGY

### 10.1 MVP Success Criteria

**✅ MVP Success = Launch without bugs + 200 beta users + <4 second response**

### 10.2 6-Month Success Criteria

- 10,000+ total users
- 500+ premium subscribers
- ₹1L+ monthly revenue
- >90% detection accuracy
- <5% monthly churn
- 1-2 enterprise partnerships

### 10.3 12-Month Goals

- 100K+ users
- 5K+ premium subscribers
- ₹1 Cr+ annual revenue
- 5-10 enterprise clients
- Regional language support
- Android app with 100K+ downloads

### 10.4 Potential Exit Scenarios

**Scenario 1: Acquisition (Most likely)**
- Acquire by: Google, Meta, WhatsApp, Razorpay, Paytm
- Valuation: $2-10M USD
- Timeline: 18-24 months

**Scenario 2: Independent Growth**
- Build to ₹10 Cr+ annual revenue
- 200K+ users, 20K+ premium
- Remain independent

**Scenario 3: B2B Focus**
- Pivot to enterprise sales
- Sell to banks, fintech, government
- Build enterprise SaaS (₹10-50 Cr+ valuation)

---

## 11. APPENDIX

### 11.1 Competitive Analysis

| Feature | Us | TrueCaller | WhatsApp Safety | Google Safe |
|---------|-----|-----------|-----------------|------------|
| **WhatsApp integration** | ✅ | ❌ | Limited | ❌ |
| **India-specific** | ✅ | Partial | ❌ | ❌ |
| **Affordable** | ✅ | Medium | ❌ | ❌ |
| **Message analysis** | ✅ | Call only | Limited | ❌ |
| **AI-powered** | ✅ | Rules-based | Basic | ✅ |
| **Enterprise API** | ✅ | ❌ | ❌ | ❌ |

### 11.2 User Interview Insights

**Quote 1:** "I lost ₹50K to a fake loan scam last year. I would pay ₹200/month to never let that happen again."

**Quote 2:** "I get 20+ WhatsApp scams daily. I have no way to know which are real."

**Quote 3:** "I'm scared to click links on WhatsApp. An instant verification tool would be amazing."

### 11.3 Glossary

- **DAU:** Daily Active Users
- **MAU:** Monthly Active Users
- **MRR:** Monthly Recurring Revenue
- **LTV:** Lifetime Value
- **CAC:** Customer Acquisition Cost
- **ARR:** Annual Recurring Revenue
- **ARPU:** Average Revenue Per User
- **Churn:** % of users who cancel subscription

### 11.4 Resources

**Code Repository:** GitHub (scam-detector-mvp)  
**Deployment:** Railway.app  
**API Documentation:** see DEPLOYMENT_GUIDE.md  
**Feedback Form:** [link to form]  
**Bug Reporting:** GitHub issues  

---

## 12. SIGN-OFF

| Role | Name | Date | Signature |
|------|------|------|-----------|
| **Product Manager** | - | - | - |
| **Engineering Lead** | - | - | - |
| **Marketing Lead** | - | - | - |
| **Finance/Legal** | - | - | - |

---

## DOCUMENT HISTORY

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | June 24, 2026 | Team | Initial PRD |

---

**Questions? Comments? Issues? Create GitHub issue or email team.**

**Next Review Date:** July 15, 2026 (After MVP launch)

