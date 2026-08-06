"""
MedParcours AI - Modes backend (Hội chẩn ảo + Giảng dạy)
=========================================================
Module độc lập, mount vào app FastAPI chính bằng register_modes(app).
Cung cấp:
  POST /mdt        body {"report": <report_json>}  -> JSON biên bản hội chẩn
  POST /teaching   body {"report": <report_json>}  -> JSON bài giảng theo khung HMU
  chat_system_for(mode, default)                   -> system prompt chat theo ngữ cảnh
Logic phản chiếu engine ở frontend (App.jsx) để bản gọi-thật khớp với demo.
Toàn bộ dựa trên dữ liệu CÓ TRONG report, không bịa thêm.
"""
from typing import Any, Dict, List
from pydantic import BaseModel

# ─── Tiện ích ────────────────────────────────────────────────────────────────
_ABBR = {
    "HoHL": "hở van hai lá", "HoBL": "hở van ba lá", "HHoC": "hẹp hở van động mạch chủ",
    "TAP": "tăng áp động mạch phổi", "ĐMC": "động mạch chủ", "ĐMP": "động mạch phổi",
    "VHL": "van hai lá", "VBL": "van ba lá", "AKI": "tổn thương thận cấp",
}

def expand_abbr(text: str) -> str:
    if not text:
        return ""
    out = text
    for k, v in _ABBR.items():
        out = out.replace(k, f"{k} ({v})") if k in out and f"{k} (" not in out else out
    return out

def match_kw(text: str, kws: List[str]) -> bool:
    t = (text or "").lower()
    return any(k in t for k in kws)

def pick_canh_bao(report: Dict[str, Any], kws: List[str]) -> List[Dict]:
    return [c for c in report.get("canh_bao_nguy_co", []) if match_kw(c.get("mo_ta", ""), kws)]

def short_label(s: str) -> str:
    if not s:
        return ""
    for sep in [":", " - ", "-"]:
        if sep in s:
            return s.split(sep)[0].strip()[:72]
    return s.strip()[:72]

def split_sentences(s: str) -> List[str]:
    import re
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", s or "") if len(x.strip()) > 2]

def clampN(n, a, b):
    return max(a, min(b, round(n)))

def risk_tone(p):
    return "green" if p >= 80 else ("amber" if p >= 60 else "red")

# ─── Định nghĩa chuyên khoa ──────────────────────────────────────────────────
SPEC_DEFS = [
    {"khoa": "Tim mạch", "relevance": "Rất cao", "role": "Đánh giá chức năng tim, van tim và nguy cơ suy tim.",
     "kw": ["van", "tim", "ef", "suy tim", "nt-probnp", "chênh áp", "hở van", "tăng áp", "mạch vành", "rung nhĩ"]},
    {"khoa": "Phẫu thuật Tim", "relevance": "Rất cao", "role": "Đánh giá kết quả mổ, vết mổ, dẫn lưu và biến chứng hậu phẫu.",
     "kw": ["mổ", "phẫu thuật", "sửa van", "thay van", "vòng van", "nội soi", "tuần hoàn ngoài cơ thể"]},
    {"khoa": "Hồi sức tích cực", "relevance": "Rất cao", "role": "Ổn định huyết động, hô hấp và cân bằng nội môi giai đoạn hậu phẫu.",
     "kw": ["lactate", "toan", "máy thở", "huyết động", "vận mạch", "phù phổi", "sốc", "hồi sức", "tưới máu", "an thần"]},
    {"khoa": "Truyền nhiễm", "relevance": "Cao", "role": "Đánh giá nhiễm khuẩn, lựa chọn và xuống thang kháng sinh.",
     "kw": ["nhiễm", "crp", "pct", "procalcitonin", "viêm", "bạch cầu", "sepsis", "kháng sinh", "cấy", "sốt"]},
    {"khoa": "Huyết học - Đông máu", "relevance": "Cao", "role": "Cân bằng nguy cơ chảy máu và huyết khối khi dùng chống đông.",
     "kw": ["inr", "chống đông", "đông máu", "tiểu cầu", "chảy máu", "huyết khối"]},
    {"khoa": "Thận - Tiết niệu", "relevance": "Cao", "role": "Theo dõi chức năng thận, cân bằng dịch và liều thuốc thải qua thận.",
     "kw": ["thận", "creatinin", "egfr", "aki", "lọc máu", "niệu"]},
    {"khoa": "Dinh dưỡng lâm sàng", "relevance": "Trung bình", "role": "Đánh giá và hỗ trợ dinh dưỡng để hồi phục và lành thương.",
     "kw": ["dinh dưỡng", "albumin", "suy kiệt", "sonde", "bmi", "nuôi dưỡng"]},
]
SPEC_GAP = {
    "Tim mạch": "Siêu âm tim kiểm tra lại sau can thiệp (chức năng và mức hở van).",
    "Phẫu thuật Tim": "Theo dõi vết mổ và dẫn lưu để loại trừ biến chứng ngoại khoa.",
    "Hồi sức tích cực": "Xu hướng huyết động khi giảm dần vận mạch.",
    "Truyền nhiễm": "Kết quả cấy định danh và kháng sinh đồ.",
    "Huyết học - Đông máu": "Thêm các lần đo INR để khẳng định ổn định.",
    "Thận - Tiết niệu": "Diễn biến chức năng thận khi điều chỉnh lợi tiểu.",
    "Dinh dưỡng lâm sàng": "Đánh giá nhu cầu năng lượng và khả năng dung nạp ăn đường miệng.",
}

