import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import os

class PivotPointsFinder:
    def __init__(self, n_period=20, std_multiplier=2.0, min_gap=10):
        """
        参数初始化
        n_period: 计算布林带的周期
        std_multiplier: 标准差倍数
        min_gap: 高低点之间的最小间隔
        """
        self.n_period = n_period
        self.std_multiplier = std_multiplier
        self.min_gap = min_gap
        
    def calculate_bands(self, df):
        """计算布林带"""
        df['MA'] = df['close'].rolling(window=self.n_period).mean()
        df['SD'] = df['close'].rolling(window=self.n_period).std()
        df['UB'] = df['MA'] + self.std_multiplier * df['SD']  # 上轨
        df['LB'] = df['MA'] - self.std_multiplier * df['SD']  # 下轨
        return df
    
    def find_pivot_points(self, df):
        """识别关键点"""
        df = self.calculate_bands(df)
        
        # 初始化变量
        trend = 0  # 0=待定，1=上升，-1=下降
        pivot_points = []  # 存储关键点
        last_hp = None  # 最后一个高点
        last_lp = None  # 最后一个低点
        
        # 跳过前N个没有布林带数据的点
        start_idx = self.n_period
        
        for i in range(start_idx, len(df)):
            if trend == 0:  # 初始条件判断
                if df['high'].iloc[i] > df['UB'].iloc[i]:
                    trend = 1
                    last_hp = {'index': i, 'price': df['high'].iloc[i], 'type': 'high'}
                    pivot_points.append(last_hp)
                elif df['low'].iloc[i] < df['LB'].iloc[i]:
                    trend = -1
                    last_lp = {'index': i, 'price': df['low'].iloc[i], 'type': 'low'}
                    pivot_points.append(last_lp)
            
            elif trend == 1:  # 上升趋势
                if df['high'].iloc[i] > last_hp['price']:
                    last_hp = {'index': i, 'price': df['high'].iloc[i], 'type': 'high'}
                    pivot_points[-1] = last_hp
                elif df['low'].iloc[i] < df['LB'].iloc[i]:
                    trend = -1
                    last_lp = {'index': i, 'price': df['low'].iloc[i], 'type': 'low'}
                    pivot_points.append(last_lp)
            
            elif trend == -1:  # 下降趋势
                if df['low'].iloc[i] < last_lp['price']:
                    last_lp = {'index': i, 'price': df['low'].iloc[i], 'type': 'low'}
                    pivot_points[-1] = last_lp
                elif df['high'].iloc[i] > df['UB'].iloc[i]:
                    trend = 1
                    last_hp = {'index': i, 'price': df['high'].iloc[i], 'type': 'high'}
                    pivot_points.append(last_hp)
        
        return self.clean_pivot_points(df, pivot_points)
    
    def clean_pivot_points(self, df, pivot_points):
        """清洗关键点"""
        if len(pivot_points) <= 1:
            return pivot_points
            
        cleaned_points = [pivot_points[0]]
        
        for i in range(1, len(pivot_points)):
            if pivot_points[i]['index'] - cleaned_points[-1]['index'] >= self.min_gap:
                cleaned_points.append(pivot_points[i])
        
        return cleaned_points

def plot_results(df, pivot_points):
    """绘制结果"""
    plt.figure(figsize=(15, 7))
    
    # 绘制收盘价和布林带
    plt.plot(df.index, df['close'], label='Close', color='black', alpha=1)
    plt.plot(df.index, df['MA'], label='MA', color='blue', alpha=0.6)
    plt.plot(df.index, df['UB'], label='Upper Band', color='red', alpha=0.4)
    plt.plot(df.index, df['LB'], label='Lower Band', color='green', alpha=0.4)
    
    # 标记关键点
    for point in pivot_points:
        if point['type'] == 'high':
            plt.plot(df.index[point['index']], point['price'], 'r^', markersize=3)
        else:
            plt.plot(df.index[point['index']], point['price'], 'gv', markersize=3)
    
    plt.title('价格走势与关键点')
    plt.legend()
    plt.grid(True)
    plt.show()

def process_1m_data(folder_path, date_str):
    """处理指定日期的1分钟数据"""
    file_path = os.path.join(folder_path, f'DOGE-USDT-SWAP_{date_str}.csv')
    if not os.path.exists(file_path):
        print(f"文件不存在: {file_path}")
        return
    
    # 读取数据
    df = pd.read_csv(file_path)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df.set_index('datetime', inplace=True)
    
    # 初始化并运行算法
    finder = PivotPointsFinder(n_period=40, std_multiplier=2.0, min_gap=10)
    pivot_points = finder.find_pivot_points(df)
    
    # 打印结果并绘图
    print(f"\n找到 {len(pivot_points)} 个关键点:")
    for point in pivot_points:
        print(f"类型: {point['type']}, 时间: {df.index[point['index']]}, 价格: {point['price']:.4f}")
    
    plot_results(df, pivot_points)

if __name__ == "__main__":
    # 示例：处理特定日期的数据
    folder_path = os.path.join('data', 'doge1m')
    date_str = '20220727'  # 可以改变日期
    process_1m_data(folder_path, date_str)
      