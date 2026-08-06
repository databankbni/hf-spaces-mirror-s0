document.addEventListener('DOMContentLoaded', () => {
  // --------------------------------------------------------------------------
  // CUSTOM UI NOTIFICATIONS & DIALOG MODALS
  // --------------------------------------------------------------------------
  
  // Initialize dynamic HTML components
  function initCustomUI() {
    // 1. Toast Container
    if (!document.querySelector('.toast-container')) {
      const container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    // 2. Custom Alert Modal
    if (!document.querySelector('.modal-overlay:not(.prompt-overlay):not(.wa-connect-overlay)')) {
      const overlay = document.createElement('div');
      overlay.className = 'modal-overlay';
      overlay.innerHTML = `
        <div class="modal-box">
          <div class="modal-header-icon" style="display: inline-flex; align-items: center; justify-content: center; margin-bottom: 16px;"></div>
          <h3 class="modal-title"></h3>
          <p class="modal-message"></p>
          <button class="modal-btn"></button>
        </div>
      `;
      document.body.appendChild(overlay);
    }

    // 3. WhatsApp Connect Modal (Split QR & Web)
    if (!document.querySelector('.wa-connect-overlay')) {
      const overlay = document.createElement('div');
      overlay.className = 'modal-overlay wa-connect-overlay';
      overlay.innerHTML = `
        <div class="modal-box wa-connect-box">
          <button class="modal-close-x-btn">&times;</button>
          <div class="wa-connect-header">
            <h3 class="modal-title" style="margin-bottom: 6px;">Connect on WhatsApp</h3>
            <p class="modal-message" style="margin-bottom: 0; font-size: 0.9rem; color: var(--text-secondary);">Choose your preferred way to start scanning scams</p>
          </div>
          <div class="wa-connect-split">
            <div class="wa-connect-left">
              <div class="qr-code-box">
                <img src="https://api.qrserver.com/v1/create-qr-code/?size=120x120&data=https%3A%2F%2Fapi.whatsapp.com%2Fsend%3Fphone%3D919270249103%26text%3DHello&color=10b981&bgcolor=0f1624" alt="Scan QR" class="qr-code-img" />
              </div>
              <div class="qr-desc">
                <strong>Scan QR Code</strong>
                <span>Open your phone's camera to scan and start chatting instantly</span>
              </div>
            </div>
            <div class="wa-connect-divider">
              <span>OR</span>
            </div>
            <div class="wa-connect-right">
              <div class="desktop-web-icon" style="display: flex; align-items: center; justify-content: center; margin-bottom: 12px;"><ion-icon name="desktop-outline" style="font-size: 1.8rem; color: #10b981;"></ion-icon></div>
              <a href="https://api.whatsapp.com/send?phone=919270249103&text=Hello" target="_blank" class="wa-web-btn" id="waWebConnectBtn">
                Continue to WhatsApp Web
              </a>
              <p class="web-desc">Open the chat link directly in a new browser tab</p>
            </div>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);
      
      const closeBtn = overlay.querySelector('.modal-close-x-btn');
      const webBtn = overlay.querySelector('#waWebConnectBtn');
      const close = () => overlay.classList.remove('show');
      
      closeBtn.addEventListener('click', close);
      webBtn.addEventListener('click', close);
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close();
      });
    }
  }

  initCustomUI();

  // Show customized toast notification
  window.showToast = function(message, type = 'info') {
    const container = document.querySelector('.toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let iconHtml = '<ion-icon name="information-circle-outline" style="color: #3b82f6; font-size: 1.25rem; vertical-align: middle;"></ion-icon>';
    if (type === 'success') iconHtml = '<ion-icon name="checkmark-circle-outline" style="color: #10b981; font-size: 1.25rem; vertical-align: middle;"></ion-icon>';
    if (type === 'error') iconHtml = '<ion-icon name="close-circle-outline" style="color: #ef4444; font-size: 1.25rem; vertical-align: middle;"></ion-icon>';
    if (type === 'warning') iconHtml = '<ion-icon name="warning-outline" style="color: #f59e0b; font-size: 1.25rem; vertical-align: middle;"></ion-icon>';

    toast.innerHTML = `
      <span class="toast-icon" style="display: inline-flex; align-items: center; justify-content: center; margin-right: 8px;">${iconHtml}</span>
      <span class="toast-text">${message}</span>
    `;
    
    container.appendChild(toast);
    
    // Trigger entrance transition
    setTimeout(() => toast.classList.add('show'), 10);
    
    // Auto-dismiss after 4 seconds
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  };

  // Show customized modal dialog
  window.showModal = function(title, message, type = 'info', onClose = null) {
    const overlay = document.querySelector('.modal-overlay:not(.prompt-overlay)');
    if (!overlay) return;

    const box = overlay.querySelector('.modal-box');
    const iconEl = overlay.querySelector('.modal-header-icon');
    const titleEl = overlay.querySelector('.modal-title');
    const messageEl = overlay.querySelector('.modal-message');
    const btnEl = overlay.querySelector('.modal-btn');

    // Setup modal type styling
    overlay.className = 'modal-overlay';
    overlay.classList.add(`modal-${type}`);

    let iconHtml = '<ion-icon name="information-circle" style="color: #3b82f6; font-size: 3rem;"></ion-icon>';
    if (type === 'success') iconHtml = '<ion-icon name="checkmark-circle" style="color: #10b981; font-size: 3rem;"></ion-icon>';
    if (type === 'error') iconHtml = '<ion-icon name="alert-circle" style="color: #ef4444; font-size: 3rem;"></ion-icon>';
    iconEl.innerHTML = iconHtml;

    titleEl.textContent = title;
    messageEl.textContent = message;
    btnEl.textContent = type === 'success' ? 'Continue' : 'Okay';

    const closeModal = () => {
      overlay.classList.remove('show');
      // Create new button to clear event listeners cleanly
      const newBtn = btnEl.cloneNode(true);
      btnEl.parentNode.replaceChild(newBtn, btnEl);
      if (onClose) onClose();
    };

    const handleBtnClick = (e) => {
      e.stopPropagation();
      closeModal();
    };

    const handleOverlayClick = (e) => {
      if (e.target === overlay) {
        closeModal();
      }
    };

    overlay.querySelector('.modal-btn').addEventListener('click', handleBtnClick);
    overlay.addEventListener('click', handleOverlayClick);

    overlay.classList.add('show');
  };

  // Show customized input prompt modal
  window.showPromptModal = function(title, message, placeholder, onConfirm) {
    let overlay = document.querySelector('.prompt-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'modal-overlay prompt-overlay';
      overlay.innerHTML = `
        <div class="modal-box" style="text-align: left;">
          <div class="modal-header-icon" style="background: rgba(139, 92, 246, 0.1); color: var(--purple); border: 1px solid rgba(139, 92, 246, 0.2); margin-left: 0; display: inline-flex; align-items: center; justify-content: center;"><ion-icon name="key-outline" style="font-size: 1.5rem;"></ion-icon></div>
          <h3 class="modal-title" style="margin-bottom: 8px;"></h3>
          <p class="modal-message" style="margin-bottom: 20px; font-size: 0.9rem;"></p>
          <div class="input-group" style="margin-bottom: 24px; position: relative;">
            <input type="text" id="promptModalInput" style="width: 100%; padding: 14px 16px; background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: 12px; color: var(--text-primary); font-family: inherit; font-size: 0.95rem; outline: none; transition: var(--transition-fast);" />
          </div>
          <div style="display: flex; gap: 12px;">
            <button class="btn btn-secondary prompt-cancel-btn" style="flex: 1; padding: 12px; background: rgba(255,255,255,0.05); border: 1px solid var(--border-color); color: var(--text-secondary); border-radius: 12px; font-weight: 600; cursor: pointer; border: 1px solid rgba(255,255,255,0.08);">Cancel</button>
            <button class="btn btn-primary prompt-confirm-btn" style="flex: 1; padding: 12px; background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%); color: #fff; border: none; border-radius: 12px; font-weight: 600; cursor: pointer; box-shadow: 0 4px 15px var(--primary-glow);">Submit</button>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);
      
      const input = overlay.querySelector('#promptModalInput');
      input.addEventListener('focus', () => {
        input.style.borderColor = 'var(--primary)';
        input.style.boxShadow = '0 0 10px var(--primary-glow)';
      });
      input.addEventListener('blur', () => {
        input.style.borderColor = 'var(--border-color)';
        input.style.boxShadow = 'none';
      });
    }

    const titleEl = overlay.querySelector('.modal-title');
    const messageEl = overlay.querySelector('.modal-message');
    const inputEl = overlay.querySelector('#promptModalInput');
    const cancelBtn = overlay.querySelector('.prompt-cancel-btn');
    const confirmBtn = overlay.querySelector('.prompt-confirm-btn');

    titleEl.textContent = title;
    messageEl.textContent = message;
    inputEl.placeholder = placeholder;
    inputEl.value = '';

    const closePrompt = () => {
      overlay.classList.remove('show');
      // Clone buttons to clear listeners
      const newConfirm = confirmBtn.cloneNode(true);
      confirmBtn.parentNode.replaceChild(newConfirm, confirmBtn);
      const newCancel = cancelBtn.cloneNode(true);
      cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);
      overlay.removeEventListener('click', handleOverlayClick);
      inputEl.removeEventListener('keypress', handleKeyPress);
    };

    const handleConfirm = () => {
      const val = inputEl.value.trim();
      if (val) {
        closePrompt();
        onConfirm(val);
      } else {
        inputEl.style.borderColor = 'var(--danger)';
        setTimeout(() => {
          inputEl.style.borderColor = 'var(--border-color)';
        }, 1000);
      }
    };

    const handleCancel = () => {
      closePrompt();
    };

    const handleOverlayClick = (e) => {
      if (e.target === overlay) {
        closePrompt();
      }
    };

    const handleKeyPress = (e) => {
      if (e.key === 'Enter') {
        handleConfirm();
      }
    };

    overlay.querySelector('.prompt-confirm-btn').addEventListener('click', handleConfirm);
    overlay.querySelector('.prompt-cancel-btn').addEventListener('click', handleCancel);
    overlay.addEventListener('click', handleOverlayClick);
    inputEl.addEventListener('keypress', handleKeyPress);

    overlay.classList.add('show');
    setTimeout(() => inputEl.focus(), 150);
  };

  // Override standard window.alert with showToast
  window.alert = function(msg) {
    window.showToast(msg, 'warning');
  };

  // Show WhatsApp split connection modal
  window.showWhatsAppConnectModal = function() {
    const overlay = document.querySelector('.wa-connect-overlay');
    if (overlay) overlay.classList.add('show');
  };

  // Intercept wa.me links on desktop screens (screen width > 768px)
  const waLinks = document.querySelectorAll('a[href^="https://wa.me/919270249103"], a[href^="https://api.whatsapp.com/send"]');
  waLinks.forEach(link => {
    // Avoid double intercepting the modal's own button
    if (link.id === 'waWebConnectBtn') return;
    
    link.addEventListener('click', (e) => {
      if (window.innerWidth > 768) {
        e.preventDefault();
        window.showWhatsAppConnectModal();
      }
    });
  });


  // Global DOM elements
  const scanInput = document.getElementById('scanInput');
  const charCount = document.getElementById('charCount');
  const scanBtn = document.getElementById('scanBtn');
  const scanLoader = document.getElementById('scanLoader');
  
  const outputPlaceholder = document.getElementById('outputPlaceholder');
  const outputResults = document.getElementById('outputResults');
  
  const riskBadge = document.getElementById('riskBadge');
  const confidenceRing = document.getElementById('confidenceRing');
  const confidencePct = document.getElementById('confidencePct');
  const resultExplanation = document.getElementById('resultExplanation');
  const resultActions = document.getElementById('resultActions');
  const quotaAlert = document.getElementById('quotaAlert');

  // Sample Scams Mapping
  const samples = {
    electricity: 'Electricity bill payment warning: Your electricity connection will be suspended tonight at 9:30 PM. Please call electricity board officer Mr. Sharma at 9876543211 immediately to clear your bill.',
    lottery: 'Congratulations! Your mobile number has won ₹25 Lakhs in the KBC Lottery Lucky Draw. Kindly contact Rana Pratap Singh at 919876543210 on WhatsApp to claim your prize.',
    kyc: 'Dear customer, your SBI NetBanking account is blocked today due to KYC update. Click here to verify netbanking: http://sbi-kyc-verify-portal.in and reactivate.',
    job: 'Earn ₹3000 to ₹5000 daily working part-time from home. Just like YouTube videos and subscribe to channels. Contact coordinator on Telegram: t.me/earnparttimejobs'
  };

  // 1. Textarea Character Count
  scanInput.addEventListener('input', () => {
    const len = scanInput.value.length;
    charCount.textContent = `${len} character${len === 1 ? '' : 's'}`;
  });

  // 2. Select Sample Pills
  const pills = document.querySelectorAll('.sample-pill');
  pills.forEach(pill => {
    pill.addEventListener('click', () => {
      const type = pill.getAttribute('data-scam');
      if (samples[type]) {
        scanInput.value = samples[type];
        // Dispatch input event to update char counter
        scanInput.dispatchEvent(new Event('input'));
        
        // Highlight pill active state temporarily
        pill.style.background = 'rgba(59, 130, 246, 0.2)';
        pill.style.borderColor = '#3b82f6';
        setTimeout(() => {
          pill.style.background = '';
          pill.style.borderColor = '';
        }, 1000);
      }
    });
  });

  // 3. Scan Button API Trigger
  scanBtn.addEventListener('click', async () => {
    const text = scanInput.value.trim();

    if (!text) {
      alert('Please enter or select a suspicious message to scan.');
      return;
    }

    // Reset previous risk glows
    const scanCard = document.querySelector('.scanner-card');
    scanCard?.classList.remove('risk-high-glow', 'risk-safe-glow');

    // Toggle button loader
    scanBtn.disabled = true;
    scanLoader.style.display = 'inline-block';
    
    // Show Radar Scanning Animation
    outputResults.classList.add('hidden');
    outputPlaceholder.classList.remove('hidden');
    document.querySelector('.scanner-body')?.classList.add('scanning');
    
    const radarBeam = outputPlaceholder.querySelector('.radar-beam');
    if (radarBeam) {
      radarBeam.style.animationDuration = '1s'; // speed up radar scanning during API call
    }

    // Trigger floating diagnostics step labels
    const steps = ["Checking Threat Blacklist...", "Analyzing Link Domains...", "Evaluating Semantic Urgency...", "Verifying via Gemini AI..."];
    steps.forEach((stepText, idx) => {
      setTimeout(() => {
        if (!scanBtn.disabled) return; // cancel if API call resolved early
        const label = document.createElement('div');
        label.className = 'scanner-floating-step';
        label.textContent = stepText;
        document.querySelector('.scanner-body')?.appendChild(label);
        setTimeout(() => label.remove(), 1200);
      }, idx * 450);
    });

    try {
      const response = await fetch('/api/check-scam', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: text
        })
      });

      const data = await response.json();

      if (response.status === 429 || (data.error && data.error === 'WEB_LIMIT_EXCEEDED')) {
        // Clean up active floating steps and remove scanning states instantly
        document.querySelectorAll('.scanner-floating-step').forEach(el => el.remove());
        document.querySelector('.scanner-body')?.classList.remove('scanning');
        if (radarBeam) {
          radarBeam.style.animationDuration = '3s';
        }
        
        // Show Lock Overlay
        document.getElementById('scannerLockOverlay').classList.remove('hidden');
        return;
      }

      if (!response.ok) {
        throw new Error(data.message || 'API request failed');
      }

      // Render Results
      renderResults(data);

    } catch (error) {
      console.error('Scan Error:', error);
      alert(`Scan failed: ${error.message}`);
    } finally {
      // Restore Button state
      scanBtn.disabled = false;
      scanLoader.style.display = 'none';
      document.querySelector('.scanner-body')?.classList.remove('scanning');
      if (radarBeam) {
        radarBeam.style.animationDuration = '3s'; // restore standard radar speed
      }
    }
  });

  // Render scan outputs on UI
  function renderResults(data) {
    const result = data.result;

    // Apply risk glows to scanner card
    const scanCard = document.querySelector('.scanner-card');
    scanCard?.classList.remove('risk-high-glow', 'risk-safe-glow');
    if (result.riskLevel === 'HIGH') {
      scanCard?.classList.add('risk-high-glow');
    } else if (result.riskLevel === 'SAFE') {
      scanCard?.classList.add('risk-safe-glow');
    }

    // 1. Hide placeholder and show results container
    outputPlaceholder.classList.add('hidden');
    outputResults.classList.remove('hidden');

    // 2. Set Risk Badge
    riskBadge.textContent = `${result.riskLevel} RISK`;
    riskBadge.className = 'result-badge'; // reset
    if (result.riskLevel === 'HIGH') {
      riskBadge.classList.add('badge-high');
    } else if (result.riskLevel === 'MEDIUM') {
      riskBadge.classList.add('badge-medium');
    } else {
      riskBadge.classList.add('badge-safe');
    }

    // 3. Set Explanation
    resultExplanation.textContent = result.explanation;

    // 4. Set Action Steps List
    resultActions.innerHTML = '';
    result.actions.forEach(action => {
      const li = document.createElement('li');
      li.textContent = action;
      resultActions.appendChild(li);
    });

    // 5. Animate confidence percentage and ring
    let currentPct = 0;
    const targetPct = result.confidence;
    confidencePct.textContent = '0';
    
    // Reset ring classes
    confidenceRing.className = 'ring-fill';
    if (result.riskLevel === 'HIGH') {
      confidenceRing.classList.add('ring-high');
    } else if (result.riskLevel === 'MEDIUM') {
      confidenceRing.classList.add('ring-medium');
    } else {
      confidenceRing.classList.add('ring-safe');
    }

    const interval = setInterval(() => {
      if (currentPct >= targetPct) {
        clearInterval(interval);
      } else {
        currentPct++;
        confidencePct.textContent = currentPct;
        // Stroke-dasharray for svg circle circumfrence = 100
        confidenceRing.setAttribute('stroke-dasharray', `${currentPct}, 100`);
      }
    }, 15);

    // 6. Quota details
    if (data.isPremium) {
      quotaAlert.innerHTML = `👑 <b>Premium Active</b> — Unlimited checks unlocked!`;
    } else {
      // Clarify that the Web Scan is completed (limit 1/1) but WhatsApp offers 5 scans/day on the Free tier.
      quotaAlert.innerHTML = `📊 Web demo limit: <b>0/1 check remaining today</b>. Connect on WhatsApp for <b>5 daily checks</b>!`;
    }
  }

  // 4. FAQ Accordion Toggle
  const faqItems = document.querySelectorAll('.faq-item');
  faqItems.forEach(item => {
    item.addEventListener('click', () => {
      // Toggle current
      item.classList.toggle('active');
    });
  });

  // 5. Fetch Real-time stats on load
  async function loadStats() {
    try {
      const response = await fetch('/api/stats');
      const json = await response.json();
      
      if (json.success && json.data) {
        const stats = json.data;
        
        // Update DOM attributes targets dynamically
        document.getElementById('statScams').setAttribute('data-target', stats.totalScamsDetected);
        document.getElementById('statUsers').setAttribute('data-target', stats.totalUsers);
        
        // Dynamic stats checkout URL update for user's phone context
        const phone = '919999999999';
        const checkoutBtn = document.getElementById('premiumCheckoutBtn');
        if (checkoutBtn) {
          checkoutBtn.setAttribute('href', `/payments/pay-mock?phone=${phone}`);
        }
      }
    } catch (e) {
      console.log('Failed to fetch stats, using default page values:', e);
    } finally {
      // Trigger counter animations
      initStatsCounters();
    }
  }

  // 6. Animate counting stats numbers
  function initStatsCounters() {
    const statsNumbers = document.querySelectorAll('.stat-number');
    
    // Animate individual counter
    const animateCounter = (el) => {
      const target = parseInt(el.getAttribute('data-target'), 10);
      let current = 0;
      const step = Math.ceil(target / 100); // 100 steps
      
      const counterInterval = setInterval(() => {
        current += step;
        if (current >= target) {
          el.textContent = target.toLocaleString('en-IN');
          clearInterval(counterInterval);
        } else {
          el.textContent = current.toLocaleString('en-IN');
        }
      }, 15);
    };

    // Use IntersectionObserver to animate numbers only when visible on screen
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          animateCounter(entry.target);
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.5 });

    statsNumbers.forEach(num => observer.observe(num));
  }

  // Live system status check for trust badge
  async function checkSystemStatus() {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('liveStatusText');
    if (!dot || !text) return;

    try {
      const response = await fetch('/health');
      const data = await response.json();
      
      if (response.ok && data.status === 'UP') {
        dot.className = 'status-dot online'; // solid green
        
        if (data.whatsappStatus === 'CONNECTED') {
          text.textContent = 'All Systems Operational • Bot Online';
        } else {
          text.textContent = 'Systems Active • Bot Reconnecting';
        }
      } else {
        dot.className = 'status-dot offline'; // solid red
        text.textContent = 'System Under Maintenance';
      }
    } catch (err) {
      dot.className = 'status-dot offline';
      text.textContent = 'Connection Offline';
    }
  }

  // Start initialization
  loadStats();
  checkSystemStatus();

  // Auto-trigger upgrade from URL parameter (direct WhatsApp link bridge)
  const urlParams = new URLSearchParams(window.location.search);
  const phoneParam = urlParams.get('phone');
  if (phoneParam) {
    // Wait a brief moment for page layout animations to settle
    setTimeout(() => {
      window.triggerPremiumUpgrade(phoneParam);
    }, 1200);
  }

  // Premium upgrade checkout router
  window.triggerPremiumUpgrade = async function(prefilledPhone) {
    const startCheckout = async (phoneInput) => {
      if (!phoneInput) return;
      
      // Strip non-digits and normalize to digits-only starting with country code
      let phone = phoneInput.replace(/\D/g, '');
      if (phone.startsWith('00')) {
        phone = phone.substring(2);
      }
      if (phone.startsWith('0')) {
        phone = phone.substring(1);
      }
      if (phone.length === 10) {
        phone = '91' + phone;
      }

      if (phone.length < 10) {
        window.showToast("Please enter a valid phone number with country code.", "error");
        return;
      }

      try {
        const response = await fetch('/payments/create-order', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ phoneNumber: phone })
        });
        
        const data = await response.json();
        
        if (data.error === 'ALREADY_PREMIUM') {
          window.showToast("Your account is already on the Premium tier! Enjoy unlimited scans. 👑", "warning");
          return;
        }
        
        if (data.error === 'PAYMENT_MOCK_REQUIRED' || !data.success) {
          // Fallback to beautiful mock simulator page
          window.location.href = `/payments/pay-mock?phone=${phone}`;
          return;
        }

        // Load Razorpay checkout modal
        const options = {
          key: data.keyId,
          amount: data.amount,
          currency: "INR",
          name: "AI Scam Detector",
          description: "Premium subscription upgrade",
          order_id: data.orderId,
          handler: async function (response) {
            // Send signature verification to server
            const verifyRes = await fetch('/payments/verify-order', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json'
              },
              body: JSON.stringify({
                phoneNumber: phone,
                razorpayPaymentId: response.razorpay_payment_id,
                razorpayOrderId: response.razorpay_order_id,
                razorpaySignature: response.razorpay_signature
              })
            });
            
            const verifyData = await verifyRes.json();
            if (verifyData.success) {
              window.showModal(
                "Upgrade Complete! 🎉",
                "Your payment was successful and your account is now Premium! Enjoy unlimited scans and full history access.",
                "success",
                () => { window.location.href = "/history.html"; }
              );
            } else {
              window.showModal(
                "Payment Failed",
                "Signature verification failed: " + verifyData.message,
                "error"
              );
            }
          },
          prefill: {
            contact: phone
          },
          theme: {
            color: "#3b82f6"
          }
        };
        
        // Load script dynamically and open checkout
        const script = document.createElement('script');
        script.src = 'https://checkout.razorpay.com/v1/checkout.js';
        script.onload = () => {
          const rzp = new Razorpay(options);
          rzp.open();
        };
        document.body.appendChild(script);

      } catch (err) {
        console.error("Upgrade error:", err);
        window.location.href = `/payments/pay-mock?phone=${phone}`;
      }
    };

    if (prefilledPhone) {
      await startCheckout(prefilledPhone);
    } else {
      window.showPromptModal(
        "Upgrade to Premium",
        "Enter your WhatsApp phone number to proceed with secure payment verification.",
        "e.g. 919876543210",
        async (val) => {
          await startCheckout(val);
        }
      );
    }
  };

  /* ==========================================================================
     3D MOUSE PARALLAX TILT ENGINE (SCI-FI HUD PERSPECTIVE)
     ========================================================================== */
  const heroVisual = document.querySelector('.hero-visual');
  const phoneMockup = document.querySelector('.phone-mockup');
  const hudLeft = document.querySelector('.hud-left');
  const hudRight = document.querySelector('.hud-right');

  if (heroVisual && phoneMockup) {
    let heroVisualRect = null;

    const updateHeroRect = () => {
      heroVisualRect = heroVisual.getBoundingClientRect();
    };

    heroVisual.addEventListener('mouseenter', updateHeroRect);
    window.addEventListener('resize', updateHeroRect);
    window.addEventListener('scroll', updateHeroRect, { passive: true });

    heroVisual.addEventListener('mousemove', (e) => {
      if (window.innerWidth <= 768) return; // Disable on mobile/tablets
      if (!heroVisualRect) updateHeroRect();

      const x = e.clientX - heroVisualRect.left;
      const y = e.clientY - heroVisualRect.top;

      const centerX = heroVisualRect.width / 2;
      const centerY = heroVisualRect.height / 2;

      // Calculate angles (max 14 degrees rotation)
      const rotateX = ((centerY - y) / centerY) * 14;
      const rotateY = ((x - centerX) / centerX) * 14;

      // Rotate the phone body
      phoneMockup.style.transform = `rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;

      // Rotate and parallax push the HUD panels
      if (hudLeft) {
        hudLeft.style.transform = `rotateX(${rotateX * 1.3}deg) rotateY(${rotateY * 1.3}deg) translate3d(0, 0, 75px)`;
      }
      if (hudRight) {
        hudRight.style.transform = `rotateX(${rotateX * 1.3}deg) rotateY(${rotateY * 1.3}deg) translate3d(0, 0, 75px)`;
      }
    });

    heroVisual.addEventListener('mouseleave', () => {
      phoneMockup.style.transform = 'rotateX(0deg) rotateY(0deg)';
      if (hudLeft) {
        hudLeft.style.transform = '';
      }
      if (hudRight) {
        hudRight.style.transform = '';
      }
      heroVisualRect = null;
    });
  }

  /* ==========================================================================
     INTERACTIVE HTML5 CANVAS NODE NETWORK (HERO BACKDROP)
     ========================================================================== */
  const canvas = document.getElementById('matrixCanvas');
  if (canvas) {
    const ctx = canvas.getContext('2d');
    let particles = [];
    const maxParticles = window.innerWidth < 768 ? 12 : 38;
    let mouse = { x: null, y: null, radius: 140 };
    let canvasRect = canvas.getBoundingClientRect();

    const resizeCanvas = () => {
      canvas.width = canvas.parentElement.offsetWidth;
      canvas.height = canvas.parentElement.offsetHeight;
      canvasRect = canvas.getBoundingClientRect();
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    window.addEventListener('scroll', () => {
      canvasRect = canvas.getBoundingClientRect();
    }, { passive: true });

    window.addEventListener('mousemove', (e) => {
      mouse.x = e.clientX - canvasRect.left;
      mouse.y = e.clientY - canvasRect.top;
    });

    window.addEventListener('mouseleave', () => {
      mouse.x = null;
      mouse.y = null;
    });

    const threatLabels = ["Phishing Link", "OTP Scam", "Fake Lottery", "UPI Fraud", "KYC Alert", "Spam SMS"];

    class Particle {
      constructor() {
        this.reset(true);
      }

      reset(init = false) {
        this.x = Math.random() * canvas.width;
        this.y = init ? Math.random() * canvas.height : (Math.random() > 0.5 ? 0 : canvas.height);
        this.size = Math.random() * 2.5 + 1.5;
        this.speedX = Math.random() * 0.5 - 0.25;
        this.speedY = Math.random() * 0.5 - 0.25;
        this.opacity = Math.random() * 0.5 + 0.35;
        
        // 20% chance to spawn as a threat scam node (red)
        this.isThreat = Math.random() < 0.2;
        this.label = this.isThreat ? threatLabels[Math.floor(Math.random() * threatLabels.length)] : null;
        this.pulse = 0;
      }

      update() {
        this.x += this.speedX;
        this.y += this.speedY;

        if (this.x < 0 || this.x > canvas.width || this.y < 0 || this.y > canvas.height) {
          this.reset();
        }

        if (mouse.x !== null && mouse.y !== null) {
          const dx = mouse.x - this.x;
          const dy = mouse.y - this.y;
          // Math optimization: check squared distance first to avoid Math.hypot reflows
          const distanceSq = dx * dx + dy * dy;
          const maxDistanceSq = mouse.radius * mouse.radius;
          
          if (distanceSq < maxDistanceSq) {
            const distance = Math.sqrt(distanceSq);
            if (this.isThreat) {
              // Draw interception green beam
              const laserAlpha = (mouse.radius - distance) / mouse.radius;
              ctx.strokeStyle = `rgba(16, 185, 129, ${laserAlpha * 0.8})`;
              ctx.lineWidth = 1.2;
              ctx.beginPath();
              ctx.moveTo(mouse.x, mouse.y);
              ctx.lineTo(this.x, this.y);
              ctx.stroke();

              // If threat reaches target shield radius, disarm it (turn green)
              if (distance < mouse.radius - 30) {
                this.isThreat = false;
                this.label = null;
                this.opacity = 0.85;
                
                // Draw a mini burst wave
                ctx.fillStyle = 'rgba(16, 185, 129, 0.35)';
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.size * 3.5, 0, Math.PI * 2);
                ctx.fill();
              }
            } else {
              // Magnetic repulsion for safe green nodes
              const force = (mouse.radius - distance) / mouse.radius;
              this.x -= (dx / distance) * force * 1.5;
              this.y -= (dy / distance) * force * 1.5;
            }
          }
        }
      }

      draw() {
        if (this.isThreat) {
          this.pulse += 0.07;
          const pulseSize = this.size + Math.sin(this.pulse) * 1.2;
          ctx.fillStyle = `rgba(239, 68, 68, ${this.opacity})`;
          ctx.beginPath();
          ctx.arc(this.x, this.y, pulseSize, 0, Math.PI * 2);
          ctx.fill();

          ctx.fillStyle = `rgba(239, 68, 68, ${this.opacity * 0.8})`;
          ctx.font = '8px Space Grotesk, Outfit, sans-serif';
          ctx.fillText(this.label, this.x + 8, this.y + 3);
        } else {
          ctx.fillStyle = `rgba(16, 185, 129, ${this.opacity})`;
          ctx.beginPath();
          ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    for (let i = 0; i < maxParticles; i++) {
      particles.push(new Particle());
    }

    let animationFrameId = null;
    const animateMatrix = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      // Draw Mouse Active Shield Grid
      if (mouse.x !== null && mouse.y !== null) {
        ctx.strokeStyle = 'rgba(16, 185, 129, 0.07)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(mouse.x, mouse.y, mouse.radius, 0, Math.PI * 2);
        ctx.stroke();

        ctx.fillStyle = 'rgba(16, 185, 129, 0.015)';
        ctx.beginPath();
        ctx.arc(mouse.x, mouse.y, mouse.radius, 0, Math.PI * 2);
        ctx.fill();
      }

      for (let i = 0; i < particles.length; i++) {
        particles[i].update();
        particles[i].draw();

        for (let j = i + 1; j < particles.length; j++) {
          // Avoid drawing green lines linking red threat nodes
          if (particles[i].isThreat || particles[j].isThreat) continue;

          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          // Math optimization: check squared bounds first
          const distSq = dx * dx + dy * dy;
          if (distSq < 9025) { // 95^2 = 9025
            const distance = Math.sqrt(distSq);
            const alpha = (95 - distance) / 95 * 0.12;
            ctx.strokeStyle = `rgba(16, 185, 129, ${alpha})`;
            ctx.lineWidth = 0.8;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.stroke();
          }
        }
      }
      animationFrameId = requestAnimationFrame(animateMatrix);
    };

    // Intersection observer to only run animation matrix when visible in view
    const canvasObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          if (!animationFrameId) {
            animateMatrix();
          }
        } else {
          if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
            animationFrameId = null;
          }
        }
      });
    }, { threshold: 0.02 });
    canvasObserver.observe(canvas);
  }

  /* ==========================================================================
     STATS ROLL-UP ENGINE
     ========================================================================== */
  const countUp = (el, target) => {
    let current = 0;
    const duration = 1500; // ms
    const frameRate = 1000 / 60; // 60fps
    const totalFrames = Math.round(duration / frameRate);
    const increment = target / totalFrames;
    let frame = 0;

    const step = () => {
      frame++;
      current += increment;
      if (frame >= totalFrames) {
        el.textContent = target.toLocaleString() + (el.id === 'statRate' ? '%' : (el.id === 'statUptime' ? 's' : '+'));
      } else {
        el.textContent = Math.floor(current).toLocaleString();
        requestAnimationFrame(step);
      }
    };
    requestAnimationFrame(step);
  };

  /* ==========================================================================
     GSAP + SCROLLTRIGGER CINEMATIC ANIMATIONS
     ========================================================================== */
  if (typeof gsap !== 'undefined') {
    gsap.registerPlugin(ScrollTrigger);

    // Navbar Shrink & Glow on Scroll
    gsap.to(".navbar", {
      scrollTrigger: {
        trigger: "body",
        start: "top -60px",
        toggleActions: "play none none reverse",
        scrub: 0.5
      },
      padding: "10px 0",
      background: "rgba(3, 7, 18, 0.85)",
      borderBottom: "1px solid rgba(16, 185, 129, 0.12)",
      boxShadow: "0 10px 30px rgba(0, 0, 0, 0.3)",
      backdropFilter: "blur(20px)"
    });

    // Grid scale on scroll (background parallax zoom)
    gsap.to(".grid-bg-overlay", {
      scrollTrigger: {
        trigger: "body",
        start: "top top",
        end: "bottom bottom",
        scrub: 0.5
      },
      scale: 1.15,
      yPercent: 8,
      ease: "none"
    });

    // Hero Entry Animation sequence
    gsap.from(".hero-content .badge", { opacity: 0, scale: 0.8, y: -20, duration: 0.6, ease: "back.out(1.7)" });
    gsap.from(".hero-content h1", { opacity: 0, y: 40, duration: 0.8, delay: 0.15, ease: "power3.out" });
    gsap.from(".hero-content .hero-description", { opacity: 0, y: 20, duration: 0.8, delay: 0.3, ease: "power3.out" });
    gsap.from(".hero-ctas", { opacity: 0, y: 30, duration: 0.8, delay: 0.45, ease: "power3.out" });
    gsap.from(".hero-trust", { opacity: 0, duration: 1, delay: 0.6, ease: "power2.out" });
    gsap.from(".hero-visual", { opacity: 0, scale: 0.95, duration: 1.2, delay: 0.4, ease: "power3.out" });

    // Scroll-Linked Phone Mockup 3D Rotation (Camera tilt as you scroll)
    gsap.to(".phone-mockup", {
      scrollTrigger: {
        trigger: ".hero-section",
        start: "top top",
        end: "bottom top",
        scrub: 1
      },
      rotationY: 35,
      rotationX: -15,
      z: -120,
      y: 80,
      ease: "none"
    });

    // Scroll Reveal trigger loops
    const reveals = gsap.utils.toArray('.reveal-on-scroll');
    reveals.forEach((element) => {
      if (element.id === 'stats') {
        gsap.to(element, {
          scrollTrigger: {
            trigger: element,
            start: "top 78%",
            onEnter: () => {
              element.classList.add('visible');
              const numbers = element.querySelectorAll('.stat-number');
              numbers.forEach(num => {
                const targetVal = parseInt(num.getAttribute('data-target'), 10);
                if (targetVal) countUp(num, targetVal);
              });
            }
          }
        });
      } else {
        gsap.to(element, {
          scrollTrigger: {
            trigger: element,
            start: "top 78%",
            onEnter: () => element.classList.add('visible')
          }
        });
      }
    });

    // Staggered Step Cards Entrance Scroll Reveals
    gsap.from(".step-card", {
      scrollTrigger: {
        trigger: ".steps-grid",
        start: "top 82%",
        toggleActions: "play none none none"
      },
      y: 60,
      rotationX: -15,
      opacity: 0,
      stagger: 0.15,
      duration: 0.8,
      ease: "power2.out",
      transformPerspective: 1000
    });

    // 3D Entrance Rotations for Cards (Feature & Pricing) on Scroll
    const entries = gsap.utils.toArray('.feature-card, .pricing-card');
    entries.forEach(card => {
      gsap.fromTo(card,
        { 
          rotationX: -18,
          rotationY: 12,
          y: 80,
          opacity: 0,
          transformPerspective: 1000
        },
        {
          scrollTrigger: {
            trigger: card,
            start: "top 85%",
            toggleActions: "play none none none"
          },
          rotationX: 0,
          rotationY: 0,
          y: 0,
          opacity: 1,
          duration: 0.9,
          ease: "power2.out"
        }
      );
    });

    // 3D Mouse Parallax Hover Tilt for Pricing Cards (GPU optimized caching)
    const pricingCards = document.querySelectorAll('.pricing-card');
    pricingCards.forEach(card => {
      let cardRect = null;
      card.addEventListener('mouseenter', () => {
        cardRect = card.getBoundingClientRect();
      });
      card.addEventListener('mousemove', (e) => {
        if (window.innerWidth <= 768 || !cardRect) return;
        const x = e.clientX - cardRect.left;
        const y = e.clientY - cardRect.top;
        const centerX = cardRect.width / 2;
        const centerY = cardRect.height / 2;
        const rotateX = ((centerY - y) / centerY) * 10;
        const rotateY = ((x - centerX) / centerX) * 10;
        
        gsap.to(card, {
          rotationX: rotateX,
          rotationY: rotateY,
          transformPerspective: 800,
          duration: 0.3,
          overwrite: "auto"
        });
      });
      card.addEventListener('mouseleave', () => {
        gsap.to(card, {
          rotationX: 0,
          rotationY: 0,
          duration: 0.5,
          overwrite: "auto"
        });
        cardRect = null;
      });
    });

    // Magnetic Card Micro-interactions (Framer-Motion like feel, cached coords)
    const cards = gsap.utils.toArray('.feature-card, .step-card');
    cards.forEach(card => {
      let cardRect = null;
      card.addEventListener('mouseenter', () => {
        cardRect = card.getBoundingClientRect();
      });
      card.addEventListener('mousemove', (e) => {
        if (window.innerWidth <= 768 || !cardRect) return;
        
        const x = e.clientX - cardRect.left - cardRect.width / 2;
        const y = e.clientY - cardRect.top - cardRect.height / 2;
        
        gsap.to(card, {
          x: x * 0.12,
          y: y * 0.12,
          duration: 0.3,
          ease: "power2.out"
        });
      });
      
      card.addEventListener('mouseleave', () => {
        gsap.to(card, {
          x: 0,
          y: 0,
          duration: 0.5,
          ease: "power3.out"
        });
        cardRect = null;
      });
    });

    // Magnetic Button Micro-interactions (Subtle Micro-pull)
    const magneticBtns = document.querySelectorAll('.btn-primary, .btn-secondary, #heroWhatsAppBtn, #scanBtn');
    magneticBtns.forEach(btn => {
      let btnCenter = { x: 0, y: 0 };

      btn.addEventListener('mouseenter', () => {
        // Calculate center relative to document scroll when button is resting
        const rect = btn.getBoundingClientRect();
        btnCenter.x = rect.left + rect.width / 2 + window.scrollX;
        btnCenter.y = rect.top + rect.height / 2 + window.scrollY;
      });

      btn.addEventListener('mousemove', (e) => {
        if (window.innerWidth <= 768) return;
        const mouseX = e.pageX;
        const mouseY = e.pageY;

        const x = mouseX - btnCenter.x;
        const y = mouseY - btnCenter.y;

        // Extremely subtle micro-pull (max 3-5px translation)
        gsap.to(btn, {
          x: x * 0.06,
          y: y * 0.06,
          scale: 1.01,
          duration: 0.3,
          ease: "power2.out"
        });
      });

      btn.addEventListener('mouseleave', () => {
        gsap.to(btn, {
          x: 0,
          y: 0,
          scale: 1,
          duration: 0.5,
          ease: "elastic.out(1.1, 0.4)"
        });
      });
    });
  } else {
    // Fallback: IntersectionObserver scroll reveals if GSAP is unavailable
    const revealElements = document.querySelectorAll('.reveal-on-scroll');
    const revealObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          if (entry.target.id === 'stats') {
            const numbers = entry.target.querySelectorAll('.stat-number');
            numbers.forEach(num => {
              const targetVal = parseInt(num.getAttribute('data-target'), 10);
              if (targetVal) countUp(num, targetVal);
            });
          }
          observer.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.1,
      rootMargin: '0px 0px -40px 0px'
    });
    revealElements.forEach(el => revealObserver.observe(el));
  }

  /* ==========================================================================
     LIVE CONVERSATION CHAT SIMULATOR (HERO SCREEN)
     ========================================================================== */
  const messagesContainer = document.querySelector('.phone-messages');
  
  if (messagesContainer) {
    const chatSequence = [
      {
        incoming: "Dear customer your SBI account block today due to KYC update. click here to verify netbanking: http://sbi-kyc-verify-portal.in",
        outgoing: "🚨 *RISK ASSESSMENT: HIGH*\n🎯 *Confidence:* 95%\n\nℹ️ *Reason:*\nThis message impersonates SBI requesting urgent KYC verification through an unofficial website. Real banks never send WhatsApp verification links.\n\n💡 *What to do:*\n❌ Don't click the link.\n❌ Don't share netbanking ID/password.\n✅ Contact official customer support."
      },
      {
        incoming: "Congratulations! Your mobile number has won ₹25 Lakhs in KBC Lucky Draw. Please contact WhatsApp manager +91-92702-49103 to claim your prize.",
        outgoing: "🚨 *RISK ASSESSMENT: HIGH*\n🎯 *Confidence:* 99%\n\nℹ️ *Reason:*\nClassic advance-fee lottery fraud scam impersonating Kaun Banega Crorepati (KBC). They will ask you to pay processing fees.\n\n💡 *What to do:*\n❌ Don't pay any 'fees'.\n❌ Don't share bank details.\n✅ Block the number immediately."
      },
      {
        incoming: "Urgent: Your electricity bill is unpaid. Power will disconnect at 9:30 PM. Click to update your payment status: http://power-bill-update-board.in",
        outgoing: "🚨 *RISK ASSESSMENT: HIGH*\n🎯 *Confidence:* 96%\n\nℹ️ *Reason:*\nElectricity boards never notify service disconnection via personal WhatsApp numbers, nor do they send payment links directly.\n\n💡 *What to do:*\n❌ Don't click the link.\n❌ Don't make any quick payments.\n✅ Verify via official board portal."
      }
    ];

    let sequenceIndex = 0;
    let typingTimeout = null;

    const simulateChat = () => {
      if (!messagesContainer) return;
      messagesContainer.innerHTML = ''; // clear messages

      const current = chatSequence[sequenceIndex];

      // 1. Render incoming text message
      const incomingDiv = document.createElement('div');
      incomingDiv.className = 'msg msg-incoming';
      incomingDiv.innerHTML = `
        <span class="msg-meta">Forwarded</span>
        <p>${current.incoming}</p>
        <span class="msg-time">${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
      `;
      messagesContainer.appendChild(incomingDiv);
      messagesContainer.scrollTop = messagesContainer.scrollHeight;

      // 2. Delay, then trigger typing indicator bubble
      typingTimeout = setTimeout(() => {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'msg msg-outgoing msg-typing';
        typingDiv.innerHTML = `<p><span class="dot"></span><span class="dot"></span><span class="dot"></span></p>`;
        messagesContainer.appendChild(typingDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        // 3. Delay, replace typing bubble with outgoing report
        typingTimeout = setTimeout(() => {
          typingDiv.remove();
          
          const outgoingDiv = document.createElement('div');
          outgoingDiv.className = 'msg msg-outgoing msg-glow';
          outgoingDiv.innerHTML = `
            <p>${current.outgoing.replace(/\n/g, '<br>')}</p>
            <span class="msg-time">${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
          `;
          messagesContainer.appendChild(outgoingDiv);
          messagesContainer.scrollTop = messagesContainer.scrollHeight;

          // 4. Delay and trigger next message in loop
          sequenceIndex = (sequenceIndex + 1) % chatSequence.length;
          typingTimeout = setTimeout(simulateChat, 8000);
        }, 1800);
      }, 1200);
    };

    // Add typing keyframes
    const style = document.createElement('style');
    style.innerHTML = `
      .msg-typing p {
        display: flex;
        gap: 4px;
        align-items: center;
        padding: 8px 12px !important;
      }
      .msg-typing .dot {
        width: 6px;
        height: 6px;
        background: rgba(255, 255, 255, 0.5);
        border-radius: 50%;
        animation: typing-blink 1.4s infinite both;
      }
      .msg-typing .dot:nth-child(2) { animation-delay: .2s; }
      .msg-typing .dot:nth-child(3) { animation-delay: .4s; }
      @keyframes typing-blink {
        0% { opacity: .2; }
        20% { opacity: 1; }
        100% { opacity: .2; }
      }
    `;
    document.head.appendChild(style);

    // Initial trigger
    setTimeout(simulateChat, 2000);
  }

  /* ==========================================================================
     CUSTOM CYBER CURSOR ENGINE (GSAP SMOOTH LERP)
     ========================================================================== */
  const cursorDot = document.querySelector('.custom-cursor-dot');
  const cursorOutline = document.querySelector('.custom-cursor-outline');

  if (cursorDot && cursorOutline && window.innerWidth > 768) {
    let mouseX = 0, mouseY = 0;
    let outlineX = 0, outlineY = 0;

    window.addEventListener('mousemove', (e) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
    });

    // Smooth lerping outline and dot cursor using GPU-accelerated translate3d
    const lerpCursor = () => {
      outlineX += (mouseX - outlineX) * 0.25;
      outlineY += (mouseY - outlineY) * 0.25;
      
      cursorDot.style.transform = `translate3d(${mouseX}px, ${mouseY}px, 0) translate(-50%, -50%)`;
      cursorOutline.style.transform = `translate3d(${outlineX}px, ${outlineY}px, 0) translate(-50%, -50%)`;
      
      requestAnimationFrame(lerpCursor);
    };
    lerpCursor();

    // Hover triggers for all interactive nodes
    const hoverSelectors = 'a, button, select, input, textarea, label, .feature-card, .pricing-card, .step-card, .stat-card, .pill-option';
    
    // Delegate hover classes dynamically
    document.addEventListener('mouseover', (e) => {
      if (e.target.closest(hoverSelectors)) {
        cursorDot.classList.add('cursor-hover');
        cursorOutline.classList.add('cursor-hover');
      }
    });

    document.addEventListener('mouseout', (e) => {
      if (e.target.closest(hoverSelectors)) {
        cursorDot.classList.remove('cursor-hover');
        cursorOutline.classList.remove('cursor-hover');
      }
    });

    // Click triggers
    window.addEventListener('mousedown', () => {
      cursorOutline.classList.add('cursor-click');
    });
    window.addEventListener('mouseup', () => {
      cursorOutline.classList.remove('cursor-click');
    });
  }

  // 4. Scroll-linked Navbar Shrink
  const navbar = document.querySelector('.navbar');
  if (navbar) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 40) {
        navbar.classList.add('scrolled');
      } else {
        navbar.classList.remove('scrolled');
      }
    }, { passive: true });
  }
});