def _meta(report, key):
    # Report thật dùng tên "xet_nghiem_key"; demo/mock có thể dùng "xet_nghiem_meta".
    # Đọc cả hai để MDT/Giảng dạy luôn lấy được chỉ số.
    labs = report.get("xet_nghiem_meta") or report.get("xet_nghiem_key") or []
    for x in labs:
        if (x.get("key", "") or "").lower() == key.lower():
            return x
    return None

def derive_risk(report):
    out = []
    ef = _meta(report, "EF")
    if ef and ef.get("rawVal") is not None:
        out.append({"ten": "Chức năng tim", "pct": clampN(min(95, ef["rawVal"] + 22), 20, 95)})
    bnp = _meta(report, "NT-proBNP")
    if bnp and bnp.get("rawVal") is not None:
        v = bnp["rawVal"]; out.append({"ten": "Kiểm soát suy tim", "pct": 75 if v < 1000 else 62 if v < 2500 else 50})
    crp = _meta(report, "CRP")
    if crp and crp.get("rawVal") is not None:
        v = crp["rawVal"]; out.append({"ten": "Kiểm soát nhiễm khuẩn", "pct": 85 if v < 10 else 64 if v < 50 else 55 if v < 120 else 45})
    egfr = _meta(report, "eGFR")
    if egfr and egfr.get("rawVal") is not None:
        v = egfr["rawVal"]; out.append({"ten": "Chức năng thận", "pct": 85 if v >= 60 else 60 if v >= 45 else 45})
    inr = _meta(report, "INR")
    if inr:
        tr = inr.get("trend", []) or []
        had_high = any((x or 0) > 3 for x in tr) or (inr.get("rawVal", 0) or 0) > 3
        in_range = 2 <= (inr.get("rawVal", 0) or 0) <= 3
        out.append({"ten": "Kiểm soát chống đông", "pct": 48 if had_high else 82 if in_range else 62})
    for o in out:
        o["tone"] = risk_tone(o["pct"])
    return out

def build_thread(report, names):
    t = []
    good = next((x for x in report.get("clinical_takeaway", []) if x.get("loai") == "good"), None)
    if "Tim mạch" in names:
        t.append({"khoa": "Tim mạch", "text": good["txt"] if good else "Chức năng tim ổn định, các chỉ số tim mạch đang cải thiện."})
    if "Truyền nhiễm" in names:
        t.append({"khoa": "Truyền nhiễm", "text": "Đồng ý. Tuy nhiên CRP/PCT từng rất cao, chưa thể loại trừ hoàn toàn nhiễm khuẩn tồn dư."})
    if "Huyết học - Đông máu" in names:
        t.append({"khoa": "Huyết học - Đông máu", "text": "Đồng ý. Tuy nhiên INR còn dao động, cần thận trọng nguy cơ chảy máu nếu can thiệp."})
    if "Hồi sức tích cực" in names:
        t.append({"khoa": "Hồi sức tích cực", "text": "Bổ sung: cần cai vận mạch và hỗ trợ hô hấp từng bước theo huyết động."})
    if "Thận - Tiết niệu" in names:
        t.append({"khoa": "Thận - Tiết niệu", "text": "Đồng ý. Lưu ý điều chỉnh liều thuốc và lợi tiểu theo chức năng thận."})
    if "Dinh dưỡng lâm sàng" in names:
        t.append({"khoa": "Dinh dưỡng lâm sàng", "text": "Nguy cơ dễ bị bỏ sót: suy kiệt làm chậm hồi phục và cai máy thở, cần nuôi dưỡng tích cực."})
    return t

