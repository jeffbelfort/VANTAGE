from PyQt6.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QComboBox,QSpinBox,QPushButton,QPlainTextEdit,QMessageBox
class OfficePanel(QWidget):
 def __init__(self,terminal):
  super().__init__();self.terminal=terminal;self.world=None;layout=QVBoxLayout(self);form=QFormLayout();self.employer=QComboBox();form.addRow('Institution',self.employer);self.employer.currentIndexChanged.connect(lambda:self.refresh(self.world));self.property=QComboBox();form.addRow('Premises',self.property);self.mode=QComboBox();self.mode.addItems(['lease','purchase']);form.addRow('Tenure',self.mode);self.months=QSpinBox();self.months.setRange(1,120);self.months.setValue(12);form.addRow('Lease months',self.months);layout.addLayout(form);self.start=QPushButton('Acquire selected premises');self.start.clicked.connect(lambda:self.action('office_start'));layout.addWidget(self.start);self.office=QComboBox();layout.addWidget(self.office)
  for title,action in [('Close premises / pay remaining rent','office_end'),('Relocate to selected premises','office_relocate'),('List owned building for sale','office_sell')]:
   button=QPushButton(title);button.clicked.connect(lambda checked=False,action=action:self.action(action));layout.addWidget(button)
  self.details=QPlainTextEdit();self.details.setReadOnly(True);layout.addWidget(self.details,1)
 def action(self,action):
  if QMessageBox.question(self,'Confirm premises commitment','Commit the selected institution? Acquisitions use the selected property and term. Early lease termination pays all remaining contractual rent; owned buildings remain assets until sold.')==QMessageBox.StandardButton.Yes:self.terminal.send(action,{'entity':self.employer.currentData(),'catalogue':self.property.currentData(),'mode':self.mode.currentText(),'months':self.months.value(),'office':self.office.currentData()})
 def populate(self,combo,items):
  old=combo.currentData();combo.blockSignals(True);combo.clear()
  for title,id in items:combo.addItem(title,id)
  i=combo.findData(old)
  if i>=0:combo.setCurrentIndex(i)
  combo.blockSignals(False)
 def refresh(self,world):
  if not world:return
  self.world=world;self.populate(self.employer,[(e['name'],e['id']) for e in world.get('entities',{}).values() if e['controlled'] and e['id']!='personal']);entity=self.employer.currentData();self.populate(self.property,[(f"{o['name']} · {o['location']} · {o['capacity']} staff · purchase £{o['price']} · rent £{o['rent']}/month",o['id']) for o in world.get('office_catalogue',[])]);offices=[o for o in world.get('offices',[]) if o['entity']==entity];self.populate(self.office,[(o['name']+' · '+o['status'],o['id']) for o in offices]);lines=[f"Staff capacity: {world.get('office_capacity',{}).get(entity,10)}; 10 remote baseline places. Full lease rent is a liability with a matching right-of-use asset. Early termination pays remaining rent. Prestige can reduce recruitment salary demands."]
  for c in world.get('office_catalogue',[]):lines.append(f"{c['name']} · equipment {c['equipment']}/100 · prestige {c['prestige']}/100 · utilities £{c['utilities']}/month · equipment £{c['equipment_cost']}/month · owned maintenance £{c['maintenance']}/month")
  for o in offices:lines.append(f"{o['name']} · {o['mode']} · {o['status']} · {o['capacity']} staff\nPaid £{o['paid']}; unpaid billed rent £{o['unpaid_rent']}; unpaid operations £{o['unpaid_operations']}\nFull remaining lease debt £{-float(world['balances'].get('debt:'+entity+':lease_'+o['id'],0)):.2f}")
  self.details.setPlainText('\n\n'.join(lines))
