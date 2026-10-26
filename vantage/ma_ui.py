"""Native company-acquisition interface; uses the same transactional commands."""
import json
from .presentation import describe, label
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QTreeWidget,QTreeWidgetItem,QPlainTextEdit,QPushButton,QInputDialog,QMessageBox
class MAPanel(QWidget):
 def __init__(self,terminal,owned=False):
  super().__init__();self.terminal=terminal;self.owned=owned;self.world={};layout=QVBoxLayout(self);self.search=QLineEdit();self.search.setPlaceholderText('Search independent businesses by company, sector, country or sale status');self.search.textChanged.connect(self.filter);layout.addWidget(self.search);self.tree=QTreeWidget();self.tree.setHeaderLabels(['Company / sector / country','Equity value GBP','Cash / liabilities','Availability']);layout.addWidget(self.tree);self.details=QPlainTextEdit();self.details.setReadOnly(True);layout.addWidget(self.details);tools=QHBoxLayout()
  for index,(label,callback) in enumerate([('Inspect accounts',self.inspect),('Make acquisition offer',self.offer),('Review / progress offer',self.review),('Operating policy',self.operations),('Request exit quote',self.exit),('Enable buyer board',self.board)]):
   if index==3:layout.addLayout(tools);tools=QHBoxLayout()
   if owned and label in ('Make acquisition offer','Review / progress offer','Enable buyer board'):continue
   if not owned and label in ('Operating policy','Request exit quote'):continue
   b=QPushButton(label);b.clicked.connect(callback);tools.addWidget(b)
  layout.addLayout(tools)
 def refresh(self,w):
  self.world=w;self.filter()
 def filter(self):
  selected=self.selected();self.tree.clear();q=self.search.text().lower()
  for r in self.world.get('company_market',[]):
   if bool(r['controlled'])!=self.owned or r.get('public') and not self.owned:continue
   if q and q not in ' '.join(str(r[k]) for k in ('name','sector','location','availability')).lower():continue
   item=QTreeWidgetItem([r['name']+' / '+r['sector']+' / '+r['location'],f"£{float(r['equity_value']):,.2f}",f"£{float(r['cash']):,.2f} / £{float(r['liabilities']):,.2f}",r['availability']]);item.setData(0,Qt.ItemDataRole.UserRole,r['id']);self.tree.addTopLevelItem(item)
   if selected==r['id']:self.tree.setCurrentItem(item)
  if not self.world.get('company_market'):self.details.setPlainText('This existing world has no new-world independent corporate population. No companies or resources have been silently injected.')
 def selected(self):
  item=self.tree.currentItem();return item.data(0,Qt.ItemDataRole.UserRole) if item else None
 def display(self,result):self.details.setPlainText(describe(result,{k:v['name'] for k,v in self.world.get('entities',{}).items()}))
 def pick(self,title,ids):
  if not ids:return None
  choices=[id+' · '+self.world.get('entities',{}).get(id,{}).get('name',id) for id in ids];value,ok=QInputDialog.getItem(self,title,title,choices,0,False);return value.split(' · ')[0] if ok else None
 def buyer(self):return self.pick('Acquiring fund / company',[id for id,e in self.world.get('entities',{}).items() if e.get('controlled')])
 def inspect(self):
  if self.selected():self.terminal.send('ma_profile',{'entity':self.selected()},self.display)
 def board(self):
  buyer=self.buyer()
  if buyer and QMessageBox.question(self,'Independent governance','Enable level1 independent board controls at £500/month?')==QMessageBox.StandardButton.Yes:self.terminal.send('controls',{'entity':buyer,'level':1},self.display)
 def offer(self):
  id=self.selected()
  if not id:return
  buyer=self.buyer()
  if not buyer:return
  row=next(r for r in self.world['company_market'] if r['id']==id);seller=self.pick('Selling shareholder',list(row['owners']))
  if not seller:return
  percent,ok=QInputDialog.getDouble(self,'Stake','Percentage of the total company',100,.01,100,2)
  if not ok:return
  amount,ok=QInputDialog.getDouble(self,'Indicative offer','Cash consideration GBP',float(row['equity_value'])*percent/100*1.05,.01,1e15,2)
  if not ok:return
  debt,ok=QInputDialog.getDouble(self,'Acquisition debt','Optional unsecured debt GBP;100% stake only',0,0,amount-.01,2)
  if ok:self.terminal.send('ma_offer',{'entity':id,'buyer':buyer,'seller':seller,'percent':percent,'amount':amount,'debt':debt},self.display)
 def review(self):
  offers=[r for r in self.world.get('ma_offers',[]) if not self.selected() or r['entity']==self.selected()]
  if not offers:return
  choices=[r['id']+' · '+r['status']+' · '+str(r['amount']) for r in offers];choice,ok=QInputDialog.getItem(self,'Acquisition offers','Select persisted offer',choices,0,False)
  if not ok:return
  r=next(r for r in offers if r['id']==choice.split(' · ')[0]);self.display(r);action={'COUNTERED':'ma_negotiate','ACCEPTED':'ma_diligence','DILIGENCE':'ma_approve','SIGNED':'ma_close','EXIT_OFFER':'ma_exit_accept'}.get(r['status'])
  if action and QMessageBox.question(self,'Progress acquisition',{'ma_negotiate':'Accept seller counterprice '+r['counterprice']+'?', 'ma_diligence':'Pay diligence costs of0.1%, minimum£500 maximum£200k?', 'ma_approve':'Obtain existing corporate approvals and sign?', 'ma_close':'Close acquisition: actual cash, debt and ownership settle atomically?', 'ma_exit_accept':'Accept the funded exit offer and transfer the shares?'}[action])==QMessageBox.StandardButton.Yes:self.terminal.send(action,{'id':r['id']},self.display)
 def operations(self):
  id=self.selected()
  if not id:return
  options=['balanced','growth','efficiency','Set daily Growth investment budget','Appoint operational manager','Recruit stronger management','Fund expansion','Distribute eligible profits','Recruit operating team','Request customer proposal','Accept customer proposal'];choice,ok=QInputDialog.getItem(self,'Portfolio operations','Action',options,0,False)
  if not ok:return
  if choice in ('balanced','growth','efficiency'):self.terminal.send('ma_manage',{'entity':id,'strategy':choice},self.display)
  elif choice=='Set daily Growth investment budget':
   amount,ok=QInputDialog.getDouble(self,'Growth investment authority','Daily equipment budget / GBP; 0 disables',0,0,1e12,2)
   if ok:self.terminal.send('ma_manage',{'entity':id,'daily_investment_budget':str(amount)},self.display)
  elif choice=='Appoint operational manager':self.terminal.send('ma_manage',{'entity':id,'appoint_manager':True},self.display)
  elif choice=='Recruit stronger management':
   if QMessageBox.question(self,'Recruit management','Pay1% of annual payroll from company cash to recruit quality85 management?')==QMessageBox.StandardButton.Yes:self.terminal.send('ma_manage',{'entity':id,'management_quality':85},self.display)
  elif choice=='Recruit operating team':
   count,ok=QInputDialog.getInt(self,'Recruit operating team','Headcount; 8% of annual salary recruitment fee and ongoing payroll at current benchmark',1,1,100)
   if ok:self.terminal.send('company_operate',{'entity':id,'kind':'hire','count':count},self.display)
  elif choice=='Request customer proposal':self.terminal.send('company_operate',{'entity':id,'kind':'proposal'},self.display)
  elif choice=='Accept customer proposal':
   proposals=[c for r in self.world.get('company_market',[]) if r['id']==id for c in r.get('engagements',[]) if c['status']=='PROPOSED']
   selected,ok=QInputDialog.getItem(self,'Assign delivery team','Funded contract; staff are reserved and customer advance held in escrow',[c['id']+' · '+c['name']+' · £'+c['fee'] for c in proposals],0,False) if proposals else ('',False)
   if ok:self.terminal.send('company_operate',{'entity':id,'kind':'accept','contract':selected.split(' · ')[0]},self.display)
  else:
   amount,ok=QInputDialog.getDouble(self,'Actual company funds','Amount GBP',1000,.01,1e15,2)
   if ok:self.terminal.send('company_operate' if choice=='Fund expansion' else 'ma_dividend',{'entity':id,'amount':amount,'kind':'equipment'},self.display)
 def exit(self):
  id=self.selected()
  if not id:return
  owners=self.world['entities'][id]['owners'];seller=self.pick('Selling shareholder',list(owners))
  if not seller:return
  percent,ok=QInputDialog.getDouble(self,'Exit stake','Percentage of total company to sell',float(owners[seller])/float(self.world['entities'][id]['units'])*100,.01,100,2)
  if ok:self.terminal.send('ma_exit',{'entity':id,'seller':seller,'percent':percent},self.display)
