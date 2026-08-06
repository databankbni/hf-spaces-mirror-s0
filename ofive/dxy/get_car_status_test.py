#!/usr/bin/env python3
"""
获取车辆最新状态测试脚本
用法：
    python test_get_vehicle_status.py                          # 默认本地地址
    python test_get_vehicle_status.py --url http://your-server:7860
"""

import argparse
import sys
import requests

DEFAULT_API_URL = "https://ofive-dxy.hf.space/api/vehicle_status"


def get_latest_status(api_url: str):
    """调用 GET 接口获取最新车辆状态"""
    try:
        resp = requests.get(api_url, timeout=5)
        print(f"HTTP 状态码: {resp.status_code}")
        data = resp.json()
        print(f"响应内容: {data}")

        if resp.status_code == 200:
            if "status" in data:
                print(f"✅ 最新状态: {data['status']}, 记录时间: {data.get('created_at', '未知')}")
            else:
                print("ℹ️ 暂无车辆状态记录")
        else:
            print(f"❌ 请求失败: {data.get('error', '未知错误')}")

    except requests.exceptions.ConnectionError:
        print(f"❌ 无法连接到服务器，请确认 Flask 服务正在运行且地址正确：{api_url}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 请求出错: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="测试获取车辆最新状态接口")
    parser.add_argument(
        "--url",
        default=DEFAULT_API_URL,
        help=f"接口地址，默认 {DEFAULT_API_URL}"
    )
    args = parser.parse_args()

    print(f"正在请求: {args.url}")
    get_latest_status(args.url)


if __name__ == "__main__":
    main()