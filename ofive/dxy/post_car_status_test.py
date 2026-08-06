#!/usr/bin/env python3
"""
车辆状态上报测试脚本
用法：
    python test_vehicle_status.py                     # 随机发送 stop 或 running
    python test_vehicle_status.py --status running    # 指定状态
    python test_vehicle_status.py --status stop       # 指定状态
    python test_vehicle_status.py --invalid           # 测试非法状态
"""

import argparse
import random
import sys
import requests

API_URL = "https://ofive-dxy.hf.space/api/vehicle_status"  # 根据实际情况修改地址和端口


def send_status(status: str):
    """发送状态到接口"""
    payload = {"status": status}
    try:
        resp = requests.post(API_URL, json=payload, timeout=5)
        print(f"请求状态: {status}")
        print(f"HTTP 状态码: {resp.status_code}")
        print(f"响应内容: {resp.json()}")
        print("-" * 40)
    except requests.exceptions.ConnectionError:
        print(f"❌ 无法连接到服务器，请确认 Flask 服务正在运行且地址正确：{API_URL}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 请求出错: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="测试车辆状态上报接口")
    parser.add_argument(
        "--status",
        choices=["stop", "running"],
        help="要发送的状态，不指定则随机发送"
    )
    args = parser.parse_args()

    if args.status:
        # 发送指定状态
        send_status(args.status)
    else:
        # 随机发送 stop 或 running，连续测试几次
        for i in range(5):
            status = random.choice(["stop", "running"])
            print(f"第 {i+1} 次测试:")
            send_status(status)

    # 额外测试非法状态（可选）
    print("\n测试非法状态 'invalid':")
    send_status("invalid")


if __name__ == "__main__":
    send_status("stop")
    # main()