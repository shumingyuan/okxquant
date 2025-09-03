from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
import datetime  # For datetime objects
import os.path  # To manage paths
import sys  # To find out the script name (in argv[0])
import backtrader as bt
import pandas as pd
import matplotlib.pyplot as plt

class DualMAStrategy(bt.Strategy):
    params = (
        ('fast_period', 5),    # 快速均线周期
        ('slow_period', 15),    # 慢速均线周期
        ('trend_period', 40),   # 趋势均线周期
        ('trend_thresh', 0),    # 趋势判断阈值
        ('atr_period', 40),     # ATR周期
        ('atr_thresh', 30),    # ATR阈值（百分比）
    )

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print('%s, %s' % (dt.isoformat(), txt))

    def __init__(self):
        # 订单相关变量
        self.dataclose = self.datas[0].close
        self.order = None
        self.bar_executed = None
        self.buyprice = None
        self.buycomm = None
        
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

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
                self.bar_executed = len(self)
            elif order.issell():
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
                self.bar_executed = None  # 重置bar_executed

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')

        self.order = None

    def next(self):
        self.log('Close, %.2f' % self.dataclose[0])
        self.log(f'Trend Slope: {self.trend_slope[0]:.2f}%')
        if self.order:
            return

        # 如果有待处理订单，等待
        if self.order:
            return

        # 检查波动率是否过大
        if self.atr[0] >self.dataclose[0] * self.params.atr_thresh / 100:
            return
            
        if not self.position:  # 没有持仓
            # 检查是否满足做多条件：
            # 1. 金叉信号
            # 2. 上升趋势
            if (self.crossover > 0 and  # 金叉
                self.trend_slope >self.params.trend_thresh):
                self.log(f'prama: {self.params.trend_thresh:.2f}%')
                # 计算购买数量
                cash = self.broker.getcash()
                size = cash * 0.75 / self.dataclose[0]  # 使用95%的现金
                size = round(size, 3)  # 四舍五入到3位小数
                
                if size > 0.001:  # 确保交易量大于最小限制
                    self.log(f'BUY CREATE, Price: {self.dataclose[0]:.2f}, Size: {size:.3f}, Cash: {cash:.2f}')
                    self.log(f'Signal: Cross={self.crossover[0]:.2f}, Trend={self.trend_slope[0]:.2f}%')
                    self.order = self.buy(size=size)
                else:
                    self.log(f'资金不足或数量太小，无法下单. Cash: {cash:.2f}, Size: {size:.3f}')
                    
        else:  # 有持仓
            # 死叉或趋势转向下跌时卖出
            if (self.crossover < 0 ): 
                
                size = self.position.size
                self.log(f'SELL CREATE, Price: {self.dataclose[0]:.2f}, Size: {size:.3f}')
                self.log(f'Signal: Cross={self.crossover[0]:.2f}, Trend={self.trend_slope[0]:.2f}%')
                self.order = self.sell(size=size)


if __name__ == '__main__':
    cerebro = bt.Cerebro()
    
    # 添加策略
    cerebro.addstrategy(DualMAStrategy,
                       fast_period=10,
                       slow_period=50,
                       trend_period=100,
                       trend_thresh=0.03,
                       atr_thresh=0.6)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe',
                       riskfreerate=0.02,
                       annualize=True,
                       timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade_analyzer')


    class PandasData(bt.feeds.PandasData):
        params = (
            ('datetime', 'datetime'),
            ('open', 'open'),
            ('high', 'high'),
            ('low', 'low'),
            ('close', 'close'),
            ('volume', 'vol'),
            ('openinterest', None),
        )


    # 读取CSV文件
    df = pd.read_csv('data\\doge1m\\DOGE-USDT-SWAP_20220728.csv', parse_dates=['datetime'])
    df = df.sort_values('datetime')

    # 创建数据源
    data = PandasData(dataname=df)

    cerebro.adddata(data)
    cerebro.broker.setcash(100000.0)
    # 设置交易规则
    cerebro.broker.setcommission(commission=0.001)  # 设置0.1%的交易手续费
    cerebro.broker.set_slippage_perc(0.001)  # 设置0.1%的滑点
    cerebro.broker.set_slippage_fixed(1)  # 设置固定滑点
    
    print('Initial Portfolio Value: %.2f' % cerebro.broker.getvalue())

    # 运行回测
    results = cerebro.run()
    strat = results[0]
    
    # 打印回测结果
    portfolio_value = cerebro.broker.getvalue()
    print('最终资金: %.2f' % portfolio_value)
    print(f'收益率: {((portfolio_value - 100000.0) / 100000.0 * 100):.2f}%')
    drawdown = strat.analyzers.drawdown.get_analysis()
    print(f'最大回撤: {drawdown.max.drawdown:.2f}%')
    print(f'最长回撤期: {drawdown.max.len}天')
    
    # 打印夏普比率
    if strat.analyzers.sharpe.get_analysis().get('sharperatio') is None:
        print('夏普比率: 无法计算（可能是因为收益率为零或负数）')
    else:
        sharpe = strat.analyzers.sharpe.get_analysis()
        print(f'夏普比率: {sharpe["sharperatio"]:.3f}')
    
    # 绘制图表
    fig = cerebro.plot(style='candlestick',  # 使用K线图
                      volume=True,  # 显示成交量
                      width=20,     # 图表宽度
                      height=10,    # 图表高度
                      tight=True,   # 紧凑布局
                      barup='green',  # 上涨蜡烛颜色
                      bardown='red',  # 下跌蜡烛颜色
                      grid=True)    # 显示网格
    
    plt.show()
