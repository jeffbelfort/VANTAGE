"""Native Qt employee workspace backed by the same transactional API as React."""
import json
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QComboBox,QPushButton,QDoubleSpinBox,QSpinBox,QPlainTextEdit,QMessageBox,QLabel,QInputDialog
from .employees import ROLES

class EmployeePanel(QWidget):
 def __init__(self,terminal):
  super().__init__();self.terminal=terminal;self.world=None;layout=QVBoxLayout(self)
  self.workforce=QLabel();self.workforce.setWordWrap(True);layout.addWidget(self.workforce)
  self.employer=QComboBox();layout.addWidget(QLabel('Legal employer — permissions apply only to this institution'));layout.addWidget(self.employer);self.employer.currentIndexChanged.connect(lambda:self.refresh(self.world))
  form=QFormLayout();self.role=QComboBox()
  for id,role in ROLES.items():self.role.addItem(role[0],id)
  form.addRow('Role',self.role);self.candidate=QComboBox();form.addRow('Candidate',self.candidate);self.salary=QDoubleSpinBox();self.salary.setRange(4000,1000000);self.salary.setValue(4000);self.salary.setPrefix('£');form.addRow('Monthly salary offer',self.salary);layout.addLayout(form)
  row=QHBoxLayout();layout.addLayout(row)
  def button(text,callback,parent=row):
   b=QPushButton(text);b.clicked.connect(callback);parent.addWidget(b);return b
  self.find_button=button('Find candidates',lambda:self.send('recruit',{'entity':self.employer.currentData(),'role':self.role.currentData()}))
  self.offer_button=button('Make salary offer',self.offer);self.hire_button=button('Hire accepted candidate',self.hire)
  self.candidate.currentIndexChanged.connect(self.select_candidate)
  b=QPushButton('Set / stop selected analyst weekly research');b.clicked.connect(self.research_mandate);layout.addWidget(b)
  self.employee=QComboBox();layout.addWidget(self.employee);self.employee.currentIndexChanged.connect(self.select_employee)
  self.details=QLabel('Recruit an employee to begin.');self.details.setWordWrap(True);layout.addWidget(self.details)
  form=QFormLayout();self.pay=QDoubleSpinBox();self.pay.setRange(4000,1000000);form.addRow('Contract monthly salary',self.pay);self.manager=QComboBox();form.addRow('Reports to',self.manager);layout.addLayout(form)
  row=QHBoxLayout();layout.addLayout(row)
  button('Change salary',lambda:self.change('salary',{'salary':str(self.pay.value())},True));button('Promote',lambda:self.change('promote',{'salary':str(self.pay.value())},True));button('Set manager',lambda:self.change('manager',{'manager':self.manager.currentData()}));button('Pay outstanding wages',lambda:self.change('pay'));button('Assign role review',lambda:self.send('employee_task',{'employee':self.employee.currentData(),'kind':'review'}));button('Dismiss with notice pay',lambda:self.change('dismiss',{},True))
  form=QFormLayout();self.per=QDoubleSpinBox();self.per.setRange(0,1e9);self.per.setValue(1000);self.daily=QDoubleSpinBox();self.daily.setRange(0,1e9);self.daily.setValue(5000);form.addRow('Delegated per-order limit / GBP',self.per);form.addRow('Delegated daily limit / GBP',self.daily);layout.addLayout(form)
  row=QHBoxLayout();layout.addLayout(row);button('Authorise bounded trading',lambda:self.change('delegate',{'trade':True,'per_order':str(self.per.value()),'daily':str(self.daily.value())},True));button('Revoke trading authority',lambda:self.change('delegate',{'trade':False,'per_order':0,'daily':0}))
  form=QFormLayout();self.side=QComboBox();self.side.addItems(['buy','sell']);self.qty=QSpinBox();self.qty.setRange(1,1000000000);form.addRow('Side (security selected on Trading desk)',self.side);form.addRow('Quantity',self.qty);self.intelligence=QComboBox();form.addRow('Declared confidential basis (staff may refuse)',self.intelligence);layout.addLayout(form)
  row=QHBoxLayout();layout.addLayout(row);button('Assign trade instruction',lambda:self.send('employee_task',{'employee':self.employee.currentData(),'kind':'order','symbol':self.terminal.symbol,'side':self.side.currentText(),'qty':self.qty.value(),'intelligence':self.intelligence.currentData()}));self.approval=QComboBox();row.addWidget(self.approval);button('Approve selected trade',self.approve)
  self.reports=QPlainTextEdit();self.reports.setReadOnly(True);layout.addWidget(self.reports,1)
 def send(self,action,p):self.terminal.send(action,p)
 def confirm(self,text):return QMessageBox.question(self,'Confirm employment instruction',text)==QMessageBox.StandardButton.Yes
 def selected(self):return next((e for e in (self.world or {}).get('employees',[]) if e['id']==self.employee.currentData()),None)
 def offer(self):
  if self.candidate.currentData():self.send('employment_offer',{'candidate':self.candidate.currentData(),'salary':str(self.salary.value())})
 def hire(self):
  offer=next((o for o in reversed(self.world.get('employment_offers',[])) if o['candidate']==self.candidate.currentData() and o['status']=='ACCEPTED' and o['expires']>=self.world['tick']),None)
  if not offer:self.terminal.notice.setText('Make an acceptable salary offer first.');return
  if self.confirm('Hire '+self.candidate.currentText()+' at £'+offer['salary']+' per month?'):self.send('employee_hire',{'offer':offer['id']})
 def change(self,kind,extra=None,confirm=False):
  if self.selected() and (not confirm or self.confirm(kind.capitalize()+' for '+self.selected()['name']+'? Earned wages remain payable; dismissal includes seven days of notice pay.')):self.send('employee_change',{'employee':self.employee.currentData(),'kind':kind,**(extra or {})})
 def approve(self):
  if self.approval.currentData() and self.confirm('Approve this trade at the market price when executed?'):self.send('employee_approve',{'task':self.approval.currentData()})
 def select_candidate(self):
  c=next((c for c in (self.world or {}).get('recruitment',[]) if c['id']==self.candidate.currentData()),None)
  if c:self.salary.setValue(float(c['minimum_salary']))
 def research_mandate(self):
  e=self.selected()
  if not e:return
  symbol,ok=QInputDialog.getText(self,'Recurring research','Underlying symbol; each weekly report costs £250. Blank stops the mandate.',text=e.get('research_policy',{}).get('symbol','NVDA'))
  if ok:self.send('staff_research_policy',{'employee':e['id'],'symbol':symbol or e.get('research_policy',{}).get('symbol','NVDA'),'enabled':bool(symbol)})
 def select_employee(self):
  e=self.selected()
  if e:
   self.pay.setValue(float(e['salary']));self.per.setValue(float(e['delegation']['per_order']));self.daily.setValue(float(e['delegation']['daily']));self.details.setText(f"{e['name']} · {ROLES[e['role']][0]} · {e['status']}\n{e['background']}. {e['qualifications']}. {e['experience']} years; competence {e['competence']}/100, reliability {e['reliability']}/100.\nSalary £{e['salary']}/month. Paid £{e['paid']}; unpaid £{e['unpaid']}. Seven days’ notice pay on dismissal.")
  else:self.details.setText('Select an employee to manage their contract and work.')
 def populate(self,combo,items):
  selected=combo.currentData();combo.blockSignals(True);combo.clear()
  for title,id in items:combo.addItem(title,id)
  index=combo.findData(selected)
  if index>=0:combo.setCurrentIndex(index)
  combo.blockSignals(False)
 def refresh(self,world):
  if not world:return
  self.world=world;self.populate(self.employer,[(e['name'],e['id']) for e in world.get('entities',{}).values() if e['controlled'] and e['id']!='personal']);entity=self.employer.currentData()
  self.populate(self.intelligence,[('Public information / no confidential basis',None)]+[(t['symbol']+' · '+t['id'],t['id']) for t in world.get('intelligence',[]) if t['account']==entity and t['symbol']==self.terminal.symbol and t['status']=='CONFIDENTIAL' and t['publish_tick']>world['tick']])
  work=world.get('workforce',{}).get(entity,{})
  self.workforce.setText(str(work.get('headcount',0))+' total staff · '+str(work.get('aggregate_headcount',0))+' aggregate operating team · £'+str(work.get('monthly_payroll','0.00'))+'/month payroll budget. '+work.get('note',''))
  people=[e for e in world.get('employees',[]) if e['entity']==entity];names={e['id']:e['name'] for e in people}
  self.populate(self.candidate,[(f"{c['name']} · {ROLES[c['role']][0]} · £{c['minimum_salary']}/month · {c['qualifications']} · competence {c['competence']} · integrity {c.get('integrity','—')} · loyalty {c.get('loyalty','—')}",c['id']) for c in world.get('recruitment',[]) if c['entity']==entity and c['status']=='AVAILABLE']);self.populate(self.employee,[(e['name']+' · '+ROLES[e['role']][0]+' · '+e['status'],e['id']) for e in people]);self.populate(self.manager,[('Player',None)]+[(e['name'],e['id']) for e in people if e['status']=='EMPLOYED' and e['id']!=self.employee.currentData()])
  self.populate(self.approval,[(names.get(t['employee'],'Former employee')+' · '+str(t['instruction']['qty'])+' '+t['instruction']['symbol'],t['id']) for t in world.get('employee_tasks',[]) if t['entity']==entity and t['status']=='AWAITING APPROVAL'])
  lines=[]
  for r in world.get('employee_reports',[]):
   if r['entity']==entity:lines.append(r['time']+' · '+names.get(r['employee'],'Former employee')+'\n'+r['summary']+'\n'+json.dumps(r['evidence'],indent=2))
  for t in world.get('employee_tasks',[]):
   if t['entity']==entity:lines.append(names.get(t['employee'],'Former employee')+' · '+t['kind']+' · '+t['status']+'\n'+str(t['result']))
  for r in world.get('employee_activity',[])[-100:]:
   if r['entity']==entity:lines.append(r['time']+' · '+names.get(r['employee'],'Former employee')+' · '+r['detail'])
  self.reports.setPlainText('\n\n'.join(reversed(lines)));self.select_employee()
