# region imports
from AlgorithmImports import *
# endregion
from datetime import timedelta

class MarriedPut3(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2017, 1, 1)  # Set Start Date
        self.SetEndDate(2020, 7, 1)
        self.SetCash(100_000)  # Set Strategy Cash
        
        self.equity = self.AddEquity("MCD", Resolution.Minute)
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.symbol = self.equity.Symbol

        self.rank = 0
        self.contract = str()
        self.contracts = []
        self.contractsAdded = set()

        self.DaysBeforeExp = 2 # number of days before expiry to exit
        self.DTE = 25 # target days till expiration
        self.OTM = 0.01 # target percentage OTM of put
        self.lookbackIV = 25 # lookback length of IV indicator
        self.IVlvl = 0.5 # enter position at this lvl of IV indicator
        self.percentage = 0.7 # percentage of portfolio for underlying asset
        self.options_alloc = 12 # 1 option for X num of shares (balanced would be 100)

        self.Schedule.On(self.DateRules.EveryDay(self.symbol), \
                        self.TimeRules.AfterMarketOpen(self.symbol, 30), \
                        self.Plotting)
        self.SetWarmUp(timedelta(self.lookbackIV)) 

    def VIXRank(self):
        history = self.History(self.symbol, self.lookbackIV, Resolution.Daily)
        # (Current - Min) / (Max - Min)
        self.rank = ((history["high"][-1] - history["low"][-1]) / (max(history["high"]) - min(history["low"])))


    def OnData(self, data: Slice):
        if(self.IsWarmingUp):
            return
        
        if not self.Portfolio[self.symbol].Invested:
            self.SetHoldings(self.symbol, self.percentage)
        
        # buy put if VIX relatively high
        self.VIXRank()

        if self.rank > self.IVlvl:
            self.BuyPut(data)
        
        # close put before it expires
        if self.contracts != []:
            closed = False
            for c in self.contracts:
                if (c.ID.Date - self.Time) <= timedelta(self.DaysBeforeExp):
                    self.Liquidate(c)
                    self.Log("Closed: too close to expiration")
                    closed = True
            if (closed):
                self.contracts = []

    def BuyPut(self, data):
        # get option data
        if self.contracts == []:
            self.contracts = self.OptionsFilter(data)
            return
        
        # if not invested and option data added successfully, buy option
        for c in self.contracts:
            if not self.Portfolio[c].Invested and data.ContainsKey(c):
                self.Buy(c, round(self.Portfolio[self.symbol].Quantity / self.options_alloc))

    def OptionsFilter(self, data):
        ''' OptionChainProvider gets a list of option contracts for an underlying symbol at requested date.
            Then you can manually filter the contract list returned by GetOptionContractList.
            The manual filtering will be limited to the information included in the Symbol
            (strike, expiration, type, style) and/or prices from a History call '''

        contracts = self.OptionChainProvider.GetOptionContractList(self.symbol, data.Time)
        self.underlyingPrice = self.Securities[self.symbol].Price

        # filter the out-of-money put options from the contract list which expire close to self.DTE num of days from now
        otm_puts = [i for i in contracts if i.ID.OptionRight == OptionRight.Put and
                                            self.underlyingPrice - i.ID.StrikePrice > self.OTM * self.underlyingPrice and
                                            self.DTE - 8 < (i.ID.Date - data.Time).days < self.DTE + 8]
        recontracts = []
        if len(otm_puts) > 0:
            # sort options by closest to self.DTE days from now and desired strike, and pick first
            contract = sorted(sorted(otm_puts, key = lambda x: abs((x.ID.Date - self.Time).days - self.DTE)),
                                                     key = lambda x: self.underlyingPrice - x.ID.StrikePrice)[0]
            if contract not in self.contractsAdded:
                self.contractsAdded.add(contract)
                # use AddOptionContract() to subscribe the data for specified contract
                self.AddOptionContract(contract, Resolution.Minute)
            recontracts.append(contract)
        
        if len(recontracts) != 1:
            recontracts = []
        return recontracts 

    def Plotting(self):
        # plot IV indicator
        self.Plot("Vol Chart", "Rank", self.rank)
        # plot indicator entry level
        self.Plot("Vol Chart", "lvl", self.IVlvl)
        # plot underlying's price
        self.Plot("Data Chart", self.symbol, self.Securities[self.symbol].Close)
        # plot strike of put option
        
        option_invested = [x.Key for x in self.Portfolio if x.Value.Invested and x.Value.Type==SecurityType.Option]
        if option_invested:
                self.Plot("Data Chart", "strike", option_invested[0].ID.StrikePrice)

    def OnOrderEvent(self, orderEvent):
        # log order events
        self.Log(str(orderEvent))