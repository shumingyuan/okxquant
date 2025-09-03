import backtrader as bt
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

class LinearRegressionStrategy(bt.Strategy):
    params = (
        ('window', 260),           # 回归窗口
        ('slope_thresh', 0.2),    # 斜率阈值
        ('stop_loss', 0.05),      # 5%止损
        ('trailing_stop', 0.01),   # 2%移动止损
        ('break_even', 0.01),      # 1%保本线
    )

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.order = None
        self.buyprice = None
        self.buycomm = None
        
        # 用于存储趋势状态
        self.trends = []
        self.slopes = []
        self.current_trend = 0
        
        # 止损相关变量
        self.stop_price = None
        self.highest_price = 0
        self.break_even_triggered = False

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print('%s, %s' % (dt.isoformat(), txt))

    def detect_trend(self):
        if len(self) < self.params.window:
            return 0
        
        prices = np.array([self.dataclose.get(i, size=1)[0] 
                          for i in range(-self.params.window+1, 1)])
        x = np.arange(self.params.window).reshape(-1, 1)
        y = prices.reshape(-1, 1)
        
        lr = LinearRegression().fit(x, y)
        slope = lr.coef_[0][0]
        
        if slope > self.params.slope_thresh:
            return 1
        elif slope < -self.params.slope_thresh:
            return -1
        return 0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.buyprice = order.executed.price
                self.highest_price = self.buyprice
                self.stop_price = self.buyprice * (1 - self.params.stop_loss)
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}')
                
            elif order.issell():
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}')
                self.break_even_triggered = False
                self.highest_price = 0
                self.stop_price = None

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')
            
        self.order = None

    def next(self):
        if self.order:
            return
            
        self.current_trend = self.detect_trend()
        self.log(f'Close: {self.dataclose[0]:.2f}, Trend: {self.current_trend}')
        
        if self.position:
            # 更新移动止损
            if self.dataclose[0] > self.highest_price:
                self.highest_price = self.dataclose[0]
                if self.dataclose[0] > self.stop_price:
                    trailing_stop = self.highest_price * (1 - self.params.trailing_stop)
                    if self.dataclose[0] < trailing_stop:
                        self.log(f'SELL CREATE (TRAILING STOP), Price: {self.dataclose[0]:.2f}')
                        self.order = self.sell(size=self.position.size)
            
            # 止损
            if self.dataclose[0] < self.stop_price:
                self.log(f'SELL CREATE (STOP LOSS), Price: {self.dataclose[0]:.2f}')
                self.order = self.sell(size=self.position.size)
            
            # 趋势反转卖出
            elif self.current_trend < 0:
                self.log(f'SELL CREATE (TREND REVERSAL), Price: {self.dataclose[0]:.2f}')
                self.order = self.sell(size=self.position.size)
                
        else:
            if self.current_trend > 0:  # 上升趋势买入
                size = 0.5  # 使用固定仓位
                self.log(f'BUY CREATE, Price: {self.dataclose[0]:.2f}, Size: {size:.3f}')
                self.order = self.buy(size=size)

def run_backtest(csv_file):
    cerebro = bt.Cerebro()
    
    # 添加策略
    cerebro.addstrategy(LinearRegressionStrategy)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe',
                       riskfreerate=0.02,
                       annualize=True)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade_analyzer')
    
    # 读取数据
    df = pd.read_csv(csv_file, parse_dates=['datetime'])
    df = df.sort_values('datetime')
    
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
    
    # 设置初始资金和手续费
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.broker.set_slippage_perc(0.001)
    
    print('初始资金: %.2f' % cerebro.broker.getvalue())
    
    results = cerebro.run()
    strat = results[0]
    
    # 打印回测结果
    portfolio_value = cerebro.broker.getvalue()
    print('最终资金: %.2f' % portfolio_value)
    print(f'收益率: {((portfolio_value - 100000.0) / 100000.0 * 100):.2f}%')
    
    # 打印回撤和夏普比率
    drawdown = strat.analyzers.drawdown.get_analysis()
    print(f'最大回撤: {drawdown.max.drawdown:.2f}%')
    print(f'最长回撤期: {drawdown.max.len}天')
    sharpe = strat.analyzers.sharpe.get_analysis()
    print(f'夏普比率: {sharpe["sharperatio"]:.3f}')
    
    cerebro.plot(style='candlestick', volume=True)

if __name__ == "__main__":
    run_backtest('btc_history_3year.csv')
