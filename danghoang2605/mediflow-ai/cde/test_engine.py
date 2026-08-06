"""
test_engine.py — Test cho Clinical Decision Engine v2 (Layer 1-5).

Bao gồm test HỒI QUY cho bug đã phát hiện qua chính việc viết engine này:
bệnh nhân sửa van bị phân loại nhầm subtype "mechanical" do NEGATION_PHRASES
thiếu cụm "khong phai" — đã sửa trong clinical_rules.py, giữ test ở đây để
không bị quay lại lỗi cũ.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from disease_classifier import classify_profiles, has_profile, identify_patient
from indicators import is_applicable
from engine import evaluate_v2


def _report(chan_doan, tien_su="", labs=None, drugs=None, tuoi=62, gioi="Nam"):
    return {
        "thong_tin_benh_nhan": {"tuoi": tuoi, "gioi_tinh": gioi},
        "chan_doan_chinh": chan_doan,
        "tien_su_benh": tien_su,
        "dau_hieu_sinh_ton": {},
        "xet_nghiem_key": labs or [],
        "thuoc_cuoi_ky": drugs or [],
    }


# ─── TEST HỒI QUY: subtype không bị nhầm khi có phủ định ─────────────────────
def test_valve_repair_khong_bi_nham_thanh_mechanical():
    """Bug đã phát hiện: 'đã sửa van. Không phải van cơ học.' từng bị phân
    loại subtype=mechanical. Phải là subtype=repair."""
    r = _report("Hở van hai lá nhiều, đã sửa van. Không phải van cơ học.")
    profiles = classify_profiles(r)
    assert has_profile(profiles, "valve_disease")
    assert has_profile(profiles, "valve_disease", "repair")
    assert not has_profile(profiles, "valve_disease", "mechanical")


def test_valve_mechanical_dung_phan_loai():
    r = _report("Sau phẫu thuật thay van động mạch chủ cơ học On-X.")
    profiles = classify_profiles(r)
    assert has_profile(profiles, "valve_disease", "mechanical")


def test_benh_nhan_khong_co_benh_van_khong_active_valve_profile():
    r = _report("Nhiễm trùng tiểu. Viêm phổi.")
    profiles = classify_profiles(r)
    assert not has_profile(profiles, "valve_disease")


# ─── TEST: 1 bệnh nhân thuộc nhiều profile cùng lúc ───────────────────────────
def test_benh_nhan_co_ca_van_co_hoc_va_rung_nhi():
    r = _report("Sau thay van cơ học On-X. Rung nhĩ mạn tính.")
    profiles = classify_profiles(r)
    assert has_profile(profiles, "valve_disease", "mechanical")
    assert has_profile(profiles, "atrial_fibrillation")
    assert len(profiles) == 2


def test_ckd_active_tu_egfr_thap_khong_can_keyword():
    """CKD phải active dù hồ sơ không có chữ 'suy thận' — chỉ cần eGFR thấp
    qua tính toán (calculated_trigger), đúng góp ý Tấn về việc profile có
    thể kích hoạt từ kết quả tính toán, không chỉ từ keyword."""
    r = _report("Sau mổ tim.", labs=[
        {"key": "Creatinin", "rawVal": 250, "trend": [250]},
    ], tuoi=70)
    egfr = 25  # giả lập eGFR thấp (không gọi compute_egfr thật ở đây để test độc lập)
    profiles = classify_profiles(r, egfr=egfr)
    assert has_profile(profiles, "ckd")


# ─── TEST: Indicator applicability (Layer 3) ──────────────────────────────────
def test_inr_target_mechanical_chi_applicable_khi_dung_subtype():
    profiles_mechanical = [{"profile_id": "valve_disease", "subtype": "mechanical", "ten_hien_thi": "x", "confidence": "x"}]
    profiles_repair = [{"profile_id": "valve_disease", "subtype": "repair", "ten_hien_thi": "x", "confidence": "x"}]
    assert is_applicable("inr_target_mechanical", profiles_mechanical) is True
    assert is_applicable("inr_target_mechanical", profiles_repair) is False


def test_valve_gradient_applicable_cho_moi_subtype_van():
    profiles_repair = [{"profile_id": "valve_disease", "subtype": "repair", "ten_hien_thi": "x", "confidence": "x"}]
    assert is_applicable("valve_gradient", profiles_repair) is True


def test_valve_gradient_khong_applicable_khi_khong_co_benh_van():
    assert is_applicable("valve_gradient", []) is False


def test_ttr_applicable_cho_ca_valve_va_af_khong_chi_rieng_valve():
    """Sửa đúng Vấn đề 1: TTR không còn ngầm định 'có INR = van cơ học'."""
    profiles_af_only = [{"profile_id": "atrial_fibrillation", "subtype": None, "ten_hien_thi": "x", "confidence": "x"}]
    assert is_applicable("ttr", profiles_af_only) is True


def test_egfr_luon_applicable_khong_can_profile():
    assert is_applicable("egfr", []) is True


# ─── TEST: engine.py end-to-end (Layer 1-5 tích hợp) ──────────────────────────
def test_evaluate_v2_tra_active_profiles():
    r = _report("Thay van cơ học On-X. Rung nhĩ.", labs=[
        {"key": "INR", "rawVal": 2.5, "trend": [2.0, 2.5, 3.0]},
    ])
    out = evaluate_v2(r)
    assert "active_profiles" in out
    profile_ids = [p["profile_id"] for p in out["active_profiles"]]
    assert "valve_disease" in profile_ids
    assert "atrial_fibrillation" in profile_ids
    # Tương thích ngược: field cũ vẫn còn
    assert "risk_scores" in out
    assert "egfr" in out


def test_evaluate_v2_khong_tinh_cha2ds2vasc_khi_khong_co_af_profile():
    r = _report("Viêm phổi. Không có bệnh tim mạch.")
    out = evaluate_v2(r)
    assert out["risk_scores"]["cha2ds2_vasc"] is None
    assert out["risk_scores"]["has_bled"] is None


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
