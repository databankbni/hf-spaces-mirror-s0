from flask import Flask, request, jsonify, send_from_directory, render_template
import psycopg2
from psycopg2.extras import RealDictCursor
from decimal import Decimal
import os
import requests
from datetime import datetime, timedelta, date
from datetime import timezone, timedelta

app = Flask(__name__)

# 数据库配置
DB_CONFIG = {
    'host': 'aws-1-eu-west-1.pooler.supabase.com',
    'database': 'postgres',
    'user': 'postgres.rwcwnmzzljhbpcsyqcbo',
    'password': 'qLRPGv4NKo0OEfm9',
    'port': 5432
}


def get_db_connection():
    """获取数据库连接"""
    conn = psycopg2.connect(**DB_CONFIG)
    return conn


@app.route('/')
def index():
    """返回主页面"""
    return send_from_directory('.', 'index.html')


@app.route('/api/recharge', methods=['POST'])
def recharge():
    """充值接口 - 增加余额"""
    try:
        data = request.get_json()
        amount = Decimal(str(data.get('amount', 0)))

        if amount <= 0:
            return jsonify({'error': '充值金额必须大于0'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # 更新余额 - 增加金额
        cursor.execute(
            """
            UPDATE meter_balances 
            SET credit_amount = credit_amount + %s
            WHERE id = 1
            RETURNING credit_amount
            """,
            (amount,)
        )

        result = cursor.fetchone()

        if result:
            new_balance = result[0]
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({
                'message': f'充值成功！当前余额：{new_balance}',
                'new_balance': float(new_balance)
            }), 200
        else:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': '充值失败，未找到记录'}), 404

    except Exception as e:
        return jsonify({'error': f'服务器错误：{str(e)}'}), 500


@app.route('/api/calibrate', methods=['POST'])
def calibrate():
    """校准接口 - 设置余额为指定值"""
    try:
        data = request.get_json()
        amount = Decimal(str(data.get('amount', 0)))

        if amount < 0:
            return jsonify({'error': '校准金额不能为负数'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # 更新余额 - 设置为指定金额
        cursor.execute(
            """
            UPDATE meter_balances 
            SET credit_amount = %s
            WHERE id = 1
            RETURNING credit_amount
            """,
            (amount,)
        )

        result = cursor.fetchone()

        if result:
            new_balance = result[0]
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({
                'message': f'校准成功！当前余额：{new_balance}',
                'new_balance': float(new_balance)
            }), 200
        else:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': '校准失败，未找到记录'}), 404

    except Exception as e:
        return jsonify({'error': f'服务器错误：{str(e)}'}), 500


@app.route('/api/balance', methods=['GET'])
def get_balance():
    """获取当前余额"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT credit_amount FROM meter_balances WHERE id = 1")
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        if result:
            return jsonify({'balance': float(result[0])}), 200
        else:
            return jsonify({'error': '未找到余额记录'}), 404

    except Exception as e:
        return jsonify({'error': f'服务器错误：{str(e)}'}), 500


def calculate_profit(buy_price, sell_price, quantity, market='sh'):
    # 常量定义
    FEE_JINGSHOU = 0.0000341
    FEE_ZHENGGUAN = 0.00002
    FEE_GUOHU = 0.00001
    FEE_YINHUA = 0.0005
    COMMISSION_RATE = 0.0001  # 注意：实际券商佣金可能不同，通常最低5元
    buy_amount = buy_price * quantity
    sell_amount = sell_price * quantity
    # 买入费用计算
    buy_fee_jingshou = buy_amount * FEE_JINGSHOU
    buy_fee_zhengguan = buy_amount * FEE_ZHENGGUAN
    if market == 'sh':
        buy_fee_guohu = buy_amount * FEE_GUOHU
    else:
        buy_fee_guohu = 0
    buy_commission = max(buy_amount * COMMISSION_RATE, 5)
    total_buy_fees = buy_fee_jingshou + buy_fee_zhengguan + buy_fee_guohu + buy_commission
    total_buy_cost = buy_amount + total_buy_fees
    # 卖出费用计算
    sell_fee_jingshou = sell_amount * FEE_JINGSHOU
    sell_fee_zhengguan = sell_amount * FEE_ZHENGGUAN
    if market == 'sh':
        sell_fee_guohu = sell_amount * FEE_GUOHU
    else:
        sell_fee_guohu = 0
    sell_fee_yinhua = sell_amount * FEE_YINHUA
    sell_commission = max(sell_amount * COMMISSION_RATE, 5)
    total_sell_fees = sell_fee_jingshou + sell_fee_zhengguan + sell_fee_guohu + sell_fee_yinhua + sell_commission
    net_sell_proceeds = sell_amount - total_sell_fees
    # 最终收益
    profit = net_sell_proceeds - total_buy_cost

    return {
        "value": profit,
        "details": {
            "total_fees": total_buy_fees + total_sell_fees,
            "cost": total_buy_cost,
            "revenue": net_sell_proceeds
        }
    }

@app.route('/calst', methods=['GET', 'POST'])
def calst():
    result = None
    error = None
    # 默认表单数据，用于页面回显
    form_data = {
        'buy_price': '',
        'sell_price': '',
        'quantity': '',
        'market': 'sh'
    }
    if request.method == 'POST':
        try:
            # 1. 获取用户输入
            buy_price = float(request.form.get('buy_price'))
            sell_price = float(request.form.get('sell_price'))
            quantity = int(request.form.get('quantity'))
            market = request.form.get('market', 'sh')
            # 更新回显数据
            form_data = {
                'buy_price': buy_price,
                'sell_price': sell_price,
                'quantity': quantity,
                'market': market
            }
            # 2. 执行计算
            result = calculate_profit(buy_price, sell_price, quantity, market)
        except ValueError:
            error = "输入错误：请输入有效的数字。"
        except Exception as e:
            error = f"计算发生错误: {str(e)}"
    return render_template('calst.html', result=result, error=error, form=form_data)


def generate_url(base_url="https://node.v2rayshare.top", type="1"):
    # 获取当前日期
    now = datetime.now() - timedelta(hours=12)

    # 格式化日期
    year = now.strftime("%Y")  # 2026
    month = now.strftime("%m")  # 04
    day = now.strftime("%d")  # 21

    # 组合完整的日期字符串
    date_str = f"{year}{month}{day}"  # 20260421

    # 生成文件名
    filename = f"{type}-{date_str}.txt"

    # 生成完整URL
    url = f"{base_url}/uploads/{year}/{month}/{filename}"

    return url

@app.route('/v2ray')
def proxy_v2ray():
    """
    代理转发接口
    获取当天的订阅文件内容并返回
    """
    try:
        # 1. 获取当前日期，格式为 YYYYMMDD (例如 20231027)
        # 如果目标网站格式是 YYYY-MM-DD，请修改为 strftime('%Y-%m-%d')
        # today = datetime.now().strftime('%Y%m%d')

        type = request.args.get('type')

        # 2. 构造目标 URL
        target_url = generate_url(type=type) #f"https://clashgithub.com/wp-content/uploads/rss/{today}.txt"
        print(target_url)
        # target_url = f"https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/v2"
        # 3. 请求外部资源
        # 设置 timeout 防止请求卡死，headers 模拟浏览器访问（部分网站需要）
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        resp = requests.get(target_url, timeout=10, headers=headers)

        # 4. 检查响应状态
        if resp.status_code == 200:
            # 解码，原站是 GBK（那堆乱码就是 GBK 被当 UTF-8 读了），先按 GBK 解再转 UTF-8 输出
            try:
                text = resp.content.decode('gbk')
            except UnicodeDecodeError:
                text = resp.content.decode('utf-8', errors='ignore')

            # 只保留非注释行（不以 # 开头，忽略纯空白）
            lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith('#')]
            clean = '\n'.join(lines) + '\n'

            return clean.encode('utf-8'), 200, {'Content-Type': 'text/plain; charset=utf-8'}
        else:
            return jsonify({
                'error': '目标资源获取失败',
                'status_code': resp.status_code,
                'url': target_url
            }), 502

    except requests.exceptions.Timeout:
        return jsonify({'error': '请求外部服务超时'}), 504
    except Exception as e:
        return jsonify({'error': f'代理服务内部错误：{str(e)}'}), 500

@app.route('/duration')
def get_duration_chart():
    """
    展示通勤时间趋势图
    支持通过date参数选择日期，如：/duration?date=2024-01-15
    """
    try:
        # 获取日期参数，默认为今天
        date_str = request.args.get('date')
        if date_str:
            try:
                selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                selected_date = date.today()
        else:
            selected_date = date.today()

        conn = get_db_connection()
        cursor = conn.cursor()

        # 查询指定日期的通勤记录，按时间排序
        cursor.execute("""
            SELECT 
                record_time,
                duration_minutes
            FROM travel_duration_records 
            WHERE DATE(record_time) = %s
            ORDER BY record_time
        """, (selected_date,))

        records = cursor.fetchall()
        cursor.close()
        conn.close()

        # 处理数据用于图表
        time_data = []
        duration_data = []
        durations = []

        for record in records:
            time_data.append(record[0].isoformat())
            duration = record[1]
            duration_data.append(duration)
            durations.append(duration)

        # 服务端计算统计数据
        record_count = len(records)
        avg_duration = 0
        min_duration = 0
        max_duration = 0

        if record_count > 0:
            avg_duration = round(sum(durations) / record_count, 1)
            min_duration = min(durations)
            max_duration = max(durations)

        # 如果没有数据，使用前一天的数据
        if record_count == 0:
            # 尝试获取最近有数据的日期
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DATE(record_time) as date
                FROM travel_duration_records
                WHERE DATE(record_time) < %s
                GROUP BY DATE(record_time)
                ORDER BY DATE(record_time) DESC
                LIMIT 1
            """, (selected_date,))

            recent_record = cursor.fetchone()
            cursor.close()
            conn.close()

            if recent_record:
                # 重定向到有数据的最近日期
                return f"""
                <script>
                    alert('{selected_date} 没有通勤记录，将显示最近的日期：{recent_record[0]}');
                    window.location.href = '/duration?date={recent_record[0]}';
                </script>
                """

        # 渲染HTML模板
        return render_template(
            'duration.html',
            time_data=time_data,
            duration_data=duration_data,
            today=selected_date.strftime('%Y年%m月%d日'),
            selected_date=selected_date.strftime('%Y-%m-%d'),
            record_count=record_count,
            avg_duration=avg_duration,
            min_duration=min_duration,
            max_duration=max_duration,
            last_update=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )

    except Exception as e:
        return jsonify({'error': f'服务器错误：{str(e)}'}), 500

@app.route('/api/last_trip', methods=['GET'])
def get_last_trip():
    """
    获取最近一次已完成行程的
    起始时间、结束时间、耗时（分钟）、行驶距离（公里）
    基于 drives 表
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT start_date,
                   end_date,
                   duration_min,
                   distance
            FROM drives
            WHERE end_date IS NOT NULL
            ORDER BY end_date DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return jsonify({'message': '暂无已完成的行车记录'}), 200

        # UTC 时间转换为北京时间（UTC+8）
        utc_plus_8 = timezone(timedelta(hours=8))
        start_time = row[0].replace(tzinfo=timezone.utc).astimezone(utc_plus_8)
        end_time = row[1].replace(tzinfo=timezone.utc).astimezone(utc_plus_8)

        duration_minutes = row[2]
        distance_km = row[3]  # 行驶距离（公里）

        return jsonify({
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_minutes': duration_minutes,
            'distance_km': distance_km
        }), 200

    except Exception as e:
        return jsonify({'error': f'服务器错误：{str(e)}'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7860, debug=True)
