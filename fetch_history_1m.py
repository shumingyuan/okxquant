import requests
import pandas as pd
import time
from datetime import datetime, timedelta
import os

def fetch_one_day(instId, date, bar='1m'):
    """获取某一天的分钟数据"""
    all_data = []
    # 计算目标日期的起始和结束时间戳
    start_time = int(datetime.combine(date, datetime.min.time()).timestamp() * 1000)
    end_time = int((datetime.combine(date, datetime.max.time())).timestamp() * 1000)
    after = end_time
    
    base_url = "https://www.okx.com"
    endpoint = "/api/v5/market/history-mark-price-candles"
    
    while True:
        params = {
            'instId': instId,
            'bar': bar,
            'limit': 100,
            'after': str(after)
        }
        
        url = base_url + endpoint
        response = requests.get(url, params=params)
        
        if response.status_code != 200:
            print(f"请求失败: {response.status_code}")
            break
            
        result = response.json()
        data = result['data']
        
        if not data:
            break
            
        all_data.extend(data)
        last_ts = int(data[-1][0])
        
        if last_ts <= start_time:
            break
            
        after = last_ts
        time.sleep(0.2)  # 避免请求过快
    
    return all_data

def process_and_save_data(data, filename):
    """处理数据并保存到CSV"""
    if not data:
        return False
        
    df = pd.DataFrame(data, columns=[
        'ts', 'open', 'high', 'low', 'close', 'vol'
    ])
    
    for col in ['open', 'high', 'low', 'close', 'vol']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df['datetime'] = pd.to_datetime(df['ts'], unit='ms')
    df = df.sort_values('datetime')
    df = df[['datetime', 'open', 'high', 'low', 'close', 'vol']]
    
    df.to_csv(filename, index=False)
    return True

def fetch_daily_data(instId, start_date, end_date, output_folder):
    """获取指定日期范围内的分钟数据"""
    # 创建输出目录
    os.makedirs(output_folder, exist_ok=True)
    
    current_date = start_date
    while current_date <= end_date:
        filename = os.path.join(output_folder, f"{instId}_{current_date.strftime('%Y%m%d')}.csv")
        
        print(f"正在获取 {current_date.strftime('%Y-%m-%d')} 的数据...")
        
        # 如果文件已存在，跳过
        if os.path.exists(filename):
            print(f"文件 {filename} 已存在，跳过")
            current_date -= timedelta(days=1)
            continue
        
        data = fetch_one_day(instId, current_date)
        if process_and_save_data(data, filename):
            print(f"成功保存到 {filename}")
        else:
            print(f"获取 {current_date.strftime('%Y-%m-%d')} 的数据失败")
        
        current_date -= timedelta(days=1)
        time.sleep(0.2)  # 每天数据获取后暂停1秒

if __name__ == "__main__":
    # 设置参数
    instId = 'DOGE-USDT-SWAP'
    start_date = datetime.now() - timedelta(days=365*3)  # 3年前
    end_date = datetime.now()
    output_folder = os.path.join('data', 'doge1m')
    print( start_date)
    # 开始获取数据
    # fetch_daily_data(instId, start_date, end_date, output_folder)