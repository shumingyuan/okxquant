import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime
tuple=[]
# 添加自定义布林带指标类
class BollingerBands(bt.Indicator):
    lines = ('ma', 'upper', 'lower',)
    params = (('period', 20), ('devfactor', 2),)
    
    plotlines = dict(
        ma=dict(color='blue', alpha=0.5),
        upper=dict(color='red', alpha=0.3),
        lower=dict(color='green', alpha=0.3)
    )
    plotinfo = dict(subplot=False)

    def __init__(self):
        self.lines.ma = bt.indicators.SMA(self.data, period=self.params.period)
        stddev = bt.indicators.StandardDeviation(self.data, period=self.params.period)
        self.lines.upper = self.lines.ma + self.params.devfactor * stddev
        self.lines.lower = self.lines.ma - self.params.devfactor * stddev

class PivotPointIndicator(bt.Indicator):
    """用于在图表上显示关键点的指标"""
    lines = ('pivots',)
    plotinfo = dict(plot=True, subplot=False)
    
    plotlines = dict(
        pivots=dict(marker='*', markersize=8, color='black', fillstyle='full',
                   ls='')  # ls='' 使其只显示标记点，不显示连线
    )
    
    def __init__(self):
        super(PivotPointIndicator, self).__init__()
        # 添加数据源关联
        self.data = self.data0  # 确保使用相同的数据源
        self.plotinfo.plotmaster = self.data0  # 确保绘图对齐

    def next(self):
        # 默认值设为NaN
        self.lines.pivots[0] = float('nan')

