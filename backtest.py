from tqdm import tqdm
class backtest:
    def __init__(self,data, result_label, test_size, set_amount, fee, max_buy):
        """
        data(DataFrame) : ex) Include close price

        result_label(list) : ex) [-1,0,0,1,-1,....] (-1,0,1)만 포함

        test_size(int) : ex) 1440 * 30

        set_amount(float) : ex) 0.02

        fee(float) : ex) fee == 0.08% -> 0.0008

        max_buy(int) : ex) 10000 
        """
        self.data = data # 주가 데이터
        self.result_label = result_label # 머신러닝의 예측값
        self.test_size = test_size # 테스트 데이터의 길이
        self.set_amount = set_amount # 한번 매수할 떄 수량
        self.fee = fee # 한번 거래 할 때 수수료
        self.max_buy = max_buy # 최대 누적 매수 횟수

        # 손절형 순환매매에서 사용하는 변수
        self.buy_flag = 0
        self.sell_flag = 0

        # 공통 사용 변수
        self.quantityBuying = 0 # 현재 매수 수량
        self.BuyingList = [] # 현재 매수 했던 가격들의 리스트
        self.totalYield = 0 # 최종 수익률
        self.totalNumberSales = 0 # 총 매도 횟수
        self.win = 0
        self.quantityBuyingList = [] # 매수 수량을 저장하는 리스트
        self.amount = 0 # 현재 가지고 있는 주식 수량
        self.MDDList = [] # MDD를 계산하기 위한 리스트
        self.average_price = 0 # 평단가
        
    def initializes(self):
        self.buy_flag = 0
        self.sell_flag = 0

        # 공통 사용 변수
        self.quantityBuying = 0
        self.BuyingList = []
        self.totalYield = 0
        self.totalNumberSales = 0
        self.win = 0
        self.quantityBuyingList = []
        self.amount = 0
        self.MDDList = []
        self.average_price = 0

    def SellInitializes(self,currYield):
        if currYield > 0:
            self.win += 1
        self.average_price = 0
        self.totalNumberSales += 1
        self.totalYield += currYield
        self.amount = 0
        self.BuyingList.clear()
        self.quantityBuying = 0
        self.buy_flag = 0
        self.sell_flag = 0
        

    def basicStrategy(self):
        x_test = self.data.iloc[-self.test_size:]
        x_test['label'] = self.result_label
        self.initializes()
        for i in tqdm(range(len(x_test))):
            
            if x_test.iloc[i]['label'] == 1 and self.quantityBuying < self.max_buy:
                self.quantityBuying += 1
                self.average_price = ( self.average_price * self.amount + x_test.iloc[i]['close'] * self.set_amount) / (self.amount + self.set_amount)
                self.amount += self.set_amount
                self.BuyingList.append(x_test.iloc[i]['close'])

            if x_test.iloc[i]['label'] == 0 and self.quantityBuying != 0:
                currYield = (x_test.iloc[i]['close']-self.average_price) * self.amount - (self.average_price * self.fee * self.amount)
                self.quantityBuyingList.append(self.quantityBuying)

                self.SellInitializes(currYield)

            if self.quantityBuying > 0:
                self.MDDList.append(round((sum(self.BuyingList)/self.quantityBuying-x_test.iloc[i]['close'])/x_test.iloc[i]['close'],2))
        self.quantityBuyingList.sort()
        self.MDDList.sort()
        
        if len(self.quantityBuyingList) == 0 or self.totalNumberSales == 0:
            print("Zero DivisionError")
            raise ZeroDivisionError
        return {
            "averageNumberSales" : sum(self.quantityBuyingList)/len(self.quantityBuyingList),
            "totalYield" : self.totalYield,
            "win_rate" : self.win/self.totalNumberSales,
            "MDD" : self.MDDList[-1],
            "max_buying" : self.quantityBuyingList[-1],
            "NumberTrading" : self.totalNumberSales
        }
    
    def WaitingStrategy(self, term = 5):
        x_test = self.data.iloc[-self.test_size:]
        x_test['label'] = self.result_label
        self.initializes()

        waiting = 0
        for i in tqdm(range(len(x_test))):
            
            if x_test.iloc[i]['label'] == 1 and self.quantityBuying < self.max_buy and waiting > term:
                self.quantityBuying += 1
                self.average_price = ( self.average_price * self.amount + x_test.iloc[i]['close'] * self.set_amount) / (self.amount + self.set_amount)
                self.amount += self.set_amount
                self.BuyingList.append(x_test.iloc[i]['close'])

            elif x_test.iloc[i]['label'] == 0 and self.quantityBuying != 0:
                currYield = (x_test.iloc[i]['close']-self.average_price) * self.amount - (self.average_price * self.fee * self.amount)
                self.quantityBuyingList.append(self.quantityBuying)

                self.SellInitializes(currYield)
                waiting = 0

            if x_test.iloc[i]["label"] == 1:
                waiting += 1

            if self.quantityBuying > 0:
                self.MDDList.append(round((sum(self.BuyingList)/self.quantityBuying-x_test.iloc[i]['close'])/x_test.iloc[i]['close'],2))
        self.quantityBuyingList.sort()
        self.MDDList.sort()
        
        if len(self.quantityBuyingList) == 0 or self.totalNumberSales == 0:
            print("Zero DivisionError")
            raise ZeroDivisionError
        return {
            "averageNumberSales" : sum(self.quantityBuyingList)/len(self.quantityBuyingList),
            "totalYield" : self.totalYield,
            "win_rate" : self.win/self.totalNumberSales,
            "MDD" : self.MDDList[-1],
            "max_buying" : self.quantityBuyingList[-1],
            "NumberTrading" : self.totalNumberSales
        }