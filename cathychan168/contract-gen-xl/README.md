---
title: 贤凌合同生成服务
emoji: 📄
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# 贤凌合同生成服务（XL）

深圳市贤凌科技有限公司合同/订单生成微服务。
接收合同 JSON → 填 Excel 模板 → 转 PDF → 返回 base64。

## API

### POST /generate

```json
{
  "party_b": "客户公司全称",
  "products": [
    {"name": "示例型号", "unit": "kgs", "quantity": 400, "unit_price": 20.7}
  ],
  "party_b_phone": "",
  "party_b_address": "",
  "party_b_bank": "",
  "party_b_account": "",
  "output_format": "both",
  "doc_type": "正式合同"
}
```

返回：
```json
{
  "contract_no": "XL202605010001",
  "doc_type": "正式合同",
  "total_amount": 8280,
  "total_amount_cn": "捌仟贰佰捌拾元整",
  "filename_xlsx": "XL...xlsx",
  "filename_pdf": "XL...pdf",
  "excel_base64": "...",
  "pdf_base64": "..."
}
```

## 编号前缀

- `正式合同` → `XL` + YYYYMMDD + 4位序号（年度累计）
- `仅订单` → `DD` + YYYYMMDD + 4位序号（独立计数器）
