const puppeteer = require('puppeteer');

function getInvoiceHTML(info) {
  const { name, phone, orderNumber, date, title = 'فاتورة طلب' } = info;
  const products = info.products || [{ product: info.product || 'غير محدد', quantity: info.quantity || 0 }];
  const totalQty = products.reduce((s, p) => s + Number(p.quantity || 0), 0);
  const showCustomer = info.hideCustomer ? false : true;
  let rows = products.map(p => `<tr><td>${p.product}</td><td style="font-weight:700;color:#c47f2b">${p.quantity}</td></tr>`).join('');
  return `<!DOCTYPE html>
<html dir="rtl">
<head><meta charset="utf-8">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Noto Sans','Segoe UI',Tahoma,Arial,sans-serif;background:#f5f0eb;padding:20px;direction:rtl}
.invoice{max-width:520px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.1)}
.head{background:linear-gradient(135deg,#c47f2b,#8b5e2b);color:#fff;padding:28px 25px;text-align:center;position:relative}
.head .logo{font-size:32px;margin-bottom:4px;display:block}
.head h1{font-size:18px;font-weight:400;opacity:.9;margin-bottom:2px}
.head .shop{font-size:24px;font-weight:700;letter-spacing:1px}
.head .sub{font-size:12px;opacity:.8;margin-top:6px}
.head .sub span{background:rgba(255,255,255,.2);padding:3px 10px;border-radius:20px;display:inline-block;margin:2px}
.body{padding:22px 25px}
.tbl{width:100%;border-collapse:separate;border-spacing:0;margin:12px 0;border-radius:10px;overflow:hidden}
.tbl th{background:#8b5e2b;color:#fff;padding:11px 10px;font-size:13px;font-weight:500}
.tbl td{padding:10px;border-bottom:1px solid #f0ebe5;text-align:center;font-size:13px;color:#444}
.tbl tr:last-child td{border-bottom:none}
.tbl tr:hover td{background:#fdf9f5}
.total{display:flex;justify-content:space-between;padding:14px 16px;background:#f8f4ef;border-radius:10px;margin-top:12px;font-size:15px;color:#333}
.total .lbl{font-weight:500;color:#8b5e2b}
.total .val{font-weight:700;color:#c47f2b}
.foot{padding:18px;text-align:center;border-top:1px solid #f0ebe5;color:#8b5e2b;font-size:13px;background:#faf8f5}
.foot strong{font-size:15px}
</style></head><body>
<div class="invoice">
<div class="head">
<span class="logo">🍞</span>
<div class="shop">مخبز سنابل الطاحونه</div>
<h1>${title}</h1>
<div class="sub"><span>#${orderNumber}</span><span>${date}</span></div>
</div>
<div class="body">
${showCustomer ? `<div class="info-row">
<div><div class="lbl">الاسم</div><div class="val">${name}</div></div>
<div><div class="lbl">رقم الهاتف</div><div class="val">${phone}</div></div>
</div>` : ''}
<table class="tbl"><tr><th>المنتج</th><th>العدد</th></tr>${rows}</table>
<div class="total"><span class="lbl">إجمالي القطع</span><span class="val">${totalQty}</span></div>
</div>
<div class="foot"><strong>شكراً لطلبكم</strong><br>مخبز سنابل الطاحونه 🍞</div>
</div>
</body></html>`;
}

async function generateInvoiceImage(info) {
  const html = getInvoiceHTML(info);
  const browser = await puppeteer.launch({
    executablePath: process.env.CHROME_PATH || process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--no-zygote',
      '--disable-gpu',
    ],
  });
  try {
    const page = await browser.newPage();
    await page.setContent(html);
    await page.setViewport({ width: 600, height: 800 });
    const buf = await page.screenshot({ type: 'png', fullPage: true });
    return buf;
  } finally {
    await browser.close();
  }
}

module.exports = { generateInvoiceImage };
