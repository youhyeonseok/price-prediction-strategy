import pandas as pd
import numpy as np
from tqdm import tqdm
class Labeling:
    def __init__(self, data, term):
        self.data = data
        self.term = term
        self.labeled = []
    def run(self):
        """
        기준
            0 :  -30% ~ -50%
            1 : -10% ~ -30% 
            2 : -10% ~ +10%
            3 : +10% ~ 30%
            4 : +30% ~ 50% 
        """
        temp = []
        print("get data term mean...")
        for i in tqdm(range(len(self.data) - self.term)):
            curr_price = self.data.iloc[i]["close"]
            term_price = self.data.iloc[i + self.term]["close"]

            diff = (term_price - curr_price) / curr_price * 100
            temp.append(diff)
            
        means = np.mean(temp)
            
        very_low = means * -4
        low = means * -2
        middle = means
        high = means * 2
        very_high = means * 4
        
        print("data Labeling...")
        for i in tqdm(range(0, len(self.data) - self.term)):
            curr_diff = self.data.iloc[i + self.term]["close"] - self.data.iloc[i]["close"]
            persent = int(round(curr_diff/self.data.iloc[i]["close"] * 100, 0))

            if persent <= very_low:
                self.labeled.append(0)

            elif persent > very_low and persent <= low:
                self.labeled.append(1)

            elif persent > low and persent <= high:
                self.labeled.append(2)

            elif persent > high and persent <= very_high:
                self.labeled.append(3)

            elif persent > very_high:
                self.labeled.append(4)
        
        return self.labeled