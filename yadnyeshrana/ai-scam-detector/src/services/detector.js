const { GoogleGenAI } = require('@google/generative-ai');
const axios = require('axios');
const crypto = require('crypto');
const dbService = require('./db');

// In-memory caches to prevent Gemini and redirect query quota abuse (Free-tier optimizations)
const analysisCache = new Map();
const urlRedirectCache = new Map();
const CACHE_EXPIRY_MS = 60 * 60 * 1000;       // 1 Hour TTL for scan checks
const URL_CACHE_EXPIRY_MS = 6 * 60 * 60 * 1000; // 6 Hours TTL for redirect chains

function getQueryCacheKey(text, imageMedia) {
  let input = text || '';
  if (imageMedia && imageMedia.data) {
    input += '_' + crypto.createHash('md5').update(imageMedia.data).digest('hex');
  }
  return crypto.createHash('sha256').update(input).digest('hex');
}

// Initialize Gemini API client if API key is provided and not default
const geminiApiKey = process.env.GEMINI_API_KEY;
const isGeminiConfigured = !!geminiApiKey && geminiApiKey !== 'your_gemini_api_key_here';

let genAI = null;
if (isGeminiConfigured) {
  try {
    // Note: The @google/generative-ai SDK typically uses a direct client or GoogleGenAI class depending on version.
    // In latest SDK, we initialize it using GoogleGenAI or GoogleGenerativeAI. Let's support standard GoogleGenerativeAI from package.
    const { GoogleGenerativeAI } = require('@google/generative-ai');
    genAI = new GoogleGenerativeAI(geminiApiKey);
    console.log('🤖 Gemini 1.5 Flash Service initialized');
  } catch (error) {
    console.error('⚠️ Failed to initialize Gemini client:', error.message);
  }
}

/**
 * Extract URLs from text message
 */
function extractUrls(text) {
  const urlRegex = /(https?:\/\/[^\s]+)/gi;
  return text.match(urlRegex) || [];
}

/**
 * Resolve single URL redirect chains (up to 3 hops)
 */
async function resolveUrl(url) {
  const cached = urlRedirectCache.get(url);
  if (cached && (Date.now() - cached.timestamp < URL_CACHE_EXPIRY_MS)) {
    return cached.resolved;
  }

  const saveToCache = (resolved) => {
    urlRedirectCache.set(url, { timestamp: Date.now(), resolved });
    return resolved;
  };

  try {
    // Follow redirect chains up to 3 hops using HEAD
    const response = await axios.head(url, {
      maxRedirects: 3,
      timeout: 1500,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
      }
    });
    return saveToCache(response.request.res.responseUrl || url);
  } catch (err) {
    // If it is a timeout, network offline or DNS failure, do not attempt GET fallback (saves ~6 seconds)
    const isNetworkError = err.code === 'ECONNABORTED' || 
                          err.code === 'ENOTFOUND' || 
                          err.message.includes('timeout') || 
                          err.message.includes('Network Error');
    if (isNetworkError) {
      return saveToCache(url);
    }

    try {
      // Fallback to GET for services blocking HEAD requests (e.g. 405 Method Not Allowed)
      const response = await axios.get(url, {
        maxRedirects: 3,
        timeout: 1500,
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
      });
      return saveToCache(response.request.res.responseUrl || url);
    } catch (e) {
      return saveToCache(url); // fallback to original URL on network error
    }
  }
}

/**
 * Resolve all URLs in a text body concurrently
 */
async function resolveAllUrls(text) {
  if (!text) return text;
  const urls = extractUrls(text);
  if (urls.length === 0) return text;

  let resolvedText = text;
  try {
    const resolutions = await Promise.all(
      urls.map(async (url) => {
        const resolved = await resolveUrl(url);
        return { original: url, resolved };
      })
    );

    for (const { original, resolved } of resolutions) {
      if (original !== resolved) {
        resolvedText = resolvedText.replaceAll(original, resolved);
      }
    }
  } catch (e) {
    console.error('Error resolving redirect URLs:', e.message);
  }
  return resolvedText;
}

/**
 * Extract Indian phone numbers from text message
 */
function extractPhoneNumbers(text) {
  // Regex targeting standard 10 digit Indian numbers, optionally prefixed with +91 or 91 or 0
  const phoneRegex = /(?:\+?91|0)?[6-9]\d{9}/g;
  return text.match(phoneRegex) || [];
}

