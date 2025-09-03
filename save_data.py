import okx.MarketData as MarketData

flag = "0"  # 实盘:0 , 模拟盘：1

marketDataAPI =  MarketData.MarketAPI(flag=flag)

# 获取标记价格K线数据
result = marketDataAPI.get_mark_price_candlesticks(
    instId="BTC-USDT-SWAP"
)
print(result)