def build_ask_mdt(report, names):
    def f(arr):
        return [a for a in arr if a["khoa"] in names]
    text = " ".join([report.get("chan_doan_chinh", "")] +
                    [c.get("mo_ta", "") for c in report.get("canh_bao_nguy_co", [])] +
                    [t.get("nhom", "") for t in report.get("thuoc_cuoi_ky", [])])
    has = lambda *k: match_kw(text, list(k))
    out = []
    if has("kháng sinh", "nhiễm", "crp", "pct"):
        out.append({"q": "Có nên xuống thang kháng sinh không?",
                    "answers": f([{"khoa": "Truyền nhiễm", "stance": "Nghiêng về Có", "ly_do": "CRP/PCT giảm mạnh, lâm sàng cải thiện."},
                                  {"khoa": "Hồi sức tích cực", "stance": "Trung lập", "ly_do": "Cần ổn định nguồn nhiễm trước khi thu hẹp phổ."},
                                  {"khoa": "Tim mạch", "stance": "Trung lập", "ly_do": "Ưu tiên đối chiếu kết quả cấy vi sinh."}]),
                    "moderator": {"muc": "Trung bình", "khuyen_nghi": "Tiếp tục theo dõi marker viêm và cân nhắc xuống thang khi có bằng chứng vi sinh phù hợp."}})
    if has("vận mạch", "dobutamine", "tăng co"):
        out.append({"q": "Có nên giảm/ngừng thuốc vận mạch (Dobutamine)?",
                    "answers": f([{"khoa": "Hồi sức tích cực", "stance": "Nghiêng về Có", "ly_do": "Huyết động cải thiện, lactate đã giảm."},
                                  {"khoa": "Tim mạch", "stance": "Trung lập", "ly_do": "Cần đánh giá cung lượng tim/EF trước khi cai."}]),
                    "moderator": {"muc": "Cao", "khuyen_nghi": "Giảm dần theo huyết động và lactate, không ngừng đột ngột; đánh giá lại chức năng tim mỗi bước."}})
    out.append({"q": "Đã đủ điều kiện chuyển bệnh nhân ra khỏi Hồi sức (ICU)?",
                "answers": f([{"khoa": "Hồi sức tích cực", "stance": "Nghiêng về Có", "ly_do": "Đã cai vận mạch, hô hấp tự thở ổn định."},
                              {"khoa": "Truyền nhiễm", "stance": "Trung lập", "ly_do": "Chờ marker nhiễm khuẩn giảm thêm và không sốt."},
                              {"khoa": "Tim mạch", "stance": "Nghiêng về Có", "ly_do": "Huyết động ổn, không còn phụ thuộc trợ tim."}]),
                "moderator": {"muc": "Trung bình", "khuyen_nghi": "Cân nhắc chuyển khoa khi huyết động - hô hấp ổn định và nhiễm khuẩn được kiểm soát."}})
    return out

