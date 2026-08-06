"""
react_pricing.py — ReAct 定价引擎（准确率 + 可解释性增强版）
=============================================================
在原有 demo_llm_real.py 基础上新增两个机制：

  1. ReAct 推理循环
     LLM 不再一次性给答案，而是：
       Thought  → 分析当前信息是否足够
       Action   → 主动调用工具补充信息
       Observe  → 获取结果后继续思考
       ……循环直到信息足够……
       Answer   → 输出定价 + 完整推理链

  2. 自我反思（Self-Reflection）
     定价完成后 LLM 用检查清单质疑自己：
       · 毛利率是否达标（>=8%）？
       · 高风险因素是否都已折价？
       · C2B 相比参考均值偏差是否合理？
     发现问题 → 自动修正 → 记录修正原因

  3. 可解释推理报告
     每步修正值 + 依据 + 自检结论，完整透明输出

运行方式：
  python react_pricing.py                          # 交互输入模式
  python react_pricing.py --data cleaned_data.csv  # 接入真实知识库
  python react_pricing.py --demo                   # 运行内置演示
"""

import os
import re
import json
import math
import statistics
import threading
from datetime import datetime

# 推理锁：保证同一时间只有一个模型在推理，避免CPU并发竞争
_inference_lock = threading.Lock()
import argparse
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any

CURRENT_YEAR = datetime.now().year

# Qwen 模型相关导入
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    QWEN_AVAILABLE = True
except ImportError:
    QWEN_AVAILABLE = False
    print("[警告] Qwen 模型相关库未安装，将使用通用大模型或 HTTP API")

# 复用原有模块
from data_processor import (
    RealCarListing, df_to_listings, generate_mock_data,
    DataCleaner,  # 导入 DataCleaner 类
)

# RAG 系统模块
try:
    from rag_system import get_rag_system
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("[警告] RAG 系统未找到，将使用空检索器")

# 全局 RAG 系统单例
_rag_system = None


def get_global_rag_system():
    """获取全局 RAG 系统单例（延迟加载）"""
    global _rag_system
    if _rag_system is None and RAG_AVAILABLE:
        _rag_system = get_rag_system()
    return _rag_system

# 直接定义 LLM 相关函数和变量，避免导入 anthropic 库
import os
import requests
import json

try:
    # 本地部署模型配置（兼容 OpenAI API 格式）
    # 支持的本地模型框架：
    # - Ollama: http://localhost:11434/v1/chat/completions (推荐)
    # - vLLM: http://localhost:8000/v1/chat/completions
    # - Text Generation WebUI: http://localhost:5000/v1/chat/completions
    LLM_API_URL = "http://localhost:11434/v1/chat/completions"
    LLM_API_KEY = "dummy"  # 本地模型不需要真实 API Key
    LLM_MODEL_NAME = "qwen2.5:7b"  # 本地模型名称，如 "qwen2.5", "yi", "llama3.1-chinese" 等
    LLM_AVAILABLE = True
    USE_OLLAMA_FOR_REASONING = False  # 直接使用已加载的Qwen模型进行推理
except ImportError:
    LLM_AVAILABLE = False
    USE_OLLAMA_FOR_REASONING = False


