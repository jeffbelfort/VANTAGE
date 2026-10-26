"""Native accessible counterpart of the React corporate management workspace."""
import json
from .presentation import describe, label as human_label
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QTreeWidget,QTreeWidgetItem,QTabWidget,QPlainTextEdit,QPushButton,QInputDialog,QMessageBox,QTreeWidgetItemIterator

def pounds(v):return f'£{float(v):,.2f}' if v is not None else 'Unavailable'

def financial_value(value):
 # Metrics may include explanatory scope text as well as monetary strings.
 try:return pounds(value)
 except (ValueError,TypeError):return str(value)

class CorporatePanel(QWidget):
 def __init__(self,terminal):
  super().__init__();self.terminal=terminal;self.world=None;layout=QVBoxLayout(self)
  self.tree=QTreeWidget();self.tree.setHeaderLabels(['Company / relationship','Available cash','Net equity / NAV','Condition']);self.tree.setMinimumHeight(200);self.tree.itemSelectionChanged.connect(self.selection);layout.addWidget(self.tree)
  tools=QHBoxLayout();self.buttons={}
  for index,(label,callback) in enumerate([('Expand all',self.tree.expandAll),('Collapse all',self.tree.collapseAll),('Fund / lend',self.fund),('Review pending payment',self.approve_payment),('Repay claim',self.repay),('Propose loan terms',self.propose),('Decide proposal',self.decide),('Appoint administrator',self.admin),('Corporate lifecycle',self.lifecycle),('Review corporate actions',self.lifecycle_review),('Enable credit-fund investor units',self.register_credit_fund),('Group accounts',self.group_accounts),('Operating investment',self.operating_investment),('Enable company trading',self.enable_trading)]):
   if index in (4,8,12):layout.addLayout(tools);tools=QHBoxLayout()
   button=QPushButton(label);button.clicked.connect(callback);tools.addWidget(button);self.buttons[label]=button
  layout.addLayout(tools);self.tabs=QTabWidget();self.views={}
  for name in ['Overview','Financials','Ownership & governance','Transactions','Debt & creditors','Legal & history','Corporate actions']:
   view=QPlainTextEdit();view.setReadOnly(True);self.views[name]=view;self.tabs.addTab(view,name)
  layout.addWidget(self.tabs)
 def selected(self):
  items=self.tree.selectedItems();return items[0].data(0,Qt.ItemDataRole.UserRole) if items else None
 def refresh(self,world):
  if not world:return
  selected=self.selected() or self.terminal.active;expanded=set();iterator=QTreeWidgetItemIterator(self.tree)
  while iterator.value():
   item=iterator.value()
   if item.isExpanded():expanded.add(item.data(0,Qt.ItemDataRole.UserRole))
   iterator+=1
  self.world=world;self.tree.blockSignals(True);self.tree.clear();nodes={}
  for id,e in world.get('entities',{}).items():
   if not e.get('controlled'):continue
   c=world.get('corporate',{}).get(id,{});m=c.get('financials',world['metrics'].get(id,{}));item=QTreeWidgetItem([e['name']+' · '+c.get('relationship',e['kind'])+(' · investor NAV' if e['kind']=='fund' else ''),pounds(m.get('available_cash')),pounds(m.get('equity')),c.get('condition',e['status'])]);item.setData(0,Qt.ItemDataRole.UserRole,id);nodes[id]=item
  for id,item in nodes.items():
   e=world['entities'][id];parent=e.get('parent') or (world.get('corporate',{}).get(id,{}).get('management_entity') if e['kind']=='fund' else None);seen={id};ancestor=parent;cycle=False
   while ancestor in world['entities']:
    if ancestor in seen:cycle=True;break
    seen.add(ancestor);ancestor=world['entities'][ancestor].get('parent')
   if parent in nodes and not cycle:nodes[parent].addChild(item)
   else:self.tree.addTopLevelItem(item)
  for id,item in nodes.items():
   if id in expanded or selected==id:item.setExpanded(True)
  if selected in nodes:
   self.tree.setCurrentItem(nodes[selected]);parent=nodes[selected].parent()
   while parent:parent.setExpanded(True);parent=parent.parent()
  self.tree.resizeColumnToContents(0);self.tree.blockSignals(False);self.selection()
 def selection(self):
  id=self.selected()
  if not self.world or not id:return
  w=self.world;e=w['entities'][id];c=w.get('corporate',{}).get(id,{});f=c.get('financials',w['metrics'].get(id,{}));names=lambda account:w['entities'].get(account,{}).get('name',account)
  payable=[q for q in w['claims_book'] if q['debtor']==id and float(q['balance'])>0];restricted=c.get('restriction',{}).get('frozen',False)
  availability={'Enable company trading':id in w.get('private_businesses',{}) and e['status']=='ACTIVE' and not restricted,'Operating investment':e['kind']=='company' and e['status']=='ACTIVE' and not restricted,'Group accounts':True,'Enable credit-fund investor units':self.world.get('entity_capabilities',{}).get(id,{}).get('adopt_credit_fund_units',False),'Corporate lifecycle':e['kind'] in ('company','holding','credit_fund') and e['status']=='ACTIVE' and not restricted,'Review corporate actions':any(r['status']=='PENDING' and id in (r['terms'].get('entity'),r['terms'].get('seller'),r['terms'].get('buyer'),r['terms'].get('survivor')) for r in w.get('corporate_actions',[])),'Fund / lend':not restricted,'Review pending payment':not restricted and any(r['source']==id and r['status'] in ('AWAITING BOARD','INSUFFICIENT FUNDS') for r in w.get('related_transactions',[])),'Repay claim':not restricted and bool(payable),'Propose loan terms':not restricted and any(q['kind']=='INTERCOMPANY' and q['status'] in ('ACTIVE','OVERDUE') for q in payable),'Decide proposal':not restricted and any(r['status']=='PENDING' and id in (r['creditor'],r['debtor']) for r in w.get('corporate_proposals',[])),'Appoint administrator':e['kind']!='personal' and e['status']=='ACTIVE'}
  for label,enabled in availability.items():self.buttons[label].setEnabled(enabled);self.buttons[label].setToolTip('Subject to existing authority, restrictions and actual cash.' if enabled else 'Unavailable: active restrictions, no eligible pending obligation/instruction, or entity status.')
  self.views['Overview'].setPlainText(e['name']+'\n'+c.get('relationship','')+'\n'+c.get('condition',e['status'])+'\n\nAvailable cash '+pounds(f.get('available_cash'))+'\nTotal assets '+pounds(f.get('total_assets'))+'\nTotal liabilities '+pounds(f.get('total_liabilities'))+'\nNet equity / NAV '+pounds(f.get('equity'))+'\nRecovery payables '+pounds(f.get('recovery_payables'))+'\n\n'+describe(w.get('private_businesses',{}).get(id,{}).get('direction',{}))+'\n\n'+describe(c.get('recommendations',[]))+'\n\n'+c.get('note','Updated backend required for detailed projections.')+'\n\nActions remain subject to signatories, cash, board approval and restrictions. Insolvency does not erase claims.')
  self.views['Financials'].setPlainText('\n'.join(human_label(k)+': '+financial_value(v) for k,v in f.items() if isinstance(v,str))+'\n\nCumulative expenses:\n'+describe(w.get('statements',{}).get(id,{}).get('expenses',{}),{k:v['name'] for k,v in self.world.get('entities',{}).items()}))
  self.views['Ownership & governance'].setPlainText(describe({'ownership':c.get('owners'),'personal_beneficial_interest':c.get('beneficial'),'parent':e.get('parent'),'directors':e['directors'],'ceo':e.get('ceo'),'signatories':e['signatories'],'payment_limit':e['payment_limit']},{k:v['name'] for k,v in self.world.get('entities',{}).items()}))
  transactions=[r for r in w.get('related_transactions',[]) if id in (r['source'],r['destination'])]
  self.views['Transactions'].setPlainText('\n\n'.join(r['time']+' · '+r['id']+'\n'+names(r['source'])+' → '+names(r['destination'])+' · '+pounds(r['amount'])+'\n'+r['kind']+' · '+r['classification']+' · '+r['status']+'\nClaim '+r.get('claim','none')+'\n'+'; '.join(r['reasons']) for r in reversed(transactions)))
  self.views['Debt & creditors'].setPlainText(describe({'claims':[q for q in w['claims_book'] if id in (q['creditor'],q['debtor'])],'loans':[q for q in w['loans'] if q['account']==id],'proposals':[q for q in w.get('corporate_proposals',[]) if id in (q['creditor'],q['debtor'])]},{k:v['name'] for k,v in self.world.get('entities',{}).items()}))
  self.views['Corporate actions'].setPlainText(describe({'actions':[r for r in w.get('corporate_actions',[]) if id in (r['terms'].get('entity'),r['terms'].get('seller'),r['terms'].get('buyer'),r['terms'].get('survivor'))],'distributions':[r for r in w.get('corporate_distributions',[]) if r['entity']==id]},{k:v['name'] for k,v in self.world.get('entities',{}).items()}))
  self.views['Legal & history'].setPlainText(describe({'restriction':c.get('restriction'),'cases':[q for q in w.get('legal_cases',[]) if q['entity']==id],'administrations':[q for q in w.get('administrations',[]) if q['entity']==id],'recent_audit':[q for q in w.get('audit',[]) if id in json.dumps(q['detail'])]},{k:v['name'] for k,v in self.world.get('entities',{}).items()}))
 def pick_claim(self,commercial=False):
  rows=[q for q in self.world['claims_book'] if q['debtor']==self.selected() and float(q['balance'])>0 and (not commercial or q['kind']=='INTERCOMPANY')]
  choice,ok=QInputDialog.getItem(self,'Choose obligation','Claim; recovery obligations cannot be privately restructured',[q['id']+' · '+q['kind']+' · '+pounds(q['balance']) for q in rows],0,False) if rows else ('',False)
  return next((q for q in rows if choice.startswith(q['id'])),None) if ok else None
 def approve_payment(self):
  rows=[r for r in self.world.get('related_transactions',[]) if r['source']==self.selected() and r['status'] in ('AWAITING BOARD','INSUFFICIENT FUNDS')]
  if not rows:return
  choice,ok=QInputDialog.getItem(self,'Existing payment approval','Pending source instruction; independent board authority still required',[r['id']+' · '+r['kind']+' · '+pounds(r['amount']) for r in rows],0,False)
  if not ok:return
  r=next(r for r in rows if r['id']==choice.split(' · ')[0]);e=self.world['entities'][self.selected()];personal=e['kind']=='personal' and not e['controls'] and 'board' not in e['directors'];reviewer='board'
  if not personal:
   eligible=[d for d in e['directors'] if d!=r['actor'] and 'govern' in e['signatories'].get(d,[])]
   if not eligible:QMessageBox.information(self,'Board authority','Appoint an authorised independent director or fund governance controls in Oversight.');return
   reviewer,ok=QInputDialog.getItem(self,'Independent approval','Authorised director',eligible,0,False)
   if not ok:return
  self.terminal.send('related_approve',{'id':r['id'],'reviewer':reviewer})
 def repay(self):
  q=self.pick_claim()
  if not q:return
  amount,ok=QInputDialog.getDouble(self,'Repay creditor','Actual debtor cash GBP',float(q['balance']),.01,float(q['balance']),2)
  if ok:self.terminal.send('claim_repay',{'id':q['id'],'amount':str(amount)})
 def propose(self):
  q=self.pick_claim(True)
  if not q:return
  months,ok=QInputDialog.getInt(self,'Credit amendment','Months from creditor acceptance',12,1,360)
  if not ok:return
  rate,ok=QInputDialog.getDouble(self,'Credit amendment','Proposed APR',float(q['rate']),0,100,2)
  if not ok:return
  upfront,ok=QInputDialog.getDouble(self,'Credit amendment','Upfront actual payment on acceptance',0,0,float(q['balance']),2)
  if ok:self.terminal.send('corporate_proposal',{'claim':q['id'],'months':months,'rate':str(rate),'upfront':str(upfront)})
 def decide(self):
  rows=[r for r in self.world.get('corporate_proposals',[]) if r['status']=='PENDING' and self.selected() in (r['creditor'],r['debtor'])]
  if not rows:return
  choice,ok=QInputDialog.getItem(self,'Creditor decision','Pending proposal',[r['id'] for r in rows],0,False)
  if ok:self.terminal.send('corporate_decision',{'id':choice,'accept':QMessageBox.question(self,'Creditor approval','Approve subject to creditor authority, restrictions and viability checks?')==QMessageBox.StandardButton.Yes})
 def fund(self):
  if not self.selected():return
  sources=[id for id,e in self.world['entities'].items() if e.get('controlled') and id!=self.selected()];choice,ok=QInputDialog.getItem(self,'Capital source','Funding account',[id+' · '+self.world['entities'][id]['name'] for id in sources],0,False)
  if not ok:return
  source=choice.split(' · ')[0];kind,ok=QInputDialog.getItem(self,'Capital classification','Equity requires direct parent; loans retain creditor claims',['equity','loan'],0,False)
  if not ok:return
  amount,ok=QInputDialog.getDouble(self,'Funding','GBP; above-limit instructions require existing board review',1000,.01,1e15,2)
  if not ok:return
  rate=0;months=12
  if kind=='loan':
   rate,ok=QInputDialog.getDouble(self,'Loan','APR',5,0,100,2)
   if not ok:return
   months,ok=QInputDialog.getInt(self,'Loan','Months',12,1,360)
  if ok:self.terminal.send('related',{'source':source,'destination':self.selected(),'kind':kind,'amount':str(amount),'rate':str(rate),'months':months,'disclosed':True})
 def admin(self):
  if self.selected() and QMessageBox.question(self,'Administration','Suspend ordinary management and appoint administrator? Debts and cases remain; assets realise through actual liquidity.')==QMessageBox.StandardButton.Yes:self.terminal.send('administration',{'entity':self.selected()})

 def lifecycle(self):
  id=self.selected()
  if not id:return
  labels={'Acquire / sell shares; reorganise ownership':'sale','Merge into corporate parent':'merger','Convert commercial debt to equity':'swap','Voluntary liquidation':'liquidation','Declare dividend':'dividend','Return paid-in capital':'capital_return'}
  choice,ok=QInputDialog.getItem(self,'Corporate lifecycle','Action',list(labels),0,False)
  if not ok:return
  kind=labels[choice];p={'kind':kind,'entity':id};e=self.world['entities'][id]
  def account(title,options):
   selected,accepted=QInputDialog.getItem(self,title,title,[a+' · '+self.world['entities'][a]['name'] for a in options],0,False) if options else ('',False)
   return selected.split(' · ')[0] if accepted else None
  if kind=='sale':
   p['seller']=account('Selling shareholder',list(e['owners']));p['buyer']=account('Funded buyer',[a for a,x in self.world['entities'].items() if x.get('controlled') and a not in (id,p['seller'])])
   if not p['seller'] or not p['buyer']:return
   percent,ok=QInputDialog.getDouble(self,'Shares','Percent of all company shares',100,.000001,100,6)
   if not ok:return
   p['percent']=str(percent)
  if kind=='merger':
   p['survivor']=account('Corporate successor',[a for a,x in self.world['entities'].items() if x['kind'] in ('company','holding','credit_fund') and a!=id])
   if not p['survivor']:return
  if kind=='swap':
   claim=self.pick_claim(True)
   if not claim:return
   p['claim']=claim['id'];valuation,ok=QInputDialog.getDouble(self,'Share valuation','Agreed pre-money equity value GBP',1000,.01,1e15,2)
   if not ok:return
   p['valuation']=str(valuation)
  if kind not in ('merger','liquidation'):
   amount,ok=QInputDialog.getDouble(self,'Financial terms','Cash price/distribution or debt face conversion amount GBP',1000,.01,1e15,2)
   if not ok:return
   p['amount']=str(amount)
  def reviewed(preview):
   text=describe(preview,{k:v['name'] for k,v in self.world.get('entities',{}).items()})
   box=QMessageBox(self);box.setWindowTitle('Corporate consequence preview');box.setText(preview['kind']+' · '+self.world['entities'][preview['terms']['entity']]['name']);box.setInformativeText('Cash '+pounds(preview['financials']['cash'])+' · liabilities '+pounds(preview['financials']['debt'])+' · equity '+pounds(preview['financials']['equity'])+'\n'+describe(preview['details'],{k:v['name'] for k,v in self.world.get('entities',{}).items()})+'\nNo funds move until a separately approved action completes. Required approvals and ownership are in Details.');box.setDetailedText(text);box.setStandardButtons(QMessageBox.StandardButton.Ok|QMessageBox.StandardButton.Cancel)
   if box.exec()==QMessageBox.StandardButton.Ok:self.terminal.send('lifecycle_propose',preview['terms'])
  self.terminal.send('lifecycle_preview',p,callback=reviewed)
 def lifecycle_review(self):
  id=self.selected();rows=[r for r in self.world.get('corporate_actions',[]) if r['status']=='PENDING' and id in (r['terms'].get('entity'),r['terms'].get('seller'),r['terms'].get('buyer'),r['terms'].get('survivor'))]
  choice,ok=QInputDialog.getItem(self,'Corporate action review','Pending action',[r['id']+' · '+r['kind'] for r in rows],0,False) if rows else ('',False)
  if not ok:return
  r=next(r for r in rows if choice.startswith(r['id']));choices=['Record required approvals','Complete approved action','Withdraw proposal']+(['Negotiate purchase price'] if r['kind']=='sale' else [])
  action,ok=QInputDialog.getItem(self,'Corporate action review','Choose a separate approval or settlement action',choices,0,False)
  if not ok:return
  if action=='Negotiate purchase price':
   amount,ok=QInputDialog.getDouble(self,'Counteroffer','New GBP price; earlier approvals will be cleared',float(r['terms']['amount']),.01,1e15,2)
   if ok:self.terminal.send('lifecycle_counteroffer',{'id':r['id'],'amount':str(amount)})
  elif QMessageBox.question(self,'Confirm corporate instruction',action+'? All current authority, ownership, cash and restriction checks still apply. Review the Corporate actions tab for the financial preview.')==QMessageBox.StandardButton.Yes:
   command={'Record required approvals':'lifecycle_approve','Complete approved action':'lifecycle_execute','Withdraw proposal':'lifecycle_cancel'}[action];self.terminal.send(command,{'id':r['id']})

 def register_credit_fund(self):
  id=self.selected()
  if id and QMessageBox.question(self,'Credit fund unit registration','Existing equity owners become unit holders. Cash, positions, debts and investigations remain; only investment basis is reclassified. Enable investor subscriptions?')==QMessageBox.StandardButton.Yes:self.terminal.send('fund_register',{'entity':id})

 def group_accounts(self):
  if not self.selected():return
  def display(result):self.views['Financials'].setPlainText(describe(result,{k:v['name'] for k,v in self.world.get('entities',{}).items()}));self.tabs.setCurrentWidget(self.views['Financials'])
  self.terminal.send('consolidated_statement',{'entity':self.selected()},callback=display)
 def operating_investment(self):
  if not self.selected():return
  sector,ok=QInputDialog.getItem(self,'Operating business','Sector',['services','manufacturing','technology'],0,False)
  if not ok:return
  capital,ok=QInputDialog.getDouble(self,'Productive capital','GBP; actual cash procurement, staffing and ongoing costs apply',100000,.01,1e15,2)
  if ok and QMessageBox.question(self,'Confirm productive investment','Invest actual company cash? Operating income depends on productive capacity, real employees and finite customer demand; losses are possible.')==QMessageBox.StandardButton.Yes:self.terminal.send('business_start',{'entity':self.selected(),'sector':sector,'capital':str(capital)})

 def enable_trading(self):
  id=self.selected()
  if id:self.terminal.send('ma_manage',{'entity':id,'appoint_manager':True})
