import backtrader as bt
import pandas as pd

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

class MASlope(bt.Indicator):
    lines = ('slope',)
    params = (('period', 25),)
    
    def __init__(self):
        self.ma = bt.indicators.SMA(self.data, period=self.p.period)
        self.lines.slope = bt.indicators.ROC(self.ma, period=1)

class ImprovedStrategy(bt.Strategy):
    params = (
        ('ma_long',20),
        ('ma_mid', 5),
        ('ma_short', 1),
        ('slope_thresh', 0.002),  # 斜率阈值
        ('atr_period', 14),
        ('atr_thresh', 0.0),    # ATR倍数阈值
        ('volume_thresh', 0.2),  # 成交量百分位阈值
    )
    
    def __init__(self):
        # 均线和斜率
        self.ma_long = MASlope(period=self.p.ma_long)
        self.ma_mid = bt.indicators.SMA(self.data, period=self.p.ma_mid)
        self.ma_short = bt.indicators.SMA(self.data, period=self.p.ma_short)
        
        # 交叉信号
        self.crossover = bt.indicators.CrossOver(self.ma_short, self.ma_mid)
        
        # ATR和成交量过滤器
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.volume_ma = bt.indicators.SMA(self.data.volume, period=20)
        
        # 记录上一次的MA值用于计算斜率
        self.last_ma = None
        
        # 用于跟踪订单
        self.order = None

    def next(self):
        if self.order:
            return
        
        # 检查成交量是否足够
        if self.data.volume[0] < self.volume_ma[0] * self.p.volume_thresh:
            return
            
        # 检查波动是否正常
        if self.atr[0] > self.data.close[0] * self.p.atr_thresh / 100:
            return
        
        # 判断趋势（通过25H MA的斜率）
        is_uptrend = self.ma_long.slope[0] > self.p.slope_thresh
        
        if is_uptrend:
            if not self.position:  # 没有持仓
                if self.crossover > 0:  # 金叉
                    self.order = self.buy(size=0.5)
            else:  # 已有持仓
                if self.crossover < 0:  # 死叉
                    self.order = self.sell(size=self.position.size)
        else:  # 下跌趋势
            if self.position:  # 有持仓就平仓
                self.order = self.sell(size=self.position.size)

def run_backtest(csv_file, title):
    df = pd.read_csv(csv_file, parse_dates=['datetime'])
    df = df.sort_values('datetime')
    cerebro = bt.Cerebro()
    data = PandasData(dataname=df)
    cerebro.adddata(data)
    cerebro.addstrategy(ImprovedStrategy)
    cerebro.broker.set_cash(10000)
    print(f"初始资金: {cerebro.broker.getvalue():.2f}")
    cerebro.run()
    print(f"回测后资金: {cerebro.broker.getvalue():.2f}")
    cerebro.plot(style='candlestick', volume=True, title=title)

if __name__ == "__main__":
    run_backtest('btc_history_3year.csv', 'BTC 回测')
    # run_backtest('doge_history.csv', 'DOGE 回测')
