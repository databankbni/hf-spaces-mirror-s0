const express = require('express');
const router = express.Router();
const Razorpay = require('razorpay');
const crypto = require('crypto');
const dbService = require('../services/db');
const whatsappService = require('../services/whatsapp');
const { normalizePhone } = require('../services/security');

// Initialize Razorpay if keys are configured
const keyId = process.env.RAZORPAY_KEY_ID;
const keySecret = process.env.RAZORPAY_KEY_SECRET;
let razorpay = null;

if (keyId && keySecret && keyId !== 'your_razorpay_key_id_here') {
  try {
    razorpay = new Razorpay({
      key_id: keyId,
      key_secret: keySecret
    });
    console.log('💳 Razorpay SDK initialized successfully');
  } catch (error) {
    console.error('⚠️ Razorpay initialization failed:', error.message);
  }
}

/**
 * POST /payments/create-subscription
 * API to create subscription (Real Razorpay integration)
 */
router.post('/create-subscription', async (req, res) => {
  let { phoneNumber, planId } = req.body;

  if (!phoneNumber) {
    return res.status(400).json({ success: false, error: 'Phone number is required.' });
  }

  phoneNumber = normalizePhone(phoneNumber);
  if (!phoneNumber) {
    return res.status(400).json({ success: false, error: 'Invalid phone number format.' });
  }

  if (!razorpay) {
    return res.status(501).json({
      success: false,
      error: 'PAYMENT_MOCK_REQUIRED',
      message: 'Razorpay keys are not configured. Please use GET /payments/pay-mock?phone=NUMBER for local testing.'
    });
  }

  try {
    // Standard Razorpay subscription request structure
    // (Note: in production you must first create plans in Razorpay Dashboard)
    const subscription = await razorpay.subscriptions.create({
      plan_id: planId || 'plan_scam_detector_premium', // example plan id
      customer_notify: 1,
      total_count: 12, // charge monthly for 1 year
      addons: [],
      notes: {
        phoneNumber
      }
    });

    res.json({
      success: true,
      subscriptionId: subscription.id,
      paymentUrl: subscription.short_url
    });
  } catch (error) {
    console.error('Error creating Razorpay subscription:', error);
    res.status(500).json({
      success: false,
      error: 'SUBSCRIPTION_CREATION_FAILED',
      message: error.message
    });
  }
});

/**
 * POST /payments/verify-payment
 * Verify signature of Razorpay callback (Real Razorpay webhook/redirect)
 */
router.post('/verify-payment', async (req, res) => {
  let { phoneNumber, razorpayPaymentId, razorpaySubscriptionId, razorpaySignature } = req.body;
  phoneNumber = normalizePhone(phoneNumber);
  if (!phoneNumber) {
    return res.status(400).json({ success: false, error: 'Invalid phone number format.' });
  }

  if (!razorpay) {
    return res.status(501).json({ success: false, error: 'Razorpay keys not configured.' });
  }

  try {
    // Generate signature verify string
    const secret = process.env.RAZORPAY_KEY_SECRET;
    const expectedSignature = crypto
      .createHmac('sha256', secret)
      .update(razorpayPaymentId + '|' + razorpaySubscriptionId)
      .digest('hex');

    if (expectedSignature === razorpaySignature) {
      // Payment verified! Set user to premium (1 month)
      const premiumData = await dbService.setPremium(phoneNumber, 1);
      
      // Send purchase success message to the user on WhatsApp
      try {
        await whatsappService.sendMessage(phoneNumber, `👑 *Scam Detector Premium Active!*\n\nThank you for your purchase! Your account (+${phoneNumber}) has been successfully upgraded to Premium.\n\nEnjoy unlimited, priority checks and access to your scanning history. Protect your savings! 🛡️`);
      } catch (err) {
        console.error('Failed to send payment confirmation WhatsApp message:', err.message);
      }
      
      res.json({
        success: true,
        message: 'Payment verified successfully and subscription activated.',
        data: premiumData
      });
    } else {
      res.status(400).json({
        success: false,
        error: 'INVALID_SIGNATURE',
        message: 'Signature verification failed.'
      });
    }
  } catch (error) {
    console.error('Error verifying payment:', error);
    res.status(500).json({
      success: false,
      error: 'VERIFICATION_FAILED',
      message: error.message
    });
  }
});

