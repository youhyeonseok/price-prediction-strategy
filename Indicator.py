import pandas_ta as pta, pandas as pd, numpy as np

class DataManage:
    def __init__(self,data,parameter = [
        {"rsi" : {"period" : 14}},
        {"ma" : {"period" : 7}},
        {"ma" : {"period" : 25}},
        {"ema" :{"period" : 7}},
        {"ema" :{"period" : 25}},
        {"stochastic" : {"n" : 14,"m" : 5,"t" : 5}},
        {"bb" : {"length" : 21,"std" : 2}},
        {"kdj" : {}},
        {"macd" : {"fast_period": 12, "slow_period" : 26}}
        ],target_data = "close"):

        self.data = data
        self.parameter = parameter
        self.target_data = target_data
        fuction_list = {
            "rsi" : "self.rsi()",
            "ma" : "self.ma()",
            "ema" : "self.add_ema()",
            "stochastic" : "self.stochastic()",
            "bb" : "self.bb()",
            "kdj" : "self.kdj()",
            "macd" : "self.macd()",
            "disparity" : "self.disparity()",
        }
        
        for line in parameter:
            for indicator in line.keys():
                eval("self." + indicator + "("+"line[indicator]"+")")
    def rsi(self,parameter):
        rsi = pta.rsi(self.data[self.target_data], length=parameter["period"])
        self.data.loc[:, 'rsi'+'_'+str(parameter["period"])] = rsi
        
    def ma(self,parameter):
        self.data['mean'+'_'+str(parameter["period"])] = self.data[self.target_data].rolling(window=parameter["period"]).mean()

    def ema(self,parameter):
        array = self.data[self.target_data]
        ema = pta.ma("ema", pd.Series(array.astype(float)), length=int(parameter["period"]))
        self.data['ema'+'_'+str(parameter["period"])] = ema

    def stochastic(self,parameter):
        ndays_high = self.data.high.rolling(window = parameter["n"],min_periods = 1).max()
        ndays_low = self.data.low.rolling(window = parameter["n"],min_periods = 1).min()
        fast_k = ((self.data.close - ndays_low) / (ndays_high - ndays_low)) * 100
        slow_k = fast_k.ewm(span=parameter["t"]).mean()
        slow_d = slow_k.ewm(span=parameter["t"]).mean()

        self.data = self.data.assign(fast_k = fast_k, fast_d = slow_k, slow_k = slow_k, slow_d = slow_d)

    def bb(self,parameter):
        currunt_upper_bollinger_band = pta.bbands(self.data["close"], length = parameter["length"], std = parameter["std"])

        self.data = self.data.assign(BBL = currunt_upper_bollinger_band['BBL_'+str(parameter["length"])+'_2.0'],BBM = currunt_upper_bollinger_band['BBL_'+str(parameter["length"])+'_2.0'],
        BBU = currunt_upper_bollinger_band['BBL_'+str(parameter["length"])+'_2.0'],BBP = currunt_upper_bollinger_band['BBL_'+str(parameter["length"])+'_2.0'])

    def kdj(self,high=None, low=None, close=None, length=None, signal=None, offset=None):
        temp = pta.kdj(high=self.data.high,low=self.data.low,close=self.data.close)
        self.data = pd.concat([self.data,temp],axis=1)
        
    def macd(self,parameter):

        temp = pta.macd(
            self.data.close,
            fast=int(parameter["fast_period"]),
            slow=int(parameter["slow_period"]),
            signal=9,
        )
        self.datga = pd.concat([self.data,temp],axis=1)

    def disparity(self,parameter):
        # 종가기준으로 이동평균선 값을 구함
        ma = self.data["close"].rolling(parameter["period"]).mean()

        # 시가가 이평선 기준으로 얼마나 위에 있는지 구함
        self.data['disparity'] = 100*(self.data["open"]/ma)
        
    def get_data(self):
        return self.data.dropna()