class HigherLowStrategy(bt.Strategy):
    params = (
        ('n_period', 40),          # 布林带周期
        ('std_multiplier', 2.0),   # 布林带标准差倍数
        ('min_gap', 10),          # 高低点最小间隔
        ('wait_bars', 3),         # 等待确认的K线数
        ('bounce_thresh', 0.005),   # 回调确认阈值(0.5%)
        ('stop_loss', 0.02),      # 止损比例(1%)
        ('trailing_stop', 0.01),   # 移动止损比例(0.5%)
        ('fast_period', 5),    # 快速均线周期
        ('slow_period', 15),    # 慢速均线周期
        ('trend_period', 40),   # 趋势均线周期
        ('trend_thresh', 0),    # 趋势判断阈值
        ('atr_period', 40),     # ATR周期
        ('atr_thresh', 30),    # ATR阈值（百分比）
    )

    def __init__(self):
        # 基础数据
        self.dataclose = self.datas[0].close
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low
          # 技术指标
        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.params.fast_period)
        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.params.slow_period)
        self.trend_ma = bt.indicators.SMA(self.data.close, period=self.params.trend_period)
        
        # 交叉信号
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
        
        # 趋势判断
        self.trend_slope = (self.trend_ma - self.trend_ma(-1)) / self.trend_ma(-1) * 100
        
        # ATR
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_period)
        # 订单和位置管理
        self.order = None
        self.buyprice = None
        self.stoplose = None
        self.highest_price = 0
        
        # 使用自定义布林带指标
        self.boll = BollingerBands(self.data, 
                                  period=self.params.n_period,
                                  devfactor=self.params.std_multiplier)
        
        # 修改关键点存储变量
        self.current_high = None  # 当前正在形成的高点
        self.current_low = None   # 当前正在形成的低点
        self.confirmed_high = None  # 最后确认的高点
        self.confirmed_low = None   # 最后确认的低点
        self.pivot_points_high = []  # 确认的高点列表
        self.pivot_points_low = []   # 确认的低点列表
        self.pivot_len=None
        # 状态标记
        self.in_high_search = False  # 是否在寻找高点
        self.in_low_search = False   # 是否在寻找低点
        
        # 显示标记
        self.show_pivot = False
        self.pivot_price = None
        self.pivot_indicator = PivotPointIndicator()
        self.potential_entry = None  # 潜在入场点
    def log(self, txt, dt=None):
        # 精确到分钟
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f'{dt.strftime("%Y-%m-%d %H:%M")}, {txt}')

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY执行, 价格: {order.executed.price:.4f}, 数量: {order.executed.size:.3f}')
                self.buyprice = order.executed.price
                self.highest_price = self.buyprice
            elif order.issell() or order.isclose():
                self.log(f'SELL执行, 价格: {order.executed.price:.4f}, 数量: {order.executed.size:.3f}')
                self.reset_trade_vars()

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('订单取消/保证金不足/拒绝')

        self.order = None

    def is_higher_low(self, current_low):
        """判断是否形成更高的低点"""
        if not self.last_low:
            return False
        return current_low > self.last_low['price']

    def check_bounce(self):
        """检查是否出现足够的回调"""
        if not self.potential_entry:
            return False
        current_price = self.dataclose[0]
        entry_price = self.potential_entry['price']
        bounce = (current_price - entry_price) / entry_price
        return bounce > self.params.bounce_thresh

    def is_valid_pattern(self):
        """检查是否形成有效的交易模式"""
        if (len(self.pivot_points_high) < 1 or 
            len(self.pivot_points_low) < 2):
            return False
            
        last_high = self.pivot_points_high[-1]
        last_low = self.pivot_points_low[-1]
        prev_low = self.pivot_points_low[-2]
        
        # 检查高点和低点的顺序是否正确
        if last_high['index'] < prev_low['index']:
            return False
        
        # 检查价格关系
        return (last_low['price'] > prev_low['price'] and
                last_high['price'] > (self.confirmed_high['price'] if self.confirmed_high else 0))

    def reset_trade_vars(self):
        """重置交易相关变量"""
        self.current_high = None
        self.current_low = None
        self.in_high_search = False
        self.in_low_search = False
        # 补充重置，防止旧状态影响后续逻辑
        self.potential_entry = None
        self.buyprice = None
        self.stoplose = None
        self.highest_price = 0
        self.show_pivot = False
        self.pivot_price = None

    def next(self):
        # 如果有未完成订单，避免重复下单
        if self.order:
            return
        
        # 重置显示标记
        self.show_pivot = False
        self.pivot_price = None
        
        # 处理订单和持仓（仅在有多头仓位时考虑止损/移动止损）
        if self.position and self.position.size > 0:
            # 更新最高价
            if self.dataclose[0] > self.highest_price:
                self.highest_price = self.dataclose[0]
                
            # 移动止损检查
            trailing_stop = self.highest_price * (1 - self.params.trailing_stop)
            if self.dataclose[0] < trailing_stop:
                self.log(f'移动止损触发, 价格: {self.dataclose[0]:.4f}')
                self.order = self.close()  # 只平掉当前多头，不做反手
                return
               
            # 固定止损检查
            if self.stoplose is not None and self.dataclose[0] < self.stoplose:
                self.log(f'止损触发, 价格: {self.dataclose[0]:.4f}')
                self.order = self.close()  # 只平掉当前多头
                return
        
        # 识别关键点和更新状态
        if self.datahigh[0] > self.boll.upper[0]:
            # 向上突破布林带，开始寻找高点
            if not self.in_high_search:
                # 如果之前在寻找低点，确认低点
                if self.in_low_search and self.current_low is not None:
                    self.confirmed_low = {
                        'price': self.current_low,
                        'index': len(self)-1,
                        'type': 'low'
                    }
                    self.pivot_points_low.append(self.confirmed_low)
                    self.show_pivot = True
                    self.pivot_price = self.confirmed_low['price']
                    self.log(f'确认低点: {self.confirmed_low["price"]:.4f}')
                
                self.in_high_search = True
                self.in_low_search = False
                self.current_high = self.datahigh[0]
            else:
                # 更新当前高点
                if self.datahigh[0] > self.current_high:
                    self.current_high = self.datahigh[0]
                    self.pivot_len = len(self)
                # else:
                #     #当前价格是否回落0.01
                #     if self.datahigh[0] < self.current_high * (1 - self.params.bounce_thresh):
                #         self.log(f'高点回落超过阈值, 价格: {self.datahigh[0]:.4f}')
                #         if self.dataclose[0]<self.pivot_points_high[-1]['price']:
                #                 self.order =self.close()
        elif self.datalow[0] < self.boll.lower[0]:
            # 向下突破布林带，开始寻找低点
            if not self.in_low_search:
                # 如果之前在寻找高点，确认高点
                if self.in_high_search and self.current_high is not None:
                    self.confirmed_high = {
                        'price': self.current_high,
                        'index': len(self)-1,
                        'type': 'high'
                    }
                    self.pivot_points_high.append(self.confirmed_high)
                    self.show_pivot = True
                    self.pivot_price = self.confirmed_high['price']
                    self.log(f'确认高点: {self.confirmed_high["price"]:.5f}')
                
                self.in_low_search = True
                self.in_high_search = False
                self.current_low = self.datalow[0]
            else:
                # 更新当前低点
                if self.datalow[0] < self.current_low:
                    self.current_low = self.datalow[0]
                    self.pivot_len = len(self)
                # else:
                #     #当前价格是否回升0.01
                #     if self.datalow[0] > self.current_low * (1 + self.params.bounce_thresh):
                #         self.log(f'低点回升超过阈值, 价格: {self.datalow[0]:.4f}')
                #         if self.dataclose[0]>self.pivot_points_low[-1]['price']:
                #                 self.order =self.close()
        # 检查是否形成有效的更高低点模式
        if (len(self.pivot_points_high) >= 2 and 
            len(self.pivot_points_low) >= 2):
            last_high = self.pivot_points_high[-1]
            last_low = self.pivot_points_low[-1]
            prev_low = self.pivot_points_low[-2]
            prev_high = self.pivot_points_high[-2]
            # if self.datalow[0] < self.boll.lower[0]:
            #     print('当前价格低于布林带下轨')
            # if self.datalow[0] < prev_high['price']:
            #     print('当前价格低于上一个高点')
            if last_low['price'] > prev_low['price'] and self.datalow[0] < self.boll.ma[0] and self.dataclose[0]>prev_low['price']:
                self.potential_entry = last_low
                self.wait_count = self.params.wait_bars
                self.log(f'发现更高低点模式: 低点价格: {last_low["price"]:.4f}')
            
        
        # 入场逻辑（仅在空仓时买入，且避免多次下单）
        if self.potential_entry and not self.position and self.datalow[0] < self.boll.lower[0] and self.dataclose[0]>self.potential_entry['price']:
            if self.wait_count > 0:
                self.wait_count -= 1
            elif self.check_bounce():
                size = self.broker.getcash() * 0.5 / self.dataclose[0]
                if size > 0:
                    self.stoplose = self.potential_entry['price']
                    self.log(f'买入信号触发, 价格: {self.dataclose[0]:.4f}, 止损: {self.stoplose:.4f}')
                    self.order = self.buy(size=size)
        # 更新图表显示
        if self.show_pivot and self.pivot_price is not None:
            self.pivot_indicator.lines.pivots[0] = self.pivot_price
        else:
            self.pivot_indicator.lines.pivots[0] = float('nan')

