"""Bounded model depth shared by displayed ladders and actual executions."""
from decimal import Decimal as D

def depth(ins,tick):
 total=int(ins['liquidity']);used=int(D(ins.get('liquidity_used','0'))) if ins.get('liquidity_tick')==tick else 0;out=[];price=D(ins['price']);quantum=D(ins.get('tick_size','.01'))
 for level in range(5):
  start=total*level//5;end=total*(level+1)//5;qty=max(0,end-max(start,used));spread=D('.0005')+D('.0004')*level
  out.append(dict(qty=qty,bid=str(max(quantum,(price*(1-spread)).quantize(quantum))),ask=str((price*(1+spread)).quantize(quantum))))
 return out

def execute_depth(ins,tick,requested,buy,limit=None):
 qty=D(0);consideration=D(0)
 for row in depth(ins,tick):
  price=D(row['ask' if buy else 'bid'])
  if limit is not None and ((buy and price>limit) or (not buy and price<limit)):break
  take=min(requested-qty,D(row['qty']));qty+=take;consideration+=take*price
  if qty>=requested:break
 return qty,consideration/qty if qty else D(0)
