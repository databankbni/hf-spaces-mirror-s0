/* Danh sách công cụ (lưới panel phải) + nhãn/icon dùng chung */

const TOOL_ICONS = {
  calculator: '🧮', google_search: '🔍', get_weather: '🌤',
  get_news: '📰', translate: '🌐', image: '🖼', tts: '🔊', stt: '🎤',
  get_gold_price: '🪙', play_story: '📖', search_stories: '🔎',
};
const TOOL_LABELS = {
  calculator: 'Máy tính', google_search: 'Tìm kiếm',
  get_weather: 'Thời tiết', get_news: 'Tin tức VNExpress',
  get_gold_price: 'Giá vàng', play_story: 'Phát Truyện', search_stories: 'Tìm Truyện',
};

let allTools = [];      // danh sách tools + schema từ /api/tools
// Tools vẫn đăng ký với thiết bị (DeepSeek gọi qua MCP) nhưng ẩn khỏi lưới UI.
const HIDDEN_TOOLS = ['show_why_image', 'hide_why_image'];

/* ---- Load system tools (right panel) ---- */
async function loadTools() {
  try {
    const { tools } = await fetch('/api/tools').then(r => r.json());
    allTools = tools || [];
    const grid = document.getElementById('toolsGrid');
    const visibleTools = allTools.filter(t => !HIDDEN_TOOLS.includes(t.name));
    if (!visibleTools.length) {
      grid.innerHTML = '<div class="loading-tools" style="color:#666">Chưa có công cụ nào</div>';
      return;
    }
    grid.innerHTML = visibleTools.map(t => `
      <div class="tool-card" onclick="openTestModal('${t.name}')" title="Click để test">
        <span class="tool-icon">${TOOL_ICONS[t.name] || '🔧'}</span>
        <div>
          <div class="tool-name">${TOOL_LABELS[t.name] || t.name}</div>
          <div style="font-size:10px;color:#555;margin-top:2px">▶ Click để test</div>
        </div>
      </div>`).join('');
  } catch {
    document.getElementById('toolsGrid').innerHTML =
      '<div class="loading-tools" style="color:#666">Không thể tải công cụ</div>';
  }
}
