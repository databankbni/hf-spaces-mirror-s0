import os
import base64
import json
import re
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from zai import ZhipuAiClient  # 使用新的 SDK

from boom_detector import get_boom_times


BASE_DIR = Path(__file__).resolve().parent
VIDEO_DIR = BASE_DIR
ZHIPU_MODEL = os.environ.get("ZHIPU_MODEL", "glm-5v-turbo")  # 更换默认模型
USE_LOCAL_IMAGE = os.environ.get("USE_LOCAL_IMAGE", "false").lower() == "true"
ENABLE_THINKING = os.environ.get("ENABLE_THINKING", "true").lower() == "true"  # 是否启用深度思考

ALLOWED_VIDEO_EXTS = {
    ".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v"
}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

CACHE = {}


class AnalyzeRequest(BaseModel):
    video: str
    pivot_x: float | None = None
    pivot_y: float | None = None


class AICoordRequest(BaseModel):
    image_base64: str
    prompt: str
    target_type: str | None = None
    frame_time: float | None = None
    video_width: int | None = None
    video_height: int | None = None


@app.get("/")
def index():
    index_path = BASE_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)


@app.get("/videos")
def list_videos():
    videos = []
    for p in VIDEO_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in ALLOWED_VIDEO_EXTS:
            videos.append(p.name)
    videos.sort()
    return {
        "videos": videos,
        "count": len(videos)
    }


