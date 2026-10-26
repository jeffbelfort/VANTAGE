"""Human-readable read-only presentation; persistent identifiers remain unchanged."""
import re

LABELS={'var_scope':'Risk model coverage','treasury_dv01_gbp':'Treasury sensitivity per basis point (GBP)','equity_gross':'Equity and option gross exposure','net_asset_value':'Net asset value','personal_percent':'Your beneficial ownership (%)','manager':'Management company','unpaid':'Accrued unpaid wages','payroll_next':'Next payday (simulation hour)','capital_limit':'Per-security capital ceiling','set_time':'Set on','set_by':'Set by'}
def label(key):
 return LABELS.get(str(key),str(key).replace('_',' ').capitalize())
def describe(value,names=None,field='',depth=0):
 names=names or {};indent='  '*depth
 if isinstance(value,dict):
  return '\n'.join(indent+names.get(str(k),label(k))+': '+('\n'+describe(v,names,str(k),depth+1) if isinstance(v,(dict,list)) else describe(v,names,str(k))) for k,v in value.items()) or indent+'None recorded'
 if isinstance(value,list):return '\n'.join(indent+'• '+describe(v,names,field,depth+1).lstrip() for v in value) or indent+'None recorded'
 if value is None:return 'Not recorded'
 if isinstance(value,bool):return 'Yes' if value else 'No'
 text=str(value)
 if text in names:return names[text]
 if re.fullmatch(r'-?\d+(\.\d+)?',text) and re.search('cash|salary|amount|equity|asset|liabilities|budget|paid|debt|nav|revenue|profit|fees|capital|reserve|balance',field,re.I):return f'£{float(text):,.2f}'
 return text.replace('_',' ') if text.isupper() else text
