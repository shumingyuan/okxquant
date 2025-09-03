import requests
import pandas as pd
import time

def fetch_and_save(instId, filename, bar='1H', days=365):
    all_data = []
    now = int(time.time() * 1000)  
    end_time = now - days * 24 * 60 * 60 * 1000
    after = now
    index = 1
    
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
        print(data)
        if not data:
            print(f"第{index}页无数据，结束获取")
            break
            
        all_data.extend(data)
        last_ts = int(data[-1][0])
        
        print(f"第{index}页获取到{len(data)}条数据，最早时间：{pd.to_datetime(last_ts, unit='ms')}")
        
        if last_ts <= end_time:
            print(f"已达到目标时间：{pd.to_datetime(end_time, unit='ms')}")
            break
            
        after = last_ts
        index += 1
        time.sleep(0.5)  # 增加延迟避免被限制
    
    if not all_data:
        print("未获取到任何数据")
        return
        
    print(f"总共获取到{len(all_data)}条数据")
    
    # 修改列名以匹配数据格式
    df = pd.DataFrame(all_data, columns=[
        'ts', 'open', 'high', 'low', 'close', 'vol'  # 只保留实际返回的6列
    ])
    
    # 转换数据类型
    for col in ['open', 'high', 'low', 'close', 'vol']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df['datetime'] = pd.to_datetime(df['ts'], unit='ms')
    df = df.sort_values('datetime')
    df = df[['datetime', 'open', 'high', 'low', 'close', 'vol']]
    
    # 检查数据是否有效
    print(f"数据样例：\n{df.head()}")
    print(f"数据统计：\n{df.describe()}")
    
    df.to_csv(filename, index=False)
    print(f"数据已保存到{filename}，时间范围：{df['datetime'].min()} 至 {df['datetime'].max()}")

if __name__ == "__main__":
    # 设置为3年数据
    fetch_and_save('DOGE-USDT-SWAP', 'doge_history.csv', bar='1m', days=365*3)