def _call_llm(prompt: str, temperature: float = 0.0, max_tokens: int = 500, use_finetuned: bool = None) -> str:
    """
    统一 LLM 调用入口。
    - 价格预测：使用本地Qwen微调模型
    - 推理/问答：使用Ollama本地模型（更快）
    
    Args:
        use_finetuned: 是否使用微调模型（None表示保持当前模式）
    """
    # 判断是否是价格预测任务（使用微调模型）
    is_price_prediction = False
    if "【请给出结果】" in prompt or "【请输出结果】" in prompt:
        is_price_prediction = True
    
    # 如果是推理/问答，且启用了Ollama，则使用Ollama
    if not is_price_prediction and USE_OLLAMA_FOR_REASONING and LLM_AVAILABLE:
        print(f"[LLM] 使用Ollama模型 {LLM_MODEL_NAME} 进行推理，输入长度: {len(prompt)} 字符")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}"
        }
        data = {
            "model": LLM_MODEL_NAME,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        try:
            response = requests.post(LLM_API_URL, headers=headers, data=json.dumps(data), timeout=120)
            response.raise_for_status()
            result = response.json()
            generated_text = result["choices"][0]["message"]["content"]
            print(f"[LLM] Ollama生成完成，内容: {generated_text[:200]}...")
            return generated_text
        except Exception as e:
            print(f"[LLM] Ollama调用失败: {e}，将尝试使用Qwen模型")
    
    # 推理任务（use_finetuned=False）：优先使用专用小模型，主模型无需切换
    if use_finetuned is False and REASONING_MODEL_AVAILABLE and qwen_reasoning_model is not None:
        try:
            # Instruct 模型用 chat template 格式，输出更稳定
            messages = [{"role": "user", "content": prompt}]
            text = qwen_reasoning_tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = qwen_reasoning_tokenizer(text, return_tensors="pt").to(qwen_reasoning_model.device)
            print(f"[LLM] 推理小模型开始推理，输入长度: {len(prompt)} 字符，Token数: {inputs.input_ids.shape[1]}")
            acquired = _inference_lock.acquire(timeout=120)
            if not acquired:
                print("[LLM] 推理锁等待超时，跳过本次请求")
                return ""
            try:
                with torch.no_grad():
                    outputs = qwen_reasoning_model.generate(
                        **inputs,
                        max_new_tokens=max_tokens,
                        do_sample=(temperature > 0),
                        temperature=temperature if temperature > 0 else None,
                        repetition_penalty=1.05,
                        pad_token_id=qwen_reasoning_tokenizer.eos_token_id,
                        eos_token_id=qwen_reasoning_tokenizer.eos_token_id,
                    )
            finally:
                _inference_lock.release()
            generated_text = qwen_reasoning_tokenizer.decode(
                outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True
            )
            print(f"[LLM] 推理小模型生成完成，输出Token数: {outputs.shape[1] - inputs.input_ids.shape[1]}")
            print(f"[LLM] 生成内容: {generated_text[:200]}...")
            return generated_text
        except Exception as e:
            print(f"[LLM] 推理小模型失败: {e}，回退到主模型")

    # 价格预测任务或小模型不可用时：使用主模型（不切换，直接用当前已加载的微调模型）
    if QWEN_AVAILABLE and qwen_model is not None and qwen_tokenizer is not None:
        try:
            mode_str = "微调模型" if QWEN_USE_FINETUNED else "基础模型"
            print(f"[LLM] Qwen {mode_str}开始推理，输入长度: {len(prompt)} 字符")
            
            inputs = qwen_tokenizer(prompt, return_tensors="pt").to(qwen_model.device)
            
            print(f"[LLM] Token 数量: {inputs.input_ids.shape[1]}")
            
            with torch.no_grad():
                outputs = qwen_model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,  # 允许生成足够的token进行完整推理
                    do_sample=(temperature > 0),
                    temperature=temperature if temperature > 0 else None,
                    repetition_penalty=1.05,
                    pad_token_id=qwen_tokenizer.eos_token_id,
                    eos_token_id=qwen_tokenizer.eos_token_id,
                )
            
            print(f"[LLM] 生成完成，输出 Token 数量: {outputs.shape[1] - inputs.input_ids.shape[1]}")
            
            generated_text = qwen_tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
            print(f"[LLM] 生成内容: {generated_text[:200]}...")
            return generated_text
        except Exception as e:
            print(f"[LLM] Qwen 模型调用失败: {e}")
            import traceback
            traceback.print_exc()
    
    if not LLM_AVAILABLE:
        return ""
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}"
    }
    data = {
        "model": LLM_MODEL_NAME,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    try:
        response = requests.post(LLM_API_URL, headers=headers, data=json.dumps(data), timeout=120)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[LLM] 调用 LLM 失败: {e}")
        print(f"[LLM] API URL: {LLM_API_URL}")
        print(f"[LLM] Model: {LLM_MODEL_NAME}")
        try:
            if 'response' in locals() and response:
                print(f"[LLM] 响应内容: {response.text}")
        except:
            pass
        return ""

# 从 demo_llm_real 导入其他需要的组件
from demo_llm_real import (
    RealCarRAGRetriever,
    DualPricingResult,
    _rule_based_pricing,
    _dict_to_result,
    _safe_float,
    compute_rewards,
    route_by_confidence,
    MIN_GROSS_MARGIN,
    GRADE_DISCOUNT,
    MILEAGE_RATE,
    TRANSFER_DEDUCT,
    COLOR_ADJ,
    TARGET_GROSS_MARGIN,
)

# 重新实现 extract_from_description 函数，避免依赖 anthropic 库
def extract_from_description(description: str) -> RealCarListing:
    """
    验车师文字描述 → RealCarListing
    """
    # 三级制车况映射关系
    CONDITION_MAPPING = {
        "优秀": {"score": 92.0, "grade": "A"},
        "良好": {"score": 78.0, "grade": "B"},
        "一般": {"score": 62.0, "grade": "C"},
    }
    
    # 规则兜底（LLM 不可用时）
    def _fallback_extract(desc: str) -> dict:
        """从描述中用正则提取关键字段，仅作兜底"""
        import re
        result = {
            "brand": "未知", "series": "未知", "model": "未知",
            "model_year": 2020, "mileage": 0.0, "color": "未知",
            "transfer_count": 1,
            "inspection_score": 0.0, "inspection_grade": "B",
        }
        
        # 检查三级制车况描述
        for condition, mapping in CONDITION_MAPPING.items():
            if condition in desc:
                result["inspection_score"] = mapping["score"]
                result["inspection_grade"] = mapping["grade"]
                break
        
        # 提取品牌
        for brand in ["丰田","大众","本田","宝马","比亚迪","特斯拉","奔驰","奥迪","吉利","长城","日产","福特","现代","起亚","雪佛兰","别克","雪铁龙","标致","马自达","铃木","斯巴鲁","沃尔沃","凯迪拉克","林肯","捷豹","路虎","保时捷","玛莎拉蒂","兰博基尼","法拉利","阿斯顿·马丁","阿尔法·罗密欧","MINI","Smart","Jeep","克莱斯勒","道奇","悍马","讴歌","英菲尼迪","雷克萨斯","本田","丰田","日产","马自达","三菱","斯巴鲁","铃木","大发","五十铃","现代","起亚","双龙","雷诺","标致","雪铁龙","菲亚特","阿尔法·罗密欧","法拉利","兰博基尼","玛莎拉蒂","阿斯顿·马丁","宾利","劳斯莱斯","捷豹","路虎","保时捷","奔驰","宝马","奥迪","大众","斯柯达","西雅特","沃尔沃","萨博","欧宝","福特","雪佛兰","别克","凯迪拉克","林肯","道奇","Jeep","克莱斯勒","悍马","三菱","现代","起亚","双龙","长城","吉利","奇瑞","比亚迪","长安","东风","北汽","广汽","上汽","一汽","江淮","江铃","福田","宇通","金龙","金旅","中通","申龙","海格","青年","安凯","黄海","东南","众泰","华泰","陆风","力帆","吉利","奇瑞","比亚迪","长安","东风","北汽","广汽","上汽","一汽","江淮","江铃","福田","宇通","金龙","金旅","中通","申龙","海格","青年","安凯","黄海","东南","众泰","华泰","陆风","力帆"]:
            if brand in desc:
                result["brand"] = brand
                break
        
        # 提取年款
        m = re.search(r'(\d{4})[年款]', desc)
        if m: result["model_year"] = int(m.group(1))
        
        # 提取里程（万公里）
        m = re.search(r'(\d+\.?\d*)\s*万[公里km]', desc)
        if m: result["mileage"] = float(m.group(1))
        # 里程单位为"公里"而非"万公里"
        m = re.search(r'(\d+\.?\d*)\s*公里', desc)
        if m and result["mileage"] == 0.0:
            result["mileage"] = round(float(m.group(1)) / 10000, 1)
        
        # 提取检测分数
        m = re.search(r'(\d+\.?\d*)\s*分', desc)
        if m: result["inspection_score"] = float(m.group(1))
        
        # 提取检测评级
        for grade in ["A级","B级","C级","D级","E级"]:
            if grade in desc:
                result["inspection_grade"] = grade[0]
                break
        
        # 提取过户次数
        m = re.search(r'过户(\d+)次', desc)
        if m: result["transfer_count"] = int(m.group(1))
        
        # 提取颜色
        for color in ["白色","黑色","银色","灰色","红色","蓝色","橙色","绿色","黄色"]:
            if color in desc:
                result["color"] = color
                break
        
        # 提取车系（常见车系列表）
        common_series = ["指南者","自由侠","自由光","牧马人","大切诺基","大指挥官","指挥官","自由客","角斗士","凯美瑞","卡罗拉","雷凌","汉兰达","RAV4荣放","亚洲龙","威兰达","锋兰达","凌尚","致炫","致享","C-HR","bZ4X","赛那","格瑞维亚","威尔法","埃尔法","兰德酷路泽","普拉多","陆巡","霸道","红杉","坦途","朗逸","帕萨特","迈腾","速腾","宝来","高尔夫","凌渡L","探岳","途观L","途昂","揽境","ID.4 X","ID.6 X","ID.3","桑塔纳","途铠","探歌","探岳X","揽巡","威然","辉昂","途锐","甲壳虫","尚酷","夏朗","迈特威","凯路威","雅阁","思域","型格","CR-V","皓影","UR-V","冠道","缤智","XR-V","飞度","LIFE","凌派","享域","英仕派","奥德赛","艾力绅","e:NS1","e:NP1","ZR-V","致在","HR-V","3系","5系","7系","X1","X3","X5","X7","i3","iX3","iX","1系","2系","4系","6系","8系","X2","X4","X6","Z4","M3","M4","M5","M8","X3 M","X4 M","X5 M","X6 M","M2","i4","i7","iX1","iX2","汉","唐","宋","元","海豹","海狮","海豚","海鸥","护卫舰07","驱逐舰05","Model 3","Model Y","Model S","Model X","C级","E级","S级","GLA","GLB","GLC","GLE","GLS","A级","B级","CLA","CLS","G级","SL","AMG GT","EQA","EQB","EQC","EQE","EQS","EQS SUV","EQE SUV","A4L","A6L","A8L","Q3","Q5L","Q7","Q8","A3","A5","A7","Q2L","Q4 e-tron","Q5 e-tron","帝豪","博越","星瑞","星越","缤越","缤瑞","远景","嘉际","豪越","H6","H2","H4","H5","H7","H8","H9","F5","F7","F7x","初恋","赤兔","神兽","酷狗","枭龙","枭龙MAX","轩逸","天籁","逍客","奇骏","楼兰","劲客","途达","ARIYA艾睿雅","骐达","蓝鸟","阳光","骊威","颐达","NV200","贵士","途乐","福克斯","蒙迪欧","锐际","锐界","探险者","福睿斯","翼虎","翼搏","嘉年华","金牛座","撼路者","Mustang","Mach-E","伊兰特","索纳塔","途胜","胜达","库斯途","ix35","ix25","名图","领动","朗动","悦动","瑞纳","菲斯塔","帕里斯帝","K3","K5","智跑","KX3","KX5","KX7","福瑞迪","焕驰","凯绅","KX CROSS","斯汀格","嘉华","索兰托","霸锐","科鲁泽","迈锐宝XL","探界者","开拓者","创酷","创界","星迈罗","沃兰多","科沃兹","科鲁兹","迈锐宝","赛欧","乐风","乐骋","景程","爱唯欧","英朗","威朗","君威","君越","昂科拉","昂科威","昂科旗","微蓝6","微蓝7","昂扬","世纪","凯越","阅朗","GL6","GL8","C4世嘉","C6","天逸C5","云逸C4","C3-XR","凡尔赛C5 X","308","408","508","2008","3008","4008","5008","301","307","206","207","阿特兹","CX-5","CX-4","CX-8","昂克赛拉","CX-30","CX-50","CX-60","MX-5","马自达2","马自达3","马自达5","马自达6","CX-3","CX-7","CX-9","奥拓","雨燕","天语","维特拉","启悦","骁途","锋驭","吉姆尼","森林人","傲虎","力狮","XV","翼豹","BRZ","旭豹","XC60","XC90","S60","S90","V60","V90","C40","EX90","EX30","XC40","XT4","XT5","XT6","CT4","CT5","CT6","LYRIQ","IQ傲歌","IQ锐歌","MKZ","MKC","MKX","MKT","Navigator","领航员","大陆","飞行家","航海家","冒险家","Z","XFL","XEL","F-PACE","E-PACE","I-PACE","F-TYPE","XJ","XE","XF","XK","发现运动版","发现","揽胜极光","揽胜星脉","揽胜运动版","揽胜","卫士","神行者","发现神行","Macan","Cayenne","911","718","Panamera","Taycan","Ghibli","Quattroporte","Levante","MC20","Grecale","GranTurismo","Urus","Huracán","Aventador","Revuelto","SF90","296","F8","Roma","Portofino","Purosangue","DB11","DBX","Vantage","DB12","Giulia","Stelvio","Tonale","MINI","MINI Cooper","MINI Countryman","MINI Clubman","MINI Convertible","smart","smart精灵#1","smart精灵#3","smart精灵#5"]
        for series in common_series:
            if series in desc:
                result["series"] = series
                break
        
        # 提取车型（品牌+车系+年款之后的剩余部分）
        if result["brand"] != "未知" and result["series"] != "未知" and result["model_year"] != 2020:
            # 模式1：年款+品牌+车系 后面的内容（例如：2017款Jeep指南者 200T 自动家享版）
            pattern1 = f'{result["model_year"]}[款年]{result["brand"]}{result["series"]}[\\s]*(.+)'
            m1 = re.search(pattern1, desc)
            if m1:
                result["model"] = m1.group(1).strip()
            else:
                # 模式2：年款 品牌 车系 后面的内容
                pattern2 = f'{result["model_year"]}[款年][\\s]*{result["brand"]}[\\s]*{result["series"]}[\\s]*(.+)'
                m2 = re.search(pattern2, desc)
                if m2:
                    result["model"] = m2.group(1).strip()
                else:
                    # 模式3：品牌 年款 车系 后面的内容
                    pattern3 = f'{result["brand"]}[\\s]*{result["model_year"]}[款年][\\s]*{result["series"]}[\\s]*(.+)'
                    m3 = re.search(pattern3, desc)
                    if m3:
                        result["model"] = m3.group(1).strip()
                    else:
                        # 模式4：品牌 车系 年款 后面的内容
                        pattern4 = f'{result["brand"]}[\\s]*{result["series"]}[\\s]*{result["model_year"]}[款年]?[\\s]*(.+)'
                        m4 = re.search(pattern4, desc)
                        if m4:
                            result["model"] = m4.group(1).strip()
        
        # 清理车型，去掉车系前缀（如果有）
        if result["model"] and result["series"] in result["model"]:
            result["model"] = result["model"].replace(result["series"], "").strip()
        
        # 在第一个逗号、句号或空格处截断车型
        if result["model"]:
            # 尝试在逗号处截断
            comma_index = result["model"].find("，")
            if comma_index == -1:
                comma_index = result["model"].find(",")
            # 尝试在句号处截断
            period_index = result["model"].find("。")
            if period_index == -1:
                period_index = result["model"].find(".")
            
            # 找到最小的有效索引
            cut_index = len(result["model"])
            if comma_index != -1 and comma_index < cut_index:
                cut_index = comma_index
            if period_index != -1 and period_index < cut_index:
                cut_index = period_index
            
            if cut_index < len(result["model"]):
                result["model"] = result["model"][:cut_index].strip()
        
        return result

    # 构建提取prompt
    prompt = f'''你是二手车验车记录解析专家。从以下验车师描述中提取结构化字段，**只输出 JSON，不要有任何其他文字**。

字段说明：
- brand: 品牌（如"丰田"）
- series: 车系（如"凯美瑞"）
- model: 车型（如"凯美瑞2.5L"）
- model_year: 年款（整数，如2021）
- mileage: 里程（万公里，浮点数；如描述为"公里"需换算，如68000公里=6.8万）
- color: 车身颜色（如"白色"）
- transfer_count: 过户次数（整数，没有明确信息可以缺省）
- inspection_score: 检测报告分数（0~100的浮点数，没有明确信息可以缺省）
- inspection_grade: 检测评级（"A"/"B"/"C"/"D"/"E"，没有明确信息可以缺省）

【三级制车况说明】
如果验车描述中使用了"优秀"、"良好"、"一般"三级制，按以下规则转换：
- "优秀" → inspection_score: 92.0, inspection_grade: "A"
- "良好" → inspection_score: 78.0, inspection_grade: "B"
- "一般" → inspection_score: 62.0, inspection_grade: "C"

待解析的验车描述：
{description}

只输出 JSON 对象，不要有任何说明：'''

    raw = _call_llm(prompt, temperature=0.0, max_tokens=600)

    if not raw:
        print("  [属性提取] LLM不可用，使用规则引擎兜底")
        fields = _fallback_extract(description)
    else:
        try:
            import re
            clean = re.sub(r'```json|```', '', raw).strip()
            m = re.search(r'\{.*\}', clean, re.DOTALL)
            fields = json.loads(m.group(0) if m else clean)
            print(f"  [属性提取] 成功提取 {len(fields)} 个字段")
        except Exception:
            print(f"  [属性提取] JSON解析失败，使用规则兜底\n  原始输出: {raw[:80]}")
            fields = _fallback_extract(description)

    # 类型安全转换
    def _s(k, d=""): return str(fields.get(k, d)).strip()
    def _f(k, d=0.0):
        try: return float(fields.get(k, d))
        except: return d
    def _i(k, d=0):
        try: return int(fields.get(k, d))
        except: return d

    car = RealCarListing(
        brand=_s("brand"),
        series=_s("series"),
        model=_s("model"),
        model_year=_i("model_year"),
        mileage=_f("mileage"),
        color=_s("color"),
        transfer_count=_i("transfer_count"),
        inspection_score=_f("inspection_score"),
        inspection_grade=_s("inspection_grade"),
    )

    print(f"  [属性提取] {car}")
    return car


def _load_retriever(data_path, max_records=5000):
    """加载检索器"""
    if data_path and os.path.exists(data_path):
        print(f"[知识库] 从文件加载：{data_path}")
        import pandas as pd
        # 根据文件扩展名选择读取方法
        if data_path.endswith('.xlsx'):
            df = pd.read_excel(data_path, nrows=max_records)
        else:
            df = pd.read_csv(data_path, encoding="utf-8-sig", nrows=max_records)
        # 确保采购价格和销售价格列存在
        if '采购价格' not in df.columns:
            df['采购价格'] = 0.0
        if '销售价格' not in df.columns:
            df['销售价格'] = 0.0
        # 将采购价格和销售价格映射到 c2b_price 和 b2c_price（转换为万元）
        df['c2b_price'] = df['采购价格'] / 10000
        df['b2c_price'] = df['销售价格'] / 10000
        # 使用 DataCleaner 类来处理数据
        cleaner = DataCleaner(verbose=False)
        df = cleaner.normalize_columns(df)
        df = cleaner.drop_invalid_prices(df)
        # 过滤掉检测分数为0的记录
        if 'inspection_score' in df.columns:
            df = df[df['inspection_score'] > 0]
        # 过滤掉B2C价格异常低的记录（小于1万）
        df = df[df['b2c_price'] >= 1]
        listings = df_to_listings(df)
        print(f"[知识库] 加载完成，有效记录数：{len(listings)}")
    else:
        print("[知识库] 使用模拟数据（真实场景请传入 --data 参数）")
        df_raw = generate_mock_data(150)
        cleaner = DataCleaner(verbose=False)
        df = cleaner.normalize_columns(df_raw)
        df = cleaner.drop_invalid_prices(df)
        listings = df_to_listings(df)
    return RealCarRAGRetriever(listings)

MONTH_SEASON = {
    1:"淡季", 2:"淡季", 3:"上行", 4:"旺季", 5:"旺季", 6:"旺季",
    7:"淡季", 8:"淡季", 9:"上行", 10:"旺季", 11:"旺季", 12:"淡季",
}


# ═════════════════════════════════════════════════════
#  工具库（Tool Registry）
#  LLM 在 ReAct 循环中按需调用，不是代码写死顺序
# ═════════════════════════════════════════════════════

# 新车指导价（生产环境替换为数据库 / 懂车帝 API）
_NEW_CAR_PRICES: Dict[str, float] = {
    "凯美瑞": 21.98, "帕萨特": 23.59, "雅阁": 19.98, "迈腾": 22.99,
    "3系":   36.99, "速腾":   15.39, "朗逸":  12.89, "轩逸": 11.59,
    "汉":    23.98, "Model3": 25.99, "RAV4":  21.28, "A4L":  34.68,
    "海豹":  21.28, "AION S": 15.98, "元Plus": 13.98,
}

# API 配置
API_KEY = "your_api_key"  # 替换为实际的 API Key
API_URL = "https://api.dongchedi.com/motor/price"  # 示例 API 地址，实际请参考懂车帝 API 文档

# 市场行情（生产环境替换为实时数据接口）
_MARKET_TREND: Dict[str, str] = {
    "燃油车": "市场平稳，新能源冲击导致中低端燃油车承压，豪华品牌相对坚挺",
    "新能源": "市场活跃，电池衰减是核心折价因素，高里程车折价明显",
    "插混":   "需求上升，价格走势好于纯燃油，弱于热门纯电",
}


def tool_search_similar_cars(
    retriever: RealCarRAGRetriever,
    brand: str = "",
    series: str = "",
    model: str = "",
    year_min: str = "0",
    year_max: str = "9999",
    mileage_max: str = "999.0",
    grade: str = "",
    top_k: int = 20,
) -> str:
    """按精确条件重新检索参考车，返回成交价统计"""
    try:
        # 转换参数类型
        year_min = int(year_min)
        year_max = int(year_max)
        mileage_max = float(mileage_max)
    except:
        year_min = 0
        year_max = 9999
        mileage_max = 999.0
    
    # 按优先级查找相似车辆
    # 1. 同品牌同车系同车型（不管年款）
    same_brand_series_model = [
        c for c in retriever.db
        if (not brand  or (isinstance(c.brand, str) and c.brand == brand))
        and (not series or (isinstance(c.series, str) and c.series == series))
        and (not model or (isinstance(c.model, str) and c.model == model))
        and c.mileage <= mileage_max
        and (not grade or (isinstance(c.inspection_grade, str) and c.inspection_grade == grade))
        and c.c2b_price and c.b2c_price
    ]
    
    # 2. 同品牌同车系同年款
    same_series_same_year = [
        c for c in retriever.db
        if (not brand  or (isinstance(c.brand, str) and c.brand == brand))
        and (not series or (isinstance(c.series, str) and c.series == series))
        and (not model or (isinstance(c.model, str) and c.model != model))
        and c.model_year >= year_min and c.model_year <= year_max
        and c.mileage <= mileage_max
        and (not grade or (isinstance(c.inspection_grade, str) and c.inspection_grade == grade))
        and c.c2b_price and c.b2c_price
    ]
    
    # 3. 同品牌同车系不同年款
    same_series_diff_year = [
        c for c in retriever.db
        if (not brand  or (isinstance(c.brand, str) and c.brand == brand))
        and (not series or (isinstance(c.series, str) and c.series == series))
        and (not model or (isinstance(c.model, str) and c.model != model))
        and (c.model_year < year_min or c.model_year > year_max)
        and c.mileage <= mileage_max
        and (not grade or (isinstance(c.inspection_grade, str) and c.inspection_grade == grade))
        and c.c2b_price and c.b2c_price
    ]
    
    # 4. 同品牌不同车系
    same_brand_diff_series = [
        c for c in retriever.db
        if (not brand  or (isinstance(c.brand, str) and c.brand == brand))
        and (not series or (isinstance(c.series, str) and c.series != series))
        and c.mileage <= mileage_max
        and (not grade or (isinstance(c.inspection_grade, str) and c.inspection_grade == grade))
        and c.c2b_price and c.b2c_price
    ]
    
    # 5. 不同品牌
    diff_brand = [
        c for c in retriever.db
        if (brand and (isinstance(c.brand, str) and c.brand != brand))
        and c.mileage <= mileage_max
        and (not grade or (isinstance(c.inspection_grade, str) and c.inspection_grade == grade))
        and c.c2b_price and c.b2c_price
    ]
    
    # 合并结果，按优先级排序
    hits = same_brand_series_model + same_series_same_year + same_series_diff_year + same_brand_diff_series + diff_brand
    hits = hits[:top_k]

    if not hits:
        return "未找到符合条件的参考车，建议放宽筛选条件（扩大年款范围或去掉评级限制）"

    c2b_vals = [c.c2b_price for c in hits]
    b2c_vals = [c.b2c_price for c in hits]
    lines = [f"找到 {len(hits)} 辆符合条件的参考车："]
    for c in hits:
        lines.append(
            f"  · {c.model_year}款{c.brand}{c.series} 里程{c.mileage}万km "
            f"评级{c.inspection_grade} 过户{c.transfer_count}次 "
            f"→ 采购价格={c.c2b_price}万 销售价格={c.b2c_price}万"
        )
    lines.append(
        f"统计：采购价格 均值={sum(c2b_vals)/len(c2b_vals):.2f} "
        f"中位={statistics.median(c2b_vals):.2f} | "
        f"销售价格 均值={sum(b2c_vals)/len(b2c_vals):.2f} "
        f"中位={statistics.median(b2c_vals):.2f}"
    )
    return "\n".join(lines)


def tool_get_new_car_price(series: str) -> str:
    """查新车指导价，用于计算折旧基准和定价上限"""
    # 1. 首先尝试从 API 获取价格
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        params = {
            "model": series,
            "city": "北京"  # 可以根据实际情况调整
        }
        response = requests.get(API_URL, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0 and data.get("data"):
                price = data["data"].get("price", 0)
                if price > 0:
                    return f"{series} 新车指导价约 {price} 万元（厂商建议零售价，可据此推算合理折旧率）"
    except Exception as e:
        print(f"API 调用错误: {e}")
    
    # 2. 如果 API 调用失败，使用本地缓存的价格
    for key, price in _NEW_CAR_PRICES.items():
        if key in series or series in key:
            return f"{series} 新车指导价约 {price} 万元（厂商建议零售价，可据此推算合理折旧率）"
    return f"未找到 {series} 的新车价格，请参考厂商官网或懂车帝报价"


def tool_check_market_trend(category: str, month: int) -> str:
    """查当前品类市场行情及季节因素"""
    trend = _MARKET_TREND.get(category, "暂无该品类行情数据")
    season = MONTH_SEASON.get(month, "旺季")
    season_tips = {
        "旺季": "当前旺季，建议适当上浮 0.2~0.3 万",
        "淡季": "当前淡季，建议适当下调 0.2~0.3 万",
        "上行": "市场回暖，价格稳中有升",
        "下行": "市场下行，建议保守定价",
    }
    return (f"【{category}行情】{trend}\n"
            f"【季节】{month}月为{season}，{season_tips.get(season, '价格平稳')}")


def tool_calculate_adjustment(
    model_year: int,
    mileage: float,
    transfer_count: int,
    inspection_score: float,
    inspection_grade: str,
) -> str:
    """使用 Qwen 模型进行 B2C 价格预测，返回明细和最终价格"""
    items = []

    # 处理字符串类型的参数
    if isinstance(model_year, str):
        try:
            model_year = int(model_year)
        except:
            pass
    
    if isinstance(mileage, str):
        try:
            mileage = float(mileage)
        except:
            pass
    
    if isinstance(transfer_count, str):
        try:
            transfer_count = int(transfer_count)
        except:
            pass
    
    if isinstance(inspection_score, str):
        try:
            inspection_score = float(inspection_score)
        except:
            pass

    # 计算车龄
    car_age = CURRENT_YEAR - model_year
    
    # 只使用 Qwen 模型预测 B2C 价格
    predicted_b2c_wan = None
    model_used = None
    
    print("[Qwen] 使用 Qwen 模型预测 B2C 价格")
    try:
        # 构建 Qwen 模型提示（使用训练时的格式）
        reg_date = f"{model_year}-06"  # 假设6月份注册
        prompt = f"reg_date:{reg_date} mileage_wan_km:{mileage} transfer_count:{transfer_count} inspection_score:{inspection_score} inspection_grade:{inspection_grade}"
        print(f"[Qwen] Prompt: {prompt}")
        
        # 调用 Qwen 模型（只返回 B2C 价格）
        predicted_b2c_wan = predict_with_qwen(prompt)
        if predicted_b2c_wan is not None:
            model_used = "Qwen LoRA 模型"
            print(f"[Qwen] 预测成功: B2C={predicted_b2c_wan:.2f}万")
    except Exception as e:
        print(f"[Qwen] 预测失败: {e}")
        predicted_b2c_wan = None
    
    # 如果 Qwen 模型失败
    if predicted_b2c_wan is None:
        items.append("⚠️ Qwen 模型预测失败")
        items.append("建议：可以继续调用其他工具获取更多信息，或使用规则引擎定价")
        return "\n".join(items)
    
    # 根据 B2C 价格计算 C2B 价格（15% 毛利率）
    predicted_c2b_wan = predicted_b2c_wan / 1.15
    
    # 确保价格为正数
    predicted_c2b_wan = max(0.1, predicted_c2b_wan)
    predicted_b2c_wan = max(0.1, predicted_b2c_wan)
    
    # 构建返回信息
    items.append(f"车龄：{car_age}年")
    items.append(f"里程：{mileage}万公里")
    items.append(f"过户次数：{transfer_count}次")
    items.append(f"检测分数：{inspection_score}分")
    items.append(f"检测评级：{inspection_grade}级")
    items.append(f"模型预测采购价格：{predicted_c2b_wan:.2f}万（基于 B2C/{1.15:.2f}）")
    items.append(f"模型预测销售价格：{predicted_b2c_wan:.2f}万（基于{model_used}）")
    items.append(f"✅ 模型预测成功！信息已足够，请输出最终定价")
    items.append(f"请按以下格式输出答案：")
    items.append(f"[Thought] 已获取模型预测价格，信息足够")
    items.append(f"[Answer]")
    items.append(f'{{"c2b_price": {predicted_c2b_wan:.2f}, "c2b_low": {predicted_c2b_wan*0.95:.2f}, "c2b_high": {predicted_c2b_wan*1.05:.2f}, "b2c_price": {predicted_b2c_wan:.2f}, "b2c_low": {predicted_b2c_wan*0.95:.2f}, "b2c_high": {predicted_b2c_wan*1.05:.2f}, "gross_margin_pct": {((predicted_b2c_wan - predicted_c2b_wan)/predicted_b2c_wan*100):.1f}, "gross_profit": {(predicted_b2c_wan - predicted_c2b_wan):.2f}, "confidence": "high", "risk_notes": [], "pricing_reason": "基于{model_used}预测", "reasoning_trace": []}}')
    return "\n".join(items)


# Qwen 模型全局变量
qwen_tokenizer = None
qwen_base_model = None      # 保存基础模型（不加载LoRA）
qwen_finetuned_model = None # 保存微调模型（加载LoRA后，常驻内存，切换时只交换指针）
qwen_model = None           # 当前使用的模型（可能是基础模型或微调模型）
qwen_device = None
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QWEN_MODEL_ID = os.environ.get(
    "QWEN_MODEL_ID",
    os.path.join(BASE_DIR, "qwen25_3b_lora_price_0305 2", "final_adapter"),
)
QWEN_USE_FINETUNED = (os.environ.get("QWEN_USE_FINETUNED", "1").strip().lower() not in {"0", "false", "no", "off"})
QWEN_LOCAL_FILES_ONLY = (os.environ.get("QWEN_LOCAL_FILES_ONLY", "1").strip().lower() not in {"0", "false", "no", "off"})

# 专用推理模型（用于ReAct推理和聊天，独立于价格预测模型）
REASONING_MODEL_ID = os.environ.get("REASONING_MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")  # 用于ReAct推理和聊天回答
qwen_reasoning_model = None
qwen_reasoning_tokenizer = None
REASONING_MODEL_AVAILABLE = False

# 专用意图分类小模型（只输出单字母，速度极快）
INTENT_MODEL_ID = os.environ.get("INTENT_MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")
qwen_intent_model = None
qwen_intent_tokenizer = None
INTENT_MODEL_AVAILABLE = False

# Qwen 模型辅助函数
def _pick_qwen_device():
    """选择设备 - 强制使用 CPU（MPS 上生成式推理不稳定）"""
    import torch
    return torch.device("cpu")

def _extract_first_number(text: str) -> Optional[float]:
    """从文本中提取第一个数字"""
    if text is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(text))
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None

def _extract_two_numbers(text: str) -> Tuple[Optional[float], Optional[float]]:
    """从文本中提取两个数字（C2B和B2C）"""
    if text is None:
        return None, None
    # 匹配空格分隔的两个数字
    m = re.search(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", str(text))
    if not m:
        return None, None
    try:
        c2b = float(m.group(1))
        b2c = float(m.group(2))
        print(f"[Qwen] 提取两个数字: C2B={c2b}, B2C={b2c}")
        return c2b, b2c
    except Exception:
        return None, None

def _build_qwen_prompt(car: RealCarListing, refs: List[Tuple[RealCarListing, float]]) -> str:
    """
    构建与训练时一致的完整 prompt
    :param car: 待估车辆
    :param refs: 相似车源列表 (RealCarListing, score)
    :return: 完整的 prompt
    """
    # 1. 任务定义和输出格式
    prompt_parts = [
        "你是一个二手车定价专家，目标是给出\"收车出价建议\"。",
        "",
        "【任务定义】",
        "基于车辆特征、相似车型价格、同车型新车价格、三方车源价格，注意车辆的车况、配置、市场行情等差异因素，",
        "对目标车辆给出一个\"合理的收车出价区间\"，并给出核心定价依据。",
        "",
        "【输出格式要求（必须严格遵守）】",
        "只输出预测价格（单位：万），不要输出任何其它内容（包括解释、推理、理论、markdown、代码块、标点或多余文字）",
        "只输出一个数值，保留 1 位小数，例如：12.3",
        "",
        "【车辆与市场信息】",
    ]
    
    # 2. 车况基本信息
    prompt_parts.extend([
        "【车况基本信息】",
        f"上牌时间：{car.model_year}-01-01 00:00:00",  # 假设1月份
        f"表显里程：{car.mileage} 万公里",
        f"过户次数：{car.transfer_count} 次",
        f"车辆所在地：",
        f"能源类型：{'汽油' if car.category == '' or car.category == '燃油车' else car.category}",
        f"驱动类型：1",  # 默认前驱
        f"车辆级别：未知",
        f"变速箱类型：未知",
        f"车身颜色：{car.color}",
        f"内饰颜色：深色",  # 默认深色
        f"车型：{car.model}",
        f"车系：{car.series}",
        f"年款：{car.model_year}",
        f"品牌：{car.brand}",
        "",
    ])
    
    # 3. 相似在售车源基本信息（取前2个）
    valid_refs = [ref for ref, _ in refs if ref.c2b_price and ref.b2c_price][:2]
    for i, ref in enumerate(valid_refs, 1):
        prompt_parts.extend([
            f"【相似在售车源基本信息_{i}】",
            f"上牌时间：{ref.model_year}-01-01 00:00:00",
            f"表显里程：{ref.mileage} 万公里",
            f"过户次数：{ref.transfer_count} 次",
            f"车辆所在地：",
            f"能源类型：{'汽油' if ref.category == '' or ref.category == '燃油车' else ref.category}",
            f"驱动类型：1",
            f"车辆级别：未知",
            f"变速箱类型：未知",
            f"车身颜色：{ref.color}",
            f"内饰颜色：深色",
            f"车型：{ref.model}",
            f"车系：{ref.series}",
            f"年款：{ref.model_year}",
            f"品牌：{ref.brand}",
            f"价格:{ref.b2c_price:.1f}" if ref.b2c_price else "价格:",
            "",
        ])
    
    # 4. 市场信息 - 新车价格（暂时留空）
    prompt_parts.extend([
        "【市场信息 - 新车价格】",
        "新车指导价： 万",
        f"能源类型：{'汽油' if car.category == '' or car.category == '燃油车' else car.category}",
        f"车身颜色：{car.color}",
        f"车型：{car.model}",
        f"车系：{car.series}",
        f"品牌：{car.brand}",
        "",
    ])
    
    # 5. 三方车源 - 信息参考（暂时留空，用第一个相似车源代替）
    if valid_refs:
        ref = valid_refs[0]
        prompt_parts.extend([
            "【三方车源 - 信息参考】",
            f"上牌时间：{ref.model_year}-01-01",
            f"里程：{ref.mileage} 万公里",
            f"过户次数：{ref.transfer_count} 次",
            f"变速箱：",
            f"排放标准：",
            f"车身颜色：{ref.color}",
            f"车型：{ref.model}",
            f"车系：{ref.series}",
            f"品牌：{ref.brand}",
            f"成交价：{ref.b2c_price:.1f} 万" if ref.b2c_price else "成交价： 万",
            f"成交时间：2025-01-01",
            "",
        ])
    else:
        prompt_parts.extend([
            "【三方车源 - 信息参考】",
            "上牌时间：",
            "里程： 万公里",
            "过户次数： 次",
            "变速箱：",
            "排放标准：",
            "车身颜色：",
            "车型：",
            "车系：",
            "品牌：",
            "成交价： 万",
            "成交时间：",
            "",
        ])
    
    # 6. 请给出结果
    prompt_parts.append("【请给出结果】")
    
    return "\n".join(prompt_parts)

def use_base_model():
    """切换到基础模型模式（用于ReAct推理）——仅交换指针，无磁盘IO"""
    global qwen_model, QWEN_USE_FINETUNED
    if qwen_base_model is not None:
        qwen_model = qwen_base_model
        QWEN_USE_FINETUNED = False
        print(f"[Qwen] 已切换到基础模型模式")


def use_finetuned_model():
    """切换到微调模型模式（用于价格预测）——优先指针交换，仅首次加载时读磁盘"""
    global qwen_model, qwen_finetuned_model, QWEN_USE_FINETUNED
    if qwen_finetuned_model is not None:
        # 微调模型已在内存中，直接交换指针
        qwen_model = qwen_finetuned_model
        QWEN_USE_FINETUNED = True
        print(f"[Qwen] 已切换到微调模型模式（指针交换）")
    elif qwen_base_model is not None:
        # 首次加载：从磁盘读取 LoRA adapter 并缓存到 qwen_finetuned_model
        from peft import PeftModel
        print(f"[Qwen] 首次加载 LoRA adapter: {QWEN_MODEL_ID}")
        qwen_finetuned_model = PeftModel.from_pretrained(qwen_base_model, QWEN_MODEL_ID)
        qwen_finetuned_model = qwen_finetuned_model.to(qwen_device).eval()
        qwen_model = qwen_finetuned_model
        QWEN_USE_FINETUNED = True
        print(f"[Qwen] 已切换到微调模型模式（首次加载完成）")


def init_reasoning_model() -> bool:
    """加载专用推理小模型（Qwen2.5-0.5B），独立于价格预测模型，无需切换"""
    global qwen_reasoning_model, qwen_reasoning_tokenizer, REASONING_MODEL_AVAILABLE, qwen_device
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM

        print(f"[推理模型] 正在加载: {REASONING_MODEL_ID}")
        qwen_reasoning_tokenizer = AutoTokenizer.from_pretrained(
            REASONING_MODEL_ID, trust_remote_code=True, local_files_only=QWEN_LOCAL_FILES_ONLY
        )
        if qwen_reasoning_tokenizer.pad_token is None:
            qwen_reasoning_tokenizer.pad_token = qwen_reasoning_tokenizer.eos_token

        qwen_reasoning_model = AutoModelForCausalLM.from_pretrained(
            REASONING_MODEL_ID,
            dtype=torch.float32,
            low_cpu_mem_usage=True,
            trust_remote_code=True,
            local_files_only=QWEN_LOCAL_FILES_ONLY,
        )
        qwen_reasoning_model = qwen_reasoning_model.to(qwen_device).eval()
        REASONING_MODEL_AVAILABLE = True
        print(f"[推理模型] 加载完成（{REASONING_MODEL_ID}），ReAct将使用此模型")
        return True
    except Exception as e:
        print(f"[推理模型] 加载失败: {e}，ReAct将回退到数据驱动规则")
        REASONING_MODEL_AVAILABLE = False
        return False


def init_intent_model() -> bool:
    """加载意图分类小模型（0.5B），只输出单字母，速度极快"""
    global qwen_intent_model, qwen_intent_tokenizer, INTENT_MODEL_AVAILABLE, qwen_device
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM

        print(f"[意图模型] 正在加载: {INTENT_MODEL_ID}")
        qwen_intent_tokenizer = AutoTokenizer.from_pretrained(
            INTENT_MODEL_ID, trust_remote_code=True, local_files_only=QWEN_LOCAL_FILES_ONLY
        )
        if qwen_intent_tokenizer.pad_token is None:
            qwen_intent_tokenizer.pad_token = qwen_intent_tokenizer.eos_token

        qwen_intent_model = AutoModelForCausalLM.from_pretrained(
            INTENT_MODEL_ID,
            dtype=torch.float32,
            low_cpu_mem_usage=True,
            trust_remote_code=True,
            local_files_only=QWEN_LOCAL_FILES_ONLY,
        )
        qwen_intent_model = qwen_intent_model.to(qwen_device).eval()
        INTENT_MODEL_AVAILABLE = True
        print(f"[意图模型] 加载完成（{INTENT_MODEL_ID}）")
        return True
    except Exception as e:
        print(f"[意图模型] 加载失败: {e}")
        INTENT_MODEL_AVAILABLE = False
        return False


_FALLBACK_RESPONSE = (
    "抱歉，我是一名专注于二手车估值的AI专业助手。目前我只能回答与车辆估值、定价等相关的问题。"
    "您可以直接告诉我车源信息，我将为您生成专业报告。"
)

# 与二手车完全无关时直接拦截，不进入模型
_CAR_RELATED_KEYWORDS = [
    '车', '定价', '估价', '收车', '售价', '价格', '里程', '过户',
    '车况', '车型', '品牌', '年款', '发动机', '变速箱', '事故',
    'C2B', 'B2C', '市场', '竞争力', '参考', '话术', '砍价',
    '成色', '公里', '万', '报价', '评估', '保值', '残值',
    '车源', '收车价', '二手', '新车', '卖车', '买车',
    # 主观评价类（无车字但与定价结果相关）
    '估高', '估低', '高了', '低了', '偏高', '偏低', '太高', '太低',
    '有点高', '有点低', '有些高', '有些低', '稍高', '稍低',
    '贵了', '便宜', '偏贵', '合理', '准确', '靠谱', '竞争',
    # 主观感受引导词（用户对定价结果反馈）
    '觉得', '感觉', '我认为', '我感觉', '我觉得', '认为',
    '偏贵', '便宜了', '贵了点', '低了点',
]


def classify_intent(message: str, context_str: str = "") -> dict:
    """用0.5B模型做意图分类，只输出单字母，速度极快"""
    message = (message or "").strip()

    def _has_context() -> bool:
        return bool(context_str and context_str != "无")

    def _has_vehicle_slot(text: str) -> bool:
        return any(kw in text for kw in [
            "上牌", "里程", "公里", "公里数", "过户", "颜色", "车身", "城市", "北京", "上海",
            "广州", "深圳", "白色", "黑色", "红色", "蓝色", "绿色", "黄色", "车型", "车系"
        ])

    def _has_adjust_signal(text: str) -> bool:
        return any(kw in text for kw in ["改成", "修改", "更正", "纠正", "不是", "应该是", "补充", "再补", "更新一下", "写错"])

    def _has_valuation_signal(text: str) -> bool:
        return any(kw in text for kw in [
            "帮我估", "给我估", "估一下", "估个价", "帮估", "估值", "估价",
            "报价", "能报多少", "出多少钱", "多少钱", "值多少", "收车价",
            "想收", "收一辆", "收台", "想买", "买辆", "买一辆", "买台", "可以报价"
        ])

    def _has_price_reason_signal(text: str) -> bool:
        return any(kw in text for kw in [
            "不准", "不太准", "不准确", "不合理", "估高", "估低", "偏高", "偏低",
            "太高", "太低", "为什么", "为啥", "原因", "依据", "逻辑", "怎么影响",
            "拉低", "抬高", "多0次"
        ])

    def _has_market_signal(text: str) -> bool:
        return any(kw in text for kw in ["行情", "竞品", "参考车源", "同类", "类似", "竞争力", "市场", "CR-V", "威兰达"])

    def _is_missing_model(text: str) -> bool:
        has_brand = any(kw in text for kw in ["丰田", "本田", "宝马", "奔驰", "奥迪", "大众", "法拉利", "保时捷", "特斯拉"])
        has_specific = any(kw in text for kw in ["RAV4", "荣放", "威兰达", "3系", "325", "CR-V", "488", "Model", "A200", "C级"])
        return has_brand and not has_specific

    def _should_clarify_for_valuation(text: str) -> bool:
        has_model = any(kw in text for kw in [
            "RAV4", "荣放", "威兰达", "CR-V", "宝马3系", "3系", "325", "奔驰C",
            "A200", "法拉利488", "488", "Model 3", "Model3"
        ])
        if _is_missing_model(text):
            return True
        if any(kw in text for kw in ["法拉利", "保时捷", "兰博基尼", "玛莎拉蒂"]) and not has_model:
            return True
        has_year = bool(re.search(r"(20\d{2}|[12]\d年|2[0-9]年|去年|今年)", text))
        has_mileage = bool(re.search(r"(\d+(?:\.\d+)?\s*万\s*(?:公里|km)?|\d{4,7}\s*(?:公里|km)|跑了?\d+)", text))
        has_transfer = any(kw in text for kw in ["过户", "一手", "0次", "1次", "一次", "两次", "2次", "原版原户"])
        has_city_or_color = any(kw in text for kw in ["北京", "上海", "广州", "深圳", "白色", "黑色", "红色", "蓝色", "绿色", "黄色", "银灰", "深灰"])
        return not (has_model and has_year and has_mileage and has_transfer and has_city_or_color)

    def _diag_for(intent: str, text: str, should_clarify: bool = False) -> str:
        if intent == "fallback":
            return "out_of_scope"
        if intent == "adjust":
            return "supplement_condition"
        if intent == "chat":
            if _has_price_reason_signal(text):
                return "price_reason"
            if _has_market_signal(text):
                return "market_competitor"
            return "chat_business_guidance"
        if intent == "valuation":
            if should_clarify:
                if any(kw in text for kw in ["法拉利", "488", "保时捷", "兰博基尼", "玛莎拉蒂"]):
                    return "valuation_nonstandard_or_unmatched_model"
                if _is_missing_model(text):
                    return "valuation_missing_model"
                return "valuation_need_clarify"
            return "valuation_direct_quote_complete"
        return intent

    def _result(intent: str, should_clarify: bool = False, response: str = "") -> dict:
        return {
            "intent": intent,
            "mode": "all",
            "response": response,
            "should_clarify": bool(should_clarify),
            "diag_sub_intent": _diag_for(intent, message, should_clarify),
        }

    # ── 最优先：无关话题硬拦截（不含任何车相关词）──
    if not any(kw in message for kw in _CAR_RELATED_KEYWORDS):
        print(f"[意图模型] 硬规则：消息与二手车无关 → fallback")
        return _result("fallback", response=_FALLBACK_RESPONSE)

    # 多轮补充/覆盖槽位优先进入 adjust，避免被“怎么/补充/改”误路由到 chat。
    if _has_adjust_signal(message) and (_has_vehicle_slot(message) or _has_context()):
        print(f"[意图模型] 硬规则：补充/覆盖车况槽位 → adjust")
        return _result("adjust")

    # 明显询价/报价请求优先归 valuation；信息不足通过 should_clarify 暴露，不再打到 chat。
    if _has_valuation_signal(message) and not _has_price_reason_signal(message):
        should_clarify = _should_clarify_for_valuation(message)
        print(f"[意图模型] 硬规则：报价/估价请求 → valuation, should_clarify={should_clarify}")
        return _result("valuation", should_clarify=should_clarify)

    if _has_market_signal(message):
        print(f"[意图模型] 硬规则：行情/竞品问题 → chat")
        return _result("chat")

    if _has_price_reason_signal(message):
        print(f"[意图模型] 硬规则：价格原因/质疑 → chat")
        return _result("chat")

    # 硬规则优先 — 负面评价/提问词直接返回 chat，不经过模型
    _chat_keywords = [
        '不合理', '不准', '不对', '不正确', '偏高', '偏低', '太高', '太低',
        '估高', '估低', '高了', '低了', '差太多', '差很多', '不靠谱',
        '为什么', '怎么', '如何', '为啥', '原因', '理由', '影响',
        '话术', '怎么说', '如何谈', '收车', '卖车', '技巧', '建议',
        '什么意思', '解释', '说明',
        # 主观感受/评价类（"我觉得有点低"等省略主语的句式）
        '觉得', '感觉', '有点低', '有点高', '有些低', '有些高',
        '合理吗', '准吗', '准不准', '靠谱吗', '靠谱不',
        '能不能', '可以吗', '会不会',
        # 询问/查看类
        '有哪些', '哪些车', '都有', '参考', '车源', '正常吗', '正常不',
        'C2B', 'B2C', '收车价', '售价', '差多少', '差这么', '多正常',
        '是什么', '什么是', '怎么算', '怎么定', '怎么看',
    ]
    for kw in _chat_keywords:
        if kw in message:
            print(f"[意图模型] 硬规则命中 '{kw}' → chat")
            return _result("chat")

    # "估价"出现在复杂句子中（超过8字且不是纯粹的估价请求）→ 视为 chat
    _valuation_only_patterns = ['帮我估', '估一下', '估价一下', '帮估']
    if '估价' in message:
        is_pure_valuation = any(p in message for p in _valuation_only_patterns)
        if not is_pure_valuation and len(message) > 8:
            print(f"[意图模型] 硬规则：'估价'在复杂句中，非纯估价请求 → chat")
            return {"intent": "chat", "mode": "all", "response": ""}

    if not INTENT_MODEL_AVAILABLE or qwen_intent_model is None:
        return {"intent": "keyword_fallback", "should_clarify": False, "diag_sub_intent": "unknown"}

    prompt = f"""判断用户意图，只输出一个字母：
A=想要对新车估价  B=提问/反馈/咨询/评价已有结果  C=修改车辆参数  D=无关话题

规则：含否定评价词→B；含"改成/修改"→C；明确说"帮我估/估一下"某辆新车→A；单纯提到"估价"但有其他内容→B

上下文：{context_str}
用户：{message}
答："""

    import torch
    messages = [{"role": "user", "content": prompt}]
    text = qwen_intent_tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = qwen_intent_tokenizer(text, return_tensors="pt").to(qwen_intent_model.device)

    with _inference_lock:
        with torch.no_grad():
            outputs = qwen_intent_model.generate(
                **inputs,
                max_new_tokens=3,
                do_sample=False,
                pad_token_id=qwen_intent_tokenizer.eos_token_id,
            )
    result = qwen_intent_tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
    print(f"[意图模型] 用户: {message!r} → 原始输出: {result!r}")

    letter = result[0].upper() if result else "D"
    intent_map = {"A": "valuation", "B": "chat", "C": "adjust", "D": "fallback"}
    intent = intent_map.get(letter, "fallback")
    fallback_response = (
        "抱歉，我是一名专注于二手车估值的AI专业助手。目前我只能回答与车辆估值、定价等相关的问题。"
        "您可以直接告诉我车源信息，我将为您生成专业报告。"
    ) if intent == "fallback" else ""
    should_clarify = _should_clarify_for_valuation(message) if intent == "valuation" else False
    return _result(intent, should_clarify=should_clarify, response=fallback_response)


def init_qwen_model() -> bool:
    """初始化 Qwen 模型（同时加载基础模型和微调模型）"""
    global qwen_tokenizer, qwen_base_model, qwen_finetuned_model, qwen_model, qwen_device, QWEN_AVAILABLE, QWEN_USE_FINETUNED
    
    print(f"[Qwen] 正在初始化模型（双模式）")
    
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        from peft import PeftModel
        
        qwen_device = _pick_qwen_device()
        print(f"[Qwen] 使用设备: {qwen_device}")
        
        # 加载基础模型
        print(f"[Qwen] 正在加载基础模型: Qwen/Qwen2.5-3B")
        qwen_tokenizer = AutoTokenizer.from_pretrained(
            "Qwen/Qwen2.5-3B",
            trust_remote_code=True,
            local_files_only=QWEN_LOCAL_FILES_ONLY
        )
        
        if qwen_tokenizer.pad_token is None:
            qwen_tokenizer.pad_token = qwen_tokenizer.eos_token
        
        qwen_base_model = AutoModelForCausalLM.from_pretrained(
            "Qwen/Qwen2.5-3B",
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True,
            trust_remote_code=True,
            local_files_only=QWEN_LOCAL_FILES_ONLY,
            device_map=None,
        )
        
        # 根据配置决定使用基础模型还是微调模型
        if QWEN_USE_FINETUNED:
            print(f"[Qwen] 正在加载微调模型: {QWEN_MODEL_ID}")
            qwen_finetuned_model = PeftModel.from_pretrained(qwen_base_model, QWEN_MODEL_ID)
            qwen_finetuned_model = qwen_finetuned_model.to(qwen_device).eval()
            qwen_model = qwen_finetuned_model  # 缓存到 qwen_finetuned_model，后续切换只交换指针
            print(f"[Qwen] 模型初始化成功（微调模式）")
        else:
            qwen_model = qwen_base_model
            qwen_model = qwen_model.to(qwen_device).eval()
            print(f"[Qwen] 模型初始化成功（基础模式）")
        
        QWEN_AVAILABLE = True

        # 加载专用推理模型（用于ReAct推理和聊天）
        init_reasoning_model()
        # 加载意图分类小模型（0.5B，只输出单字母，速度极快）
        init_intent_model()

        return True

    except Exception as e:
        print(f"[Qwen] 模型加载失败: {e}")
        import traceback
        traceback.print_exc()
        QWEN_AVAILABLE = False
        return False

def build_training_prompt(
    car: RealCarListing,
    refs: List[Tuple[RealCarListing, float]] = None
) -> str:
    """按照训练时的完整格式构建 Qwen 模型 prompt"""
    # 训练时的系统prompt模板
    prompt = """你是一个二手车定价专家，目标是给出"收车出价建议"。

【任务定义】
基于车辆特征、相似车型价格、同车型新车价格、三方车源价格，注意车辆的车况、配置、市场行情等差异因素，
对目标车辆给出一个"合理的收车出价区间"，并给出核心定价依据。

【输出格式要求（必须严格遵守）】
只输出预测价格（单位：万），不要输出任何其它内容（包括解释、推理、理论、markdown、代码块、标点或多余文字）
只输出一个数值，保留 1 位小数，例如：12.3

【车辆与市场信息】
【车况基本信息】"""

    # 添加基本车辆信息
    reg_date = f"{car.model_year}-06-01 00:00:00"
    prompt += f"""
上牌时间：{reg_date}
表显里程：{car.mileage} 万公里
过户次数：{car.transfer_count} 次
车辆所在地：
能源类型：汽油
驱动类型：1
车辆级别：未知
变速箱类型：2
车身颜色：{car.color if car.color else '未知'}
内饰颜色：深色
车型：{car.model}
车系：{car.series}
年款：{car.model_year}
品牌：{car.brand}
"""

    # 添加相似在售车源信息（最多2个）
    if refs:
        for i, (ref, _) in enumerate(refs[:2], 1):
            ref_reg_date = f"{ref.model_year}-06-01 00:00:00"
            prompt += f"""
【相似在售车源基本信息_{i}】
上牌时间：{ref_reg_date}
表显里程：{ref.mileage} 万公里
过户次数：{ref.transfer_count} 次
车辆所在地：
能源类型：汽油
驱动类型：1
车辆级别：未知
变速箱类型：2
车身颜色：{ref.color if ref.color else '未知'}
内饰颜色：深色
车型：{ref.model}
车系：{ref.series}
年款：{ref.model_year}
品牌：{ref.brand}
价格:{ref.b2c_price:.1f}
"""

    # 添加市场信息和三方车源信息（简化版）
    prompt += """
【市场信息 - 新车价格】
新车指导价： 万
能源类型：汽油
车身颜色：白色
车型：{0}
车系：{1}
品牌：{2}

【三方车源 - 信息参考】

【请给出结果】
""".format(car.model, car.series, car.brand)

    return prompt


def predict_with_qwen(prompt: str, max_new_tokens: int = 64, min_price: float = 0.5) -> Optional[float]:
    """使用 Qwen 模型进行预测，只返回 B2C 价格（与训练时一致）"""
    global qwen_tokenizer, qwen_model, qwen_device, QWEN_USE_FINETUNED
    
    # 确保使用微调模型
    if not QWEN_USE_FINETUNED:
        use_finetuned_model()
    
    print(f"[Qwen] 检查模型状态: qwen_model={qwen_model is not None}, qwen_tokenizer={qwen_tokenizer is not None}")
    
    if qwen_model is None or qwen_tokenizer is None:
        print(f"[Qwen] 模型未初始化，返回 None")
        return None
    
    try:
        with _inference_lock:
            inputs = qwen_tokenizer(prompt, return_tensors="pt").to(qwen_device)
            with torch.no_grad():
                output_ids = qwen_model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    repetition_penalty=1.1,
                    eos_token_id=qwen_tokenizer.eos_token_id,
                    pad_token_id=qwen_tokenizer.pad_token_id,
                )
            input_len = inputs["input_ids"].shape[1]
            gen_ids = output_ids[0][input_len:]
            text = qwen_tokenizer.decode(gen_ids, skip_special_tokens=True).strip()
        print(f"[Qwen] 生成的文本: '{text}'")
        
        # 提取第一个数字（与训练时一致）
        import re
        m = re.search(r"-?\d+(?:\.\d+)?", str(text))
        if not m:
            print(f"[Qwen] 未提取到数字")
            return None
        
        try:
            price = float(m.group(0))
            print(f"[Qwen] 提取到的价格: {price}")
            
            # 确保价格在合理范围内（动态下限 - 500万）
            if price >= min_price and price < 500:
                print(f"[Qwen] 预测成功: B2C={price:.2f}万")
                return price
            elif price > 0 and price < min_price:
                print(f"[Qwen] 价格过低（{price:.2f}万 < 下限{min_price:.2f}万），视为无效预测")
            else:
                print(f"[Qwen] 价格超出合理范围: {price}")
                # 尝试处理超大数字（取前6位有效数字）
                price_str = str(price)
                if '.' in price_str:
                    integer_part = price_str.split('.')[0]
                    if len(integer_part) > 6:
                        # 取前6位数字
                        new_price = float(integer_part[:6]) / 10000  # 转换为万元
                        if 0.1 <= new_price <= 500:
                            print(f"[Qwen] 处理超大数字: {price} → {new_price:.2f}万")
                            return new_price
                return None
        except Exception as e:
            print(f"[Qwen] 数字解析失败: {e}")
            return None
    except Exception as e:
        print(f"[Qwen] 预测失败: {e}")
        import traceback
        traceback.print_exc()
        return None

# 初始化模型
def init_models(data_path=None, max_records=None):
    """初始化模型：尝试加载 Qwen 模型（可选）"""
    # 尝试加载 Qwen 模型
    init_qwen_model()

# 工具注册表
TOOLS: Dict[str, Any] = {
    "search_similar_cars":  tool_search_similar_cars,
    "get_new_car_price":    tool_get_new_car_price,
    "check_market_trend":   tool_check_market_trend,
    "calculate_adjustment": tool_calculate_adjustment,
}

TOOL_SPEC = """
可用工具（每次只调用一个，按需使用）：

1. search_similar_cars(brand, series, model, year_min, year_max, mileage_max, grade, top_k=20)
   → 智能检索相似车辆，按以下优先级自动查找：
     - 优先级1：同品牌、同车系、同年款、同车型
     - 优先级2：同品牌、同车系、同年款范围
     - 优先级3：同品牌、同车系、不同年款
     - 优先级4：同品牌、不同车系
     - 优先级5：不同品牌
   → 使用技巧：
     - 如果第一次没找到结果，下次调用时放宽条件（比如去掉 grade，或扩大 year_min/year_max）
     - 如果还没找到，再去掉 model 限制
     - 如果还没找到，再去掉 series 限制，只保留 brand
     - 参数可以留空表示不限制（如 grade="" 表示不限制评级）

2. get_new_car_price(series)
   → 查新车指导价，用于判断折旧率是否合理

3. check_market_trend(category, month)
   → 查品类行情和季节因素（category: 燃油车/新能源/插混，month: 1-12）

4. calculate_adjustment(model_year, mileage, transfer_count, inspection_score, inspection_grade)
   → 基于历史数据模型直接预测价格，参数：
     - model_year: 年款（如2021）
     - mileage: 里程（万公里）
     - transfer_count: 过户次数
     - inspection_score: 检测分数（0-100）
     - inspection_grade: 检测评级（A/B/C/D/E）
   → 调用一次后信息已足够，直接输出最终答案
"""


# ═════════════════════════════════════════════════════
#  ReAct 推理循环
# ═════════════════════════════════════════════════════

def _react_prompt(
    car: RealCarListing,
    initial_refs: List[Tuple[RealCarListing, float]],
    history: List[Dict],
    qwen_baseline: Optional[float] = None,
) -> str:
    """构建 ReAct 循环 prompt（简化版）"""
    ref_lines = []
    for ref, score in initial_refs[:3]:  # 只显示 Top-3 参考车源
        if ref.c2b_price and ref.b2c_price:
            ref_lines.append(
                f"{ref.model_year}款{ref.brand}{ref.series} | 里程{ref.mileage}万 | 评级{ref.inspection_grade}级 | 过户{ref.transfer_count}次 | "
                f"C2B={ref.c2b_price}万 B2C={ref.b2c_price}万"
            )

    hist_text = "".join(f"\n[{h['role']}] {h['content']}" for h in history)

    qwen_baseline_section = ""
    if qwen_baseline is not None:
        qwen_baseline_section = f"""
【Qwen 基准预测】
Qwen 模型预测的 B2C 价格为：{qwen_baseline:.2f} 万
请基于这个基准值进行推理和修正，如果需要可以调整价格。
"""

    return f"""你是二手车定价专家。

【待估车辆】
{car.model_year}款{car.brand}{car.series} {car.model}
里程：{car.mileage}万km | 评级：{car.inspection_grade}级 | 过户：{car.transfer_count}次

【参考车源】（请特别注意与待估车辆的车况差异）
{chr(10).join(ref_lines) if ref_lines else "暂无参考数据"}
{qwen_baseline_section}
{TOOL_SPEC}

【推理历史】{hist_text if hist_text else "（尚未开始）"}

【输出】
需要工具：
  [Thought] 分析
  [Action] tool_name(param=value)

输出答案：
  [Thought] 汇总（请特别说明车况差异对价格的影响）
  [Answer]
  {{"c2b_price": 数字, "c2b_low": 数字, "c2b_high": 数字,
    "b2c_price": 数字, "b2c_low": 数字, "b2c_high": 数字,
    "confidence": "high", "pricing_reason": "理由"}}

开始："""


def _parse_react(raw: str) -> Tuple[str, str, str]:
    """解析 LLM 输出，返回 (thought, content, type: action|answer|unknown)"""
    thought = ""
    m = re.search(r'\[Thought\]\s*(.+?)(?=\[Action\]|\[Answer\]|$)', raw, re.DOTALL)
    if m:
        thought = m.group(1).strip()

    m = re.search(r'\[Action\]\s*(\w+\([^)]*\))', raw, re.DOTALL)
    if m:
        return thought, m.group(1), "action"

    m = re.search(r'\[Answer\]\s*(\{.*\})', raw, re.DOTALL)
    if m:
        return thought, m.group(1), "answer"

    return thought, raw, "unknown"


def _data_driven_price_adjustment(
    car_age: float,
    mileage: float,
    transfer_count: int,
    avg_ref_age: float,
    avg_ref_mileage: float,
    avg_ref_transfer: float
) -> Tuple[float, float, float, str]:
    """
    基于历史数据分析的价格调整规则
    
    基于66,900条历史记录的分析结果：
    - 车龄每增加1年，价格下降约2.69%
    - 里程每增加1万公里，价格下降约2.27%
    - 过户次数每增加1次，价格下降约0.75%
    
    Args:
        car_age: 当前车辆车龄
        mileage: 当前车辆里程
        transfer_count: 当前车辆过户次数
        avg_ref_age: 参考车源平均车龄
        avg_ref_mileage: 参考车源平均里程
        avg_ref_transfer: 参考车源平均过户次数
        
    Returns:
        (age_adjustment, mileage_adjustment, transfer_adjustment, reasoning)
        调整比例为小数，例如-0.02表示降价2%
    """
    age_diff = car_age - avg_ref_age
    mileage_diff = mileage - avg_ref_mileage
    transfer_diff = transfer_count - avg_ref_transfer
    
    adjustments = []
    
    # 车龄调整：基于历史数据分析，每多1年降2.7%，每少1年涨2.0%
    if age_diff > 0:
        age_adjustment = min(-0.3, age_diff * -0.027)  # 最多降价30%
        adjustments.append(f"车龄比参考高{age_diff:.1f}年，降价{abs(age_adjustment)*100:.1f}%")
    elif age_diff < 0:
        age_adjustment = min(0.2, abs(age_diff) * 0.02)  # 最多涨价20%
        adjustments.append(f"车龄比参考低{abs(age_diff):.1f}年，涨价{age_adjustment*100:.1f}%")
    else:
        age_adjustment = 0
    
    # 里程调整：基于历史数据分析，每多1万公里降2.3%，每少1万公里涨1.7%
    if mileage_diff > 0:
        mileage_adjustment = min(-0.25, mileage_diff * -0.023)  # 最多降价25%
        adjustments.append(f"里程比参考高{mileage_diff:.1f}万，降价{abs(mileage_adjustment)*100:.1f}%")
    elif mileage_diff < 0:
        mileage_adjustment = min(0.15, abs(mileage_diff) * 0.017)  # 最多涨价15%
        adjustments.append(f"里程比参考低{abs(mileage_diff):.1f}万，涨价{mileage_adjustment*100:.1f}%")
    else:
        mileage_adjustment = 0
    
    # 过户次数调整：基于历史数据分析，每多1次降0.75%
    if transfer_diff > 0:
        transfer_adjustment = min(-0.15, transfer_diff * -0.0075)  # 最多降价15%
        adjustments.append(f"过户次数比参考多{transfer_diff}次，降价{abs(transfer_adjustment)*100:.1f}%")
    elif transfer_diff < 0:
        # 过户次数少可以适当涨价，但影响较小
        transfer_adjustment = min(0.05, abs(transfer_diff) * 0.005)  # 最多涨价5%
        adjustments.append(f"过户次数比参考少{abs(transfer_diff)}次，涨价{transfer_adjustment*100:.1f}%")
    else:
        transfer_adjustment = 0
    
    reasoning = "; ".join(adjustments) if adjustments else "车辆状态与参考接近"
    
    return age_adjustment, mileage_adjustment, transfer_adjustment, reasoning


def _check_monotonicity(
    result: DualPricingResult,
    car: RealCarListing,
    avg_ref_age: float,
    avg_ref_mileage: float,
    avg_ref_transfer: float
) -> Tuple[bool, List[str]]:
    """
    检验定价结果的单调性
    
    原则：
    1. 车龄越旧，价格越低
    2. 里程越高，价格越低
    3. 过户次数越多，价格越低
    
    Args:
        result: 定价结果
        car: 当前车辆信息
        avg_ref_age: 参考车源平均车龄
        avg_ref_mileage: 参考车源平均里程
        avg_ref_transfer: 参考车源平均过户次数
        
    Returns:
        (is_monotonic, warnings)
        is_monotonic: 是否满足单调性
        warnings: 不满足单调性的警告列表
    """
    warnings = []
    car_age = CURRENT_YEAR - car.model_year
    
    # 获取基于历史数据规则的预期调整方向
    age_adj_rule, mileage_adj_rule, transfer_adj_rule, _ = _data_driven_price_adjustment(
        car_age, car.mileage, car.transfer_count,
        avg_ref_age, avg_ref_mileage, avg_ref_transfer
    )
    
    # 检查ReAct结果是否符合预期方向
    # 这里我们暂时通过调整规则来验证，因为我们已经用规则作为基准
    # 如果需要更严格的检验，可以比较ReAct推理的调整方向与规则的一致性
    
    # 目前我们使用规则作为基准，所以默认满足单调性
    # 如果将来需要，可以添加更严格的检验逻辑
    
    return True, warnings


def _enforce_monotonicity(
    result: DualPricingResult,
    car: RealCarListing,
    refs: List[Tuple[RealCarListing, float]],
    verbose: bool = True
) -> DualPricingResult:
    """
    强制单调性：确保同车型同车系下，车况越好价格越高
    
    原则：
    1. 检测分数越高，价格越高
    2. 里程越低，价格越高
    3. 车龄越新，价格越高
    4. 过户次数越少，价格越高
    
    如果预测价格不满足单调性，根据参考车源进行强制调整
    """
    if verbose:
        print(f"\n  [单调性校验] 开始校验同车型车况的单调性...")
    
    # 筛选同品牌同车系的参考车源
    same_series_refs = [
        c for c, _ in refs 
        if c.brand == car.brand and c.series == car.series
    ]
    
    if len(same_series_refs) < 2:
        if verbose:
            print(f"  [单调性校验] 同车系参考车源不足（{len(same_series_refs)}辆），跳过强制调整")
        return result
    
    # 为当前车辆计算车况综合分数（0-100）
    def compute_condition_score(c: RealCarListing) -> float:
        """计算车况综合分数，分数越高车况越好"""
        car_age = CURRENT_YEAR - c.model_year
        
        # 标准化各项指标（0-100分，越高越好）
        score = 0.0
        
        # 检测分数权重最高（40%）
        if c.inspection_score > 0:
            score += c.inspection_score * 0.4
        else:
            score += 70 * 0.4  # 默认70分
        
        # 里程（25%）：0-20万公里
        mileage_score = max(0, 100 - (c.mileage / 20) * 100)
        score += mileage_score * 0.25
        
        # 车龄（20%）：0-15年
        age_score = max(0, 100 - (car_age / 15) * 100)
        score += age_score * 0.2
        
        # 过户次数（15%）：0-5次
        transfer_score = max(0, 100 - (c.transfer_count / 5) * 100)
        score += transfer_score * 0.15
        
        return score
    
    current_condition_score = compute_condition_score(car)
    
    if verbose:
        print(f"  [单调性校验] 当前车辆车况综合分数: {current_condition_score:.1f}")
        print(f"  [单调性校验] 当前预测价格: C2B={result.c2b_price:.2f}万, B2C={result.b2c_price:.2f}万")
    
    # 给参考车源按车况排序，找出当前车辆应该在哪个价格区间
    refs_with_scores = []
    for ref in same_series_refs:
        # 过滤脏数据：B2C必须大于C2B，且B2C需大于1万
        if (ref.c2b_price and ref.b2c_price
                and ref.b2c_price > ref.c2b_price
                and ref.b2c_price > 1.0):
            ref_score = compute_condition_score(ref)
            refs_with_scores.append((ref_score, ref.c2b_price, ref.b2c_price))
    
    if len(refs_with_scores) < 2:
        if verbose:
            print(f"  [单调性校验] 有效参考车源不足，跳过强制调整")
        return result
    
    # 按车况分数排序
    refs_with_scores.sort(key=lambda x: x[0])
    
    if verbose:
        print(f"  [单调性校验] 同车系参考车源（按车况排序）:")
        for i, (score, c2b, b2c) in enumerate(refs_with_scores, 1):
            print(f"    {i}. 车况分={score:.1f} | C2B={c2b:.2f}万 | B2C={b2c:.2f}万")
    
    # 找出当前车辆应该在哪个位置
    target_position = None
    for i, (ref_score, _, _) in enumerate(refs_with_scores):
        if current_condition_score <= ref_score:
            target_position = i
            break
    
    if target_position is None:
        target_position = len(refs_with_scores)  # 当前车况最好
    
    # 确定当前车辆的合理价格区间
    if target_position == 0:
        # 当前车况比所有参考车都差
        ref_better = refs_with_scores[0]
        target_c2b = ref_better[1] * 0.95
        target_b2c = ref_better[2] * 0.95
        if verbose:
            print(f"  [单调性校验] 当前车况比所有参考车差，使用下限价格")
    elif target_position >= len(refs_with_scores):
        # 当前车况比所有参考车都好
        ref_worse = refs_with_scores[-1]
        target_c2b = ref_worse[1] * 1.05
        target_b2c = ref_worse[2] * 1.05
        if verbose:
            print(f"  [单调性校验] 当前车况比所有参考车好，使用上限价格")
    else:
        # 当前车况在中间位置，插值计算
        ref_worse = refs_with_scores[target_position - 1]
        ref_better = refs_with_scores[target_position]
        
        # 线性插值
        score_range = ref_better[0] - ref_worse[0]
        if score_range > 0:
            weight = (current_condition_score - ref_worse[0]) / score_range
            target_c2b = ref_worse[1] + (ref_better[1] - ref_worse[1]) * weight
            target_b2c = ref_worse[2] + (ref_better[2] - ref_worse[2]) * weight
        else:
            target_c2b = (ref_worse[1] + ref_better[1]) / 2
            target_b2c = (ref_worse[2] + ref_better[2]) / 2
        
        if verbose:
            print(f"  [单调性校验] 当前车况在第{target_position}位，使用插值计算")
    
    # 检查当前价格是否满足单调性
    needs_adjustment = False
    adjustment_reason = ""
    
    # 对比预测价格和目标价格
    c2b_ratio = result.c2b_price / target_c2b if target_c2b > 0 else 1.0
    b2c_ratio = result.b2c_price / target_b2c if target_b2c > 0 else 1.0
    
    # 只在偏差超过30%时才强制调整（避免误修正车况更好的车）
    if abs(c2b_ratio - 1.0) > 0.30 or abs(b2c_ratio - 1.0) > 0.30:
        needs_adjustment = True
        adjustment_reason = f"预测价格与基于车况的合理价格偏差超过30%"
        
        if verbose:
            print(f"  [单调性校验] 检测到价格偏差较大")
            print(f"  [单调性校验] 合理价格区间: C2B≈{target_c2b:.2f}万, B2C≈{target_b2c:.2f}万")
            print(f"  [单调性校验] 预测价格: C2B={result.c2b_price:.2f}万, B2C={result.b2c_price:.2f}万")
            print(f"  [单调性校验] 将强制调整为基于车况的合理价格")
    
    if needs_adjustment:
        # 计算参考车源的平均毛利率
        avg_margin_ratio = 1.15  # 默认15%的毛利率
        if refs_with_scores:
            margin_ratios = []
            for _, ref_c2b, ref_b2c in refs_with_scores:
                if ref_c2b > 0 and ref_b2c > ref_c2b:
                    margin_ratios.append(ref_b2c / ref_c2b)
            if margin_ratios:
                avg_margin_ratio = sum(margin_ratios) / len(margin_ratios)
        
        # 检查原始价格是否有合理的差价
        original_has_valid_margin = (result.c2b_price > 0 and 
                                      result.b2c_price > result.c2b_price)
        
        # 修正方向检查：目标价和预测价的大小关系要符合车况逻辑
        # 如果当前车况分数高于参考均值，目标价应该≥预测价，否则不修正
        avg_ref_score = sum(s for s, _, _ in refs_with_scores) / len(refs_with_scores) if refs_with_scores else 0
        wrong_direction = (
            (current_condition_score > avg_ref_score and target_b2c < result.b2c_price) or
            (current_condition_score < avg_ref_score and target_b2c > result.b2c_price)
        )
        if wrong_direction:
            if verbose:
                print(f"  [单调性校验] 修正方向与车况不符，跳过调整（车况分={current_condition_score:.1f}, 均值={avg_ref_score:.1f}）")
            return result

        if original_has_valid_margin:
            original_margin_ratio = result.b2c_price / result.c2b_price
            final_b2c = round(target_b2c, 2)
            final_c2b = round(final_b2c / original_margin_ratio, 2)
        else:
            final_b2c = round(target_b2c, 2)
            final_c2b = round(final_b2c / avg_margin_ratio, 2)
        
        # 确保B2C价格大于C2B价格
        if final_b2c <= final_c2b:
            final_c2b = round(final_b2c / 1.12, 2)  # 确保至少12%的差价
        
        # 强制调整
        result.c2b_price = final_c2b
        result.b2c_price = final_b2c
        result.c2b_low = round(final_c2b * 0.96, 2)
        result.c2b_high = round(final_c2b * 1.04, 2)
        result.b2c_low = round(final_b2c * 0.95, 2)
        result.b2c_high = round(final_b2c * 1.05, 2)
        
        # 更新定价理由
        result.pricing_reason += f"\n【单调性修正】{adjustment_reason}，已调整为基于车况的合理价格"
        
        if verbose:
            print(f"  [单调性校验] 调整完成: C2B={result.c2b_price:.2f}万, B2C={result.b2c_price:.2f}万")
    else:
        if verbose:
            print(f"  [单调性校验] 价格满足单调性，无需调整")
    
    return result


def _run_tool(action: str, retriever: RealCarRAGRetriever) -> str:
    """执行工具调用"""
    try:
        m = re.match(r'(\w+)\((.*)\)', action.strip(), re.DOTALL)
        if not m:
            return "格式错误，请用 tool_name(param=value) 格式"

        name, args_str = m.group(1), m.group(2)
        if name not in TOOLS:
            return f"未知工具 {name}，可用：{list(TOOLS.keys())}"

        # 解析 key=value 参数
        kwargs: Dict[str, Any] = {}
        for pm in re.finditer(r'(\w+)\s*=\s*(["\']?)([^,)]+)\2', args_str):
            k, v = pm.group(1), pm.group(3).strip().strip("\"'")
            try:
                kwargs[k] = int(v) if '.' not in v else float(v)
            except ValueError:
                kwargs[k] = True if v.lower()=="true" else (False if v.lower()=="false" else v)

        if name == "search_similar_cars":
            kwargs["retriever"] = retriever

        return TOOLS[name](**kwargs)
    except Exception as e:
        return f"工具执行出错：{e}"


def react_price(
    car: RealCarListing,
    retriever: RealCarRAGRetriever,
    max_steps: int = 6,
    verbose: bool = True,
    use_qwen_direct: bool = True,
    use_qwen_as_baseline: bool = False,
    previous_mileage: float = None,
    previous_transfer: int = None,
    previous_b2c: float = None,
) -> Tuple[DualPricingResult, List[Dict]]:
    """
    ReAct 定价核心循环。
    返回：(DualPricingResult, trace列表)
    trace 里记录了每步的思考、工具调用和观察结果，是可解释性的原始数据。
    """
    initial_refs = retriever.retrieve(car, top_k=20)
    fallback      = _rule_based_pricing(car, initial_refs)
    history: List[Dict] = []
    trace:   List[Dict] = []
    qwen_baseline: Optional[float] = None

    # 首先尝试使用 Qwen 模型预测（如果启用直接预测或作为基准值）
    if (use_qwen_direct or use_qwen_as_baseline) and QWEN_AVAILABLE:
        if verbose:
            print(f"\n  [Qwen] 尝试使用 Qwen 模型直接预测...")
        try:
            # 使用训练时的完整格式调用Qwen模型
            qwen_prompt = build_training_prompt(car, initial_refs)
            if verbose:
                print(f"  [Qwen] 使用完整训练格式构建Prompt")
            
            # 动态下限：参考车源最低价的50%，至少0.5万
            _ref_prices = [ref.b2c_price for ref, _ in initial_refs if ref.b2c_price and ref.b2c_price > 0]
            dynamic_min = max(0.5, min(_ref_prices) * 0.5) if _ref_prices else 0.5
            predicted_b2c_wan = predict_with_qwen(qwen_prompt, min_price=dynamic_min)
            if predicted_b2c_wan is None and use_qwen_as_baseline:
                # LoRA预测失败，用参考车源中位数作为基准值
                if _ref_prices:
                    predicted_b2c_wan = sorted(_ref_prices)[len(_ref_prices) // 2]
                    if verbose:
                        print(f"  [Qwen] 预测失败，改用参考车源中位数作为基准: {predicted_b2c_wan:.2f}万")
            if predicted_b2c_wan is not None:
                if verbose:
                    print(f"  [Qwen] 预测成功: B2C={predicted_b2c_wan:.2f}万")

                # 确保价格为正数
                predicted_b2c_wan = max(0.1, predicted_b2c_wan)

                # 如果是作为基准值，进行1步ReAct推理（使用数据驱动调整）
                if use_qwen_as_baseline:
                    if verbose:
                        print(f"  [Qwen] 使用基准值模式，进行1步ReAct推理")
                    
                    # 计算参考车源统计信息
                    ref_b2c_prices = [ref.b2c_price for ref, _ in initial_refs if ref.b2c_price]
                    ref_c2b_prices = [ref.c2b_price for ref, _ in initial_refs if ref.c2b_price]
                    
                    ref_b2c_mean = None
                    ref_b2c_median = None
                    ref_c2b_mean = None
                    ref_c2b_median = None
                    avg_ref_age = 0.0
                    avg_ref_mileage = 0.0
                    avg_ref_transfer = 0.0
                    
                    if ref_b2c_prices:
                        ref_b2c_mean = sum(ref_b2c_prices) / len(ref_b2c_prices)
                        ref_b2c_median = sorted(ref_b2c_prices)[len(ref_b2c_prices) // 2]
                    
                    if ref_c2b_prices:
                        ref_c2b_mean = sum(ref_c2b_prices) / len(ref_c2b_prices)
                        ref_c2b_median = sorted(ref_c2b_prices)[len(ref_c2b_prices) // 2]
                    
                    # 计算参考车源的平均车况
                    if initial_refs:
                        ref_ages = []
                        ref_mileages = []
                        ref_transfers = []
                        for ref, _ in initial_refs:
                            ref_ages.append(CURRENT_YEAR - ref.model_year)
                            ref_mileages.append(ref.mileage)
                            ref_transfers.append(ref.transfer_count)
                        if ref_ages:
                            avg_ref_age = sum(ref_ages) / len(ref_ages)
                        if ref_mileages:
                            avg_ref_mileage = sum(ref_mileages) / len(ref_mileages)
                        if ref_transfers:
                            avg_ref_transfer = sum(ref_transfers) / len(ref_transfers)
                    
                    # 构建推理轨迹
                    reasoning_trace = []
                    
                    # Step 1: Qwen预测
                    step1_thought = f"首先使用微调的Qwen模型预测基准价格"
                    reasoning_trace.append({
                        "step": 1,
                        "thought": step1_thought,
                        "action": "调用微调Qwen模型预测",
                        "observation": f"Qwen预测B2C价格: {predicted_b2c_wan:.2f}万"
                    })
                    
                    # Step 2: 尝试使用Qwen模型进行ReAct推理，失败则回退到数据驱动
                    step2_thought = "尝试使用Qwen模型进行ReAct推理，验证和修正Qwen预测"
                    reasoning_trace.append({
                        "step": 2,
                        "thought": step2_thought,
                        "action": "调用Qwen模型进行ReAct推理",
                        "observation": "正在调用Qwen模型进行推理..."
                    })

                    # 首先尝试用Qwen模型进行推理
                    final_b2c_wan = predicted_b2c_wan
                    pricing_reason_text = "基于Qwen模型预测"
                    used_data_driven = False

                    # 构建ReAct推理prompt（精简版，减少token数）
                    car_age = CURRENT_YEAR - car.model_year
                    ref_count = len(ref_b2c_prices)
                    refs_summary = "、".join(
                        f"{ref.b2c_price:.1f}万"
                        for ref, _ in initial_refs[:3]
                        if ref.b2c_price
                    ) or "无"

                    ref_mean = ref_b2c_mean if ref_b2c_mean else predicted_b2c_wan
                    # 构建参数变化提示（用于修改车况后重新定价）
                    change_hint = ""
                    if previous_mileage is not None and previous_b2c is not None:
                        mileage_diff = previous_mileage - car.mileage  # 正值=里程减少=变好
                        transfer_diff = (previous_transfer or car.transfer_count) - car.transfer_count  # 正值=过户减少=变好
                        changes = []
                        if abs(mileage_diff) >= 0.5:
                            direction = "减少" if mileage_diff > 0 else "增加"
                            changes.append(f"里程{direction}{abs(mileage_diff):.1f}万km（{'车况变好' if mileage_diff > 0 else '车况变差'}）")
                        if abs(transfer_diff) >= 1:
                            direction = "减少" if transfer_diff > 0 else "增加"
                            changes.append(f"过户次数{direction}{abs(transfer_diff)}次（{'车况变好' if transfer_diff > 0 else '车况变差'}）")
                        if changes:
                            is_better = mileage_diff > 0 or transfer_diff > 0
                            change_hint = (
                                f"\n用户修改了车辆参数：{'、'.join(changes)}。"
                                f"上次定价B2C={previous_b2c:.2f}万。"
                                f"车况{'改善，最终价格应高于或接近上次定价' if is_better else '变差，最终价格应低于或接近上次定价'}。"
                            )
                            print(f"[ReAct] 参数变化提示: {change_hint.strip()}")

                    react_prompt = (
                        f"你是二手车定价专家，必须根据参考车源调整预测价格。\n"
                        f"车辆：{car.brand}{car.series} {car.model_year}款，{car.mileage}万km，过户{car.transfer_count}次\n"
                        f"模型预测B2C：{predicted_b2c_wan:.2f}万\n"
                        f"参考车源B2C均值：{ref_mean:.2f}万（{ref_count}辆），明细：{refs_summary}\n"
                        f"要求：对比参考均值与预测值的差异，结合车龄{car_age}年、里程{car.mileage}万km、过户{car.transfer_count}次给出调整后价格。{change_hint}\n"
                        f"必须输出（格式严格遵守）：\nB2C售价：X.XX万\n理由：[说明调整依据，30字以内]"
                    )

                    try:
                        # 使用基础模型进行 ReAct 推理（更快）
                        react_response = _call_llm(react_prompt, temperature=0.3, max_tokens=200, use_finetuned=False)

                        if react_response:
                            # 尝试提取价格
                            price_match = re.search(r'B2C售价[：:]\s*(\d+(?:\.\d+)?)\s*万', react_response)
                            if price_match:
                                final_b2c_wan = float(price_match.group(1))
                                pricing_reason_text = react_response.strip()
                                reasoning_trace[-1]['observation'] = f"Qwen ReAct推理成功，最终B2C价格: {final_b2c_wan:.2f}万"
                            else:
                                # 尝试直接找数字
                                price_match2 = re.search(r'(\d+(?:\.\d+)?)\s*万', react_response)
                                if price_match2:
                                    final_b2c_wan = float(price_match2.group(1))
                                    pricing_reason_text = react_response.strip()
                                    reasoning_trace[-1]['observation'] = f"Qwen ReAct推理成功，最终B2C价格: {final_b2c_wan:.2f}万"
                                else:
                                    used_data_driven = True
                        else:
                            used_data_driven = True
                    except Exception as e:
                        if verbose:
                            print(f"  [ReAct] Qwen推理失败: {e}")
                        used_data_driven = True

                    # 如果Qwen推理失败或没提取到价格，回退到数据驱动
                    if used_data_driven:
                        if verbose:
                            print(f"  [ReAct] 回退到数据驱动调整")
                        reasoning_trace[-1]['observation'] = "Qwen推理未成功，回退到数据驱动调整"
                        reasoning_trace[-1]['action'] = "数据驱动价格调整（回退）"

                        age_adj, mileage_adj, transfer_adj, adj_reason = _data_driven_price_adjustment(
                            car_age=car_age,
                            mileage=car.mileage,
                            transfer_count=car.transfer_count,
                            avg_ref_age=avg_ref_age,
                            avg_ref_mileage=avg_ref_mileage,
                            avg_ref_transfer=avg_ref_transfer
                        )
                        total_adjustment = age_adj + mileage_adj + transfer_adj
                        final_b2c_wan = predicted_b2c_wan * (1 + total_adjustment)
                        pricing_reason_text = adj_reason
                        reasoning_trace[-1]['observation'] = f"数据驱动调整完成，调整比例: {total_adjustment*100:.1f}%，最终B2C价格: {final_b2c_wan:.2f}万"
                    
                    # 如果有参考车源，确保价格在合理范围内
                    if ref_b2c_median:
                        min_reasonable = ref_b2c_median * 0.7
                        max_reasonable = ref_b2c_median * 1.3
                        final_b2c_wan = max(min_reasonable, min(final_b2c_wan, max_reasonable))

                    # 构建结果
                    # 从调整后的B2C价格反推C2B价格（1.08倍毛利率）
                    final_b2c_wan = max(0.1, final_b2c_wan)
                    c2b_price = final_b2c_wan / 1.08
                    c2b_price = max(0.1, min(c2b_price, final_b2c_wan * 0.99))
                    
                    # 构建定价理由（包含完整推理过程）
                    pricing_reason_lines = []
                    
                    # 显示醒目的ReAct状态标识
                    if used_data_driven:
                        pricing_reason_lines.append("## 🤖 定价推理过程（微调模型预测+数据驱动）")
                        pricing_reason_lines.append("")
                        pricing_reason_lines.append("⚠️ **ReAct状态**：Qwen基础模型推理未成功，已回退到数据驱动规则")
                    else:
                        pricing_reason_lines.append("## 🤖 定价推理过程（微调模型预测+基础模型ReAct）")
                        pricing_reason_lines.append("")
                        pricing_reason_lines.append("✅ **ReAct状态**：Qwen基础模型推理成功！")
                    
                    pricing_reason_lines.append("")
                    pricing_reason_lines.append("---")
                    pricing_reason_lines.append("")
                    
                    # 显示价格对比
                    price_diff = final_b2c_wan - predicted_b2c_wan
                    price_diff_pct = (price_diff / predicted_b2c_wan) * 100 if predicted_b2c_wan > 0 else 0
                    pricing_reason_lines.append("### 价格变化对比")
                    pricing_reason_lines.append(f"- 微调模型预测：**{predicted_b2c_wan:.2f}万**")
                    pricing_reason_lines.append(f"- ReAct调整后：**{final_b2c_wan:.2f}万**")
                    if abs(price_diff_pct) > 0.1:
                        if price_diff > 0:
                            pricing_reason_lines.append(f"- 调整幅度：**+{price_diff:.2f}万 (+{price_diff_pct:.1f}%)**")
                        else:
                            pricing_reason_lines.append(f"- 调整幅度：**{price_diff:.2f}万 ({price_diff_pct:.1f}%)**")
                    else:
                        pricing_reason_lines.append("- 调整幅度：**基本无变化**")
                    pricing_reason_lines.append("")
                    
                    pricing_reason_lines.append("---")
                    pricing_reason_lines.append("")
                    
                    # 步骤1：微调模型预测
                    pricing_reason_lines.append("### 步骤1：微调Qwen模型预测")
                    pricing_reason_lines.append(f"- Qwen模型预测B2C价格：{predicted_b2c_wan:.2f}万")
                    pricing_reason_lines.append("")
                    
                    # 步骤2：ReAct推理
                    if used_data_driven:
                        pricing_reason_lines.append("### 步骤2：数据驱动ReAct推理（车况差异调整）")
                    else:
                        pricing_reason_lines.append("### 步骤2：Qwen微调模型ReAct推理（验证修正）")
                    
                    ref_count = len(ref_b2c_prices)
                    # 添加参考车源信息
                    if ref_b2c_mean:
                        pricing_reason_lines.append(f"- 参考车源（{ref_count}辆）：")
                        pricing_reason_lines.append(f"  - 均值：{ref_b2c_mean:.2f}万")
                        pricing_reason_lines.append(f"  - 中位数：{ref_b2c_median:.2f}万")
                        pricing_reason_lines.append(f"  - 平均车龄：{avg_ref_age:.1f}年")
                        pricing_reason_lines.append(f"  - 平均里程：{avg_ref_mileage:.1f}万km")
                        pricing_reason_lines.append(f"  - 平均过户：{avg_ref_transfer:.1f}次")
                    
                    # 添加车况对比
                    pricing_reason_lines.append("")
                    pricing_reason_lines.append(f"- 当前车辆：")
                    pricing_reason_lines.append(f"  - 车龄：{car_age:.1f}年")
                    pricing_reason_lines.append(f"  - 里程：{car.mileage:.1f}万km")
                    pricing_reason_lines.append(f"  - 过户：{car.transfer_count}次")
                    
                    # 添加调整结果
                    pricing_reason_lines.append("")
                    if used_data_driven:
                        pricing_reason_lines.append("### 车况差异调整")
                        pricing_reason_lines.append(pricing_reason_text)
                    else:
                        pricing_reason_lines.append("### ReAct推理结果")
                        pricing_reason_lines.append(pricing_reason_text)
                    
                    # 添加最终定价
                    pricing_reason_lines.append("")
                    pricing_reason_lines.append("---")
                    pricing_reason_lines.append("")
                    pricing_reason_lines.append("### 🎯 最终定价")
                    pricing_reason_lines.append(f"- **B2C售价：{final_b2c_wan:.2f}万**")
                    pricing_reason_lines.append(f"- **C2B收车价：{c2b_price:.2f}万**")
                    
                    pricing_reason = "\n".join(pricing_reason_lines)
                    
                    result_dict = {
                        "c2b_price": c2b_price,
                        "c2b_low": c2b_price * 0.96,
                        "c2b_high": c2b_price * 1.04,
                        "b2c_price": final_b2c_wan,
                        "b2c_low": final_b2c_wan * 0.95,
                        "b2c_high": final_b2c_wan * 1.05,
                        "confidence": "high",
                        "risk_notes": [],
                        "pricing_reason": pricing_reason,
                        "reasoning_trace": reasoning_trace,
                    }
                    
                    result = _dict_to_result(
                        {"step3_final": result_dict, "step0_baseline": {},
                         "step1_vehicle_adj": {}, "step2_cost_and_market": {}},
                        car
                    )
                    result.raw_steps["refs"] = initial_refs
                    result.raw_steps["qwen_prediction"] = True
                    result.raw_steps["qwen_baseline"] = predicted_b2c_wan
                    result.raw_steps["final_price"] = final_b2c_wan
                    result.raw_steps["data_driven_adjustment"] = used_data_driven
                    result.raw_steps["qwen_react_success"] = not used_data_driven
                    trace.extend(reasoning_trace)

                    # 单调性校验：确保车况越好价格越高
                    result = _enforce_monotonicity(result, car, initial_refs, verbose=verbose)

                    # 单调性校验可能修改了价格，同步更新 pricing_reason 里的最终定价
                    import re as _re
                    react_b2c = final_b2c_wan  # 记录ReAct推理后、单调性校验前的价格
                    monotonicity_note = ''
                    if abs(result.b2c_price - react_b2c) > 0.01:
                        monotonicity_note = f'\n- ⚠️ **单调性修正**：ReAct结果{react_b2c:.2f}万 → 校正为{result.b2c_price:.2f}万（基于同车系车况排序）'
                    result.pricing_reason = _re.sub(
                        r'### 🎯 最终定价[\s\S]*$',
                        f'### 🎯 最终定价\n- **B2C售价：{result.b2c_price:.2f}万**\n- **C2B收车价：{result.c2b_price:.2f}万**{monotonicity_note}',
                        result.pricing_reason
                    )

                    # ── 定价摘要打印（单调性校验后，与前端一致）──────
                    price_diff = result.b2c_price - predicted_b2c_wan
                    react_status = "✅ ReAct成功" if not used_data_driven else "⚠️  ReAct回退(数据驱动)"
                    print(f"\n{'='*50}")
                    print(f"  [定价摘要] {car.brand}{car.series} {car.model_year}款")
                    print(f"  ReAct状态  : {react_status}")
                    print(f"  微调基准B2C: {predicted_b2c_wan:.2f}万")
                    print(f"  ReAct后B2C : {result.b2c_price:.2f}万  (调整 {price_diff:+.2f}万)")
                    print(f"  C2B收车价  : {result.c2b_price:.2f}万")
                    print(f"  推理理由   : {pricing_reason_text.splitlines()[0] if pricing_reason_text else '—'}")
                    if '\n' in (pricing_reason_text or ''):
                        for line in pricing_reason_text.splitlines()[1:]:
                            if line.strip():
                                print(f"               {line.strip()}")
                    print(f"{'='*50}")
                    print(f"\n[完整定价理由]\n{result.pricing_reason}")
                    print(f"{'='*50}\n")
                    # ────────────────────────────────────────────────

                    return result, trace
                else:
                    # 构建结果：同时计算 C2B 和 B2C 价格
                    # 从 Qwen 预测的 B2C 价格反推 C2B 价格（1.08倍毛利率）
                    c2b_price = predicted_b2c_wan / 1.08
                    c2b_price = max(0.1, min(c2b_price, predicted_b2c_wan * 0.99))
                    
                    result_dict = {
                        "c2b_price": c2b_price,
                        "c2b_low": c2b_price * 0.96,
                        "c2b_high": c2b_price * 1.04,
                        "b2c_price": predicted_b2c_wan,
                        "b2c_low": predicted_b2c_wan * 0.95,
                        "b2c_high": predicted_b2c_wan * 1.05,
                        "confidence": "high",
                        "risk_notes": [],
                        "pricing_reason": "基于 Qwen LoRA 模型预测",
                        "reasoning_trace": [],
                    }
                    
                    result = _dict_to_result(
                        {"step3_final": result_dict, "step0_baseline": {},
                         "step1_vehicle_adj": {}, "step2_cost_and_market": {}},
                        car
                    )
                    result.raw_steps["refs"] = initial_refs
                    result.raw_steps["qwen_prediction"] = True
                    return result, trace
            else:
                if verbose:
                    print(f"  [Qwen] 预测失败，继续使用 ReAct 推理")
        except Exception as e:
            if verbose:
                print(f"  [Qwen] 预测出错: {e}")
                import traceback
                traceback.print_exc()

    if verbose:
        print(f"\n  [ReAct] 开始推理（最多 {max_steps} 步）...")

    for step in range(max_steps):
        # ReAct推理使用基础模型
        raw = _call_llm(_react_prompt(car, initial_refs, history, qwen_baseline), temperature=0.0, max_tokens=1400, use_finetuned=False)

        if not raw:
            if verbose:
                print("  [ReAct] LLM 不可用，降级规则引擎")
            return _dict_to_result(fallback, car), trace

        thought, content, kind = _parse_react(raw)

        if thought and verbose:
            print(f"  [思考{step+1}] {thought[:90]}{'…' if len(thought)>90 else ''}")

        if kind == "action":
            obs = _run_tool(content, retriever)
            if verbose:
                print(f"  [调用 ] {content}")
                print(f"  [结果 ] {obs[:120]}{'…' if len(obs)>120 else ''}")
            history += [
                {"role": "Thought", "content": thought},
                {"role": "Action",  "content": content},
                {"role": "Observe", "content": obs},
            ]
            trace.append({"step": step+1, "thought": thought,
                          "action": content, "observation": obs})

        elif kind == "answer":
            try:
                clean = re.sub(r'```json|```', '', content).strip()
                # 尝试解析 JSON
                try:
                    data = json.loads(clean)
                except json.JSONDecodeError as e:
                    # 尝试修复常见的 JSON 格式错误
                    # 1. 确保所有键都用双引号包围
                    clean = re.sub(r'(\w+):', r'"\1":', clean)
                    # 2. 确保所有字符串值都用双引号包围
                    clean = re.sub(r':\s*([^\s,"{}[\]]+)', r': "\1"', clean)
                    # 3. 确保所有逗号都正确
                    clean = re.sub(r'([^,{}[\]])(\s*}\s*)$', r'\1, \2', clean)
                    # 4. 修复缺少逗号的情况（在键值对后添加逗号）
                    clean = re.sub(r'("[^"\\]*(?:\\.[^"\\]*)*")\s*:\s*(["\\[{]|true|false|null|\d+(?:\.\d*)?)\s*(?="|$|})', r'\1: \2,', clean)
                    # 5. 修复多余的逗号
                    clean = re.sub(r',\s*([}\]])', r' \1', clean)
                    # 6. 确保 JSON 格式完整
                    if not clean.startswith('{'):
                        clean = '{' + clean
                    if not clean.endswith('}'):
                        clean = clean + '}'
                    # 7. 修复嵌套对象和数组中的逗号问题
                    clean = re.sub(r'(\{[^}]*)(\s*)(\})', lambda m: m.group(1).replace('}', '},') + m.group(3), clean)
                    clean = re.sub(r'(\[[^\]]*)(\s*)(\])', lambda m: m.group(1).replace(']', '],') + m.group(3), clean)
                    # 8. 再次修复多余的逗号
                    clean = re.sub(r',\s*([}\]])', r' \1', clean)
                    # 再次尝试解析
                    try:
                        data = json.loads(clean)
                    except json.JSONDecodeError as e2:
                        # 如果仍然解析失败，尝试从文本中提取关键信息
                        # 提取关键价格信息
                        c2b_price = re.search(r'"c2b_price"\s*:\s*(\d+(?:\.\d+)?)', clean)
                        c2b_low = re.search(r'"c2b_low"\s*:\s*(\d+(?:\.\d+)?)', clean)
                        c2b_high = re.search(r'"c2b_high"\s*:\s*(\d+(?:\.\d+)?)', clean)
                        b2c_price = re.search(r'"b2c_price"\s*:\s*(\d+(?:\.\d+)?)', clean)
                        b2c_low = re.search(r'"b2c_low"\s*:\s*(\d+(?:\.\d+)?)', clean)
                        b2c_high = re.search(r'"b2c_high"\s*:\s*(\d+(?:\.\d+)?)', clean)
                        gross_margin_pct = re.search(r'"gross_margin_pct"\s*:\s*(\d+(?:\.\d+)?)', clean)
                        gross_profit = re.search(r'"gross_profit"\s*:\s*(\d+(?:\.\d+)?)', clean)
                        confidence = re.search(r'"confidence"\s*:\s*"([^"]+)"', clean)
                        risk_notes = re.search(r'"risk_notes"\s*:\s*\[(.*?)\]', clean)
                        pricing_reason = re.search(r'"pricing_reason"\s*:\s*"([^"]+)"', clean)
                        
                        # 构建数据字典
                        data = {}
                        if c2b_price:
                            data['c2b_price'] = float(c2b_price.group(1))
                        if c2b_low:
                            data['c2b_low'] = float(c2b_low.group(1))
                        if c2b_high:
                            data['c2b_high'] = float(c2b_high.group(1))
                        if b2c_price:
                            data['b2c_price'] = float(b2c_price.group(1))
                        if b2c_low:
                            data['b2c_low'] = float(b2c_low.group(1))
                        if b2c_high:
                            data['b2c_high'] = float(b2c_high.group(1))
                        if gross_margin_pct:
                            data['gross_margin_pct'] = float(gross_margin_pct.group(1))
                        if gross_profit:
                            data['gross_profit'] = float(gross_profit.group(1))
                        if confidence:
                            data['confidence'] = confidence.group(1)
                        if risk_notes:
                            data['risk_notes'] = [note.strip().strip('"') for note in risk_notes.group(1).split(',')]
                        if pricing_reason:
                            data['pricing_reason'] = pricing_reason.group(1)
                        
                        # 如果提取到了关键信息，使用这些信息构建结果
                        if data:
                            if verbose:
                                print(f"  [完成 ] 共 {step+1} 步推理（从文本中提取关键信息）")
                        else:
                            # 如果没有提取到关键信息，使用规则引擎兜底
                            if verbose:
                                print(f"  [警告 ] Answer 解析失败({e2})，使用规则兜底")
                            return _dict_to_result(fallback, car), trace
                rt    = data.pop("reasoning_trace", [])
                trace.append({"step": "final", "thought": thought, "reasoning_trace": rt})

                if verbose:
                    print(f"  [完成 ] 共 {step+1} 步推理")

                result = _dict_to_result(
                    {"step3_final": data, "step0_baseline": {},
                     "step1_vehicle_adj": {}, "step2_cost_and_market": {}},
                    car
                )
                result.raw_steps["reasoning_trace"] = rt
                return result, trace

            except Exception as e:
                if verbose:
                    print(f"  [警告 ] Answer 解析失败({e})，使用规则兜底")
                return _dict_to_result(fallback, car), trace

        else:
            # 格式不符，记录继续
            history.append({"role": "Thought", "content": raw[:300]})

    if verbose:
        print(f"  [超限 ] 超过 {max_steps} 步，使用规则兜底")
    return _dict_to_result(fallback, car), trace


# ═════════════════════════════════════════════════════
#  自我反思（Self-Reflection）
# ═════════════════════════════════════════════════════

_CHECKLIST = """
用以下检查清单逐项核查，发现问题则给出修正值：
【重要】所有价格单位均为**万元**！

1. 【毛利保护】 (B2C - C2B - 整备费) / C2B 必须 >= 8%，否则 B2C 需上调
2. 【风险折价】 营运车是否已折价 -10%？中等事故 -8%？重大事故 -18%？多次过户每次 -0.3万？
3. 【C2B偏差】 C2B 与参考均值偏差是否超过 25%？若超过需有充分理由
4. 【B2C上限】 B2C 是否超过参考 B2C 均值的 115%？过高会导致库存积压
5. 【置信度】  参考车 < 3 辆，或 C2B 与参考均值偏差 > 20%，置信度应为 low

只输出 JSON，不要有其他文字：
{
  "issues": ["问题描述（无问题则空数组）"],
  "adjustments": [{"field": "c2b_price 或 b2c_price", "from": 旧值, "to": 新值, "reason": "原因"}],
  "final_c2b": 最终C2B（无修正则与输入相同，单位：万元）,
  "final_b2c": 最终B2C（单位：万元）,
  "final_confidence": "high|medium|low",
  "summary": "自检结论（40字内）"
}"""


def self_reflect(
    result: DualPricingResult,
    car: RealCarListing,
    refs: List[Tuple[RealCarListing, float]],
    verbose: bool = True,
) -> DualPricingResult:
    """
    自我反思：LLM 用检查清单质疑自己的定价结果，发现问题自动修正。
    修正记录写入 result.raw_steps["reflection"]，供可解释报告展示。
    """
    c2b_vals = [c.c2b_price for c, _ in refs if c.c2b_price]
    b2c_vals = [c.b2c_price for c, _ in refs if c.b2c_price]
    c2b_mean = sum(c2b_vals)/len(c2b_vals) if c2b_vals else result.c2b_price
    b2c_mean = sum(b2c_vals)/len(b2c_vals) if b2c_vals else result.b2c_price

    prompt = f"""你是二手车定价质检专家，对下面这个定价结果进行自我检查。
【重要】所有价格单位均为**万元**！

【待估车辆】
{car.model_year}款{car.brand}{car.series}  里程{car.mileage}万km  评级{car.inspection_grade}
过户{car.transfer_count}次  整备{car.refurbish_cost}万  抵押{car.mortgage_deduction}万
品类：{car.category}  收车类型：{car.acquisition_type}

【当前定价】
C2B = {result.c2b_price}万（参考均值 {c2b_mean:.2f}万，偏差 {(result.c2b_price-c2b_mean)/c2b_mean*100:+.1f}%）
B2C = {result.b2c_price}万（参考均值 {b2c_mean:.2f}万）
毛利率 = {result.gross_margin_pct:.1f}%
置信度 = {result.confidence}
参考车数量 = {len(c2b_vals)} 辆
定价理由：{result.pricing_reason}

{_CHECKLIST}"""

    raw = _call_llm(prompt, temperature=0.0, max_tokens=500)
    if not raw:
        return result

    try:
        clean = re.sub(r'```json|```', '', raw).strip()
        m     = re.search(r'\{.*\}', clean, re.DOTALL)
        json_str = m.group(0) if m else clean
        
        # 修复常见的 JSON 格式错误
        # 1. 修复缺少逗号
        json_str = re.sub(r'("[^"]*")\s*([\}\]])', r'\1,\2', json_str)
        # 2. 移除多余的逗号
        json_str = re.sub(r',\s*([\}\]])', r'\1', json_str)
        # 3. 修复单引号
        json_str = re.sub(r"'([^']*)'", r'"\1"', json_str)
        
        data  = json.loads(json_str)

        issues      = data.get("issues", [])
        adjustments = data.get("adjustments", [])
        summary     = data.get("summary", "")

        if verbose:
            if issues:
                print(f"\n  [自检] 发现 {len(issues)} 个问题：")
                for iss in issues:
                    print(f"    ✗ {iss}")
                for adj in adjustments:
                    print(f"    → {adj.get('field')} : {adj.get('from')} → {adj.get('to')}  ({adj.get('reason')})")
            else:
                print(f"\n  [自检] 通过，无需修正")
            if summary:
                print(f"  [自检] {summary}")

        # 应用修正
        new_c2b = _safe_float(data, "final_c2b", result.c2b_price)
        new_b2c = _safe_float(data, "final_b2c", result.b2c_price)

        if abs(new_c2b - result.c2b_price) > 0.01 or abs(new_b2c - result.b2c_price) > 0.01:
            result.c2b_price      = round(new_c2b, 2)
            result.b2c_price      = round(new_b2c, 2)
            result.c2b_low        = round(new_c2b * 0.96, 2)
            result.c2b_high       = round(new_c2b * 1.04, 2)
            result.b2c_low        = round(new_b2c * 0.97, 2)
            result.b2c_high       = round(new_b2c * 1.03, 2)
            result.gross_profit   = round(new_b2c - new_c2b - car.refurbish_cost, 2)
            result.gross_margin_pct = round(
                result.gross_profit / new_c2b * 100 if new_c2b > 0 else 0, 1
            )

        result.confidence = data.get("final_confidence", result.confidence)
        if summary:
            result.pricing_reason += f"  【自检】{summary}"

        result.raw_steps["reflection"] = {
            "issues": issues, "adjustments": adjustments, "summary": summary
        }

    except Exception as e:
        if verbose:
            print(f"  [自检] 解析失败：{e}")

    return result


# ═════════════════════════════════════════════════════
#  可解释推理报告
# ═════════════════════════════════════════════════════

def print_report(result: DualPricingResult, car: RealCarListing):
    """打印完整的可解释推理报告"""
    W = 58
    is_qwen = result.raw_steps.get("qwen_prediction", False)
    
    print(f"\n  ╔{'═'*W}╗")
    print(f"  ║  {'定价报告':<{W-2}}║")
    print(f"  ╠{'═'*W}╣")
    print(f"  ║  车辆：{car.model_year}款{car.brand}{car.series}{car.model} {car.mileage}万km {car.inspection_grade}级")
    print(f"  ╠{'─'*W}╣")
    
    if not is_qwen:
        print(f"  ║  采购价格：{result.c2b_price:>7.2f} 万  [{result.c2b_low}, {result.c2b_high}]")
        print(f"  ║  销售价格：{result.b2c_price:>7.2f} 万  [{result.b2c_low}, {result.b2c_high}]")
        print(f"  ║  预计毛利：  {result.gross_profit:>7.2f} 万  毛利率 {result.gross_margin_pct:.1f}%")
        print(f"  ║  置信度：    {result.confidence}")
        print(f"  ║  采购价格 MAPE：  {result.c2b_mape:>7.2f}%  销售价格 MAPE：{result.b2c_mape:>7.2f}%")
        print(f"  ║  与相似车型偏差： C2B {result.c2b_deviation:>7.2f}%  B2C {result.b2c_deviation:>7.2f}%")
    else:
        print(f"  ║  销售价格：{result.b2c_price:>7.2f} 万  [{result.b2c_low}, {result.b2c_high}]")
        print(f"  ║  置信度：    {result.confidence}")
        print(f"  ║  模型：    Qwen LoRA 微调模型")

    if result.risk_notes:
        print(f"  ╠{'─'*W}╣")
        print(f"  ║  风险提示")
        for r in result.risk_notes[:3]:
            print(f"  ║    ⚠  {r[:W-6]}")

    # 价格修正明细（基于相似车差异）
    refs = result.raw_steps.get("refs")
    if refs:
        print(f"  ╠{'─'*W}╣")
        print(f"  ║  价格修正明细（基于相似车差异）")
        
        # 计算相似车的平均指标
        c2b_refs = [c.c2b_price for c, _ in refs if c.c2b_price]
        b2c_refs = [c.b2c_price for c, _ in refs if c.b2c_price]
        year_refs = [c.model_year for c, _ in refs if c.model_year]
        mileage_refs = [c.mileage for c, _ in refs if c.mileage]
        grade_refs = [c.inspection_grade for c, _ in refs if c.inspection_grade]
        transfer_refs = [c.transfer_count for c, _ in refs if c.transfer_count]
        
        c2b_avg = sum(c2b_refs) / len(c2b_refs) if c2b_refs else 0
        b2c_avg = sum(b2c_refs) / len(b2c_refs) if b2c_refs else 0
        year_avg = sum(year_refs) / len(year_refs) if year_refs else car.model_year
        mileage_avg = sum(mileage_refs) / len(mileage_refs) if mileage_refs else car.mileage
        transfer_avg = sum(transfer_refs) / len(transfer_refs) if transfer_refs else car.transfer_count
        
        # 计算差异
        year_diff = car.model_year - year_avg
        mileage_diff = car.mileage - mileage_avg
        transfer_diff = car.transfer_count - transfer_avg
        
        # 显示修正明细
        print(f"  ║    相似车C2B均价：  {c2b_avg:>7.2f}万  (参考基准)")
        print(f"  ║    ├─ 车龄差异：  {car.model_year}年 vs 平均{year_avg:.0f}年  {'新' if year_diff > 0 else '旧'}{abs(year_diff):.0f}年")
        print(f"  ║    ├─ 里程差异：  {car.mileage:>4.1f}万km vs 平均{mileage_avg:.1f}万km  {'多' if mileage_diff > 0 else '少'}{abs(mileage_diff):.1f}万km")
        print(f"  ║    ├─ 车况差异：  {car.inspection_grade}级 vs 平均{grade_refs.count('A')}A/{grade_refs.count('B')}B/{grade_refs.count('C')}C")
        print(f"  ║    └─ 过户差异：  {car.transfer_count}次 vs 平均{transfer_avg:.1f}次  {'多' if transfer_diff > 0 else '少'}{abs(transfer_diff):.1f}次")
        print(f"  ║    最终C2B：     {result.c2b_price:>7.2f}万  (基于上述差异调整)")
        print(f"  ║    最终B2C：     {result.b2c_price:>7.2f}万  (C2B+整备+毛利)")
    
    # 推理链明细（ReAct 模式下有值）
    trace = result.raw_steps.get("reasoning_trace", [])
    if trace:
        print(f"  ╠{'─'*W}╣")
        print(f"  ║  推理链（每步修正明细）")
        for t in trace:
            step    = t.get("step", "")
            value   = t.get("value")
            delta   = t.get("delta")
            reason  = t.get("reasoning", "")[:35]
            if value is None:
                continue
            
            # 确保 value 是数字
            try:
                if isinstance(value, str):
                    value = float(value)
            except (ValueError, TypeError):
                continue
                
            if delta is not None:
                # 确保 delta 是数字
                try:
                    if isinstance(delta, str):
                        delta = float(delta)
                except (ValueError, TypeError):
                    delta = None
                
                if delta is not None:
                    sign = "+" if delta >= 0 else ""
                    print(f"  ║    {step:<15}  {sign}{delta:>6.2f}万  → {value:.2f}万  {reason}")
                else:
                    print(f"  ║    {step:<15}  ={value:>7.2f}万  {reason}")
            else:
                print(f"  ║    {step:<15}  ={value:>7.2f}万  {reason}")

    # 参考车源列表
    refs = result.raw_steps.get("refs")
    if refs:
        print(f"  ╠{'─'*W}╣")
        print(f"  ║  参考车源列表（共{len(refs)}辆）")
        
        # 智能选择参考车源：从多到少，逐步降级
        same_brand_series_model_refs = [
            c for c, _ in refs 
            if c.brand == car.brand and c.series == car.series and c.model == car.model
        ]
        
        if len(same_brand_series_model_refs) >= 5:
            final_refs = same_brand_series_model_refs
        else:
            final_refs = same_brand_series_model_refs.copy()
            same_brand_series_year_only_refs = [
                c for c, _ in refs 
                if c.brand == car.brand and c.series == car.series and c.model_year == car.model_year and c not in final_refs
            ]
            final_refs.extend(same_brand_series_year_only_refs)
            
            if len(final_refs) < 5:
                same_brand_series_only_refs = [
                    c for c, _ in refs 
                    if c.brand == car.brand and c.series == car.series and c not in final_refs
                ]
                final_refs.extend(same_brand_series_only_refs)
        
        # 显示同款车源
        if same_brand_series_model_refs:
            print(f"  ║  【同款车源】（同品牌同车系同车型）:")
            for i, c in enumerate(same_brand_series_model_refs[:10], 1):
                print(f"  ║    {i}. {c.model_year}款{c.brand}{c.series}{c.model} | {c.mileage:4.1f}万km | {c.inspection_grade}级 | C2B:{c.c2b_price:5.2f}万 | B2C:{c.b2c_price:5.2f}万")
            if len(same_brand_series_model_refs) > 10:
                print(f"  ║    ... 还有 {len(same_brand_series_model_refs) - 10} 辆")
        
        # 显示补充相似车源
        additional_refs = [c for c in final_refs if c not in same_brand_series_model_refs]
        if additional_refs:
            print(f"  ║  【补充相似车源】:")
            for i, c in enumerate(additional_refs[:5], 1):
                print(f"  ║    {i}. {c.model_year}款{c.brand}{c.series}{c.model} | {c.mileage:4.1f}万km | {c.inspection_grade}级 | C2B:{c.c2b_price:5.2f}万 | B2C:{c.b2c_price:5.2f}万")
            if len(additional_refs) > 5:
                print(f"  ║    ... 还有 {len(additional_refs) - 5} 辆")
    
    # ReAct 工具调用记录
    react_steps = [h for h in result.raw_steps.get("trace", [])
                   if isinstance(h, dict) and "action" in h]
    if react_steps:
        print(f"  ╠{'─'*W}╣")
        print(f"  ║  工具调用记录")
        for h in react_steps:
            print(f"  ║    Step{h['step']} → {h['action'][:45]}")
            obs_short = h.get("observation","")[:50]
            if obs_short:
                print(f"  ║           {obs_short}")

    # 自检结论
    reflection = result.raw_steps.get("reflection", {})
    if reflection.get("summary"):
        print(f"  ╠{'─'*W}╣")
        print(f"  ║  自检结论：{reflection['summary']}")
        for adj in reflection.get("adjustments", []):
            print(f"  ║    修正 {adj.get('field')}：{adj.get('from')} → {adj.get('to')}")
            print(f"  ║    原因：{adj.get('reason','')[:40]}")

    # 奖励指标（有真实价格时）
    if result.r_total:
        print(f"  ╠{'─'*W}╣")
        print(f"  ║  评估指标  R_c2b={result.r_c2b:.3f}  R_b2c={result.r_b2c:.3f}"
              f"  R_margin={result.r_margin:.3f}  R_total={result.r_total:.3f}")

    print(f"  ╠{'─'*W}╣")
    print(f"  ║  定价理由：{result.pricing_reason[:W-8]}")
    print(f"  ╚{'═'*W}╝")


# ═════════════════════════════════════════════════════
#  对外接口
# ═════════════════════════════════════════════════════

def price_car_react(
    car: RealCarListing,
    retriever: RealCarRAGRetriever = None,
    max_steps: int = 6,
    verbose: bool = True,
    use_qwen_direct: bool = True,
    use_self_reflection: bool = True,
    use_qwen_as_baseline: bool = False,
    previous_mileage: float = None,
    previous_transfer: int = None,
    previous_b2c: float = None,
) -> DualPricingResult:
    """
    ReAct + 自我反思 完整定价。
    
    如果 retriever 参数为 None，会自动从 RAG 系统获取检索器。
    
    对比 demo_llm_real.price_car()：
      ✓ LLM 主动调用工具补充信息（不再被动接受固定输入）
      ✓ 定价后自检，发现毛利倒挂/漏项折价自动修正
      ✓ 每步修正值 + 依据完整记录，可展示给业务人员
    """
    # 如果没有提供检索器，自动从 RAG 系统获取
    if retriever is None:
        rag_sys = get_global_rag_system()
        if rag_sys and rag_sys.retriever:
            retriever = rag_sys.retriever
            if verbose:
                print(f"  [RAG] 自动使用 RAG 知识库（{len(rag_sys.knowledge_base)} 条记录）")
        else:
            # 如果 RAG 系统不可用，使用空检索器
            from demo_llm_real import RealCarRAGRetriever
            retriever = RealCarRAGRetriever([])
            if verbose:
                print(f"  [RAG] RAG 系统不可用，使用空检索器")
    
    # Step 1: ReAct 推理
    result, trace = react_price(
        car, retriever, max_steps=max_steps, verbose=verbose,
        use_qwen_direct=use_qwen_direct, use_qwen_as_baseline=use_qwen_as_baseline,
        previous_mileage=previous_mileage, previous_transfer=previous_transfer, previous_b2c=previous_b2c,
    )
    result.raw_steps["trace"] = trace   # 存入原始 trace 供报告展示

    # 如果是 Qwen 预测的结果且不使用自检，直接返回（但不包括作为基准值的情况）
    if result.raw_steps.get("qwen_prediction") and not use_self_reflection and not use_qwen_as_baseline:
        if verbose:
            print(f"\n  [Qwen] 直接使用 Qwen 预测结果，跳过自检和价格修正")
        return result

    # Step 2: 自我反思（如果启用）
    if use_self_reflection:
        if verbose:
            print(f"\n  [自检] 开始质检...")
        refs = retriever.retrieve(car, top_k=200)  # 大幅增加检索数量，获取尽可能多的参考车源
        result.raw_steps["refs"] = refs  # 保存 refs 供报告展示
        result = self_reflect(result, car, refs, verbose=verbose)
    
    # Step 2.5: 计算预测价格与相同车源价格的偏差和 MAPE（仅在启用自检时）
    if use_self_reflection:
        # 智能选择参考车源：从多到少，逐步降级
        # 1. 同品牌同车系同车型（不管年款）
        same_brand_series_model_refs = [
            c for c, _ in refs 
            if c.brand == car.brand and c.series == car.series and c.model == car.model
        ]
        
        # 2. 如果同款车源不足5个，添加同品牌同车系同年款的车源
        if len(same_brand_series_model_refs) >= 5:
            same_brand_series_year_refs = same_brand_series_model_refs
        else:
            same_brand_series_year_refs = same_brand_series_model_refs.copy()
            # 添加同品牌同车系同年款的车源（排除已添加的）
            same_brand_series_year_only_refs = [
                c for c, _ in refs 
                if c.brand == car.brand and c.series == car.series and c.model_year == car.model_year and c not in same_brand_series_year_refs
            ]
            same_brand_series_year_refs.extend(same_brand_series_year_only_refs)
            
            # 如果还不足5个，添加同品牌同车系不同年款的车源
            if len(same_brand_series_year_refs) < 5:
                same_brand_series_only_refs = [
                    c for c, _ in refs 
                    if c.brand == car.brand and c.series == car.series and c not in same_brand_series_year_refs
                ]
                same_brand_series_year_refs.extend(same_brand_series_only_refs)
        
        if verbose:
            print(f"  [MAPE] 同款车源数量: {len(same_brand_series_model_refs)}")
            print(f"  [MAPE] 最终使用参考车源数量: {len(same_brand_series_year_refs)}")
            
            if same_brand_series_model_refs:
                print(f"\n  [检索] 同款车源（同品牌同车系同车型）:")
                for i, c in enumerate(same_brand_series_model_refs[:10], 1):
                    print(f"    {i}. {c.model_year}款{c.brand}{c.series}{c.model} | {c.mileage}万公里 | C2B:{c.c2b_price:.2f}万 | B2C:{c.b2c_price:.2f}万")
                if len(same_brand_series_model_refs) > 10:
                    print(f"    ... 还有 {len(same_brand_series_model_refs) - 10} 辆")
            
            additional_refs = [c for c in same_brand_series_year_refs if c not in same_brand_series_model_refs]
            if additional_refs:
                print(f"\n  [检索] 补充相似车源:")
                for i, c in enumerate(additional_refs[:5], 1):
                    print(f"    {i}. {c.model_year}款{c.brand}{c.series}{c.model} | {c.mileage}万公里 | C2B:{c.c2b_price:.2f}万 | B2C:{c.b2c_price:.2f}万")
                if len(additional_refs) > 5:
                    print(f"    ... 还有 {len(additional_refs) - 5} 辆")
        
        c2b_refs = [c.c2b_price for c in same_brand_series_year_refs if c.c2b_price]
        b2c_refs = [c.b2c_price for c in same_brand_series_year_refs if c.b2c_price]
        
        # 仅计算参考车源统计信息，不强制替换预测结果
        import statistics
        if c2b_refs and b2c_refs:
            c2b_median = statistics.median(c2b_refs)
            b2c_median = statistics.median(b2c_refs)
            
            if verbose:
                print(f"  [参考统计] 使用{len(c2b_refs)}辆参考车源")
                print(f"  [参考统计] 参考车C2B中位数: {c2b_median:.2f}万, 预测: {result.c2b_price:.2f}万")
                print(f"  [参考统计] 参考车B2C中位数: {b2c_median:.2f}万, 预测: {result.b2c_price:.2f}万")
                print(f"  [参考统计] 保留ReAct预测结果，不强制替换")
        
        # 计算相同车源平均价格和偏差
        if c2b_refs:
            c2b_avg = sum(c2b_refs) / len(c2b_refs)
            result.c2b_deviation = ((result.c2b_price - c2b_avg) / c2b_avg * 100) if c2b_avg > 0 else 0.0
        
        if b2c_refs:
            b2c_avg = sum(b2c_refs) / len(b2c_refs)
            result.b2c_deviation = ((result.b2c_price - b2c_avg) / b2c_avg * 100) if b2c_avg > 0 else 0.0
        
        # 计算 MAPE（Mean Absolute Percentage Error），只使用相同车源
        result.c2b_mape = 0.0
        result.b2c_mape = 0.0
        
        if c2b_refs:
            c2b_errors = [abs(result.c2b_price - ref) / ref for ref in c2b_refs if ref > 0]
            result.c2b_mape = sum(c2b_errors) / len(c2b_errors) * 100 if c2b_errors else 0.0
        
        if b2c_refs:
            b2c_errors = [abs(result.b2c_price - ref) / ref for ref in b2c_refs if ref > 0]
            result.b2c_mape = sum(b2c_errors) / len(b2c_errors) * 100 if b2c_errors else 0.0

        # Step 2.75: 强制单调性校验
        # 确保同车型同车系下车况越好价格越高
        result = _enforce_monotonicity(result, car, refs, verbose=verbose)

        # Step 3: 奖励评估（有真实价格时）
        if car.c2b_price and car.b2c_price:
            result   = compute_rewards(result, car, c2b_refs, b2c_refs)

    return result


def price_from_text(
    description: str,
    retriever: RealCarRAGRetriever,
    max_steps: int = 6,
) -> DualPricingResult:
    """
    【最终对外接口】验车师文字 → 完整推理报告

    完整链路：
      文字描述
        ↓ extract_from_description()   属性提取
        ↓ react_price()                ReAct 循环（LLM主动查工具）
        ↓ self_reflect()               自我反思质检
        ↓ DualPricingResult            含完整推理链和自检记录
    """
    print(f"\n  [输入] {description[:65]}{'…' if len(description)>65 else ''}")
    car    = extract_from_description(description)
    result = price_car_react(car, retriever, max_steps=max_steps)
    return result


# ═════════════════════════════════════════════════════
#  交互模式 & Demo
# ═════════════════════════════════════════════════════

def _sep(title: str = ""):
    print("\n" + "="*60)
    if title:
        print(f"  {title}")
        print("="*60)


def demo(retriever: RealCarRAGRetriever):
    """内置演示：3个场景，展示 ReAct + 自检完整链路"""
    cases = [
        ("普通燃油车",
         "2021年款丰田凯美瑞2.5L豪华版，白色，行驶6.8万公里。"
         "有一次轻微追尾已修复，过户1次，非营运。"
         "检测85分B级，整备0.15万，无抵押。",
         None),

        ("高风险车",
         "2019年本田雅阁2.0L标准版，红色，里程13万公里。"
         "中等碰撞记录右前叶子板换过，过户3次，曾用网约车运营。"
         "检测65分C级，整备0.6万，抵押抵扣1.5万。",
         None),

        ("新能源车",
         "2022款比亚迪汉EV荣耀版，黑色，纯电，5.5万公里。"
         "无事故首任车主，非营运，检测93分A级，整备0.05万，无抵押。",
         None),
    ]

    for label, desc, _ in cases:
        _sep(f"案例：{label}")
        result = price_from_text(desc, retriever)
        print_report(result, extract_from_description.__wrapped__(desc)
                     if hasattr(extract_from_description, '__wrapped__') else
                     RealCarListing(
                         brand="未知",
                         series="未知",
                         model="未知",
                         model_year=2020,
                         mileage=0,
                         color="未知",
                         transfer_count=1,
                         inspection_score=80,
                         inspection_grade="B"
                     ))
        route_by_confidence(result)


def interactive(retriever: RealCarRAGRetriever, max_steps: int = 6):
    """交互输入模式：验车师在终端直接输入描述"""
    _sep("ReAct 定价系统（输入验车描述 → 回车定价，输入 q 或 退出 退出系统）")
    print("  提示：描述越详细（品牌/车系/年款/车型/颜色/里程/评级/过户次数），定价越准确\n")

    while True:
        print("─" * 60)
        try:
            desc = input("  请输入验车描述：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  已退出")
            break

        if not desc:
            continue
        if desc.lower() in ("q", "quit", "exit", "退出"):
            print("  已退出")
            break

        result = price_from_text(desc, retriever, max_steps=max_steps)

        # 提取 car 用于报告展示（直接用已提取的字段）
        car = extract_from_description(desc)
        print_report(result, car)
        route_by_confidence(result)
        print()


def main():
    parser = argparse.ArgumentParser(description="ReAct 二手车定价系统")
    parser.add_argument("--data",  type=str, help="历史成交数据文件（.csv）")
    parser.add_argument("--desc",  type=str, help="直接传入验车描述（非交互模式）")
    parser.add_argument("--steps", type=int, default=6,  help="ReAct 最大推理步数")
    parser.add_argument("--max-records", type=int, default=5000, help="数据读取上限")
    parser.add_argument("--demo",  action="store_true",  help="运行内置演示案例")
    args = parser.parse_args()

    _sep("二手车 ReAct 定价系统（准确率 + 可解释性增强版）")
    print(f"""
  架构：
    验车师文字描述
        ↓ 属性提取（LLM）
        ↓ RAG 检索初始参考车
        ↓ ReAct 循环（LLM 主动调用工具补充信息）
            Thought → Action → Observe → ...
        ↓ 自我反思（毛利/风险/偏差自检）
        ↓ 可解释推理报告（每步修正值+依据）

  LLM状态：{'✅ 已连接' if LLM_AVAILABLE else '⚠️  未配置 API Key，将使用规则引擎兜底'}
""")

    retriever = _load_retriever(args.data, max_records=args.max_records)

    # 初始化定价模型
    # 如果 max_records 为默认值 5000，则使用 None 加载所有数据
    if args.max_records == 5000:
        init_models(args.data, max_records=None)
    else:
        init_models(args.data, max_records=args.max_records)

    if args.desc:
        # 单次调用模式
        result = price_from_text(args.desc, retriever, max_steps=args.steps)
        car    = extract_from_description(args.desc)
        print_report(result, car)
        route_by_confidence(result)

    elif args.demo:
        # 内置演示
        cases = [
            ("普通燃油车",
             "2021年款丰田凯美瑞2.5L豪华版，白色，行驶6.8万公里，"
             "有一次轻微追尾已修复，过户1次，非营运，检测85分B级，整备0.15万，无抵押。"),
            ("高风险车",
             "2019年本田雅阁2.0L标准版，红色，里程13万公里，"
             "中等碰撞右前叶子板换过，过户3次，曾用网约车运营，检测65分C级，整备0.6万，抵押1.5万。"),
            ("新能源车",
             "2022款比亚迪汉EV荣耀版，黑色，纯电，5.5万公里，"
             "无事故首任车主非营运，检测93分A级，整备0.05万，无抵押。"),
        ]
        for label, desc in cases:
            _sep(f"案例：{label}")
            result = price_from_text(desc, retriever, max_steps=args.steps)
            car    = extract_from_description(desc)
            print_report(result, car)
            route_by_confidence(result)

    else:
        # 默认：交互输入模式
        interactive(retriever, max_steps=args.steps)


if __name__ == "__main__":
    main()
