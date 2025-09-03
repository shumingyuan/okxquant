import okx.PublicData as PublicData
import pandas as pd
flag = "0"  # 实盘:0 , 模拟盘：1

publicDataAPI = PublicData.PublicAPI(flag=flag)

# 获取交易产品基础信息
result = publicDataAPI.get_instruments(
    instType="SWAP"
)
df=pd.DataFrame(result['data'])
df.to_csv('swap产品信息.csv')
print(result)