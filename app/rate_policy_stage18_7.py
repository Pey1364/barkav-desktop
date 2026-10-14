"""Rate policy shared by active BARKAV 18.7.1 management views."""
from __future__ import annotations
from typing import Any
DEFAULT_RATE_BASIS_187='دلار و طلا'
RATE_BASIS_CHOICES_187=('دلار بروز','طلا بروز',DEFAULT_RATE_BASIS_187)
def _value(value:Any)->float:
    try:return float(str(value or '').replace(',','').replace('،','').strip() or 0)
    except (TypeError,ValueError):return 0.0
def rate_factor_187(usd_current:Any,gold_current:Any,usd_baseline:Any,gold_baseline:Any,basis:str=DEFAULT_RATE_BASIS_187)->float:
    u,g,ub,gb=(_value(x) for x in (usd_current,gold_current,usd_baseline,gold_baseline));selected=str(basis or DEFAULT_RATE_BASIS_187).strip()
    if selected=='دلار بروز':return u/ub if u>0 and ub>0 else 1.0
    if selected=='طلا بروز':return g/gb if g>0 and gb>0 else 1.0
    if u>0 and g>0 and ub>0 and gb>0:
        usd_factor=u/ub
        gold_factor=g/gb
        return (gold_factor+usd_factor)/2
    return 1.0
def updated_unit_price_187(estimate_rate:Any,usd_current:Any,gold_current:Any,usd_baseline:Any,gold_baseline:Any,basis:str=DEFAULT_RATE_BASIS_187)->int:
    return int(round(_value(estimate_rate)*rate_factor_187(usd_current,gold_current,usd_baseline,gold_baseline,basis)))
