(function () {
  var API_BASE = window.location.origin;

  var SIZES = [
    { width: 360, height: 500 },
    { width: 400, height: 560 },
    { width: 440, height: 620 },
    { width: 480, height: 680 },
  ];
  var sizeIndex = 0; // 0 = default/minimum size

  // ---------- Language config ----------
  var LANG_STORAGE_KEY = 'sala_widget_lang';
  var LANGUAGES = [
    { code: 'auto', label: 'Auto' },
    { code: 'si', label: 'සිංහල' },
    { code: 'en', label: 'English' },
    { code: 'ta', label: 'தமிழ்' },
  ];

  var SPEECH_LANG_CODE = {
    auto: 'si-LK',
    si: 'si-LK',
    en: 'en-US',
    ta: 'ta-IN',
  };

  var UI_TEXT = {
    auto: {
      status: 'Online',
      placeholder: 'ප්‍රශ්නයක් type කරන්න...',
      greeting: 'ආයුබෝවන්! මම Sala AI. Products, prices, warranty ගැන ඕන දෙයක් අහන්න. 😊',
      typing: 'Sala AI type කරමින්...',
      fallback: 'සමාවෙන්න, උත්තරයක් ලබා දෙන්න බැරි වුනා.',
      error: 'සම්බන්ධතාවයේ දෝෂයක්. නැවත උත්සාහ කරන්න.',
      disclaimer: 'Sala AI වැරදි විය හැක. වැදගත් තොරතුරු නැවත පරීක්ෂා කරන්න.',
      listening: '🎤 අහගෙන ඉන්නවා... (නවත්වන්න mic එක නැවත click කරන්න)',
      transcribing: 'Voice එක text කරමින්...',
      transcribeFailed: 'හඬ හඳුනාගන්න බැරි වුනා. නැවත try කරන්න.',
    },
    si: {
      status: 'සබැඳිව ඇත',
      placeholder: 'ප්‍රශ්නයක් type කරන්න...',
      greeting: 'ආයුබෝවන්! මම Sala AI. Products, prices, warranty ගැන ඕන දෙයක් අහන්න. 😊',
      typing: 'Sala AI type කරමින්...',
      fallback: 'සමාවෙන්න, උත්තරයක් ලබා දෙන්න බැරි වුනා.',
      error: 'සම්බන්ධතාවයේ දෝෂයක්. නැවත උත්සාහ කරන්න.',
      disclaimer: 'Sala AI වැරදි විය හැක. වැදගත් තොරතුරු නැවත පරීක්ෂා කරන්න.',
      listening: '🎤 අහගෙන ඉන්නවා... (නවත්වන්න mic එක නැවත click කරන්න)',
      transcribing: 'Voice එක text කරමින්...',
      transcribeFailed: 'හඬ හඳුනාගන්න බැරි වුනා. නැවත try කරන්න.',
    },
    en: {
      status: 'Online',
      placeholder: 'Type your question...',
      greeting: "Hi there! I'm Sala AI. Ask me anything about products, prices, or warranty. 😊",
      typing: 'Sala AI is typing...',
      fallback: "Sorry, I couldn't generate a reply.",
      error: 'Connection error. Please try again.',
      disclaimer: 'Sala AI can make mistakes. Please double-check important information.',
      listening: '🎤 Listening... (click mic again to stop)',
      transcribing: 'Converting voice to text...',
      transcribeFailed: "Couldn't understand that. Please try again.",
    },
    ta: {
      status: 'இணைப்பில் உள்ளது',
      placeholder: 'உங்கள் கேள்வியை தட்டச்சு செய்யவும்...',
      greeting: 'வணக்கம்! நான் Sala AI. தயாரிப்புகள், விலைகள், உத்தரவாதம் பற்றி எதுவும் கேளுங்கள். 😊',
      typing: 'Sala AI தட்டச்சு செய்கிறது...',
      fallback: 'மன்னிக்கவும், பதிலை உருவாக்க முடியவில்லை.',
      error: 'இணைப்பு பிழை. மீண்டும் முயற்சிக்கவும்.',
      disclaimer: 'Sala AI தவறு செய்யக்கூடும். முக்கியமான தகவலை மீண்டும் சரிபார்க்கவும்.',
      listening: '🎤 கேட்கிறேன்... (நிறுத்த mic-ஐ மீண்டும் click செய்யவும்)',
      transcribing: 'குரலை உரையாக மாற்றுகிறேன்...',
      transcribeFailed: 'புரியவில்லை. மீண்டும் முயற்சிக்கவும்.',
    },
  };

  function getSavedLang() {
    try {
      return window.localStorage.getItem(LANG_STORAGE_KEY) || 'auto';
    } catch (e) {
      return 'auto';
    }
  }

  function saveLang(code) {
    try {
      window.localStorage.setItem(LANG_STORAGE_KEY, code);
    } catch (e) {
      /* ignore storage errors (private browsing etc.) */
    }
  }

  var currentLang = getSavedLang();

  // ---------- Inject styles ----------
  var style = document.createElement('style');
  style.textContent = `
    #sala-widget-btn {
      position: fixed; bottom: 24px; right: 24px; width: 58px; height: 58px;
      border-radius: 50%;
      background: linear-gradient(135deg, #2856D9 0%, #1E3F9E 100%);
      color: #fff; border: none;
      cursor: pointer; box-shadow: 0 8px 24px rgba(30,63,158,0.4);
      display: flex; align-items: center; justify-content: center;
      z-index: 999998; transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    #sala-widget-btn:hover { transform: scale(1.06); box-shadow: 0 10px 28px rgba(30,63,158,0.5); }
    #sala-widget-window {
      position: fixed; bottom: 96px; right: 24px;
      background: #fff; border-radius: 18px;
      box-shadow: 0 16px 48px rgba(15,30,70,0.22); display: none; flex-direction: column;
      overflow: hidden; z-index: 999999; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      transition: width 0.15s ease, height 0.15s ease;
      border: 1px solid rgba(30,63,158,0.08);
    }
    #sala-widget-window.open { display: flex; }
    #sala-widget-header {
      background: linear-gradient(135deg, #2856D9 0%, #1E3F9E 100%);
      color: #fff; padding: 16px 16px; display: flex;
      align-items: center; gap: 10px; flex-shrink: 0;
    }
    #sala-widget-header .avatar {
      width: 34px; height: 34px; border-radius: 9px; background: #fff;
      display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px;
      flex-shrink: 0; overflow: hidden;
    }
    #sala-widget-header .avatar img {
      width: 100%; height: 100%; object-fit: contain; display: block;
    }
    #sala-widget-header .title { font-size: 14px; font-weight: 600; margin: 0; letter-spacing: 0.2px; }
    #sala-widget-header .status { font-size: 11px; opacity: 0.85; margin: 0; }
    #sala-widget-header-right { margin-left: auto; display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
    #sala-lang-select {
      background: rgba(255,255,255,0.16); border: none; color: #fff; font-size: 11px;
      font-weight: 600; cursor: pointer; height: 24px; border-radius: 6px;
      padding: 0 4px; outline: none; font-family: inherit; -webkit-appearance: none; appearance: none;
    }
    #sala-lang-select:hover { background: rgba(255,255,255,0.28); }
    #sala-lang-select option { color: #1a1a1a; }
    .sala-font-btn {
      background: rgba(255,255,255,0.16); border: none; color: #fff; font-size: 12px;
      cursor: pointer; width: 24px; height: 24px; border-radius: 6px; line-height: 1;
      display: flex; align-items: center; justify-content: center; font-weight: 700;
    }
    .sala-font-btn:hover { background: rgba(255,255,255,0.28); }
    .sala-font-btn:disabled { opacity: 0.35; cursor: default; }
    #sala-widget-close {
      background: none; border: none; color: #fff; font-size: 20px;
      cursor: pointer; opacity: 0.85; line-height: 1; padding: 4px; margin-left: 4px;
    }
    #sala-widget-messages {
      flex: 1; overflow-y: auto; padding: 16px; background: #F5F7FB;
      display: flex; flex-direction: column; gap: 10px;
    }
    .sala-msg-wrapper { display: flex; flex-direction: column; max-width: 82%; }
    .sala-msg-wrapper.bot { align-self: flex-start; }
    .sala-msg-wrapper.user { align-self: flex-end; }
    .sala-msg { padding: 9px 13px; border-radius: 14px; font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
    .sala-msg.bot { background: #fff; border: 1px solid #E5E9F2; border-bottom-left-radius: 4px; white-space: normal; box-shadow: 0 1px 2px rgba(15,30,70,0.04); }
    .sala-msg.user { background: linear-gradient(135deg, #2856D9 0%, #1E3F9E 100%); color: #fff; border-bottom-right-radius: 4px; }
    .sala-msg.announcement { border-left: 3px solid #FF7A2F; background: #FFF8F3; }
    .sala-msg-p { margin: 0 0 6px 0; }
    .sala-msg-p:last-child { margin-bottom: 0; }
    .sala-msg-list {
      margin: 4px 0 6px 0; padding-left: 18px;
    }
    .sala-msg-list li { margin-bottom: 3px; }
    .sala-msg-list li:last-child { margin-bottom: 0; }
    .sala-msg.bot strong { color: #1E3F9E; }
    .sala-msg-actions {
      display: flex; align-items: center; gap: 6px; margin-top: 3px; padding-left: 4px;
      position: relative;
    }
    .sala-msg-speaker {
      background: none; border: none; cursor: pointer; font-size: 12px; opacity: 0.55;
      padding: 2px; line-height: 1; color: #6B7385; transition: opacity 0.15s ease;
    }
    .sala-msg-speaker:hover { opacity: 1; }
    .sala-msg-speaker.speaking { opacity: 1; }
    .sala-msg-reaction {
      font-size: 13px; display: none; cursor: pointer; line-height: 1;
    }
    .sala-msg-reaction.visible { display: inline-block; }
    .sala-emoji-picker {
      position: absolute; bottom: 100%; left: 0; margin-bottom: 4px;
      background: #fff; border: 1px solid #E5E9F2; border-radius: 20px;
      box-shadow: 0 4px 16px rgba(15,30,70,0.18); padding: 4px 6px;
      display: flex; gap: 2px; z-index: 1000000;
    }
    .sala-emoji-option {
      background: none; border: none; cursor: pointer; font-size: 16px;
      padding: 3px 4px; border-radius: 8px; transition: background 0.12s ease; line-height: 1;
    }
    .sala-emoji-option:hover { background: #F0F2F7; }
    .sala-typing-row {
      display: flex; align-items: center; gap: 8px; align-self: flex-start;
      background: #fff; border: 1px solid #E5E9F2; padding: 9px 13px; border-radius: 14px;
      border-bottom-left-radius: 4px;
    }
    .sala-spinner {
      width: 16px; height: 16px; border-radius: 50%;
      border: 2px solid #E5E9F2; border-top-color: #2856D9;
      animation: sala-spin 0.7s linear infinite;
    }
    @keyframes sala-spin { to { transform: rotate(360deg); } }
    .sala-typing-text { color: #8B93A7; font-size: 12px; font-style: italic; }
    #sala-widget-inputrow {
      display: flex; gap: 8px; padding: 12px; border-top: 1px solid #E5E9F2; background: #fff; flex-shrink: 0;
    }
    #sala-widget-input {
      flex: 1; border: 1px solid #E5E9F2; border-radius: 10px; padding: 9px 12px;
      font-size: 13px; font-family: inherit; resize: none; outline: none;
    }
    #sala-widget-input:focus { border-color: #2856D9; }
    #sala-widget-send {
      background: linear-gradient(135deg, #2856D9 0%, #1E3F9E 100%);
      color: #fff; border: none; border-radius: 10px;
      width: 40px; height: 40px; cursor: pointer; font-size: 16px; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center;
    }
    #sala-widget-send:disabled { opacity: 0.5; cursor: default; }
    #sala-mic-btn {
      background: #F0F2F7; color: #2856D9; border: none; border-radius: 10px;
      width: 40px; height: 40px; cursor: pointer; font-size: 16px; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center; transition: background 0.15s ease;
    }
    #sala-mic-btn:hover { background: #E5E9F2; }
    #sala-mic-btn:disabled { opacity: 0.6; cursor: default; }
    #sala-mic-btn.listening {
      background: #E23E3E; color: #fff;
      animation: sala-mic-pulse 1s ease-in-out infinite;
    }
    @keyframes sala-mic-pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(226,62,62,0.4); }
      50% { box-shadow: 0 0 0 6px rgba(226,62,62,0); }
    }
    #sala-widget-disclaimer {
      font-size: 10.5px; color: #C8CCD6; text-align: center;
      padding: 7px 12px; flex-shrink: 0; background: #2A2E37;
      letter-spacing: 0.1px;
    }
    @media (max-width: 480px) {
      #sala-widget-btn { right: 16px; bottom: 16px; }
    }
  `;
  document.head.appendChild(style);

  // ---------- Build DOM ----------

  var btn = document.createElement('button');
  btn.id = 'sala-widget-btn';
  btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="26" height="26"><path d="M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H8l-4 4V6a1 1 0 0 1 1-1z" fill="white"/></svg>';
  btn.setAttribute('aria-label', 'Open chat');

  var langOptionsHtml = LANGUAGES.map(function (l) {
    return '<option value="' + l.code + '">' + l.label + '</option>';
  }).join('');

  var win = document.createElement('div');
  win.id = 'sala-widget-window';
  win.innerHTML =
    '<div id="sala-widget-header">' +
      '<div class="avatar">S</div>' +
      '<div>' +
        '<p class="title">Sala AI</p>' +
        '<p class="status" id="sala-widget-status">Online</p>' +
      '</div>' +
      '<div id="sala-widget-header-right">' +
        '<select id="sala-lang-select" title="Language" aria-label="Select language">' + langOptionsHtml + '</select>' +
        '<button class="sala-font-btn" id="sala-font-minus" title="Size -">A-</button>' +
        '<button class="sala-font-btn" id="sala-font-plus" title="Size +">A+</button>' +
        '<button id="sala-widget-close" aria-label="Close chat">&times;</button>' +
      '</div>' +
    '</div>' +
    '<div id="sala-widget-messages"></div>' +
    '<div id="sala-widget-inputrow">' +
      '<textarea id="sala-widget-input" rows="1" placeholder="ප්‍රශ්නයක් type කරන්න..."></textarea>' +
      '<button id="sala-mic-btn" aria-label="Voice input" title="Speak your question">&#127908;</button>' +
      '<button id="sala-widget-send" aria-label="Send">&#10148;</button>' +
    '</div>' +
    '<div id="sala-widget-disclaimer">Sala AI can make mistakes. Please double-check important information.</div>';

  document.body.appendChild(win);
  document.body.appendChild(btn);

  var messagesEl = document.getElementById('sala-widget-messages');
  var inputEl = document.getElementById('sala-widget-input');
  var sendBtn = document.getElementById('sala-widget-send');
  var plusBtn = document.getElementById('sala-font-plus');
  var minusBtn = document.getElementById('sala-font-minus');
  var langSelect = document.getElementById('sala-lang-select');
  var statusEl = document.getElementById('sala-widget-status');
  var disclaimerEl = document.getElementById('sala-widget-disclaimer');
  var micBtn = document.getElementById('sala-mic-btn');
  var sessionId = 'web_' + Math.random().toString(36).slice(2) + Date.now();
  var greeted = false;
  var greetingEl = null;
  var greetingSpeakerBtn = null;
  var userHasSent = false;
  var announcementChecked = false;

  langSelect.value = currentLang;

  // ---------- Voice feature visibility (English-only for now) ----------
  // Sinhala/Tamil TTS + STT quality issues are still being worked on, so the
  // mic (voice input) and speaker (voice output toggle) buttons are only
  // shown when the widget is in English mode. They re-appear automatically
  // once the user switches back to "en".
  var VOICE_FEATURE_LANGS = ['en'];

  function updateVoiceFeatureVisibility() {
    var voiceAllowed = VOICE_FEATURE_LANGS.indexOf(currentLang) !== -1;

    // mic button: only relevant if browser support exists AND language is English
    micBtn.style.display = (voiceAllowed && micSupported && window.MediaRecorder) ? 'flex' : 'none';

    // if voice features just got hidden mid-use, stop anything in progress
    if (!voiceAllowed) {
      if (isRecording) stopRecording();
      stopSpeaking();
    }

    // The greeting bubble is created once and its text gets swapped in place
    // when the language changes - its speaker icon must be re-evaluated too,
    // otherwise it can be left showing (or hidden) for the wrong language.
    if (greetingSpeakerBtn) {
      var greetingLang = currentLang !== 'auto' ? currentLang : 'si';
      var showGreetingSpeaker = VOICE_FEATURE_LANGS.indexOf(greetingLang) !== -1;
      greetingSpeakerBtn.style.display = showGreetingSpeaker ? '' : 'none';
      if (!showGreetingSpeaker && currentSpeakingBtn === greetingSpeakerBtn) {
        stopSpeaking();
      }
    }
  }

  function applyLanguageUi() {
    var t = UI_TEXT[currentLang] || UI_TEXT.auto;
    statusEl.textContent = t.status;
    inputEl.placeholder = t.placeholder;
    disclaimerEl.textContent = t.disclaimer;
    if (greetingEl && !userHasSent) {
      greetingEl.innerHTML = formatBotText(t.greeting);
    }
    updateVoiceFeatureVisibility();
  }

  langSelect.addEventListener('change', function () {
    currentLang = langSelect.value;
    saveLang(currentLang);
    applyLanguageUi();
  });

  // ---------- Voice output (text-to-speech) ----------
  var synth = window.speechSynthesis;
  var speechSupported = !!synth;
  var GTTS_LANGS = ['en', 'ta', 'si'];
  var currentAudio = null;

  // Acronyms/brand terms that TTS engines tend to mispronounce as a whole
  // "word" instead of spelling out - inserting periods forces letter-by-letter
  // pronunciation ("UPS" -> "U.P.S."), which comes out far clearer.
  var SPEECH_ACRONYMS = ['UPS', 'PBX', 'GPS', 'LED', 'LCD', 'TV', 'USB', 'HDMI', 'WIFI', 'CCTV', 'DVR', 'NVR', 'FXO', 'FXS'];

  function expandAcronymsForSpeech(text) {
    var result = text;
    SPEECH_ACRONYMS.forEach(function (acr) {
      var re = new RegExp('\\b' + acr + '\\b', 'g');
      result = result.replace(re, acr.split('').join('.') + '.');
    });
    return result;
  }

  function speakBrowser(text, langCode, onEnd) {
    if (!speechSupported) {
      if (onEnd) onEnd();
      return;
    }
    try {
      synth.cancel();
      var utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = langCode;
      utterance.rate = 1;
      if (onEnd) {
        utterance.onend = onEnd;
        utterance.onerror = onEnd;
      }
      synth.speak(utterance);
    } catch (e) {
      /* speech synthesis not available on this device/browser - fail silently */
      if (onEnd) onEnd();
    }
  }

  function speakServer(text, lang, onEnd) {
    fetch(API_BASE + '/chat/voice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, language: lang }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error('voice request failed');
        return r.blob();
      })
      .then(function (blob) {
        if (currentAudio) currentAudio.pause();
        var url = URL.createObjectURL(blob);
        currentAudio = new Audio(url);
        if (onEnd) {
          currentAudio.onended = onEnd;
          currentAudio.onerror = onEnd;
        }
        currentAudio.play();
      })
      .catch(function () {
        speakBrowser(text, SPEECH_LANG_CODE[lang] || 'en-US', onEnd);
      });
  }

  // ---------- Per-message play/mute control ----------
  // Only one message can be "speaking" at a time. Clicking a speaker icon
  // while its own message is playing mutes/stops it; clicking a different
  // message's icon stops whatever was playing and starts the new one.
  var currentSpeakingBtn = null;

  var SPEAKER_ICON_IDLE =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
      '<path d="M11 5L6 9H2V15H6L11 19V5Z" fill="currentColor"/>' +
      '<path d="M15.5 8.5C16.44 9.44 17 10.68 17 12C17 13.32 16.44 14.56 15.5 15.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/>' +
    '</svg>';

  var SPEAKER_ICON_SPEAKING =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
      '<path d="M11 5L6 9H2V15H6L11 19V5Z" fill="currentColor"/>' +
      '<path d="M15.5 8.5C16.44 9.44 17 10.68 17 12C17 13.32 16.44 14.56 15.5 15.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/>' +
      '<line x1="21" y1="3" x2="3" y2="21" stroke="#E23E3E" stroke-width="2" stroke-linecap="round"/>' +
    '</svg>';

  function setSpeakerBtnState(btn, playing) {
    if (!btn) return;
    btn.classList.toggle('speaking', playing);
    btn.innerHTML = playing ? SPEAKER_ICON_SPEAKING : SPEAKER_ICON_IDLE;
    btn.title = playing ? 'Stop' : 'Listen to this answer';
  }

  function stopSpeaking() {
    if (synth) synth.cancel();
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }
    if (currentSpeakingBtn) {
      setSpeakerBtnState(currentSpeakingBtn, false);
      currentSpeakingBtn = null;
    }
  }

  function speakMessageNow(text, effectiveLang, btn) {
    if (!text) return;
    var lang = effectiveLang || (currentLang !== 'auto' ? currentLang : 'en');
    if (VOICE_FEATURE_LANGS.indexOf(lang) === -1) return;

    // clicking the currently-speaking message's own icon again = mute/stop
    if (currentSpeakingBtn === btn) {
      stopSpeaking();
      return;
    }
    stopSpeaking();
    currentSpeakingBtn = btn;
    setSpeakerBtnState(btn, true);

    var spokenText = expandAcronymsForSpeech(text);
    var onDone = function () {
      if (currentSpeakingBtn === btn) {
        setSpeakerBtnState(btn, false);
        currentSpeakingBtn = null;
      }
    };
    if (GTTS_LANGS.indexOf(lang) !== -1) {
      speakServer(spokenText, lang, onDone);
    } else {
      speakBrowser(spokenText, SPEECH_LANG_CODE[lang] || 'si-LK', onDone);
    }
  }

  // ---------- Voice input (speech-to-text via Groq Whisper) ----------
  var mediaRecorder = null;
  var audioChunks = [];
  var isRecording = false;
  var micSupported = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

  function setMicState(state) {
    // states: 'idle' | 'recording' | 'processing'
    micBtn.classList.toggle('listening', state === 'recording');
    micBtn.disabled = state === 'processing';
    micBtn.innerHTML = state === 'processing' ? '&#8987;' : '&#127908;';
  }

  function showVoiceStatus(text) {
    hideVoiceStatus();
    var row = document.createElement('div');
    row.className = 'sala-typing-row';
    row.id = 'sala-voice-indicator';
    row.innerHTML = '<div class="sala-spinner"></div><span class="sala-typing-text">' + text + '</span>';
    messagesEl.appendChild(row);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function hideVoiceStatus() {
    var el = document.getElementById('sala-voice-indicator');
    if (el) el.remove();
  }

  function pickMimeType() {
    var candidates = ['audio/webm', 'audio/ogg', 'audio/mp4'];
    for (var i = 0; i < candidates.length; i++) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported(candidates[i])) {
        return candidates[i];
      }
    }
    return '';
  }

  function startRecording() {
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then(function (stream) {
        var mimeType = pickMimeType();
        try {
          mediaRecorder = mimeType
            ? new MediaRecorder(stream, { mimeType: mimeType })
            : new MediaRecorder(stream);
        } catch (e) {
          setMicState('idle');
          return;
        }
        audioChunks = [];
        isRecording = true;
        setMicState('recording');
        var t = UI_TEXT[currentLang] || UI_TEXT.auto;
        showVoiceStatus(t.listening);

        mediaRecorder.ondataavailable = function (e) {
          if (e.data && e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = function () {
          stream.getTracks().forEach(function (track) { track.stop(); });
          isRecording = false;

          if (!audioChunks.length) {
            setMicState('idle');
            hideVoiceStatus();
            return;
          }

          setMicState('processing');
          var tt = UI_TEXT[currentLang] || UI_TEXT.auto;
          // no separate "converting voice to text" bubble - the mic button's
          // own processing icon is enough feedback while this happens
          hideVoiceStatus();

          var blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
          var formData = new FormData();
          formData.append('file', blob, 'recording.webm');
          formData.append('language', currentLang);

          fetch(API_BASE + '/chat/transcribe', {
            method: 'POST',
            body: formData,
          })
            .then(function (r) {
              if (!r.ok) throw new Error('transcribe failed');
              return r.json();
            })
            .then(function (data) {
              hideVoiceStatus();
              if (data.text) {
                inputEl.value = data.text;
                inputEl.focus();
              } else {
                addMessage(tt.transcribeFailed, 'bot', { skipActions: true });
              }
            })
            .catch(function () {
              hideVoiceStatus();
              addMessage(tt.transcribeFailed, 'bot', { skipActions: true });
            })
            .finally(function () {
              setMicState('idle');
            });
        };

        mediaRecorder.start();
      })
      .catch(function () {
        // mic permission denied or unavailable
        setMicState('idle');
        hideVoiceStatus();
      });
  }

  function stopRecording() {
    if (mediaRecorder && isRecording) {
      mediaRecorder.stop();
    }
  }

  if (micSupported && window.MediaRecorder) {
    micBtn.addEventListener('click', function () {
      if (isRecording) {
        stopRecording();
      } else {
        startRecording();
      }
    });
  } else {
    micBtn.style.display = 'none';
  }

  // Apply language-driven UI (including voice-feature visibility) now that
  // all the flags it depends on (speechSupported, micSupported, etc.) exist.
  applyLanguageUi();

  function applySize() {
    var target = SIZES[sizeIndex];
    var maxW = window.innerWidth - 32;
    var maxH = window.innerHeight - 140;

    var w = Math.min(target.width, maxW);
    var h = Math.min(target.height, maxH);

    win.style.width = w + 'px';
    win.style.height = h + 'px';

    minusBtn.disabled = sizeIndex === 0;
    plusBtn.disabled = sizeIndex === SIZES.length - 1;
  }

  plusBtn.addEventListener('click', function () {
    if (sizeIndex < SIZES.length - 1) sizeIndex += 1;
    applySize();
  });
  minusBtn.addEventListener('click', function () {
    if (sizeIndex > 0) sizeIndex -= 1;
    applySize();
  });
  window.addEventListener('resize', function () {
    if (win.classList.contains('open')) applySize();
  });

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function formatBotText(raw) {
    var escaped = escapeHtml(raw);
    var lines = escaped.split('\n');
    var htmlParts = [];
    var inList = false;

    lines.forEach(function (line) {
      var trimmed = line.trim();
      var isBullet = /^[-•]\s+/.test(trimmed);

      if (isBullet) {
        if (!inList) {
          htmlParts.push('<ul class="sala-msg-list">');
          inList = true;
        }
        var itemText = trimmed.replace(/^[-•]\s+/, '');
        htmlParts.push('<li>' + itemText + '</li>');
      } else {
        if (inList) {
          htmlParts.push('</ul>');
          inList = false;
        }
        if (trimmed === '') {
          htmlParts.push('<br>');
        } else {
          htmlParts.push('<p class="sala-msg-p">' + trimmed + '</p>');
        }
      }
    });
    if (inList) htmlParts.push('</ul>');

    var html = htmlParts.join('');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    return html;
  }

  // ---------- Reactions (auto + manual) ----------
  var REACTION_EMOJIS = ['👍', '❤️', '😂', '😮', '👏', '😢'];
  var openPickerEl = null;
  var IMPRESSIVE_WORD_COUNT = 30;

  function getReactionEmoji(rawText) {
    if (!rawText) return null;
    var plain = rawText.trim();
    if (!plain) return null;

    var wordCount = plain.split(/\s+/).filter(Boolean).length;
    var hasBulletList = /(^|\n)\s*[-•]\s+/.test(plain);
    var isDetailed = wordCount >= IMPRESSIVE_WORD_COUNT || hasBulletList;

    if (!isDetailed) return null;

    var lower = plain.toLowerCase();
    if (/(discount|offer|වට්ටම|சலுகை|warranty|වගකීම|உத்தரவாதம்)/.test(lower)) {
      return '🎉';
    }
    if (hasBulletList) {
      return '👏';
    }
    return '✨';
  }

  function closeEmojiPicker() {
    if (openPickerEl) {
      openPickerEl.remove();
      openPickerEl = null;
    }
  }

  function openEmojiPicker(actionsRow, badgeEl) {
    if (openPickerEl) {
      var wasForThisMessage = openPickerEl.parentNode === actionsRow;
      closeEmojiPicker();
      if (wasForThisMessage) return;
    }
    var picker = document.createElement('div');
    picker.className = 'sala-emoji-picker';
    REACTION_EMOJIS.forEach(function (emoji) {
      var opt = document.createElement('button');
      opt.type = 'button';
      opt.className = 'sala-emoji-option';
      opt.textContent = emoji;
      opt.addEventListener('click', function (e) {
        e.stopPropagation();
        badgeEl.textContent = emoji;
        badgeEl.classList.add('visible');
        closeEmojiPicker();
      });
      picker.appendChild(opt);
    });
    actionsRow.appendChild(picker);
    openPickerEl = picker;
  }

  document.addEventListener('click', function (e) {
    if (openPickerEl && !openPickerEl.contains(e.target)) {
      closeEmojiPicker();
    }
  });

  function addMessage(text, sender, options) {
    options = options || {};

    var wrapper = document.createElement('div');
    wrapper.className = 'sala-msg-wrapper ' + sender;

    var el = document.createElement('div');
    el.className = 'sala-msg ' + sender + (options.announcement ? ' announcement' : '');
    if (sender === 'bot') {
      el.innerHTML = formatBotText(text);
    } else {
      el.textContent = text;
    }
    wrapper.appendChild(el);

    if (sender === 'bot' && !options.skipActions) {
      var actionsRow = document.createElement('div');
      actionsRow.className = 'sala-msg-actions';

      var speakerBtn = document.createElement('button');
      speakerBtn.type = 'button';
      speakerBtn.className = 'sala-msg-speaker';
      speakerBtn.innerHTML = SPEAKER_ICON_IDLE;
      speakerBtn.title = 'Listen to this answer';
      speakerBtn.setAttribute('aria-label', 'Listen to this answer');
      speakerBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        speakMessageNow(text, options.lang, speakerBtn);
      });
      // Show the per-message speaker only when THIS answer is in English -
      // not when the UI language dropdown happens to be set to English.
      // In "auto" mode the reply can come back in Sinhala/Tamil even though
      // currentLang is 'auto', so we key off the message's own language.
      var speakerMsgLang = options.lang || (currentLang !== 'auto' ? currentLang : 'en');
      if (VOICE_FEATURE_LANGS.indexOf(speakerMsgLang) === -1) {
        speakerBtn.style.display = 'none';
      }
      actionsRow.appendChild(speakerBtn);

      var reactionBadge = document.createElement('span');
      reactionBadge.className = 'sala-msg-reaction';
      reactionBadge.title = 'Change reaction';
      var autoEmoji = getReactionEmoji(text);
      if (autoEmoji) {
        reactionBadge.textContent = autoEmoji;
        reactionBadge.classList.add('visible');
      }
      reactionBadge.addEventListener('click', function (e) {
        e.stopPropagation();
        openEmojiPicker(actionsRow, reactionBadge);
      });
      actionsRow.appendChild(reactionBadge);

      wrapper.appendChild(actionsRow);

      el.style.cursor = 'pointer';
      el.addEventListener('click', function () {
        openEmojiPicker(actionsRow, reactionBadge);
      });
    }

    messagesEl.appendChild(wrapper);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return el;
  }

  function showTyping() {
    var t = UI_TEXT[currentLang] || UI_TEXT.auto;
    var row = document.createElement('div');
    row.className = 'sala-typing-row';
    row.id = 'sala-typing-indicator';
    row.innerHTML = '<div class="sala-spinner"></div><span class="sala-typing-text">' + t.typing + '</span>';
    messagesEl.appendChild(row);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function hideTyping() {
    var el = document.getElementById('sala-typing-indicator');
    if (el) el.remove();
  }

  // ---------- Active announcement (proactive message after greeting) ----------
  function checkAnnouncement() {
    if (announcementChecked) return;
    announcementChecked = true;

    fetch(API_BASE + '/chat/announcement')
      .then(function (r) {
        if (!r.ok) throw new Error('announcement request failed');
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.active || !data.content) return;
        // small delay so it visibly arrives as a *second* message after
        // the static greeting, rather than popping in at the same instant
        setTimeout(function () {
          addMessage(data.content, 'bot', { announcement: true, skipActions: true });
        }, 500);
      })
      .catch(function () {
        // fail silently - a missing/broken announcement should never block
        // the widget from opening and working normally
      });
  }

  function openWidget() {
    win.classList.add('open');
    applySize();
    if (!greeted) {
      greeted = true;
      var t = UI_TEXT[currentLang] || UI_TEXT.auto;
      greetingEl = addMessage(t.greeting, 'bot', { lang: currentLang !== 'auto' ? currentLang : 'si' });
      greetingSpeakerBtn = greetingEl.parentNode.querySelector('.sala-msg-speaker');
      checkAnnouncement();
    }
    inputEl.focus();
  }

  function closeWidget() {
    win.classList.remove('open');
  }

  btn.addEventListener('click', function () {
    if (win.classList.contains('open')) {
      closeWidget();
    } else {
      openWidget();
    }
  });

  document.getElementById('sala-widget-close').addEventListener('click', closeWidget);

  function sendMessage() {
    var text = inputEl.value.trim();
    if (!text) return;

    var t = UI_TEXT[currentLang] || UI_TEXT.auto;
    userHasSent = true;

    addMessage(text, 'user');
    inputEl.value = '';
    sendBtn.disabled = true;
    showTyping();

    var payload = { message: text, session_id: sessionId };
    if (currentLang !== 'auto') {
      payload.language = currentLang;
    }

    fetch(API_BASE + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        hideTyping();
        var reply = data.reply || data.response || data.message || t.fallback;
        var effectiveLang = currentLang !== 'auto' ? currentLang : data.detected_language;
        addMessage(reply, 'bot', { lang: effectiveLang });
      })
      .catch(function () {
        hideTyping();
        addMessage(t.error, 'bot', { skipActions: true });
      })
      .finally(function () {
        sendBtn.disabled = false;
        inputEl.focus();
      });
  }

  sendBtn.addEventListener('click', sendMessage);
  inputEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
})();