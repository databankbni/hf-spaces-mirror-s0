/* Modal test tool + audio player */

let currentTool = null; // tool đang test
let testMode = 'form';  // 'form' | 'json'

function openTestModal(toolName) {
  const tool = allTools.find(t => t.name === toolName);
  if (!tool) return;
  currentTool = tool;
  testMode = 'form';

  document.getElementById('testToolName').textContent = toolName;
  document.getElementById('testToolDesc').textContent = tool.description || '';
  document.getElementById('resultBox').classList.remove('show');
  document.getElementById('btnRunTool').disabled = false;
  setMode('form');
  document.getElementById('testOverlay').classList.add('show');
}

function setMode(mode) {
  testMode = mode;
  document.getElementById('btnFormMode').classList.toggle('active', mode === 'form');
  document.getElementById('btnJsonMode').classList.toggle('active', mode === 'json');

  const props = currentTool?.inputSchema?.properties || {};
  const required = currentTool?.inputSchema?.required || [];
  const body = document.getElementById('testBody');

  if (mode === 'form') {
    const keys = Object.keys(props);
    if (!keys.length) {
      body.innerHTML = '<div style="color:#666;font-size:13px;padding:8px 0">Tool này không có tham số nào.</div>';
      return;
    }
    body.innerHTML = keys.map(key => {
      const p = props[key];
      const isReq = required.includes(key);
      const type = p.type || 'string';
      const desc = p.description || '';
      let inputHtml;
      if (type === 'integer' || type === 'number') {
        inputHtml = `<input class="field-input" id="field_${key}" type="number" placeholder="${p.default ?? ''}" value="${p.default ?? ''}">`;
      } else {
        inputHtml = `<input class="field-input" id="field_${key}" type="text" placeholder="${desc.split('.')[0] || key}">`;
      }
      return `
        <div class="field-group">
          <div class="field-label">${key}${isReq ? '<span class="req">*</span>' : ''}</div>
          ${desc ? `<div class="field-desc">${desc}</div>` : ''}
          ${inputHtml}
        </div>`;
    }).join('');
  } else {
    // JSON mode — pre-fill với object rỗng hoặc defaults
    const defaults = {};
    Object.entries(props).forEach(([k, v]) => {
      defaults[k] = v.default ?? (v.type === 'integer' || v.type === 'number' ? 0 : '');
    });
    body.innerHTML = `
      <div class="field-group">
        <div class="field-label">Arguments (JSON)</div>
        <textarea class="field-input" id="jsonArgs">${JSON.stringify(defaults, null, 2)}</textarea>
      </div>`;
  }
}

function collectArgs() {
  if (testMode === 'json') {
    try { return JSON.parse(document.getElementById('jsonArgs').value); }
    catch { alert('JSON không hợp lệ'); return null; }
  }
  const props = currentTool?.inputSchema?.properties || {};
  const args = {};
  for (const key of Object.keys(props)) {
    const el = document.getElementById(`field_${key}`);
    if (!el) continue;
    const type = props[key].type || 'string';
    const val = el.value.trim();
    if (val === '') continue;
    args[key] = (type === 'integer') ? parseInt(val) : (type === 'number') ? parseFloat(val) : val;
  }
  return args;
}

async function runTool() {
  const args = collectArgs();
  if (args === null) return;

  const btn = document.getElementById('btnRunTool');
  btn.disabled = true;
  btn.textContent = '⏳ Đang chạy...';

  const resultBox = document.getElementById('resultBox');
  const resultContent = document.getElementById('resultContent');
  resultBox.classList.add('show');
  resultContent.className = 'result-content';
  resultContent.textContent = 'Đang gọi tool...';
  hideAudioPlayer();

  try {
    const res = await fetch('/api/tools/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool_name: currentTool.name, arguments: args })
    });
    const data = await res.json();
    const result = data.result ?? data;
    resultContent.textContent = JSON.stringify(result, null, 2);
    if (data.success === false || result?.success === false) resultContent.classList.add('error');

    // Nếu kết quả có audio_url → hiện player luôn
    if (result && result.audio_url) showAudioPlayer(result);
  } catch (e) {
    resultContent.classList.add('error');
    resultContent.textContent = `Lỗi: ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = '▶ Run Tool';
  }
}

function showAudioPlayer(result) {
  const url = result.audio_url;
  if (!url) return;

  const titleEl  = document.getElementById('audioTitle');
  const metaEl   = document.getElementById('audioMeta');
  const audioEl  = document.getElementById('storyAudio');
  const urlEl    = document.getElementById('audioUrlText');
  const wrap     = document.getElementById('audioPlayerWrap');

  titleEl.textContent = result.title || 'Truyện cổ tích';

  const parts = [];
  if (result.episode) parts.push(`EP.${result.episode}`);
  if (result.duration) parts.push(`⏱ ${result.duration}`);
  if (result.pub_date) parts.push(result.pub_date.split(' ').slice(1,4).join(' '));
  metaEl.textContent = parts.join('  •  ');

  // Set src trực tiếp trên audio element (đáng tin cậy hơn <source> con)
  audioEl.src = url;
  audioEl.load();
  audioEl.play().catch(() => {});

  urlEl.textContent = url;
  wrap.classList.add('show');

  // Scroll xuống để thấy player
  wrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function hideAudioPlayer() {
  const audioEl = document.getElementById('storyAudio');
  audioEl.pause();
  audioEl.src = '';
  document.getElementById('audioPlayerWrap').classList.remove('show');
}

function closeTestModal() {
  hideAudioPlayer();
  document.getElementById('testOverlay').classList.remove('show');
  currentTool = null;
}

function testOverlayClick(e) {
  if (e.target === document.getElementById('testOverlay')) closeTestModal();
}