def run_backtest(csv_file):
    cerebro = bt.Cerebro()
    
    # 添加策略
    cerebro.addstrategy(HigherLowStrategy)
    
    # 读取数据
    df = pd.read_csv(csv_file)
    df['datetime'] = pd.to_datetime(df['datetime'])
    data = bt.feeds.PandasData(
        dataname=df,
        datetime='datetime',
        open='open',
        high='high',
        low='low',
        close='close',
        volume='vol',
        openinterest=None
    )
    
    cerebro.adddata(data)
    
    # 设置初始资金
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.broker.set_slippage_perc(0.001)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Minutes)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    
    print('初始资金: %.2f' % cerebro.broker.getvalue())
    results = cerebro.run()
    strat = results[0]
    
    # 打印回测结果
    print('最终资金: %.2f' % cerebro.broker.getvalue())
    print('收益率: %.2f%%' % ((cerebro.broker.getvalue() / 100000.0 - 1.0) * 100))
    print('最大回撤: %.2f%%' % strat.analyzers.drawdown.get_analysis().max.drawdown)
    if strat.analyzers.sharpe.get_analysis()['sharperatio'] is not None:
        print('夏普比率:', strat.analyzers.sharpe.get_analysis()['sharperatio'])
    else:
        print('夏普比率:0')
    
    # 修改绘图部分
    fig = cerebro.plot(style='candlestick',
                      volume=True,
                      plotdist=0.1,  # 增加图表间距
                      barup='red',   # 上涨蜡烛图颜色
                      bardown='green',  # 下跌蜡烛图颜色
                      )[0][0]
    
   