// Cached compiled Heuristics Regex Engine
let cachedScamsList = null;
let compiledPhraseRegex = null;
let compiledUrlRegex = null;
let compiledPhoneRegex = null;

// Maps to look up original scam records by lowercase keys
const phraseToScamMap = new Map();
const urlToScamMap = new Map();
const phoneToScamMap = new Map();

function escapeRegExp(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Compile or recompile the cached search indexes when known scams change
 */
function compileSearchIndexes(scamsList) {
  cachedScamsList = scamsList;
  phraseToScamMap.clear();
  urlToScamMap.clear();
  phoneToScamMap.clear();

  const escapedPhrases = [];
  const escapedUrls = [];
  const escapedPhones = [];

  for (const scam of scamsList) {
    // 1. Process phrase patterns
    if (scam.pattern) {
      const cleanPattern = scam.pattern.trim().toLowerCase();
      // Avoid compiling extremely short phrases to prevent false-positives
      if (cleanPattern.length > 5) {
        phraseToScamMap.set(cleanPattern, scam);
        escapedPhrases.push(escapeRegExp(cleanPattern));
      }
    }

    // 2. Process URLs
    if (scam.urls && Array.isArray(scam.urls)) {
      for (const url of scam.urls) {
        const cleanUrl = url.trim().toLowerCase();
        if (cleanUrl) {
          urlToScamMap.set(cleanUrl, scam);
          escapedUrls.push(escapeRegExp(cleanUrl));
        }
      }
    }

    // 3. Process Phone Numbers
    if (scam.phoneNumbers && Array.isArray(scam.phoneNumbers)) {
      for (const phone of scam.phoneNumbers) {
        const cleanPhone = phone.trim().toLowerCase();
        if (cleanPhone) {
          phoneToScamMap.set(cleanPhone, scam);
          escapedPhones.push(escapeRegExp(cleanPhone));
        }
      }
    }
  }

  // Compile RegExp objects
  compiledPhraseRegex = escapedPhrases.length > 0 ? new RegExp(escapedPhrases.join('|'), 'i') : null;
  compiledUrlRegex = escapedUrls.length > 0 ? new RegExp(escapedUrls.join('|'), 'i') : null;
  compiledPhoneRegex = escapedPhones.length > 0 ? new RegExp(escapedPhones.join('|'), 'i') : null;

  console.log(`⚡ Heuristics search index compiled: ${phraseToScamMap.size} phrases, ${urlToScamMap.size} URLs, ${phoneToScamMap.size} phone numbers.`);
}

/**
 * Fast-path local heuristics check.
 * Compares URLs/phone numbers/phrases against database of known scams.
 */
async function runHeuristicsCheck(text) {
  const lowerText = text.toLowerCase();

  const knownScams = await dbService.getKnownScams();
  if (!cachedScamsList || cachedScamsList.length !== knownScams.length) {
    compileSearchIndexes(knownScams);
  }

  // 1. Check for known scam URLs
  if (compiledUrlRegex) {
    const match = lowerText.match(compiledUrlRegex);
    if (match) {
      const matchedUrl = match[0].toLowerCase();
      const scam = urlToScamMap.get(matchedUrl);
      if (scam) {
        return {
          riskLevel: 'HIGH',
          confidence: 99,
          type: scam.type || 'known_fraud_url',
          explanation: `This URL (${matchedUrl}) has been flagged in our database as part of a scam: "${scam.pattern}".`,
          actions: [
            '❌ DO NOT click this link under any circumstances!',
            '❌ DO NOT share any personal info or OTPs on this site.',
            '✅ Report and block this sender on WhatsApp.'
          ],
          source: 'heuristics_url'
        };
      }
    }
  }

  // 2. Check for known scam phone numbers
  if (compiledPhoneRegex) {
    const match = lowerText.match(compiledPhoneRegex);
    if (match) {
      const matchedPhone = match[0].toLowerCase();
      const scam = phoneToScamMap.get(matchedPhone);
      if (scam) {
        return {
          riskLevel: 'HIGH',
          confidence: 99,
          type: scam.type || 'known_fraud_phone',
          explanation: `This phone number (${matchedPhone}) matches a reported scam sender in our database: "${scam.pattern}".`,
          actions: [
            `❌ DO NOT call or message ${matchedPhone}.`,
            '❌ DO NOT trust instructions from this contact.',
            '✅ Block and report this number immediately.'
          ],
          source: 'heuristics_phone'
        };
      }
    }
  }

  // 3. Check for blacklisted text phrases / patterns
  if (compiledPhraseRegex) {
    const match = lowerText.match(compiledPhraseRegex);
    if (match) {
      const matchedPhrase = match[0].toLowerCase();
      let scam = phraseToScamMap.get(matchedPhrase);
      if (!scam) {
        // Fallback for partial keyword overlapping
        for (const [key, val] of phraseToScamMap.entries()) {
          if (matchedPhrase.includes(key) || key.includes(matchedPhrase)) {
            scam = val;
            break;
          }
        }
      }

      if (scam) {
        return {
          riskLevel: 'HIGH',
          confidence: 99,
          type: scam.type || 'known_fraud_phrase',
          explanation: `This message contains a text phrase matched against a confirmed scam pattern in our database: "${scam.pattern}".`,
          actions: [
            '❌ DO NOT click any links in this message.',
            '❌ DO NOT share personal details or OTPs.',
            '✅ Block and report this sender on WhatsApp immediately.'
          ],
          source: 'heuristics_phrase'
        };
      }
    }
  }

  return null;
}

/**
 * Run Gemini scam analysis on the forwarded message or image document.
 */
async function runAiAnalysis(text, imagePart = null) {
  const systemPrompt = `You are the core detection engine of "AI Scam Detector," a service protecting Indian WhatsApp users from financial fraud and online scams.
Analyze the provided forwarded text message or image document and classify its risk level.

Target scams common in India:
- Utility bill fraud (e.g., electricity disconnection alerts)
- Banking/KYC fraud (e.g., account blocked, update PAN/Aadhaar card, fake SBI/HDFC text)
- KBC lottery/lucky draw fraud (e.g., Amitabh Bachchan images, ₹25 Lakhs WhatsApp lottery win)
- Part-time job fraud (e.g., earn ₹3000-5000 daily by liking YouTube videos/subscribing to Telegram)
- Parcel/Customs fraud (e.g., FedEx/DHL parcel detained, Delhi Police fake arrest threats)
- Urgent family distress scams (e.g., "Dad, I lost my phone, please UPI ₹5000 to this number")
- Unofficial loan apps scams (e.g., get ₹50,000 instant loan, click link)

Visual scam indicators (if an image document is provided):
- QR codes with text claiming "Scan to receive payment / cash back" (this is always a scam; scanning a QR code only deducts money).
- Fake official letters, notices, or arrest warrants bearing logos of RBI, CBI, Customs, Police, or banks (often containing grammatical errors, unofficial fonts, or urgent warnings).
- Fake scratch cards or lottery certificates with prize amounts (e.g., KBC ₹25L).
- Fake payment receipts (e.g., simulated Google Pay/Paytm transactions sent to convince you that money was transferred).

Language notes:
The text may be in English, Hindi, Hinglish (Hindi words written in English letters, e.g., "aapka account block ho gaya hai"), or regional languages (Marathi, Tamil, Telugu, Bengali). Treat mixed language texts as standard inputs.

You MUST respond with a valid, clean JSON object ONLY. Do not include any markdown styling, backticks, or explanation text outside the JSON.

Response JSON Schema:
{
  "riskLevel": "HIGH" | "MEDIUM" | "LOW" | "SAFE",
  "confidence": number (between 0 and 100 representing percentage confidence),
  "type": "utility_bill_fraud" | "banking_fraud" | "lottery_fraud" | "job_fraud" | "customs_fraud" | "loan_fraud" | "family_distress" | "safe_message" | "other_fraud",
  "explanation": "A concise 1-2 sentence explanation in simple English summarizing why this is or isn't a scam, highlighting specific red flags (like urgent language, demands for money, OTP request, unofficial URLs, or fake visual elements).",
  "actions": [
    "A list of 2-4 direct actionable steps for the user based on the classification."
  ]
}`;

  if (!isGeminiConfigured || !genAI) {
    // Local mock detection fallback if Gemini is not configured
    return runMockAnalysis(text, !!imagePart);
  }

  try {
    const model = genAI.getGenerativeModel({
      model: 'gemini-2.5-flash',
      systemInstruction: systemPrompt
    }, { apiVersion: 'v1beta' });

    const promptText = `Analyze the following message forwarded by a user:
---
${text || "[No caption text provided; analyze the attached image document for scam indicators]"}
---`;

    const parts = [
      { text: promptText }
    ];

    if (imagePart) {
      parts.push(imagePart);
    }

    let result = null;
    let attempts = 3;
    let lastError = null;

    for (let i = 0; i < attempts; i++) {
      try {
        result = await model.generateContent({
          contents: [
            { role: 'user', parts }
          ],
          generationConfig: {
            responseMimeType: 'application/json'
          }
        });
        break; // Success! Exit retry loop
      } catch (err) {
        lastError = err;
        console.warn(`⚠️ Gemini API call failed (Attempt ${i + 1}/${attempts}):`, err.message);
        if (i < attempts - 1) {
          // Wait 1 second before retrying
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      }
    }

    if (!result) {
      throw lastError || new Error('Failed to query Gemini API after multiple attempts.');
    }

    const responseText = result.response.text();
    let cleanJsonText = responseText.trim();
    if (cleanJsonText.startsWith('```')) {
      cleanJsonText = cleanJsonText.replace(/^```(?:json)?/i, '').replace(/```$/i, '').trim();
    }
    
    return JSON.parse(cleanJsonText);
  } catch (error) {
    console.error('❌ Gemini API Error, triggering caution fallback:', error.message);
    // If Gemini is configured but failed, return a defensive UNKNOWN caution warning to protect the user
    return {
      riskLevel: 'UNKNOWN',
      confidence: 0,
      type: 'other_fraud',
      explanation: '⚠️ [AI CONNECTION ERROR] Our real-time AI scanner is temporarily offline due to high traffic or connection limits. We could not verify this message.',
      actions: [
        '⚠️ Treat this message with extreme caution.',
        '❌ DO NOT click any links, scan QR codes, or share OTPs.',
        '✅ Try scanning this message again in a few minutes.'
      ]
    };
  }
}

/**
 * Heuristics-based mock analysis when Gemini is unavailable.
 */
function runMockAnalysis(text, hasImage = false) {
  if (hasImage) {
    return {
      riskLevel: 'HIGH',
      confidence: 85,
      type: 'other_fraud',
      explanation: '[MOCK IMAGE ANALYSIS] Scanned the attached document/image. It appears to contain a suspicious QR code, lottery claim, or unauthorized official letterhead, which is heavily associated with online financial fraud.',
      actions: [
        '❌ DO NOT scan any QR codes shown in the image to "receive" funds.',
        '❌ DO NOT pay processing fees or verify details using contacts listed in the document.',
        '✅ Double-check with the official organization (bank, electricity board, police) directly.'
      ]
    };
  }

  const lowerText = text ? text.toLowerCase() : '';
  if (!lowerText) {
    return {
      riskLevel: 'SAFE',
      confidence: 70,
      type: 'safe_message',
      explanation: '[MOCK ANALYSIS] No message content provided for evaluation.',
      actions: ['✅ Send a text message or forward a suspicious scam message to analyze.']
    };
  }
  
  // 1. Utility Bill
  if (lowerText.includes('electricity') || lowerText.includes('power cut') || lowerText.includes('disconnection') || lowerText.includes('bill officer')) {
    return {
      riskLevel: 'HIGH',
      confidence: 90,
      type: 'utility_bill_fraud',
      explanation: '[MOCK ANALYSIS] This message threatens disconnection of your power supply. Real utility companies never message from personal mobile numbers or request payments via random WhatsApp links.',
      actions: [
        '❌ DO NOT call the mobile number listed.',
        '❌ DO NOT share your Consumer ID or make payments.',
        '✅ Verify via your electricity provider\'s official app or website.'
      ]
    };
  }

  // 2. KBC / Lottery
  if (lowerText.includes('lottery') || lowerText.includes('kbc') || lowerText.includes('lucky draw') || lowerText.includes('25 lakh') || lowerText.includes('rana pratap')) {
    return {
      riskLevel: 'HIGH',
      confidence: 95,
      type: 'lottery_fraud',
      explanation: '[MOCK ANALYSIS] Promotes a fake KBC lottery or lucky draw. This is a common fraud scheme where scammers ask you to pay processing fees or GST to release fake winnings.',
      actions: [
        '❌ DO NOT pay any registration or processing fees.',
        '❌ DO NOT share bank account or Aadhaar details.',
        '✅ Report and block the contact on WhatsApp.'
      ]
    };
  }

  // 3. Bank / KYC
  if (lowerText.includes('sbi') || lowerText.includes('kyc') || lowerText.includes('blocked') || lowerText.includes('yono') || lowerText.includes('pan card') || lowerText.includes('hdfc') || lowerText.includes('icici')) {
    return {
      riskLevel: 'HIGH',
      confidence: 88,
      type: 'banking_fraud',
      explanation: '[MOCK ANALYSIS] Alerts that your bank account is blocked and requests urgent KYC update. Real banks never send update links via SMS/WhatsApp from personal 10-digit numbers.',
      actions: [
        '❌ DO NOT click on the link in the message.',
        '❌ DO NOT enter your netbanking password, OTP, or PIN on any external site.',
        '✅ Call your bank\'s official customer service helpline to check.'
      ]
    };
  }

  // 4. Job
  if (lowerText.includes('part-time') || lowerText.includes('part time') || lowerText.includes('earn daily') || lowerText.includes('telegram task') || lowerText.includes('like video')) {
    return {
      riskLevel: 'HIGH',
      confidence: 92,
      type: 'job_fraud',
      explanation: '[MOCK ANALYSIS] Offers high pay for simple online tasks (like liking videos or subbing channels). These lead to prepaid task scams where they demand money before releasing earnings.',
      actions: [
        '❌ DO NOT pay any deposit to get tasks or release payments.',
        '❌ DO NOT join telegram groups recommended in the message.',
        '✅ Ignore these work-from-home offers as they are fraudulent.'
      ]
    };
  }

  // Default Safe/Low Risk response
  return {
    riskLevel: 'SAFE',
    confidence: 70,
    type: 'safe_message',
    explanation: '[MOCK ANALYSIS] No immediate scam indicators (such as urgency, OTP request, lottery wins, or blacklisted links) were detected in this message.',
    actions: [
      '✅ This message appears safe, but always remain cautious when sharing details.',
      '✅ If this message contains links you did not expect, avoid opening them.'
    ]
  };
}

/**
 * Main detection process: Heuristics first, then LLM/Mock analysis.
 */
async function detectScam(text, phoneNumber, imageMedia = null) {
  const startTime = Date.now();

  if ((!text || text.trim() === '') && !imageMedia) {
    return {
      riskLevel: 'SAFE',
      confidence: 100,
      type: 'safe_message',
      explanation: 'No message or image content provided for evaluation.',
      actions: ['✅ Send a text message or forward a suspicious scam message or image to analyze.']
    };
  }

  // Resolve deep links / redirect chains before running heuristics or AI
  const tUrlStart = Date.now();
  const resolvedText = await resolveAllUrls(text);
  const tUrls = Date.now() - tUrlStart;

  // Check query analysis cache
  const cacheKey = getQueryCacheKey(resolvedText, imageMedia);
  const cached = analysisCache.get(cacheKey);
  if (cached && (Date.now() - cached.timestamp < CACHE_EXPIRY_MS)) {
    console.log('⚡ Returning cached analysis result (bypassing Gemini API).');
    cached.result.timings = {
      total: Date.now() - startTime,
      urls: tUrls,
      cached: true
    };
    return cached.result;
  }

  // Step A: Heuristics Matcher (Fast path, text only)
  const tHeuristicsStart = Date.now();
  let heuristicsResult = null;
  if (resolvedText && resolvedText.trim() !== '') {
    heuristicsResult = await runHeuristicsCheck(resolvedText);
  }
  const tHeuristics = Date.now() - tHeuristicsStart;
  
  if (heuristicsResult) {
    heuristicsResult.timings = {
      total: Date.now() - startTime,
      urls: tUrls,
      heuristics: tHeuristics,
      cached: false
    };
    analysisCache.set(cacheKey, { timestamp: Date.now(), result: heuristicsResult });
    return heuristicsResult;
  }

  // Step B: Formulate image parts if provided
  let imagePart = null;
  if (imageMedia && imageMedia.data && imageMedia.mimeType) {
    imagePart = {
      inlineData: {
        data: imageMedia.data,
        mimeType: imageMedia.mimeType
      }
    };
  }

  // Step C: AI / Mock Analysis (pass imagePart) using resolved text
  const tAiStart = Date.now();
  const analysisResult = await runAiAnalysis(resolvedText, imagePart);
  const tAi = Date.now() - tAiStart;

  // Store in cache
  analysisCache.set(cacheKey, {
    timestamp: Date.now(),
    result: analysisResult
  });

  // Step D: If analysis flags a new high risk scam, register it in our database automatically
  if (analysisResult.riskLevel === 'HIGH' && resolvedText && resolvedText.trim() !== '') {
    try {
      const urls = extractUrls(resolvedText);
      const phones = extractPhoneNumbers(resolvedText);
      
      // Clean up pattern snippet
      const patternSnippet = resolvedText.length > 60 ? resolvedText.substring(0, 60) + '...' : resolvedText;
      
      await dbService.addKnownScam({
        pattern: patternSnippet,
        type: analysisResult.type,
        riskLevel: analysisResult.riskLevel,
        keywords: resolvedText.split(' ').filter(word => word.length > 5).slice(0, 5),
        urls,
        phoneNumbers: phones
      });
    } catch (e) {
      console.error('Error auto-registering scam pattern:', e.message);
    }
  }

  analysisResult.timings = {
    total: Date.now() - startTime,
    urls: tUrls,
    heuristics: tHeuristics,
    ai: tAi,
    cached: false
  };

  return analysisResult;
}

/**
 * Analyze a user-submitted scam report using Gemini
 */
async function analyzeUserReport(text, imagePart = null) {
  if (!isGeminiConfigured || !genAI) {
    return { isScam: false, confidence: 0, category: 'Unknown', pattern: '' };
  }

  const systemPrompt = `You are the Security Lead for AI Scam Detector.
Analyze the following user-submitted scam report.
Determine if it is a clear, unambiguous scam/fraud attempt (phishing links, fake jobs, lottery scams, support impersonations, financial fraud).

Return a JSON object exactly matching this schema:
{
  "isScam": boolean,
  "confidence": number (0-100),
  "category": string (e.g. "UPI Fraud", "Phishing Link", "Job Scam", "Impersonation", "Lottery Scam"),
  "pattern": string (the exact domain name, phone number, UPI ID, or unique phrase pattern to add to the blacklist. Keep it simple and unique. If it is a full URL, extract the root domain. If it is a UPI ID, extract the UPI ID. If it is a phone number, extract the phone number. Only return a pattern if isScam is true).
}`;

  try {
    const model = genAI.getGenerativeModel({
      model: 'gemini-2.5-flash',
      systemInstruction: systemPrompt
    });

    const promptText = `Analyze the following user scam report:
---
${text || "[No caption text provided; analyze the attached image document for scam indicators]"}
---`;

    const parts = [
      { text: promptText }
    ];

    if (imagePart) {
      parts.push(imagePart);
    }

    let result = null;
    let attempts = 3;
    let lastError = null;

    for (let i = 0; i < attempts; i++) {
      try {
        result = await model.generateContent({
          contents: [
            { role: 'user', parts }
          ],
          generationConfig: {
            responseMimeType: 'application/json'
          }
        });
        break; // Success! Exit retry loop
      } catch (err) {
        lastError = err;
        console.warn(`⚠️ Gemini Report API call failed (Attempt ${i + 1}/${attempts}):`, err.message);
        if (i < attempts - 1) {
          // Wait 1 second before retrying
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      }
    }

    if (!result) {
      throw lastError || new Error('Failed to query Gemini API for report after multiple attempts.');
    }

    const responseText = result.response.text();
    let cleanJsonText = responseText.trim();
    if (cleanJsonText.startsWith('```')) {
      cleanJsonText = cleanJsonText.replace(/^```(?:json)?/i, '').replace(/```$/i, '').trim();
    }
    
    return JSON.parse(cleanJsonText);
  } catch (error) {
    console.error('Error analyzing user scam report:', error.message);
    return { isScam: false, confidence: 0, category: 'Unknown', pattern: '' };
  }
}

module.exports = {
  detectScam,
  extractUrls,
  extractPhoneNumbers,
  analyzeUserReport
};
