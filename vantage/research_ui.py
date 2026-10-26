"""Native commissioned research and searchable report evidence."""
import json
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QComboBox,QPushButton,QLineEdit,QPlainTextEdit,QMessageBox,QLabel

class ResearchPanel(QWidget):
 def __init__(self,terminal):
  super().__init__();self.terminal=terminal;self.world=None;layout=QVBoxLayout(self);layout.addWidget(QLabel('Request Analysis — £250 operating cost plus employed analyst time. Estimates can be wrong.'))
  form=QFormLayout();self.employer=QComboBox();self.analyst=QComboBox();form.addRow('Commissioning institution',self.employer);form.addRow('Investment analyst',self.analyst);layout.addLayout(form);self.employer.currentIndexChanged.connect(lambda:self.refresh(self.world))
  self.request=QPushButton('Request Analysis for selected Trading security');self.request.clicked.connect(self.commission);layout.addWidget(self.request);self.search=QLineEdit();self.search.setPlaceholderText('Search symbol, analyst or recommendation');self.search.textChanged.connect(lambda:self.refresh(self.world));layout.addWidget(self.search);self.reports=QPlainTextEdit();self.reports.setReadOnly(True);layout.addWidget(self.reports,1)
 def populate(self,combo,items):
  old=combo.currentData();combo.blockSignals(True);combo.clear()
  for name,id in items:combo.addItem(name,id)
  i=combo.findData(old)
  if i>=0:combo.setCurrentIndex(i)
  combo.blockSignals(False)
 def commission(self):
  if QMessageBox.question(self,'Commission analysis',f'Research {self.terminal.symbol} for this institution? £250 is paid now, plus salary expenditure while the analyst works.')==QMessageBox.StandardButton.Yes:self.terminal.send('request_analysis',{'entity':self.employer.currentData(),'analyst':self.analyst.currentData(),'symbol':self.terminal.symbol})
 def refresh(self,world):
  if not world:return
  self.world=world;self.populate(self.employer,[(e['name'],e['id']) for e in world.get('entities',{}).values() if e['controlled'] and e['id']!='personal']);entity=self.employer.currentData();self.populate(self.analyst,[(e['name'],e['id']) for e in world.get('employees',[]) if e['entity']==entity and e['role']=='analyst' and e['status']=='EMPLOYED']);self.request.setEnabled(self.analyst.count()>0);self.request.setText('Request Analysis · '+self.terminal.symbol);query=self.search.text().lower();blocks=[]
  for r in world.get('stock_research',[]):
   if r['entity']!=entity or query not in (r['symbol']+' '+r['analyst_name']+' '+r['recommendation']).lower():continue
   blocks.append(f"{r['symbol']} · {r['recommendation']} · {r['confidence']}% confidence · {r['analyst_name']}\n{r['time']} · {'Stale — review required' if r['stale'] else 'Recent'}\nEstimated range {r['currency']} {r['fair_low']}–{r['fair_high']}\n{r['valuation_basis']}\n"+'\n'.join(r['reasoning']+r['bullish_catalysts']+r['bearish_catalysts']+r['risks']+r['uncertainties'])+'\nEvidence:\n'+json.dumps(r['evidence'],indent=2)+'\nAssumptions:\n'+json.dumps(r['assumptions'],indent=2)+'\nHistorical assessment:\n'+json.dumps(r['outcome'],indent=2))
  for t in world.get('employee_tasks',[]):
   if t['entity']==entity and t['kind']=='analysis' and t['status']=='QUEUED':blocks.append(t['instruction']['symbol']+' · Research in progress · '+str(max(0,t['due']-world['tick']))+' hours until next attempt')
  self.reports.setPlainText('\n\n'.join(reversed(blocks)) or 'No reports. Commission analysis and advance simulation time.')
