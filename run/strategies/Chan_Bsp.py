import numpy as np
import pandas as pd
import os, sys
from wtpy import BaseCtaStrategy
from wtpy import CtaContext

from Chan.Chan import CChan
from Chan.ChanConfig import CChanConfig
from Chan.Common.CEnum import DATA_SRC, KL_TYPE, AUTYPE, DATA_FIELD
from Chan.DataAPI.wtAPI import parse_time_column
from Chan.KLine.KLine_Unit import CKLine_Unit


def print_class_attributes_and_methods(obj):
    print(f"===================================================Class: {obj.__class__.__name__}")
    print("Attributes and Methods:")
    for attribute in dir(obj):
        # Filter out built-in attributes and methods (those starting with '__')
        if not attribute.startswith("__"):
            try:
                # Attempt to get the value of the attribute/method
                attr_value = getattr(obj, attribute)
                if callable(attr_value):
                    print(f"{attribute} (method) -> {attr_value}")
                else:
                    print(f"{attribute} (attribute) -> {attr_value}")
            except Exception as e:
                print(f"Could not access {attribute}: {e}")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
def stdio(str):
    print(str)
    return str

class Chan_bsp(BaseCtaStrategy):
    
    def __init__(self, name:str, code:str, barCnt:int, period:str, isForStk:bool = False, lv_list = [KL_TYPE.K_DAY]):
        BaseCtaStrategy.__init__(self, name)
        self.__period__ = period
        self.__bar_cnt__ = barCnt
        self.__code__ = code
        
        self.__is_stk__ = isForStk
        self.barnum = 0
        
        self.config = CChanConfig({
            "trigger_step": True,
        })
        self.chan = CChan(
            code=code,
            # begin_time=begin_time,
            # end_time=end_time,
            # data_src=data_src,
            lv_list=lv_list,
            config=self.config,
            # autype=AUTYPE.QFQ,
        )
        self.column_name = [
            DATA_FIELD.FIELD_TIME,
            DATA_FIELD.FIELD_OPEN,
            DATA_FIELD.FIELD_HIGH,
            DATA_FIELD.FIELD_LOW,
            DATA_FIELD.FIELD_CLOSE,
            DATA_FIELD.FIELD_VOLUME,
            # DATA_FIELD.FIELD_TURNOVER,
            # DATA_FIELD.FIELD_TURNRATE,
            ]  # 每一列字段
    
    def on_init(self, context:CtaContext):
        code = self.__code__    #品种代码
        if self.__is_stk__:
            code = code + "-"   # 如果是股票代码，后面加上一个+/-，+表示后复权，-表示前复权
            
        #这里演示了品种信息获取的接口
        #　pInfo = context.stra_get_comminfo(code)
        #　print(pInfo)
        
        context.stra_prepare_bars(code, self.__period__, self.__bar_cnt__, isMain = True)
        context.stra_sub_ticks(code)
        context.stra_log_text("Chan Initiated")
        
        #读取存储的数据
        self.xxx = context.user_load_data('xxx',1)
        
    def on_tick(self, context: CtaContext, stdCode: str, newTick: dict):
        # print(newTick)
        pass
    
    def on_bar(self,  context: CtaContext, stdCode: str, newTick: dict):
        self.barnum += 1
    
    def on_calculate(self, context:CtaContext):
        code = self.__code__    #品种代码
        
        theCode = code
        if self.__is_stk__:
            theCode = theCode + "-" # 如果是股票代码，后面加上一个+/-，+表示后复权，-表示前复权
        np_bars = context.stra_get_bars(theCode, self.__period__, self.__bar_cnt__, isMain = True)        
        open    = np_bars.opens[-1]
        high    = np_bars.highs[-1]
        low     = np_bars.lows[-1]
        close   = np_bars.closes[-1]
        volume  = np_bars.volumes[-1]
        bartime = np_bars.bartimes[-1]
        # date  = context.get_date()

        # ["time_key", "open", "high", "low", "close", "volume", "turnover"] # not include "turnover_rate"
        klu = CKLine_Unit(dict(zip(self.column_name, [
            parse_time_column(str(bartime)),
            open,
            high,
            low,
            close,
            volume,
        ])))
        
        self.chan.trigger_load({KL_TYPE.K_60M: [klu]})
        bsp_list = self.chan.get_bsp()
        if not bsp_list:
            return
        last_bsp = bsp_list[-1]
        print(last_bsp.type)
        print(last_bsp.is_buy)
        print(last_bsp.bi)
        print(last_bsp.klu.klc.idx)
        print('================================================')
        return
        # date = pd.to_datetime(str(context.get_date()), format="%Y%m%d").date