def run_combined_backtest():
    """合并所有1分钟数据并进行回测"""
    import os
    from pathlib import Path
    import matplotlib.pyplot as plt
    
    # 设置数据路径
    data_path = Path('data/doge1m')
    all_data = []
    
    print("正在读取数据文件...")
    # 获取所有CSV文件并排序
    files = sorted([f for f in os.listdir(data_path) if f.endswith('.csv')])
    
    for file in files:
        try:
            df = pd.read_csv(data_path / file)
            all_data.append(df)
            print(f"已读取: {file}")
        except Exception as e:
            print(f"处理{file}时出错: {str(e)}")
    
    if not all_data:
        print("未找到数据文件")
        return
    
    # 合并所有数据
    print("\n合并数据...")
    combined_df = pd.concat(all_data, ignore_index=True)
    combined_df['datetime'] = pd.to_datetime(combined_df['datetime'])
    combined_df = combined_df.sort_values('datetime').reset_index(drop=True)
    
    print(f"数据范围: {combined_df['datetime'].min()} 到 {combined_df['datetime'].max()}")
    print(f"总K线数: {len(combined_df)}")
    
    # 创建回测实例
    cerebro = bt.Cerebro()
    
    # 添加策略
    cerebro.addstrategy(HigherLowStrategy)   # 移动止损比例
    
    # 添加数据
    data = bt.feeds.PandasData(
        dataname=combined_df,
        datetime='datetime',
        open='open',
        high='high',
        low='low',
        close='close',
        volume='vol',
        openinterest=None
    )
    cerebro.adddata(data)
    
    # 设置初始资金和手续费
    initial_cash = 100000.0
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.broker.set_slippage_perc(0.001)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Minutes)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    
    # 运行回测
    print("\n开始回测...")
    results = cerebro.run()
    strat = results[0]
    # 修改绘图部分
    fig = cerebro.plot(style='candlestick',
                      volume=True,
                      plotdist=0.1,
                      barup='red',
                      bardown='green',
                      )[0][0]
    
    # 计算统计指标
    final_value = cerebro.broker.getvalue()
    total_return = (final_value - initial_cash) / initial_cash * 100
    drawdown = strat.analyzers.drawdown.get_analysis()
    trade_analysis = strat.analyzers.trades.get_analysis()
    
    # 打印回测结果
    print("\n====== 回测结果 ======")
    print(f"初始资金: {initial_cash:.2f}")
    print(f"最终资金: {final_value:.2f}")
    print(f"总收益率: {total_return:.2f}%")
    print(f"最大回撤: {drawdown.max.drawdown:.2f}%")
    print(f"最长回撤期: {drawdown.max.len}个bar")
    if strat.analyzers.sharpe.get_analysis()['sharperatio'] is not None:
        print('夏普比率:', strat.analyzers.sharpe.get_analysis()['sharperatio'])
    else:
        print('夏普比率:0')
    
    if hasattr(trade_analysis, 'total'):
        print("\n====== 交易统计 ======")
        print(f"总交易次数: {trade_analysis.total.total}")
        print(f"盈利交易: {trade_analysis.won.total}")
        print(f"亏损交易: {trade_analysis.lost.total}")
        if trade_analysis.total.total > 0:
            win_rate = trade_analysis.won.total / trade_analysis.total.total * 100
            print(f"胜率: {win_rate:.2f}%")
        if hasattr(trade_analysis.won, 'pnl'):
            print(f"平均盈利: {trade_analysis.won.pnl.average:.2f}")
        if hasattr(trade_analysis.lost, 'pnl'):
            print(f"平均亏损: {trade_analysis.lost.pnl.average:.2f}")
    
    
   

if __name__ == '__main__':
    # 选择运行模式
    run_single = False  # 设置为False以运行合并数据回测
    
    if run_single:
        # 单文件回测
        run_backtest('data\\doge1m\\DOGE-USDT-SWAP_20220428.csv')
    else:
        # 合并数据回测
        run_combined_backtest()
