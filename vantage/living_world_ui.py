"""Native access to the same living-world actions as the React workspace."""
import json
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QComboBox,QPushButton,QDoubleSpinBox,QPlainTextEdit,QLabel,QInputDialog

class LivingWorldPanel(QWidget):
 def __init__(self,terminal):
  super().__init__();self.terminal=terminal;self.world=None;layout=QVBoxLayout(self)
  layout.addWidget(QLabel('Financial Crime — confidential access, funded programmes and persistent evidence'))
  self.owner=QComboBox();layout.addWidget(self.owner);self.contact=QComboBox();layout.addWidget(self.contact)
  self.offer=QDoubleSpinBox();self.offer.setRange(1000,100000);self.offer.setPrefix('£');layout.addWidget(self.offer)
  b=QPushButton('Approach selected insider');b.clicked.connect(lambda:self.terminal.send('insider_approach',{'account':self.owner.currentData(),'contact':self.contact.currentData(),'amount':str(self.offer.value())}));layout.addWidget(b)
  b=QPushButton('Open fixed-return programme for selected company');b.clicked.connect(self.open_programme);layout.addWidget(b)
  self.programme=QComboBox();layout.addWidget(self.programme);self.investor=QComboBox();layout.addWidget(self.investor)
  b=QPushButton('Solicit investor allocation');b.clicked.connect(self.subscribe);layout.addWidget(b)
  b=QPushButton('Queue full investor withdrawal');b.clicked.connect(lambda:self.terminal.send('programme_redeem',{'programme':self.programme.currentData(),'investor':self.investor.currentData()}));layout.addWidget(b)
  b=QPushButton('Suspend selected programme');b.clicked.connect(lambda:self.terminal.send('programme_resolution',{'programme':self.programme.currentData(),'kind':'suspend'}));layout.addWidget(b)
  b=QPushButton('Suspend withdrawals for 72 hours');b.clicked.connect(lambda:self.terminal.send('programme_resolution',{'programme':self.programme.currentData(),'kind':'suspend_withdrawals'}));layout.addWidget(b)
  b=QPushButton('Begin programme creditor recovery');b.clicked.connect(self.recover);layout.addWidget(b)
  self.case=QComboBox();layout.addWidget(self.case);b=QPushButton('Request settlement offer');b.clicked.connect(lambda:self.terminal.send('case_settlement',{'case':self.case.currentData()}));layout.addWidget(b);b=QPushButton('Accept and pay settlement');b.clicked.connect(self.settle);layout.addWidget(b)
  self.statement=QComboBox();layout.addWidget(self.statement);b=QPushButton('Correct selected investor statement');b.clicked.connect(lambda:self.terminal.send('statement_correct',{'statement':self.statement.currentData()}));layout.addWidget(b)
  self.details=QPlainTextEdit();self.details.setReadOnly(True);layout.addWidget(self.details,1)
 def open_programme(self):
  if not self.owner.currentData():return
  rate,ok=QInputDialog.getDouble(self,'Fixed-return programme','Annual promised return / percent; company bears real liabilities',30,0,200,2)
  if ok:self.terminal.send('programme_create',{'entity':self.owner.currentData(),'annual_return':str(rate)})
 def subscribe(self):
  if not self.programme.currentData():return
  amount,ok=QInputDialog.getDouble(self,'Investor allocation','GBP; maximum 10% of finite investor cash; weekly review',10000,.01,1e10,2)
  if ok:self.terminal.send('programme_subscribe',{'programme':self.programme.currentData(),'investor':self.investor.currentData(),'amount':str(amount)})
 def recover(self):
  from PyQt6.QtWidgets import QMessageBox
  if self.programme.currentData() and QMessageBox.question(self,'Company administration','Appoint an administrator for this company and all programmes? Real assets fund recovery, staff contracts end with wage claims preserved, and unpaid investor claims survive.')==QMessageBox.StandardButton.Yes:self.terminal.send('programme_resolution',{'programme':self.programme.currentData(),'kind':'liquidate'})
 def settle(self):
  from PyQt6.QtWidgets import QMessageBox
  if self.case.currentData() and QMessageBox.question(self,'Pay settlement','Pay the recorded offer, or any already-assessed penalty, from actual cash? Creditor recovery obligations remain.')==QMessageBox.StandardButton.Yes:self.terminal.send('case_settlement',{'case':self.case.currentData(),'accept':True})
 def populate(self,combo,items):
  old=combo.currentData();combo.blockSignals(True);combo.clear()
  for title,id in items:combo.addItem(title,id)
  i=combo.findData(old)
  if i>=0:combo.setCurrentIndex(i)
  combo.blockSignals(False)
 def refresh(self,w):
  if not w:return
  self.world=w;self.populate(self.case,[(c['id']+' · '+c['stage'],c['id']) for c in w['legal_cases'] if c['stage'] in ('FORMAL INVESTIGATION','ENFORCEMENT','CIVIL RECOVERY','PROSECUTION REFERRAL')]);self.populate(self.statement,[(a['entity']+' · '+a['status'],a['statement']) for a in w.get('statement_audits',[])]);self.populate(self.owner,[(e['name'],e['id']) for e in w['entities'].values() if e['controlled']]);self.populate(self.contact,[(f"{c['name']} · {c['symbol']} · {c['role']} · access {c['access']} / reliability {c['reliability']}",c['id']) for c in w.get('insiders',[])]);self.populate(self.programme,[(v['name']+' · '+v['entity'],v['id']) for v in w.get('investment_programmes',[])]);self.populate(self.investor,[(n['name'],n['id']) for n in w['npcs']]);self.details.setPlainText(json.dumps({'intelligence':w.get('intelligence',[])[-30:],'programmes':w.get('investment_programmes',[]),'reputation':w.get('personal_reputation',{}),'cases':w.get('legal_cases',[]),'audits':w.get('statement_audits',[])},indent=2))
