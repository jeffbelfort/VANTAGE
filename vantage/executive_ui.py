"""Native executive inbox and explicit departmental authority controls."""
import json
from .presentation import describe, label
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit,QPushButton,QPlainTextEdit,QLabel,QMessageBox,QCheckBox
from .staff_autonomy import AUTHORITY_LEVELS
from .employees import ROLES

class ExecutivePanel(QWidget):
 def __init__(self,terminal):
  super().__init__();self.terminal=terminal;self.world=None;layout=QVBoxLayout(self);layout.addWidget(QLabel('Executive office — evidence, decisions and bounded authority'))
  easy=QFormLayout();layout.addLayout(easy);self.team_entity=QComboBox();easy.addRow('Easy mode · company / fund',self.team_entity);self.team_style=QComboBox();self.team_style.addItems(['balanced','careful','adventurous']);easy.addRow('Team style',self.team_style);self.team_strategy=QComboBox();self.team_strategy.addItems(['blended','value','growth','quality','momentum','income']);easy.addRow('Team strategy',self.team_strategy);self.team_start=QPushButton('Auto-assign & run team');self.team_start.clicked.connect(lambda:self.terminal.send('auto_team',{'entity':self.team_entity.currentData(),'mode':self.team_style.currentText(),'strategy':self.team_strategy.currentText()}));layout.addWidget(self.team_start);self.team_pause=QPushButton('Pause team');self.team_pause.clicked.connect(lambda:self.terminal.send('auto_team',{'entity':self.team_entity.currentData(),'mode':'pause'}));layout.addWidget(self.team_pause);self.team_resume=QPushButton('Resume previous team');self.team_resume.clicked.connect(lambda:self.terminal.send('auto_team',{'entity':self.team_entity.currentData(),'mode':'resume'}));layout.addWidget(self.team_resume);self.team_status=QLabel('Long-only trading with actual employer cash; risk managers advise on measured exposures; your chosen limits remain authoritative. No routine approvals.');self.team_status.setWordWrap(True);layout.addWidget(self.team_status);self.team_entity.currentIndexChanged.connect(self.show_team_status)
  self.employee=QComboBox();layout.addWidget(self.employee);self.employee.currentIndexChanged.connect(self.choose_employee)
  form=QFormLayout();layout.addLayout(form);self.level=QComboBox()
  for key,label in AUTHORITY_LEVELS.items():self.level.addItem(str(key)+' · '+label,key)
  form.addRow('Authority',self.level);self.budget=self.money(form,'Weekly operating budget / GBP');self.capital=self.money(form,'Capital ceiling per security / GBP');self.reserve=self.money(form,'Cash reserve / GBP');self.per=self.money(form,'Per-order trading limit / GBP');self.daily=self.money(form,'Daily trading limit / GBP');self.symbols=QLineEdit();form.addRow('Selected securities (optional in market mode)',self.symbols);self.market=QCheckBox('Screen eligible equity market');form.addRow(self.market);self.sectors=QLineEdit();form.addRow('Sectors, comma separated; empty allows all',self.sectors);self.countries=QLineEdit();form.addRow('Country codes, comma separated; empty allows all',self.countries);self.strategy=QComboBox();self.strategy.addItems(['blended','value','growth','momentum','quality','income']);form.addRow('Investment strategy',self.strategy);self.position=self.money(form,'Maximum position / net assets %');self.sector=self.money(form,'Maximum sector / net assets %');self.cash_target=self.money(form,'Cash target / net assets %');self.target=QSpinBox();self.target.setRange(0,10000);form.addRow('HR target headcount',self.target);self.salary=self.money(form,'HR maximum monthly salary / GBP');self.role=QComboBox()
  for key,label in ROLES.items():self.role.addItem(label[0],key)
  form.addRow('HR recruitment role',self.role)
  self.save=QPushButton('Save department authority');self.save.clicked.connect(self.save_policy);layout.addWidget(self.save)
  hint=QLabel('Salaried analysts research holdings. Market-wide mandates screen up to three names daily, or choose no trade. All trading remains long-only within capital and order/daily limits. Level 2 relations updates cost £250; level 3 legal document work costs £500. HR searches at level 3 and hires at level 4 under salary/headcount limits.');hint.setWordWrap(True);layout.addWidget(hint)
  self.recommendation=QComboBox();layout.addWidget(self.recommendation);self.recommendation.currentIndexChanged.connect(self.choose_recommendation)
  self.approve=QPushButton('Approve selected recommendation');self.approve.clicked.connect(lambda:self.decide('accept'));layout.addWidget(self.approve);self.reject=QPushButton('Reject selected recommendation');self.reject.clicked.connect(lambda:self.decide('reject'));layout.addWidget(self.reject)
  self.entity=QComboBox();layout.addWidget(self.entity);b=QPushButton('Publish actual corporate financial update');b.clicked.connect(lambda:self.terminal.send('corporate_update',{'entity':self.entity.currentData()}));layout.addWidget(b)
  self.detail=QPlainTextEdit();self.detail.setReadOnly(True);layout.addWidget(self.detail)
  self.briefing=QPlainTextEdit();self.briefing.setReadOnly(True);layout.addWidget(self.briefing,1)
 def show_team_status(self):
  team=(self.world or {}).get('auto_teams',{}).get(self.team_entity.currentData(),{});review=team.get('risk_review',{})
  context=(self.team_entity.currentData(),team.get('set_time'),team.get('mode'),team.get('strategy'))
  if context!=getattr(self,'_team_context',None):
   self._team_context=context;self.team_style.setCurrentText(team.get('mode','balanced'));self.team_strategy.setCurrentText(team.get('strategy','blended'))
  self.team_pause.setEnabled(bool(team.get('enabled')));self.team_resume.setEnabled(bool(team) and not team.get('enabled',False));self.team_status.setText((team.get('status','Not configured')+' · '+team.get('mode','Choose a team style')+'\n'+review.get('assessment','Existing staff, real employer cash, long-only trading; no routine approvals.')))
 def money(self,form,title):
  field=QDoubleSpinBox();field.setRange(0,1e12);field.setDecimals(2);form.addRow(title,field);return field
 def populate(self,combo,items):
  old=combo.currentData();combo.blockSignals(True);combo.clear()
  for title,key in items:combo.addItem(title,key)
  index=combo.findData(old)
  if index>=0:combo.setCurrentIndex(index)
  combo.blockSignals(False)
 def choose_employee(self):
  if not self.world:return
  e=next((e for e in self.world['employees'] if e['id']==self.employee.currentData()),None)
  if not e:return
  p=e.get('department_policy',{});self.level.setCurrentIndex(self.level.findData(p.get('level',1)));self.budget.setValue(float(p.get('weekly_budget',0)));self.capital.setValue(float(p.get('capital_limit',0)));self.reserve.setValue(float(p.get('cash_reserve',0)));self.per.setValue(float(e['delegation']['per_order']));self.daily.setValue(float(e['delegation']['daily']));self.symbols.setText(','.join(p.get('symbols',[])));self.market.setChecked(p.get('universe')=='market');self.sectors.setText(','.join(p.get('sectors',[])));self.countries.setText(','.join(p.get('countries',[])));self.strategy.setCurrentText(p.get('strategy','blended'));self.position.setValue(float(p.get('max_position_pct',100)));self.sector.setValue(float(p.get('max_sector_pct',100)));self.cash_target.setValue(float(p.get('cash_target_pct',0)));self.target.setValue(p.get('headcount_target',0));self.salary.setValue(float(p.get('salary_limit',0)));self.role.setCurrentIndex(self.role.findData(p.get('recruitment_role','analyst')))
 def save_policy(self):
  if not self.employee.currentData():return
  self.terminal.send('staff_policy',dict(employee=self.employee.currentData(),universe='market' if self.market.isChecked() else 'selected',sectors=[v.strip() for v in self.sectors.text().split(',') if v.strip()],countries=[v.strip() for v in self.countries.text().split(',') if v.strip()],strategy=self.strategy.currentText(),max_position_pct=self.position.value(),max_sector_pct=self.sector.value(),cash_target_pct=self.cash_target.value(),level=self.level.currentData(),weekly_budget=str(self.budget.value()),capital_limit=str(self.capital.value()),cash_reserve=str(self.reserve.value()),per_order=str(self.per.value()),daily=str(self.daily.value()),symbols=[s.strip() for s in self.symbols.text().split(',') if s.strip()],headcount_target=self.target.value(),salary_limit=str(self.salary.value()),recruitment_role=self.role.currentData()))
 def choose_recommendation(self):
  rows=self.world.get('executive',{}).get('recommendations',[]) if self.world else [];row=next((r for r in rows if r['id']==self.recommendation.currentData()),None);self.detail.setPlainText(describe(row,{k:v['name'] for k,v in self.world.get('entities',{}).items()}) if row else 'No pending decisions.')
 def decide(self,decision):
  if not self.recommendation.currentData():return
  if decision=='accept' and QMessageBox.question(self,'Approve recommendation','Authorise this specific recommendation? Trade approval uses actual execution prices, cash and exchange risk checks. See recorded evidence and quantity below.')!=QMessageBox.StandardButton.Yes:return
  self.terminal.send('staff_decision',{'recommendation':self.recommendation.currentData(),'decision':decision})
 def refresh(self,world):
  if not world:return
  self.world=world;self.populate(self.team_entity,[(e['name'],e['id']) for e in world['entities'].values() if e['controlled'] and e['id']!='personal']);old=self.employee.currentData();self.populate(self.employee,[(e['name']+' · '+e['role']+' · '+world['entities'][e['entity']]['name'],e['id']) for e in world['employees'] if e['status']=='EMPLOYED' and world['entities'].get(e['entity'],{}).get('controlled')]);self.populate(self.entity,[(e['name'],e['id']) for e in world['entities'].values() if e['controlled']]);executive=world.get('executive',{});self.populate(self.recommendation,[(r['summary'],r['id']) for r in executive.get('recommendations',[])]);self.choose_recommendation();self.show_team_status()
  if old!=self.employee.currentData():self.choose_employee()
  self.briefing.setPlainText(describe({k:executive.get(k,[]) for k in ('departments','obligations','cases','activities','internal_reviews','briefings','investor_requests')},{k:v['name'] for k,v in self.world.get('entities',{}).items()}))