def derive_mdt(report: Dict[str, Any]) -> Dict[str, Any]:
    text = " ".join([report.get("chan_doan_chinh", ""), report.get("tom_tat_toan_canh", "")] +
                    [c.get("mo_ta", "") for c in report.get("canh_bao_nguy_co", [])] +
                    [t.get("nhom", "") for t in report.get("thuoc_cuoi_ky", [])] +
                    [(report.get("phau_thuat") or {}).get("phuong_phap", "")])
    has = lambda *k: match_kw(text, list(k))
    specialties = []
    for s in SPEC_DEFS:
        if not match_kw(text, s["kw"]):
            continue
        cbs = pick_canh_bao(report, s["kw"])
        if cbs:
            full_eval = [c["mo_ta"] for c in cbs]
        elif s["khoa"] == "Tim mạch":
            full_eval = [expand_abbr(report.get("chan_doan_chinh", ""))]
        elif s["khoa"] == "Phẫu thuật Tim":
            full_eval = ["Kết quả mổ: " + ((report.get("phau_thuat") or {}).get("ket_qua") or "theo tường trình phẫu thuật")]
        else:
            full_eval = ["Phối hợp theo dõi chung; chưa ghi nhận vấn đề chuyên biệt nổi bật."]
        de_xuat = [a["viec"] for a in report.get("hanh_dong_uu_tien", []) if match_kw(a.get("viec", "") + " " + a.get("ly_do", ""), s["kw"])][:3]
        if not de_xuat and s["khoa"] == "Tim mạch":
            de_xuat = ["Theo dõi NT-proBNP, siêu âm tim kiểm tra"]
        has_num = any(any(ch.isdigit() for ch in (c.get("can_cu", "") or "")) for c in cbs)
        conf = 90 if (cbs and has_num) else (72 if cbs else 58)
        specialties.append({
            "khoa": s["khoa"], "relevance": s["relevance"], "role": s["role"],
            "ket_luan_chinh": [short_label(x) for x in full_eval[:2]],
            "de_xuat": de_xuat, "con_thieu": SPEC_GAP.get(s["khoa"], "Cần thêm dữ liệu theo dõi."),
            "confidence": conf, "muc_cao": any(c.get("muc_do") == "cao" for c in cbs),
            "details": {"danh_gia": full_eval, "ho_tro": [c.get("can_cu") for c in cbs if c.get("can_cu")]},
        })
    names = [s["khoa"] for s in specialties]
    order = ["sốc", "sepsis", "nhiễm", "lactate", "toan", "hô hấp", "máy thở", "phù phổi", "huyết động",
             "thận", "creatinin", "egfr", "inr", "chống đông", "dinh dưỡng", "albumin", "loét"]
    def sev(c):
        t = c["mo_ta"].lower()
        idx = next((i for i, k in enumerate(order) if k in t), 999)
        return idx
    cao = sorted([c for c in report.get("canh_bao_nguy_co", []) if c.get("muc_do") == "cao"], key=sev)
    priorities = [{"rank": i + 1, "ten": short_label(c["mo_ta"]), "ly_do": c["mo_ta"]} for i, c in enumerate(cao[:3])]
    agreement = ["Thống nhất chẩn đoán chính: " + expand_abbr(report.get("chan_doan_chinh", ""))]
    agreement += [t["txt"] for t in report.get("clinical_takeaway", []) if t.get("loai") == "good"]
    concern = [f'{p["ten"]}: {p["mo_ta"]}' for p in (report.get("problem_status", {}) or {}).get("hien_tai", []) if p.get("trang_thai") == "active"]
    concern += [c["mo_ta"] for c in cao[:2]]
    uncertainty = []
    if has("van", "sửa van", "thay van"):
        uncertainty.append("Chưa có siêu âm tim kiểm tra lại sau mổ để khẳng định mức hở van và chức năng tim.")
    if has("nhiễm", "cấy", "crp", "pct"):
        uncertainty.append("Chưa khẳng định tác nhân nhiễm khuẩn (cấy định danh, kháng sinh đồ).")
    if has("dinh dưỡng", "albumin", "sonde"):
        uncertainty.append("Khả năng dung nạp dinh dưỡng đường miệng và thời điểm rút nuôi dưỡng tĩnh mạch chưa rõ.")
    if not uncertainty:
        uncertainty.append("Một số dữ liệu theo dõi còn thiếu, cần bổ sung.")
    disagreement = []
    if has("vận mạch", "dobutamine", "tăng co"):
        disagreement.append("Thời điểm cai vận mạch: cai sớm để tránh tác dụng phụ hay duy trì để bảo đảm tưới máu?")
    if has("kháng sinh", "nhiễm", "sepsis", "crp", "pct"):
        disagreement.append("Kháng sinh phổ rộng: tiếp tục đủ liệu trình hay xuống thang sớm theo đáp ứng?")
    if has("inr", "chống đông"):
        disagreement.append("Mục tiêu INR: giữ thấp (gần 2.0) để giảm chảy máu hay chuẩn 2.0-3.0 để phòng huyết khối?")
    gd = report.get("ket_luan_giai_doan", {}) or {}
    consensus = gd.get("3") or gd.get(3) or gd.get("2") or gd.get(2) or report.get("tom_tat_toan_canh", "")[:260]
    return {"risk": derive_risk(report), "specialties": specialties, "priorities": priorities,
            "thread": build_thread(report, names),
            "discussion": {"agreement": agreement, "concern": concern, "uncertainty": uncertainty, "disagreement": disagreement},
            "ask_mdt": build_ask_mdt(report, names), "consensus": consensus}

