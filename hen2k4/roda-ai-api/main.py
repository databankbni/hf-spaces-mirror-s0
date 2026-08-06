from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware # Thêm dòng này
from pydantic import BaseModel
from ultralytics import YOLO
from PIL import Image
import requests
from io import BytesIO
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(title="RODA Traffic AI API")

# BỔ SUNG ĐOẠN NÀY ĐỂ CHO PHÉP WEB GỌI API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Cho phép mọi trang web gọi vào
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


model = YOLO("best.pt")

# Định dạng dữ liệu web sẽ gửi sang (một đường link ảnh từ Supabase)
class ReportRequest(BaseModel):
    image_url: str


@app.post("/analyze-incident")
async def analyze_incident(request: ReportRequest):
    try:
        # 1. Tải ảnh từ URL do web gửi đến
        response = requests.get(request.image_url)
        response.raise_for_status()
        image = Image.open(BytesIO(response.content))
        
        # 2. Đưa ảnh vào mô hình AI để nhận diện
        results = model(image)
        
        best_match = None
        highest_conf = 0.0

        # 3. Quét kết quả để lấy vật thể rõ nhất
        for r in results:
            for box in r.boxes:
                conf = float(box.conf[0])
                class_id = int(box.cls[0])
                raw_class_name = model.names[class_id] 
                
                # Chỉ lấy vật thể có độ tự tin > 60%
                if conf > highest_conf and conf > 0.60:
                    highest_conf = conf
                    best_match = raw_class_name

        # 4. Trả kết quả chuẩn hóa về cho web
        if best_match:
            standard_label = "unknown"
            
            # Đồng bộ tên nhãn ngập úng
            if best_match.lower() in ["waterlogging", "flood", "flooded", "ngap_ung"]:
                standard_label = "flood"
            # Đồng bộ tên nhãn hố gà
            elif best_match.lower() in ["pothole", "potholes", "ho_ga", "pothole_fyp"]:
                standard_label = "pothole"
            # Đồng bộ tên nhãn thi công
            elif best_match.lower() in ["construction", "road_work", "dang_thi_cong"]:
                standard_label = "construction"
            else:
                standard_label = best_match.lower()

            # ---> GHI LOG KHI CÓ KẾT QUẢ
            logging.info(f"[DETECTED] URL: {request.image_url} | Nhãn: {standard_label} | Độ tự tin: {highest_conf:.2f}")

            return {
                "detected": True,
                "ai_label": standard_label,
                "raw_label": best_match, # Giữ lại nhãn gốc để dễ dò lỗi nếu cần
                "confidence": round(highest_conf, 2)
            }
        else:
            # ---> GHI LOG KHI KHÔNG PHÁT HIỆN SỰ CỐ
            logging.info(f"[CLEAR] URL: {request.image_url} | Không phát hiện sự cố.")
            
            return {
                "detected": False,
                "ai_label": "none",
                "raw_label": "none",
                "confidence": 0
            }
            
    except Exception as e:
        # ---> GHI LOG KHI API BỊ LỖI (Vd: URL ảnh hỏng, sập mạng...)
        logging.error(f"[ERROR] URL: {request.image_url} | Chi tiết: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))