@app.get("/ai_health")
def ai_health():
    api_key = os.environ.get("ZHIPU_API_KEY")
    info = {
        "has_api_key": bool(api_key),
        "api_key_prefix": api_key[:8] + "..." if api_key else None,
        "model": ZHIPU_MODEL,
        "sdk": "zai",
        "status": "not_tested"
    }
    if not api_key:
        info["status"] = "failed"
        info["error"] = "ZHIPU_API_KEY 未配置"
        return info
    try:
        client = ZhipuAiClient(api_key=api_key)
        response = client.chat.completions.create(
            model=ZHIPU_MODEL,
            messages=[{"role": "user", "content": "请只回复 OK"}]
        )
        info["status"] = "ok"
        info["response"] = response.choices[0].message.content
        return info
    except Exception as e:
        info["status"] = "failed"
        info["error_type"] = type(e).__name__
        info["error"] = str(e)
        return info


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    video_name = os.path.basename(req.video)
    ext = os.path.splitext(video_name)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTS:
        raise HTTPException(status_code=400, detail="不支持的视频格式")
    video_path = VIDEO_DIR / video_name
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"后端没有找到视频文件: {video_name}")
    cache_key = f"{video_name}:{req.pivot_x}:{req.pivot_y}"
    if cache_key in CACHE:
        return CACHE[cache_key]
    try:
        result = get_boom_times(str(video_path), pivot_x=req.pivot_x, pivot_y=req.pivot_y)
        response = {
            "video": video_name,
            "boom_start": result.get("boom_start"),
            "boom_end": result.get("boom_end"),
            "lift": result.get("lift_start"),
            "place": result.get("place_end")
        }
        CACHE[cache_key] = response
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai_mark_boom_tip")
@app.post("/ai_mark")
def ai_mark_boom_tip(req: AICoordRequest):
    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ZHIPU_API_KEY 未配置")

    # 强制忽略前端传来的 prompt，避免重复
    req.prompt = ""

    # 如果启用本地图片测试，则使用本地文件 frame_31s.jpg 替换前端传来的图片
    image_base64 = req.image_base64
    if USE_LOCAL_IMAGE:
        local_img_path = BASE_DIR / "frame_31s.jpg"
        if local_img_path.exists():
            with open(local_img_path, "rb") as f:
                img_bytes = f.read()
            image_base64 = "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode()
            print("🔍 使用本地图片 frame_31s.jpg 替换前端图片")
        else:
            print("⚠️ 本地图片 frame_31s.jpg 不存在，继续使用前端图片")

    # 解码图片获取尺寸
    try:
        if "," in image_base64:
            header, encoded = image_base64.split(",", 1)
        else:
            encoded = image_base64
        img_data = base64.b64decode(encoded)
        with open("api_received.jpg", "wb") as f:
            f.write(img_data)
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("无法解码图片")
        height, width = img.shape[:2]
        print(f"🔍 后端接收图片尺寸: width={width}, height={height}")
        print(f"🔍 图片base64前缀: {image_base64[:100]}...")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"图片解析失败: {str(e)}")

    target_type = (req.target_type or "general").strip().lower()
    frame_time_text = ""
    if req.frame_time is not None:
        frame_time_text = f"\n当前帧来自视频时间 {req.frame_time:.3f} 秒。"

    # 构造任务描述
    if target_type == "boom_tip":
        task_instruction = """
你需要在这张塔吊施工监控画面中，找到"塔吊主吊臂最外端的臂尖点"。

重要定义：
- 主吊臂是从塔身顶部向施工区域伸出的长桁架结构。
- 目标点是主吊臂沿长度方向距离塔身最远的端部中心点。
- 如果能看到吊臂上下两根桁架边线，请取两根边线在最外端处的中间点。
- 如果最外端是三角桁架端头，请取三角端头最外侧的中心点。
- 如果端部较细或不清晰，请沿主吊臂方向外推，估计最外端中心点。

严禁选择：
- 吊钩；
- 吊物；
- 小车；
- 塔身顶部；
- 平衡臂；
- 配重臂；
- 吊臂中间节点；
- 图片上的红色网格线或文字。
"""
    elif target_type == "trolley":
        task_instruction = """
你需要在这张塔吊施工监控画面中，找到"塔吊吊臂小车中心点"。

定义：
- 小车是在塔吊吊臂上沿吊臂方向移动的机构。
- 通常吊钩钢丝绳从小车下方垂下。
- 目标点取小车结构的视觉中心，或者吊钩钢丝绳与吊臂连接处附近的小车中心。
- 不是吊钩底部，不是吊物中心，不是塔臂尖端，不是塔身。
- 如果小车外形不明显，请优先选择竖直吊绳与吊臂相交处附近的中心点。
"""
    else:
        task_instruction = "你需要在这张施工监控画面中找到用户指定的目标点。"

    # 用户补充描述强制为空
    user_prompt = ""

    full_prompt = f"""
{task_instruction}

用户补充描述：
{user_prompt}
{frame_time_text}

图片尺寸信息：
- 图片宽度：{width} 像素
- 图片高度：{height} 像素

坐标要求：
- 当前图片没有叠加任何坐标网格，请直接根据图像内容判断目标点位置。
- 请根据整张图片的左上角作为坐标原点。
- 左上角为 x_ratio=0, y_ratio=0。
- 右下角为 x_ratio=1, y_ratio=1。
- 请返回目标点在整张图片中的归一化坐标。
- x_ratio = 目标点到图片左边界的水平距离 / 图片宽度。
- y_ratio = 目标点到图片上边界的垂直距离 / 图片高度。
- 注意：如果图片中存在视频自带黑边，也必须把黑边计入整张图片坐标范围。
- 不要返回网页显示坐标。
- 不要返回 CSS 坐标。
- 不要返回裁剪后坐标。
- x_ratio 和 y_ratio 必须是 0 到 1 之间的小数。
- 只允许输出 JSON，不要输出解释，不要输出 markdown。

严格返回格式：
{{"x_ratio": 0.1234, "y_ratio": 0.5678}}
"""
    print("=== FULL PROMPT ===")
    print(full_prompt)
    print("=== END PROMPT ===")
    print(f"🔍 使用的模型: {ZHIPU_MODEL}")
    print(f"🧠 深度思考模式: {'启用' if ENABLE_THINKING else '禁用'}")

    # 使用新的 zai SDK
    client = ZhipuAiClient(api_key=api_key)
    try:
        # 构建请求参数
        params = {
            "model": ZHIPU_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_base64}},
                        {"type": "text", "text": full_prompt}
                    ]
                }
            ],
            "temperature": 0.0,
            "top_p": 0.01,
            "seed": 42  # 固定种子增强确定性
        }
        if ENABLE_THINKING:
            params["thinking"] = {"type": "enabled"}

        response = client.chat.completions.create(**params)
        content = response.choices[0].message.content
        print(f"🔍 AI 原始返回内容: {content}")

        # 解析 JSON
        content = re.sub(r"```json\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"```\s*", "", content)
        content = content.strip()
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if match:
            content_json = match.group(0)
        else:
            content_json = content
        result = json.loads(content_json)

        if "x_ratio" in result and "y_ratio" in result:
            x_ratio = max(0.0, min(1.0, float(result["x_ratio"])))
            y_ratio = max(0.0, min(1.0, float(result["y_ratio"])))
            x = int(round(x_ratio * width))
            y = int(round(y_ratio * height))
        elif "x" in result and "y" in result:
            x = int(round(float(result["x"])))
            y = int(round(float(result["y"])))
            x = max(0, min(width - 1, x))
            y = max(0, min(height - 1, y))
            x_ratio = x / width
            y_ratio = y / height
        else:
            raise ValueError(f"缺少坐标字段: {result}")

        return {
            "success": True,
            "x": x,
            "y": y,
            "x_ratio": x_ratio,
            "y_ratio": y_ratio,
            "width": width,
            "height": height,
            "target_type": target_type
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"AI 返回格式错误，内容为: {content}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 调用失败: {str(e)}")


@app.get("/{filename}")
def serve_file(filename: str):
    safe_name = os.path.basename(filename)
    file_path = BASE_DIR / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    ext = file_path.suffix.lower()
    if ext in ALLOWED_VIDEO_EXTS:
        return FileResponse(file_path)
    if safe_name == "index.html":
        return FileResponse(file_path)
    raise HTTPException(status_code=403, detail="file type not allowed")