# ─── Giảng dạy ───────────────────────────────────────────────────────────────
def build_decisions(report):
    text = " ".join([report.get("chan_doan_chinh", "")] + [c.get("mo_ta", "") for c in report.get("canh_bao_nguy_co", [])])
    has = lambda *k: match_kw(text, list(k))
    out = []
    if has("lactate", "toan"):
        out.append({"tinh_huong": "Hậu phẫu, lactate tăng cao kèm toan chuyển hóa, bệnh nhân còn phụ thuộc thuốc vận mạch.",
                    "options": [{"k": "A", "t": "Giảm vận mạch ngay"}, {"k": "B", "t": "Hồi sức tối ưu huyết động, theo dõi lactate clearance"},
                                {"k": "C", "t": "Cho ăn đường miệng sớm"}, {"k": "D", "t": "Ngừng theo dõi sát"}],
                    "dung": "B", "giai_thich": "Lactate cao phản ánh giảm tưới máu mô; ưu tiên tối ưu cung lượng tim và theo dõi xu hướng lactate. Giảm vận mạch quá sớm có thể làm nặng tụt tưới máu."})
    if has("inr", "chống đông"):
        out.append({"tinh_huong": "Bệnh nhân vừa mổ tim, INR vọt lên ngưỡng nguy cơ chảy máu.",
                    "options": [{"k": "A", "t": "Tăng liều chống đông"}, {"k": "B", "t": "Giữ nguyên liều"},
                                {"k": "C", "t": "Tạm ngừng/giảm liều và đánh giá nguy cơ chảy máu"}, {"k": "D", "t": "Truyền chế phẩm máu ngay"}],
                    "dung": "C", "giai_thich": "INR vượt mục tiêu trên bệnh nhân vừa phẫu thuật làm tăng nguy cơ chảy máu; cần giảm/tạm ngừng và đánh giá. Đảo ngược bằng chế phẩm chỉ khi có chảy máu hoặc cần can thiệp."})
    if not out and report.get("canh_bao_nguy_co"):
        c = report["canh_bao_nguy_co"][0]
        out.append({"tinh_huong": c["mo_ta"], "options": [{"k": "A", "t": "Theo dõi tiếp"}, {"k": "B", "t": "Xử trí theo ưu tiên đã nêu"},
                    {"k": "C", "t": "Cho xuất viện"}, {"k": "D", "t": "Bỏ qua"}], "dung": "B",
                    "giai_thich": "Đây là vấn đề ưu tiên cao, cần can thiệp theo hướng đã nêu."})
    return out