// ==========================================
// MOCK CHEKOUT PORTAL (LOCAL DEVELOPMENT)
// ==========================================

/**
 * GET /payments/pay-mock
 * Serve a beautiful dark checkout simulation screen
 */
router.get('/pay-mock', async (req, res) => {
  if (razorpay) {
    return res.status(403).send('Mock checkout is disabled when Razorpay is active.');
  }
  const phone = normalizePhone(req.query.phone || '9999999999');

  const html = `
  <!DOCTYPE html>
  <html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Scam Detector Premium Checkout</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
      :root {
        --bg-color: #0b0f19;
        --card-bg: rgba(255, 255, 255, 0.03);
        --accent-glow: rgba(59, 130, 246, 0.15);
        --text-color: #f3f4f6;
        --primary: #3b82f6;
        --primary-hover: #2563eb;
        --border-color: rgba(255, 255, 255, 0.08);
      }
      body {
        margin: 0;
        padding: 0;
        background-color: var(--bg-color);
        color: var(--text-color);
        font-family: 'Outfit', sans-serif;
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 100vh;
        overflow: hidden;
      }
      .blur-glow {
        position: absolute;
        width: 400px;
        height: 400px;
        background: radial-gradient(circle, var(--accent-glow) 0%, rgba(0,0,0,0) 70%);
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        z-index: 1;
        pointer-events: none;
      }
      .checkout-container {
        position: relative;
        z-index: 2;
        background: var(--card-bg);
        border: 1px solid var(--border-color);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border-radius: 24px;
        padding: 40px;
        max-width: 420px;
        width: 100%;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        text-align: center;
        transition: all 0.3s ease;
      }
      .logo {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #60a5fa, #3b82f6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 8px;
      }
      .sub-title {
        color: #9ca3af;
        font-size: 0.95rem;
        margin-bottom: 30px;
      }
      .plan-card {
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 32px;
        text-align: left;
      }
      .plan-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
      }
      .plan-name {
        font-weight: 600;
        font-size: 1.2rem;
        color: #fff;
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .crown {
        color: #fbbf24;
      }
      .price {
        font-size: 1.5rem;
        font-weight: 700;
        color: #60a5fa;
      }
      .phone-label {
        font-size: 0.85rem;
        color: #9ca3af;
        margin-bottom: 4px;
        display: block;
      }
      .phone-input {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid var(--border-color);
        color: #fff;
        width: 100%;
        padding: 12px 16px;
        border-radius: 10px;
        font-size: 1rem;
        box-sizing: border-box;
        font-family: inherit;
        outline: none;
        margin-top: 6px;
        text-align: center;
      }
      .btn {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 16px 24px;
        font-size: 1rem;
        font-weight: 600;
        cursor: pointer;
        width: 100%;
        transition: all 0.2s ease;
        box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4);
      }
      .btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(59, 130, 246, 0.6);
      }
      .btn:active {
        transform: translateY(0);
      }
      .footer-note {
        margin-top: 20px;
        font-size: 0.75rem;
        color: #6b7280;
      }
    </style>
  </head>
  <body>
    <div class="blur-glow"></div>
    <div class="checkout-container">
      <div class="logo">Scam Detector</div>
      <div class="sub-title">Secure payment checkout powered by Razorpay</div>
      
      <form action="/payments/verify-mock" method="POST">
        <div class="plan-card">
          <div class="plan-header">
            <span class="plan-name"><span class="crown">👑</span> Premium Plan</span>
            <span class="price">₹199<span style="font-size:0.9rem; font-weight:normal; color:#9ca3af;">/mo</span></span>
          </div>
          <p style="margin:0 0 16px 0; font-size:0.85rem; color:#9ca3af; line-height: 1.4;">
            Unlocks unlimited scam checks, priority response queue, and complete scan history reports.
          </p>
          
          <label class="phone-label">Upgrading Phone Number</label>
          <input type="text" name="phone" class="phone-input" value="${phone}" readonly />
        </div>

        <button type="submit" class="btn">💳 Complete Test Payment</button>
      </form>
      
      <div class="footer-note">
        This is a local sandbox environment simulating Razorpay verification. No real money will be charged.
      </div>
    </div>
  </body>
  </html>
  `;
  res.send(html);
});

