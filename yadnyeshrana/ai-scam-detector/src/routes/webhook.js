const express = require('express');
const router = express.Router();
const axios = require('axios');
const dbService = require('../services/db');
const detectorService = require('../services/detector');
const whatsappService = require('../services/whatsapp');
const alertService = require('../services/alert');

const META_ACCESS_TOKEN = process.env.META_ACCESS_TOKEN;
const META_VERIFY_TOKEN = process.env.META_VERIFY_TOKEN || 'scam_detector_verify_token_123';

const crypto = require('crypto');
const https = require('https');
const agent = new https.Agent({
  rejectUnauthorized: false,
  secureOptions: crypto.constants.SSL_OP_LEGACY_SERVER_CONNECT,
  ciphers: 'DEFAULT:@SECLEVEL=0'
});

const META_API_BASE_URL = process.env.META_API_BASE_URL;

const userQueues = new Map();
const MAX_QUEUE_SIZE = 3;
const limitWarningCooldown = new Map(); // phone -> lastWarningTimestamp

/**
 * Sequential FIFO task runner per user to prevent concurrent race conditions
 */
function enqueueUserTask(sender, messageId, taskFn) {
  return new Promise((resolve, reject) => {
    if (!userQueues.has(sender)) {
      userQueues.set(sender, []);
    }
    
    const queue = userQueues.get(sender);
    
    if (queue.length >= MAX_QUEUE_SIZE) {
      return reject(new Error('QUEUE_FULL'));
    }
    
    const runNext = async () => {
      if (queue.length === 0) {
        userQueues.delete(sender);
        return;
      }
      
      const current = queue[0];
      try {
        const res = await current.fn();
        current.resolve(res);
      } catch (err) {
        current.reject(err);
      } finally {
        queue.shift();
        runNext();
      }
    };
    
    queue.push({ fn: taskFn, resolve, reject, messageId });
    
    if (queue.length === 1) {
      runNext();
    }
  });
}

/**
 * Download media from Meta Cloud API (supports Cloudflare Proxy)
 */
