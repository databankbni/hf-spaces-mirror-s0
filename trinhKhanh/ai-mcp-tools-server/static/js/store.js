/* Tab "Mua thêm nội dung": chủ đề của kho "1 vạn câu hỏi vì sao"
   Nguồn: GET /api/why/categories (đọc tools.why_questions trên Neon) */

const TOPIC_ICONS = {
  'vật lý':   '⚛️',
  'sinh học': '🧬',
  'vũ trụ':   '🪐',
  'hóa học':  '🧪',
};

async function loadCategories() {
  const grid = document.getElementById('topicGrid');
  const sub = document.getElementById('storeSub');
  grid.innerHTML = '<div class="store-empty">Đang tải danh sách chủ đề...</div>';

  try {
    const data = await fetch('/api/why/categories').then(r => r.json());
    const cats = data.categories || [];

    if (!data.success || !cats.length) {
      grid.innerHTML = `<div class="store-empty${data.success ? '' : ' error'}">${
        escapeHtml(data.error || 'Chưa có chủ đề nào')
      }</div>`;
      return;
    }

    sub.textContent =
      `${cats.length} chủ đề • ${data.total_questions} câu hỏi hiện có trong kho`;

    grid.innerHTML = cats.map(c => `
      <div class="topic-card">
        <div class="topic-head">
          <span class="topic-icon">${TOPIC_ICONS[c.category] || '📚'}</span>
          <span class="topic-name">${escapeHtml(c.category)}</span>
        </div>
        <div class="topic-stats">
          <span class="topic-stat">${c.total} câu hỏi</span>
          <span class="topic-stat muted">${c.with_image} có ảnh</span>
        </div>
        <button class="btn-buy" onclick="buyTopic('${escapeHtml(c.category)}')">
          Mua thêm nội dung
        </button>
      </div>`).join('');
  } catch (e) {
    grid.innerHTML = '<div class="store-empty error">Không tải được danh sách chủ đề</div>';
  }
}

function buyTopic(category) {
  // TODO: chưa có luồng thanh toán — cần chốt hành vi (gói mua? gọi API nào?).
  alert(`Chủ đề: ${category}\n\nChức năng mua chưa được đấu nối.`);
}