/**
 * POST /payments/verify-mock
 * Verifies simulated payment and updates local user profile
 */
router.post('/verify-mock', async (req, res) => {
  if (razorpay) {
    return res.status(403).send('Mock verification is disabled when Razorpay is active.');
  }
  let { phone } = req.body;

  if (!phone) {
    return res.status(400).send('Phone number missing.');
  }

  phone = normalizePhone(phone);

  try {
    // Log mock transaction
    try {
      await dbService.logTransaction(phone, 199, 'mock_order_' + Date.now(), 'mock_pay_' + Date.now(), 'success');
    } catch (txnErr) {
      console.error('Failed to log mock transaction details:', txnErr.message);
    }

    // Set user to premium (1 month duration)
    const premiumData = await dbService.setPremium(phone, 1);

    // Send purchase success message to the user on WhatsApp
    try {
      const sent = await whatsappService.sendMessage(phone, `👑 *Scam Detector Premium Active!*\n\nThank you for your purchase! Your account (+${phone}) has been successfully upgraded to Premium.\n\nEnjoy unlimited, priority checks and access to your scanning history. Protect your savings! 🛡️`);
      if (!sent) {
        console.log('⚠️ Free-form message failed. Falling back to template confirmation...');
        await whatsappService.sendTemplateMessage(phone, 'premium_upgrade_success');
      }
    } catch (err) {
      console.error('Failed to send mock payment confirmation WhatsApp message:', err.message);
    }

    const successHtml = `
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Payment Successful</title>
      <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
      <style>
        :root {
          --bg-color: #0b0f19;
          --card-bg: rgba(255, 255, 255, 0.03);
          --text-color: #f3f4f6;
          --border-color: rgba(255, 255, 255, 0.08);
        }
        body {
          margin: 0;
          padding: 0;
          background-color: var(--bg-color);
          color: var(--text-color);
          font-family: 'Outfit', sans-serif;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 100vh;
        }
        .container {
          background: var(--card-bg);
          border: 1px solid var(--border-color);
          border-radius: 24px;
          padding: 40px;
          max-width: 420px;
          width: 100%;
          text-align: center;
          box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
          backdrop-filter: blur(16px);
        }
        .success-icon {
          width: 80px;
          height: 80px;
          background: rgba(16, 185, 129, 0.1);
          color: #10b981;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 3rem;
          margin: 0 auto 24px auto;
          animation: scaleIn 0.5s ease-out;
        }
        h2 {
          color: #fff;
          margin-bottom: 8px;
        }
        p {
          color: #9ca3af;
          font-size: 0.95rem;
          line-height: 1.5;
          margin-bottom: 30px;
        }
        .btn-done {
          background: rgba(255,255,255,0.08);
          color: #fff;
          border: 1px solid rgba(255,255,255,0.1);
          border-radius: 12px;
          padding: 12px 24px;
          font-size: 0.95rem;
          cursor: pointer;
          transition: all 0.2s;
          display: inline-block;
          text-decoration: none;
        }
        .btn-done:hover {
          background: rgba(255,255,255,0.15);
        }
        @keyframes scaleIn {
          0% { transform: scale(0); opacity: 0; }
          100% { transform: scale(1); opacity: 1; }
        }
      </style>
    </head>
    <body>
      <div class="container">
        <div class="success-icon">✓</div>
        <h2>Payment Successful!</h2>
        <p>
          Congratulations! Your subscription has been activated for <b>+91 ${phone}</b>.<br><br>
          You now have <b>Premium Access</b> with unlimited checks. You can close this tab and return to WhatsApp.
        </p>
        <a href="javascript:window.close()" class="btn-done">Close Window</a>
      </div>
    </body>
    </html>
    `;
    res.send(successHtml);
  } catch (error) {
    console.error('Error completing mock payment:', error);
    res.status(500).send('Verification failed: ' + error.message);
  }
});

