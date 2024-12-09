import copy
import os, sys
import math
import numpy as np
from numpy.polynomial import Polynomial
from typing import List, Dict, Union
import copy

from Chan.Bi.Bi import CBi
from Chan.Bi.BiList import CBiList
from app.PA.PA_types import vertex
from app.PA.PA_Pattern_Chart import conv_type
from app.PA.PA_Liquidity import PA_Liquidity
from app.PA.PA_Volume_Profile import PA_Volume_Profile

# things that PA(Price Action) is lacking:
#   HFT market making,
#   statistical arbitrage,
#   gamma scalping,
#   volatility arbitrage,
#   systematic trading

DEBUG = False

# PA update flow(per batch klu): with callback functions
#   1. add new bi (vertex) (if exist)
#   2. add batch volume profile

# PA algos are afflicted under chan.bi, also updated with it
class PA_Core:
    # PA: Price Action
    
    # top/bot FX has type: loss/half/strict
    # for half/strict FX, weak FX will be overwrite by stronger FX in the same direction,
    # this is effectively a breakthrough from microstructure
    
    # Chart Patterns: using "loss" type FX is recommended
    # Trendlines:
    # Volume-Profiles:
    
    def __init__(self, bi_list:CBiList, shape_keys:List[str]):
        self.bi_list:CBiList = bi_list
        self.vertex_list:List[vertex] = []
        self.shape_keys = shape_keys
        self.init_PA_elements()
        self.bi_len:int = 0
        
        self.ts:float = 0
        self.cnt:int = 0
        
    #                     +-------------------------+
    #                     |    add virtual bi       |
    #                     v    (potential bi-break) |
    # [*] ----> [Virtual BI] ----------------> [Sure BI] -----> [Update End] --> [*]
    #            ^    ^   ^  del virtual bi                       |
    #            |    |   |  add sure bi                          |
    #            +----+   |         add virtual bi                |
    #     del virtual bi  |         (potential bi-break)          |
    #     add virtual bi  +---------------------------------------+
    
    # LOGIC:
    # A combined KLC is formed ->   try add virtual bi
    #                               else just update bi
    
    # a sure bi is fixed only after arrival of new virtual bi
    # because end of a sure bi can be updated
    
    # original: bi_list:         sure, sure, sure, sure, sure, sure, x
    # case 1:   bi_list:         sure, sure, sure, sure, sure, sure, x(updated,sure<->virtual)
    #                           |                            static | dynamic
    # case 2:   bi_list:(right)  sure, sure, sure, sure, sure, sure, sure, x
    #                           |                                  static | dynamic
    # case 3:   bi_list:(left)   sure, sure, sure, sure, sure, sure
    #                           |                            static | dynamic
    # note that in case 3, only virtual bi can potentially be removed(shift-left),
    # and is guaranteed not to trigger left-shift twice, so the last sure bi will remain static
    
    def parse_dynamic_bi_list(self):
        self.check_update_and_shift()
        # first feed new static bi to the static shapes
        if self.shift_l: # do nothing
            pass
        else:
            if self.shift_r: # get 1 more static bi
                new_static_bi = self.bi_list[-2]
                self.feed_bi_to_all_PA_elements(new_static_bi)
        # self.get_potential()
        
    def check_update_and_shift(self):
        bi_len = len(self.bi_list)
        self.shift_l = False
        self.shift_r = False
        if bi_len > self.bi_len and bi_len>1:
            self.shift_r = True
        elif bi_len < self.bi_len:
            self.shift_l = True
        self.bi_len = bi_len
        return
    
    def feed_bi_to_all_PA_elements(self, bi:CBi):
        end_x:int = bi.get_end_klu().idx
        end_y:float = bi.get_end_val()
        end_ts:float = bi.get_end_klu().time.ts
        self.end_open:float = bi.get_end_klu().open
        self.end_close:float = bi.get_end_klu().close
        self.end_volume:int = int(bi.get_end_klu().volume)
        end_bi_vertex = vertex(end_x, end_y, end_ts)
        if len(self.vertex_list) == 0:
            begin_x:int = bi.get_begin_klu().idx
            begin_y:float = bi.get_begin_val()
            begin_ts:float = bi.get_begin_klu().time.ts
            start_bi_vertex = vertex(begin_x, begin_y, begin_ts)
            self.vertex_list.append(start_bi_vertex)
            self.feed_vertex_to_all_PA_elements(start_bi_vertex)
        self.vertex_list.append(end_bi_vertex)
        self.feed_vertex_to_all_PA_elements(end_bi_vertex)
        
    def add_volume_profile(self, batch_volume_profile:List, type:str):
        price_mapped_volume:None|List[Union[List[float], List[int]]] = self.PA_Volume_Profile.update_volume_profile(batch_volume_profile, type)
        self.PA_Liquidity.add_volume_profile(price_mapped_volume)
        
    def init_PA_elements(self):
        # init shapes
        self.PA_Shapes_developed: Dict[str, List[conv_type]] = {}
        self.PA_Shapes_developing: Dict[str, List[conv_type]] = {}
        self.PA_Shapes_trading_now: Dict[str, List[conv_type]] = {}
        for key in self.shape_keys:
            self.PA_Shapes_developed[key] = []
            self.PA_Shapes_developing[key] = []
            
        self.PA_Liquidity: PA_Liquidity = PA_Liquidity()
        self.PA_Volume_Profile: PA_Volume_Profile = PA_Volume_Profile()
        
    def feed_vertex_to_all_PA_elements(self, vertex:vertex):
        if self.ts == vertex.ts: # this is just an ugly fix ([-2] may not be static)
            return
        self.add_vertex_to_shapes(vertex)
        self.add_vertex_to_liquidity(vertex, self.end_open, self.end_close)
        self.ts = vertex.ts
        
    def add_vertex_to_shapes(self, vertex:vertex):
        for shape_name in self.shape_keys:
            for shape in self.PA_Shapes_developing[shape_name][:]: # Use a slice to make a copy of the list so can remove item on-fly
                # Update existing shapes
                success = shape.add_vertex(vertex)
                if shape.is_complete():
                    self.PA_Shapes_developed[shape_name].append(shape)
                    self.PA_Shapes_developing[shape_name].remove(shape)
                    continue
                if DEBUG:
                    print(shape.name, shape.vertices, shape.state, success)
                if not success: # try add vertex and failed shape FSM check
                    self.PA_Shapes_developing[shape_name].remove(shape)
            if DEBUG:
                print('=================================================: ', vertex)
            # Start new potential shapes
            if shape_name == 'conv_type':
                self.PA_Shapes_developing[shape_name].append(conv_type(vertex))
                
    def add_vertex_to_liquidity(self, vertex:vertex, end_open:float, end_close:float):
        # liquidity zone should be formed at breakthrough, but for ease of computation
        # only update at FX formation
        self.PA_Liquidity.add_vertex(vertex, end_open, end_close)
        
    def get_potential(self):
        if not self.shift_l:
            # shift_r?: new_dynamic bi : updated_dynamic_bi
            # recalculate dynamic shapes if need for potential open position
            if self.bi_len > 0:
                dynamic_bi:CBi = self.bi_list[-1]
                self.cnt += 1
                end_x:int = dynamic_bi.get_end_klu().idx
                end_y:float = dynamic_bi.get_end_val()
                end_ts:float = dynamic_bi.get_end_klu().time.ts
                # end_open:float = dynamic_bi.get_end_klu().open
                # end_close:float = dynamic_bi.get_end_klu().close
                # end_volume:int = int(dynamic_bi.get_end_klu().volume)
                end_bi_vertex = vertex(end_x, end_y, end_ts)

                for shape_name in self.shape_keys:
                    self.PA_Shapes_trading_now[shape_name] = []
                    for shape in copy.deepcopy(self.PA_Shapes_developing[shape_name][:-1]):
                        success = shape.add_vertex(end_bi_vertex)
                        if success and shape.is_potential():
                            self.PA_Shapes_trading_now[shape_name].append(shape)
                return self.PA_Shapes_trading_now
        
    def get_chart_pattern_shapes(self, complete:bool=False, potential:bool=False, with_idx:bool=False):
        shapes:List[
            conv_type
            ] = []
        for shape_name in self.shape_keys:
            if complete:
                for shape in self.PA_Shapes_developed[shape_name]:
                    shapes.append(shape)
            if potential:
                shapes.extend(self.PA_Shapes_trading_now[shape_name])

                # if with_idx:
                #     shapes.append(shape.state)
        return shapes
    
    def get_liquidity_class(self) -> PA_Liquidity:
        return self.PA_Liquidity
    
    def get_volume_profile(self) -> PA_Volume_Profile:
        return self.PA_Volume_Profile
    