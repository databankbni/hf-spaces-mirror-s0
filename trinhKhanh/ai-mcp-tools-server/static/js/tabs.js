/* Thanh tab trên cùng: chuyển giữa "Đăng ký tools" và "Mua thêm nội dung" */

let storeLoaded = false;   // chỉ nạp danh sách chủ đề ở lần mở tab đầu tiên

function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.tab === name)
  );
  document.querySelectorAll('.tab-page').forEach(page =>
    page.classList.toggle('active', page.id === `page-${name}`)
  );

  if (name === 'store' && !storeLoaded) {
    storeLoaded = true;
    loadCategories();
  }
}