/**
 * POST /payments/create-order
 * Create a one-time order for ₹199 (Zero-setup required for developers)
 */
router.post('/create-order', async (req, res) => {
  let { phoneNumber } = req.body;

  if (!phoneNumber) {
    return res.status(400).json({ success: false, error: 'Phone number is required.' });
  }

  phoneNumber = normalizePhone(phoneNumber);
  if (!phoneNumber) {
    return res.status(400).json({ success: false, error: 'Invalid phone number format.' });
  }

  // Check if user is already Premium to prevent double payments
  try {
    const user = await dbService.getUser(phoneNumber);
    if (user && user.premium) {
      return res.status(400).json({
        success: false,
        error: 'ALREADY_PREMIUM',
        message: 'Your account is already upgraded to Premium! Enjoy unlimited scans.'
      });
    }
  } catch (dbErr) {
    console.error('Error checking user premium status in create-order:', dbErr.message);
  }

  if (!razorpay) {
    return res.json({
      success: false,
      error: 'PAYMENT_MOCK_REQUIRED',
      message: 'Razorpay keys are not configured.'
    });
  }

  try {
    const order = await razorpay.orders.create({
      amount: 19900, // ₹199 in paise
      currency: 'INR',
      receipt: `receipt_${Date.now()}`,
      notes: {
        phoneNumber
      }
    });

    res.json({
      success: true,
      orderId: order.id,
      amount: order.amount,
      keyId: process.env.RAZORPAY_KEY_ID
    });
  } catch (error) {
    console.error('Error creating Razorpay order:', error);
    res.status(500).json({
      success: false,
      error: 'ORDER_CREATION_FAILED',
      message: error.message
    });
  }
});

/**
 * POST /payments/verify-order
 * Verify order payment signature
 */
router.post('/verify-order', async (req, res) => {
  let { phoneNumber, razorpayPaymentId, razorpayOrderId, razorpaySignature } = req.body;
  phoneNumber = normalizePhone(phoneNumber);
  if (!phoneNumber) {
    return res.status(400).json({ success: false, error: 'Invalid phone number format.' });
  }

  if (!razorpay) {
    return res.status(501).json({ success: false, error: 'Razorpay keys not configured.' });
  }

  try {
    const secret = process.env.RAZORPAY_KEY_SECRET;
    const expectedSignature = crypto
      .createHmac('sha256', secret)
      .update(razorpayOrderId + '|' + razorpayPaymentId)
      .digest('hex');

    if (expectedSignature === razorpaySignature) {
      // Log the transaction
      try {
        await dbService.logTransaction(phoneNumber, 199, razorpayOrderId, razorpayPaymentId, 'success');
      } catch (txnErr) {
        console.error('Failed to log transaction details to database:', txnErr.message);
      }

      // Upgrade user
      const premiumData = await dbService.setPremium(phoneNumber, 1);
      
      // Send confirmation message
      try {
        const sent = await whatsappService.sendMessage(phoneNumber, `👑 *AI Scam Detector Premium Active!*\n\nThank you for your purchase! Your account (+${phoneNumber}) has been successfully upgraded to Premium.\n\nEnjoy unlimited, priority checks and access to your scanning history. Protect your savings! 🛡️`);
        if (!sent) {
          console.log('⚠️ Free-form message failed. Falling back to template confirmation...');
          await whatsappService.sendTemplateMessage(phoneNumber, 'premium_upgrade_success');
        }
      } catch (err) {
        console.error('Failed to send payment confirmation WhatsApp message:', err.message);
      }
      
      res.json({
        success: true,
        message: 'Payment verified successfully.',
        data: premiumData
      });
    } else {
      res.status(400).json({
        success: false,
        error: 'INVALID_SIGNATURE',
        message: 'Signature verification failed.'
      });
    }
  } catch (error) {
    console.error('Error verifying payment:', error);
    res.status(500).json({
      success: false,
      error: 'VERIFICATION_FAILED',
      message: error.message
    });
  }
});