async function downloadMetaMedia(mediaId, mimeType) {
  if (!META_ACCESS_TOKEN) return null;
  try {
    // 1. Get media URL metadata via proxy (graph.facebook.com is blocked by HF firewall)
    const targetUrl = `https://graph.facebook.com/v18.0/${mediaId}`;
    let requestUrl = targetUrl;
    const headers = {};
    if (META_API_BASE_URL) {
      requestUrl = `${META_API_BASE_URL}?targetUrl=${encodeURIComponent(targetUrl)}&authToken=${encodeURIComponent(META_ACCESS_TOKEN)}`;
    } else {
      headers['Authorization'] = `Bearer ${META_ACCESS_TOKEN}`;
    }

    const response = await axios.get(requestUrl, {
      headers: headers,
      httpsAgent: agent
    });
    
    if (response.data && response.data.url) {
      const mediaTargetUrl = response.data.url;

      // 2. Try downloading binary directly first (to bypass proxy UTF-8 conversion corruption)
      try {
        console.log(`📥 Attempting direct media download from Meta CDN...`);
        const directResponse = await axios.get(mediaTargetUrl, {
          headers: {
            'Authorization': `Bearer ${META_ACCESS_TOKEN}`
          },
          responseType: 'arraybuffer',
          httpsAgent: agent,
          timeout: 5000
        });
        console.log(`✅ Direct media download succeeded.`);
        return {
          data: Buffer.from(directResponse.data).toString('base64'),
          mimeType: mimeType
        };
      } catch (directErr) {
        console.warn(`⚠️ Direct media download failed or blocked: ${directErr.message}. Falling back to proxy route with base64.`);
        
        // 3. Fallback: Request base64 response from updated Apps Script Web App
        if (META_API_BASE_URL) {
          const proxyUrl = `${META_API_BASE_URL}?targetUrl=${encodeURIComponent(mediaTargetUrl)}&authToken=${encodeURIComponent(META_ACCESS_TOKEN)}&responseType=base64`;
          const proxyResponse = await axios.get(proxyUrl, {
            httpsAgent: agent,
            timeout: 8000
          });
          
          if (proxyResponse.data && typeof proxyResponse.data === 'string') {
            // Strip wrapping double quotes if returned by ContentService
            const base64Data = proxyResponse.data.replace(/^["']|["']$/g, '').trim();
            console.log(`✅ Proxy base64 media fallback download completed.`);
            return {
              data: base64Data,
              mimeType: mimeType
            };
          }
        }
        throw directErr;
      }
    }
  } catch (err) {
    console.error('❌ Failed to download Meta media:', err.message);
  }
  return null;
}

/**
 * Format the analysis result into a clean, readable WhatsApp message
 */
function formatWhatsAppResponse(result, checksRemaining, isPremium) {
  const emoji = result.riskLevel === 'HIGH' ? '🚨' :
                result.riskLevel === 'UNKNOWN' ? '⚠️' :
                result.riskLevel === 'MEDIUM' ? '⚠️' :
                result.riskLevel === 'LOW' ? '🛡️' : '✅';
  
  let output = `${emoji} *RISK ASSESSMENT: ${result.riskLevel}*\n`;
  output += `🎯 *Confidence:* ${result.confidence}%\n\n`;
  
  output += `ℹ️ *Reason:*\n${result.explanation}\n\n`;
  
  output += `💡 *What you should do:*\n`;
  result.actions.forEach(action => {
    output += `${action}\n`;
  });
  
  output += `\n------------------------\n`;
  if (isPremium) {
    output += `👑 *Scam Detector Premium* active. Unlimited checks!`;
  } else {
    output += `📊 Checks remaining today: *${checksRemaining}/5*\n`;
    output += `👉 Reply *UPGRADE* to get unlimited checks & history tracking!`;
  }

  return output;
}

/**
 * GET /webhook/meta-webhook
 * Verification endpoint for Meta Webhook setup
 */
router.get('/meta-webhook', (req, res) => {
  const mode = req.query['hub.mode'];
  const token = req.query['hub.verify_token'];
  const challenge = req.query['hub.challenge'];
  
  if (mode === 'subscribe' && token === META_VERIFY_TOKEN) {
    console.log('✅ Meta Webhook verified successfully!');
    res.status(200).send(challenge);
  } else {
    console.warn('❌ Meta Webhook verification failed.');
    res.status(403).send('Verification failed.');
  }
});

/**
 * POST /webhook/meta-webhook
 * Main webhook handler for incoming WhatsApp messages via Meta Cloud API
 */
router.post('/meta-webhook', async (req, res) => {
  const body = req.body;
  
  // Return 200 OK immediately
  res.status(200).send('EVENT_RECEIVED');
  
  if (!body || body.object !== 'whatsapp_business_account' || !body.entry) {
    return;
  }

  try {
    for (const entry of body.entry) {
      if (!entry.changes) continue;
      for (const change of entry.changes) {
        if (change.field !== 'messages') continue;
        
        const value = change.value;
        
        // Log status updates for debugging delivery failures
        if (value.statuses && value.statuses.length > 0) {
          const status = value.statuses[0];
          console.log(`ℹ️ Meta Status Update: Message ID ${status.id} is now [${status.status}] for recipient +${status.recipient_id}`);
          if (status.errors) {
            console.error('❌ Meta Delivery Error:', JSON.stringify(status.errors, null, 2));
          }
          continue;
        }
        
        if (!value.messages || value.messages.length === 0) continue;
        
        const message = value.messages[0];
        const sender = message.from; // Sender mobile number

        // Reject Group messages to prevent bot loops (Edge Case 3)
        const isGroup = message.group_metadata || (sender && (sender.includes('-') || sender.includes('@g.us')));
        if (isGroup) {
          console.log(`👥 Group message detected from ${sender}. Ignoring webhook request.`);
          continue;
        }

        let text = '';
        let imageMedia = null;
        let documentMedia = null;

        // Process based on message type (Edge Case 1: Unsupported media warnings & PDF support)
        if (message.type === 'text' && message.text) {
          text = message.text.body ? message.text.body.trim() : '';
        } else if (message.type === 'image' && message.image) {
          text = message.image.caption ? message.image.caption.trim() : '';
          imageMedia = {
            mediaId: message.image.id,
            mimeType: message.image.mime_type
          };
        } else if (message.type === 'document' && message.document) {
          text = message.document.caption ? message.document.caption.trim() : '';
          if (message.document.mime_type === 'application/pdf') {
            documentMedia = {
              mediaId: message.document.id,
              mimeType: message.document.mime_type,
              filename: message.document.filename
            };
          } else {
            // Unsupported document type (e.g. Word, Excel, ZIP)
            await whatsappService.sendMessage(
              sender,
              '⚠️ *Unsupported Document Format*\n\nAI Scam Detector currently only supports scanning text, website links, screenshots, or *PDF documents*.\n\nPlease upload your document in PDF format to scan it for scams! 🛡️',
              message.id
            );
            continue;
          }
        } else {
          // Unsupported message types (audio, contacts, location, video, stickers)
          await whatsappService.sendMessage(
            sender,
            '⚠️ *Unsupported Message Type*\n\nAI Scam Detector currently only supports scanning:\n• Text messages\n• Website links\n• Image screenshots\n• PDF documents\n\nPlease forward one of these to check for scam risk! 🛡️',
            message.id
          );
          continue;
        }

        console.log(`💬 Incoming Meta WhatsApp from +${sender}: "${text.substring(0, 60)}${text.length > 60 ? '...' : ''}"`);

        // Enqueue task for sequential execution (Edge Case A & B: Concurrency Control)
        enqueueUserTask(sender, message.id, async () => {
          // Check if bot is paused
          const isPaused = await dbService.isBotPaused();
          if (isPaused) {
            console.log(`🤖 Bot is paused. Ignoring message from +${sender} (Silent Mode).`);
            await whatsappService.sendMessage(sender, '🤖 AI Scam Detector is temporarily paused for system maintenance. Please try again in a few minutes.', message.id);
            return;
          }

          // 1. Fetch user profile once to minimize sequential database roundtrips
          const user = await dbService.getUser(sender);
          const isReporting = !!user.reportingState;
          if (isReporting) {
            await dbService.setUserReportingState(sender, false);
            
            try {
              await whatsappService.sendMessage(sender, '🔍 *Analyzing your report...* Please wait.', message.id);
              
              let resolvedImageMedia = null;
              let imagePart = null;
              if (imageMedia) {
                try {
                  console.log(`📥 Downloading image media for report from Meta Cloud ID: ${imageMedia.mediaId}...`);
                  resolvedImageMedia = await downloadMetaMedia(imageMedia.mediaId, imageMedia.mimeType);
                  if (resolvedImageMedia) {
                    imagePart = {
                      inlineData: {
                        data: resolvedImageMedia.data,
                        mimeType: resolvedImageMedia.mimeType
                      }
                    };
                  }
                } catch (err) {
                  console.error('❌ Failed to download report media:', err.message);
                }
              }

              const reportResult = await detectorService.analyzeUserReport(text, imagePart);
              
              if (reportResult.isScam && reportResult.pattern) {
                if (reportResult.confidence >= 85) {
                  await dbService.addKnownScam({
                    id: 'report_' + Date.now(),
                    pattern: reportResult.pattern,
                    type: reportResult.category || 'User Report',
                    riskLevel: 'HIGH',
                    keywords: [(reportResult.category || 'User Report').toLowerCase()],
                    description: 'Automated user report'
                  });
                  
                  await whatsappService.sendMessage(sender, `🛡️ *Scam Blacklisted!*\n\nThank you! Our AI has verified your report and blacklisted the pattern *${reportResult.pattern}* globally. Your report helps protect others in real-time!`, message.id);
                  
                  alertService.sendAlert(`🚨 <b>Automated Scam Blacklist</b>\n\nUser +${sender} reported a scam, and AI auto-approved it.\n\n• <b>Pattern:</b> <code>${reportResult.pattern}</code>\n• <b>Category:</b> ${reportResult.category || 'N/A'}\n• <b>Confidence:</b> ${reportResult.confidence}%`).catch(err => console.error('Alert error:', err.message));
                } else {
                  await whatsappService.sendMessage(sender, `🙏 *Thank you for your report!*\n\nOur AI detected indicators of a scam, and our security team has received your submission for manual review.`, message.id);
                  
                  alertService.sendAlert(`⚠️ <b>Pending Scam Report Review</b>\n\nUser +${sender} reported a scam. AI is unsure (Confidence: ${reportResult.confidence}%).\n\n• <b>Extracted Pattern:</b> <code>${reportResult.pattern}</code>\n• <b>Category:</b> ${reportResult.category || 'N/A'}\n• <b>Message:</b> "${text}"`).catch(err => console.error('Alert error:', err.message));
                }
              } else {
                await whatsappService.sendMessage(sender, `ℹ️ *Report Analyzed*\n\nOur AI reviewed your report and did not detect any clear scam patterns at this time. We will monitor it. Thank you for staying vigilant!`, message.id);
              }
            } catch (error) {
              console.error('Error processing user report:', error);
              await whatsappService.sendMessage(sender, '⚠️ Sorry, we encountered an error while processing your report.', message.id);
            }
            return;
          }

          // Handle greetings / help keywords
          const greetings = ['HI', 'HELLO', 'HELP', 'MENU', 'START', 'INFO'];
          if (greetings.includes(text.toUpperCase())) {
            const welcomeMessage = `🛡️ *Welcome to AI Scam Detector* 🛡️\n\nI am your automated security assistant. I help protect your savings from online frauds.\n\n💡 *How to use:* \n• *Check a Message:* Just send or forward any suspicious text, link, or image screenshot to me.\n• *Report a Scam:* Reply *REPORT* to submit a new scam pattern and blacklist it globally.\n• *My History:* Reply *HISTORY* to view your personal dashboard on the web.\n• *Upgrade:* Reply *UPGRADE* to unlock unlimited checks and priority queue.`;
            await whatsappService.sendMessage(sender, welcomeMessage, message.id);
            return;
          }

          // Handle upgrade/history keywords
          const publicUrl = process.env.PUBLIC_URL || 'https://aiscamdetector.in';
          if (text.toUpperCase() === 'UPGRADE') {
            try {
              const user = await dbService.getUser(sender);
              if (user && user.premium) {
                const formattedExpiry = user.premiumExpiry 
                  ? new Date(user.premiumExpiry).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) 
                  : 'Active';
                await whatsappService.sendMessage(sender, `👑 *Premium Status Active*\n\nYour account (+${sender}) is already on the Premium tier with unlimited scans and scan history access!\n\n📅 *Subscription Expiry:* ${formattedExpiry}\n\n👉 *Access Scan History:* ${publicUrl}/history\n\nThank you for choosing AI Scam Detector! 🛡️`, message.id);
                return;
              }
            } catch (err) {
              console.error('Error checking premium status in upgrade handler:', err.message);
            }

            const upgradeText = `👑 *Upgrade to Scam Detector Premium*\n\nProtect your savings with unlimited scans for just *₹199/month*!\n\n👉 Click here to pay securely:\n${publicUrl}/?phone=${sender}\n\n(After successful payment, your account will be upgraded immediately!)`;
            await whatsappService.sendMessage(sender, upgradeText, message.id);
            return;
          }

          if (text.toUpperCase() === 'HISTORY' || text.toUpperCase() === 'DASHBOARD') {
            await whatsappService.sendMessage(sender, `📊 *View Your Scan History*\n\nAccess your secure, decrypted scan timeline and premium risk reports here:\n\n👉 ${publicUrl}/history\n\n(You will receive a one-time verification code on WhatsApp to log in.)`, message.id);
            return;
          }

          if (text.toUpperCase() === 'REPORT' || text.toUpperCase() === '/REPORT') {
            await dbService.setUserReportingState(sender, true);
            await whatsappService.sendMessage(sender, '🚨 *Report a Scam* 🚨\n\nPlease reply directly to this message with the scam details. You can send:\n• A suspicious message/text\n• A link/website URL\n• A scammer phone number or UPI ID\n• A screenshot image of the scam!\n\nOur AI will analyze and blacklist it globally. 🛡️', message.id);
            return;
          }

          // Process Scam Check
          try {
            // 1. Quota Check (In-Memory Fast Check)
            const isTest = await dbService.isTestUser(sender);
            const today = getISTDateString();
            const isPremium = user.premium || isTest;
            
            let checksToday = user.checksToday || 0;
            if (user.lastCheckDate !== today) {
              checksToday = 0;
            }
            
            const allowed = isPremium || checksToday < 5;
            const checksRemaining = isPremium ? null : (5 - (checksToday + 1));
            
            if (!allowed) {
              const lastWarning = limitWarningCooldown.get(sender) || 0;
              const FOUR_HOURS = 4 * 60 * 60 * 1000;
              if (Date.now() - lastWarning < FOUR_HOURS) {
                console.log(`🔇 Suppressing duplicate limit warning spam for user +${sender}.`);
                return;
              }
              limitWarningCooldown.set(sender, Date.now());

              const warningText = `🚨 *Daily Free Limit Reached!*\n\nYou have used your 5 free checks for today.\n\nTo continue analyzing messages in real-time, upgrade to Premium for only *₹199/month*.\n\n👉 Reply *UPGRADE* or visit:\n${publicUrl}/?phone=${sender}`;
              await whatsappService.sendMessage(sender, warningText, message.id);
              return;
            }

            // Asynchronously increment check counts in database (DO NOT AWAIT!)
            dbService.incrementUserCheck(sender, user).catch((dbErr) => {
              console.error('⚠️ Failed to increment user checks in database (non-blocking):', dbErr.message);
            });

             // 2. Download Media if applicable
            let resolvedMedia = null;
            if (imageMedia) {
              try {
                console.log(`📥 Downloading image media from Meta Cloud ID: ${imageMedia.mediaId}...`);
                resolvedMedia = await downloadMetaMedia(imageMedia.mediaId, imageMedia.mimeType);
              } catch (err) {
                console.error('❌ Failed to download Meta media:', err.message);
              }
            } else if (documentMedia) {
              try {
                console.log(`📥 Downloading PDF document from Meta Cloud ID: ${documentMedia.mediaId}...`);
                resolvedMedia = await downloadMetaMedia(documentMedia.mediaId, documentMedia.mimeType);
              } catch (err) {
                console.error('❌ Failed to download PDF document media:', err.message);
              }
            }

            // 3. Run scam detection analysis
            const analysisResult = await detectorService.detectScam(text, sender, resolvedMedia);

            // 4. Log results to database (wrapped in try-catch so transient DB issues do not block user reply)
            const logText = imageMedia 
              ? `[Image Scan] ${text}`.trim() 
              : (documentMedia ? `[PDF Document Scan] ${text}`.trim() : text);
            // Asynchronously log to DB in the background to prevent blocking the user's WhatsApp reply
            dbService.logCheck(sender, logText, analysisResult).catch((dbErr) => {
              console.error('⚠️ Database logCheck failed (non-blocking):', dbErr.message);
            });

            // 5. Format and reply back to the user
            const replyText = formatWhatsAppResponse(
              analysisResult,
              checksRemaining,
              isPremium
            );

            await whatsappService.sendMessage(sender, replyText, message.id);

          } catch (error) {
            console.error('Error processing scam check:', error);
            await whatsappService.sendMessage(sender, '⚠️ Sorry, we encountered an error while analyzing your message. Please try again later.', message.id);
          }
        }).catch(async (err) => {
          if (err.message === 'QUEUE_FULL') {
            await whatsappService.sendMessage(
              sender,
              '⚠️ *Too many requests!* \n\nPlease wait for your current scam check to complete before sending another message.',
              message.id
            );
          } else {
            console.error(`Error processing message queue for ${sender}:`, err);
          }
        });
      }
    }
  } catch (err) {
    console.error('Error processing Meta Webhook payload:', err.message);
  }
});

/**
 * Get current date string in IST timezone (YYYY-MM-DD)
 */
function getISTDateString() {
  const date = new Date();
  const istOffset = 5.5 * 60 * 60 * 1000;
  const istDate = new Date(date.getTime() + istOffset);
  return istDate.toISOString().split('T')[0];
}

module.exports = router;