def derive_teaching(report: Dict[str, Any]) -> Dict[str, Any]:
    p = report.get("thong_tin_benh_nhan", {}) or {}
    dx = expand_abbr(report.get("chan_doan_chinh", ""))
    dxl = (report.get("chan_doan_chinh", "") or "").lower()
    dst = report.get("dau_hieu_sinh_ton")
    kham = []
    if dst:
        kham.append(f"Dấu hiệu sinh tồn ({dst.get('ngay','')}): HA {dst.get('ha_tt')}/{dst.get('ha_ttr')} mmHg, "
                    f"mạch {dst.get('mach')} l/ph, nhiệt độ {dst.get('nhiet_do')}, nhịp thở {dst.get('nhip_tho')}, "
                    f"SpO2 {dst.get('spo2')}%" + (f", lactate {dst.get('lactate')}" if dst.get("lactate") is not None else "") + ".")
    else:
        kham.append("Theo dõi toàn trạng và các cơ quan theo diễn biến.")
    kham += ["Khám tuần hoàn: trọng tâm tiếng tim, tiếng thổi và dấu hiệu suy tim (Nhìn - Sờ - Gõ - Nghe).",
             "Khám hô hấp, tiêu hóa, thận - tiết niệu: phát hiện biến chứng và đánh giá cơ quan liên quan."]
    ddx = []
    if match_kw(dxl, ["hở van", "hohl", "hở van hai lá", "hở van ba lá"]):
        ddx.append("Hở van do thoái hóa (sa van, đứt dây chằng) với hở van cơ năng do giãn vòng van / bệnh cơ tim.")
    if match_kw(dxl, ["hẹp", "hhoc", "đmc"]):
        ddx.append("Hẹp van ĐMC do thoái hóa vôi với van ĐMC hai mảnh bẩm sinh hoặc do thấp tim.")
    if match_kw(dxl, ["suy tim"]):
        ddx.append("Suy tim do bệnh van tim với suy tim do bệnh cơ tim giãn / thiếu máu cục bộ.")
    if match_kw(dxl, ["tăng áp"]):
        ddx.append("Tăng áp ĐMP nhóm 2 (do tim trái) với các nhóm tăng áp ĐMP khác.")
    if not ddx:
        ddx.append("Phân biệt nguyên nhân dựa trên bệnh cảnh và cận lâm sàng đặc hiệu.")
    red_flags = [{"dau_hieu": short_label(c.get("can_cu") or c.get("mo_ta", "")), "y_nghia": c.get("mo_ta", "")}
                 for c in report.get("canh_bao_nguy_co", []) if c.get("muc_do") == "cao"]
    reasoning_score = {"items": [
        {"ten": "Khai thác bệnh sử", "score": 9, "nx": "Nắm tốt diễn tiến trước - trong - sau mổ."},
        {"ten": "Tóm tắt bệnh án", "score": 8, "nx": "Cần làm nổi bật hơn các hội chứng chính."},
        {"ten": "Chẩn đoán phân biệt", "score": 7, "nx": "Bổ sung phân biệt nguyên nhân của tổn thương van."},
        {"ten": "Chỉ định cận lâm sàng", "score": 8, "nx": "Hợp lý; nên nêu rõ kết quả kỳ vọng."},
        {"ten": "Lập kế hoạch điều trị", "score": 9, "nx": "Toàn diện cả nội và ngoại khoa."},
    ], "overall": 82}
    phau = report.get("phau_thuat") or {}
    gd = report.get("ket_luan_giai_doan", {}) or {}
    tom_tat = split_sentences(report.get("tom_tat_toan_canh", ""))
    return {
        "dx": dx,
        "hanh_chinh": f"{p.get('ho_ten','')}, {p.get('tuoi','')} tuổi, {p.get('gioi_tinh','')}. Địa chỉ: {p.get('dia_chi','-')}. "
                      f"Vào viện: {p.get('ngay_vao_vien','')}. Số bệnh án: {p.get('so_benh_an','')}.",
        "ly_do": report.get("ly_do_vao_vien", ""),
        "benh_su": [f"{d.get('ngay','')}: {d.get('mo_ta','')}" for d in report.get("dien_bien_lam_sang", [])],
        "tien_su": report.get("tien_su_benh", ""), "kham": kham,
        "tom_tat": tom_tat, "chan_doan_so_bo": dx, "ddx": ddx,
        "bien_luan": [f"{l.get('tieu_de','')}: {l.get('noi_dung','')}" for l in report.get("ly_luan_lam_sang", [])],
        "can_lam_sang": [{"viec": a.get("viec", ""), "ly_do": a.get("ly_do", "")} for a in report.get("hanh_dong_uu_tien", [])],
        "dieu_tri_ngoai": (f"Ngoại khoa ({phau.get('ngay','')}): {phau.get('phuong_phap','')}" if phau else ""),
        "dieu_tri_noi": [f"{m.get('nhom','')}: {m.get('ten_thuoc','')}" for m in report.get("thuoc_cuoi_ky", [])],
        "tien_luong": gd.get("3") or gd.get(3) or gd.get("2") or gd.get(2) or "",
        "red_flags": red_flags, "decisions": build_decisions(report), "reasoning_score": reasoning_score,
        "muc_tieu": ["Khai thác bệnh sử và khám lâm sàng theo khung bệnh án ngoại khoa (HMU).",
                     "Tóm tắt thành hội chứng, chẩn đoán sơ bộ và phân biệt.",
                     "Biện luận và đề nghị cận lâm sàng hợp lý.",
                     "Trình bày điều trị, tiên lượng và dự phòng biến chứng."],
        "socratic": [
            {"q": "Từ bệnh sử và thăm khám, hãy tóm tắt ca này bằng 1-2 câu (nêu các hội chứng chính).", "a": " ".join(tom_tat[:2])},
            {"q": "Từ các dữ kiện hiện có, anh/chị nghĩ tới chẩn đoán sơ bộ nào và dựa vào đâu?", "a": f"{dx} Dựa trên bệnh cảnh suy tim, khám tim mạch và siêu âm tim."},
            {"q": "Vì sao nghĩ đến chẩn đoán đó? Dấu hiệu nào ủng hộ, dữ kiện nào chống lại?", "a": (report.get("ly_luan_lam_sang", [{}])[0].get("noi_dung") if report.get("ly_luan_lam_sang") else " ".join(ddx))},
            {"q": "Cần phân biệt với những bệnh nào?", "a": " ".join(ddx)},
            {"q": "Đề nghị cận lâm sàng nào và kỳ vọng kết quả gì?", "a": "; ".join(a.get("viec", "") for a in report.get("hanh_dong_uu_tien", []))},
            {"q": "Trình bày nguyên tắc điều trị và theo dõi hậu phẫu.", "a": (("Ngoại khoa: " + phau.get("phuong_phap", "") + ". ") if phau else "") + "Nội khoa: " + ", ".join(m.get("nhom", "") for m in report.get("thuoc_cuoi_ky", [])) + "."},
        ],
    }

