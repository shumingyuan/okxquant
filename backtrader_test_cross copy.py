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
        ('stop_loss', 0.05),      # 5%止损
        ('trailing_stop', 0.02),   # 2%移动止损
        ('break_even', 0.01),      # 1%保本线
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
        
        # 初始化止损和移动止损相关变量
        self.stop_loss_order = None      # 止损订单
        self.trailing_stop_order = None  # 移动止损订单
        self.highest_price = 0           # 跟踪最高价
        self.break_even_triggered = False  # 保本标志
        self.order = None
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
                self.highest_price = self.buyprice
                # # 设置止损
                self.stop_price = self.buyprice * (1 - self.params.stop_loss)
                # self.stop_loss_order = self.sell(exectype=bt.Order.Stop,
                #                                price=self.stop_price,
                #                                size=self.position.size)
                # self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
                # self.log(f'STOP LOSS SET AT: {self.stop_price:.2f}')
                self.bar_executed = len(self)
                
            elif order.issell():
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
                self.bar_executed = None
                # 清除所有止损订单
                self.stop_loss_order = None
                self.trailing_stop_order = None
                self.break_even_triggered = False
                self.highest_price = 0

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')
        self.order = None  # 重置订单状态    
       

    def next(self):
        self.log('Close, %.2f' % self.dataclose[0])
        self.log(f'Trend Slope: {self.trend_slope[0]:.2f}%')
        self.log(f'ATR: {self.atr[0]:.2f},  atr_thresh:{self.dataclose[0] * self.params.atr_thresh / 100:.2f}')
        # 
        if self.order:
            return

        # 检查波动率是否过大
        if self.atr[0] > self.dataclose[0] * self.params.atr_thresh / 100:
            return
            
        # 当前持有仓位时的逻辑
        if self.position:
            self.log(f'持仓中, 当前价格: {self.dataclose[0]:.2f}, 持仓成本: {self.buyprice:.2f}, 最高价: {self.highest_price:.2f}')
            trailing_stop = self.highest_price * (1 - self.params.trailing_stop)
            # 更新移动止损
            if self.dataclose[0] > self.highest_price:
                self.highest_price = self.dataclose[0]
                
                # 只在未止损时向上时更新移动止损
                if self.dataclose[0] > self.stop_price:
                    # 止损
                    if  self.dataclose[0] < self.buyprice * (1 - self.params.trailing_stop):                        
                        self.sell(exectype=bt.Order.Stop,
                                  price=trailing_stop,
                                  size=self.position.size)
                        
                        self.log(f'BREAK EVEN STOP SET AT: {self.buyprice:.2f}')
                    
                    
                    
            
            # 死叉时取消所有止损订单并平仓
            if self.crossover < 0:
                if self.stop_loss_order:
                    self.cancel(self.stop_loss_order)
                if self.trailing_stop_order:
                    self.cancel(self.trailing_stop_order)
                size = self.position.size
                self.log(f'SELL CREATE (CROSS), Price: {self.dataclose[0]:.2f}, Size: {size:.3f}')
                self.order = self.sell(size=size)

        # 没有持仓时的逻辑
        else:
            # 检查是否满足做多条件
            if (self.crossover > 0 and  # 金叉
                self.trend_slope > self.params.trend_thresh):  # 上升趋势
                
                # 修改计算购买数量的逻辑
                cash = self.broker.getcash()
                price = self.dataclose[0]
                # 使用现金的50%进行交易，并考虑手续费
                size =  0.5
               
                
                if size >= 0.001:  # 确保交易量大于最小限制
                    self.log(f'BUY CREATE, Price: {price:.2f}, Size: {size:.3f}, Cash: {cash:.2f}')
                    self.order = self.buy(size=size)
                else:
                    self.log(f'资金不足或数量太小，无法下单. Cash: {cash:.2f}, Size: {size:.3f}')
                    


if __name__ == '__main__':
    cerebro = bt.Cerebro()
    
    # 添加策略
    cerebro.addstrategy(DualMAStrategy,
                   fast_period=10,
                   slow_period=90,
                   trend_period=90,
                   trend_thresh=0.02,
                   atr_thresh=0.75,
                   stop_loss=0.05,      # 5%止损
                   trailing_stop=0.02,   # 2%移动止损
                   break_even=0.01)      # 1%保本
    
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
    df = pd.read_csv('btc_history_3year.csv', parse_dates=['datetime'])
    df = df.sort_values('datetime')

    # 创建数据源
    data = PandasData(dataname=df)

    cerebro.adddata(data)
    # 设置交易规则
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.001)  # 0.1%手续费
    cerebro.broker.set_slippage_perc(0.001)        # 0.1%滑点
    
    # 设置资金使用比例限制
    cerebro.addsizer(bt.sizers.PercentSizer, percents=50)

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