/**
 * POST /payments/webhook
 * Razorpay Webhook endpoint for server-to-server transaction notifications.
 * Automatically handles payment dropouts/tab closed scenarios.
 */
router.post('/webhook', express.json(), async (req, res) => {
  const signature = req.headers['x-razorpay-signature'];
  const secret = process.env.RAZORPAY_WEBHOOK_SECRET;

  // If webhook secret is not configured, we ignore verification (but log warning)
  if (!secret) {
    console.warn('⚠️ RAZORPAY_WEBHOOK_SECRET is not configured. Webhook signature check skipped.');
  } else {
    // Validate signature
    const bodyString = JSON.stringify(req.body);
    const expectedSignature = crypto
      .createHmac('sha256', secret)
      .update(bodyString)
      .digest('hex');

    if (expectedSignature !== signature) {
      console.error('❌ Razorpay Webhook signature verification failed.');
      return res.status(400).send('Invalid signature');
    }
  }

  const event = req.body.event;
  console.log(`📡 Incoming Razorpay Webhook Event: ${event}`);

  try {
    if (event === 'payment.captured' || event === 'order.paid') {
      const payment = req.body.payload.payment.entity;
      const amount = payment.amount / 100; // convert paise to INR
      const orderId = payment.order_id;
      const paymentId = payment.id;
      
      // Extract phone number from notes
      let phoneNumber = payment.notes ? payment.notes.phoneNumber : null;
      if (phoneNumber) {
        phoneNumber = normalizePhone(phoneNumber);
      }

      if (!phoneNumber) {
        console.warn('⚠️ Webhook payment has no phone number in notes. Skipping upgrade.');
        return res.status(200).send('OK (No phone number)');
      }

      console.log(`💳 Webhook Upgrade Request for +${phoneNumber} - Amount: ₹${amount} - Order: ${orderId}`);

      // Check if this transaction is already logged (to prevent double upgrades)
      const recentTxns = await dbService.getTransactions(15);
      const isAlreadyLogged = recentTxns.some(t => t.paymentId === paymentId);

      if (isAlreadyLogged) {
        console.log(`ℹ️ Transaction ${paymentId} is already processed. Webhook processing skipped.`);
        return res.status(200).send('OK (Already processed)');
      }

      // 1. Log transaction
      try {
        await dbService.logTransaction(phoneNumber, amount, orderId, paymentId, 'success');
      } catch (err) {
        console.error('Failed to log webhook transaction details:', err.message);
      }

      // 2. Set premium
      await dbService.setPremium(phoneNumber, 1);

      // 3. Send message
      try {
        const sent = await whatsappService.sendMessage(phoneNumber, `👑 *AI Scam Detector Premium Active!*\n\nThank you for your purchase! Your account (+${phoneNumber}) has been successfully upgraded to Premium.\n\nEnjoy unlimited, priority checks and access to your scanning history. Protect your savings! 🛡️`);
        if (!sent) {
          console.log('⚠️ Webhook free-form message failed. Falling back to template confirmation...');
          await whatsappService.sendTemplateMessage(phoneNumber, 'premium_upgrade_success');
        }
      } catch (err) {
        console.error('Failed to send webhook payment confirmation WhatsApp message:', err.message);
      }
    }

    res.status(200).send('OK');
  } catch (error) {
    console.error('Error processing Razorpay Webhook:', error.message);
    res.status(500).send('Internal Server Error');
  }
});

module.exports = router;