# ─── System prompt chat theo ngữ cảnh (mode) ─────────────────────────────────
_TEACH_CHAT = """Bạn là MedAmi, GIA SƯ LÂM SÀNG cho sinh viên y khoa Việt Nam, dựa trên hồ sơ bệnh án được cung cấp.
Vai trò: đóng vai giảng viên lâm sàng, dẫn dắt người học suy luận theo khung bệnh án ngoại khoa (HMU):
bệnh sử, khám, tóm tắt, chẩn đoán sơ bộ, chẩn đoán phân biệt, biện luận, cận lâm sàng, điều trị, tiên lượng.
Cách trả lời:
1. Khi người học trả lời, hãy nhận xét điểm đúng, điểm còn thiếu và cách trình bày, rồi đặt câu hỏi dẫn dắt tiếp theo.
2. Khuyến khích người học tự suy luận trước; gợi mở bằng câu hỏi thay vì đưa ngay đáp án.
3. Chỉ dùng dữ kiện CÓ trong hồ sơ. Không bịa số liệu.
4. Không dùng bảng markdown, không emoji. Dùng gạch đầu dòng khi liệt kê. Tiếng Việt, không dùng dấu gạch ngang dài."""

_MDT_CHAT = """Bạn là MedAmi, THƯ KÝ Y KHOA của buổi hội chẩn đa chuyên khoa, dựa trên hồ sơ bệnh án được cung cấp.
Vai trò: tóm tắt và làm rõ nội dung hội chẩn (ưu tiên lâm sàng, ý kiến các chuyên khoa, điểm đồng thuận và khác biệt, khuyến nghị).
Cách trả lời:
1. Trung lập, mạch lạc, theo bố cục biên bản hội chẩn.
2. Khi có khác biệt quan điểm giữa các chuyên khoa, nêu rõ từng bên và mức đồng thuận.
3. Chỉ dùng dữ kiện CÓ trong hồ sơ. Không bịa số liệu, không đưa khuyến cáo điều trị mới ngoài hồ sơ.
4. Không dùng bảng markdown, không emoji. Dùng gạch đầu dòng khi liệt kê. Tiếng Việt, không dùng dấu gạch ngang dài."""

def chat_system_for(mode: str, default: str = "") -> str:
    if mode == "teaching":
        return _TEACH_CHAT
    if mode == "hoi_chan":
        return _MDT_CHAT
    return default

# ─── Mount vào app FastAPI chính ─────────────────────────────────────────────
class ReportRequest(BaseModel):
    report: Dict[str, Any]

def register_modes(app):
    from fastapi import HTTPException

    @app.post("/mdt")
    async def mdt_endpoint(req: ReportRequest):
        try:
            return derive_mdt(req.report)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Lỗi tạo hội chẩn: {e}")

    @app.post("/teaching")
    async def teaching_endpoint(req: ReportRequest):
        try:
            return derive_teaching(req.report)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Lỗi tạo bài giảng: {e}")

    return app
