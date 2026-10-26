from PyQt6.QtWidgets import QWidget,QVBoxLayout,QComboBox,QPushButton,QPlainTextEdit,QMessageBox,QLabel,QInputDialog
class WealthPanel(QWidget):
 def __init__(self,terminal):
  super().__init__();self.terminal=terminal;self.world=None;layout=QVBoxLayout(self);layout.addWidget(QLabel('Paying account and legal owner — investor fund money cannot buy lifestyle assets.'));self.owner=QComboBox();layout.addWidget(self.owner);self.owner.currentIndexChanged.connect(lambda:self.refresh(self.world));self.catalogue=QComboBox();layout.addWidget(self.catalogue);self.buy=QPushButton('Purchase selected asset');self.buy.clicked.connect(self.purchase);layout.addWidget(self.buy);self.owned=QComboBox();layout.addWidget(self.owned);self.schedule=QPushButton('Plan funded asset activity');self.schedule.clicked.connect(self.plan_activity);layout.addWidget(self.schedule);self.services=QPushButton('Configure crew / household service contract');self.services.clicked.connect(self.service_policy);layout.addWidget(self.services);self.repair=QPushButton('Sign off selected asset repair');self.repair.clicked.connect(self.repair_asset);layout.addWidget(self.repair);self.host=QPushButton('Host private activity on selected asset');self.host.clicked.connect(self.host_activity);layout.addWidget(self.host);self.sell=QPushButton('List selected asset for resale');self.sell.clicked.connect(self.resale);layout.addWidget(self.sell);self.rent=QPushButton('Let selected property');self.rent.clicked.connect(self.let_property);layout.addWidget(self.rent);self.end_rent=QPushButton('End selected property rental');self.end_rent.clicked.connect(self.end_rental);layout.addWidget(self.end_rent);self.details=QPlainTextEdit();self.details.setReadOnly(True);layout.addWidget(self.details,1)
 def populate(self,combo,items):
  old=combo.currentData();combo.blockSignals(True);combo.clear()
  for title,id in items:combo.addItem(title,id)
  i=combo.findData(old)
  if i>=0:combo.setCurrentIndex(i)
  combo.blockSignals(False)
 def purchase(self):
  c=next((c for c in self.world.get('lifestyle_catalogue',[]) if c['id']==self.catalogue.currentData()),None)
  if c and QMessageBox.question(self,'Confirm asset purchase',f"Buy {c['name']} for £{c['price']}? The selected legal owner pays; monthly running costs £{c['monthly_cost']}.")==QMessageBox.StandardButton.Yes:self.terminal.send('asset_buy',{'owner':self.owner.currentData(),'catalogue':c['id']})
 def resale(self):
  if self.owned.currentData() and QMessageBox.question(self,'List for resale','Sell at the catalogue discount after the stated liquidity delay? Buyer funding is required.')==QMessageBox.StandardButton.Yes:self.terminal.send('asset_sale',{'asset':self.owned.currentData()})
 def let_property(self):
  a=next((a for a in self.world.get('owned_assets',[]) if a['id']==self.owned.currentData()),None)
  if not a:return
  rent,ok=QInputDialog.getDouble(self,'Let property','Monthly asking rent / GBP; 12 months; early termination costs one month',float(a['valuation'])*.04/12,.01,1e9,2)
  if ok and QMessageBox.question(self,'Confirm tenancy','Let this property to the existing household tenant sector? Actual tenant funds are required; unpaid rent remains a claim.')==QMessageBox.StandardButton.Yes:self.terminal.send('property_lease',{'asset':a['id'],'rent':str(rent),'months':12})
 def end_rental(self):
  c=next((c for c in self.world.get('property_contracts',[]) if c['asset']==self.owned.currentData() and c['status']=='ACTIVE'),None)
  if c and QMessageBox.question(self,'End rental',f"Pay £{c['rent']} to the tenant to end early? Existing arrears remain owed.")==QMessageBox.StandardButton.Yes:self.terminal.send('property_lease_end',{'contract':c['id']})
 def host_activity(self):
  if not self.owned.currentData():return
  guests=self.world['npcs']+[e for e in self.world.get('employees',[]) if e['status']=='EMPLOYED' and self.world['entities'].get(e['entity'],{}).get('controlled')]
  value,ok=QInputDialog.getText(self,'Private activity','Comma-separated guest IDs: '+', '.join(g['id']+' ('+g['name']+')' for g in guests))
  if ok and value:self.terminal.send('lifestyle_host',{'asset':self.owned.currentData(),'publicity':'PRIVATE','guests':[g.strip() for g in value.split(',') if g.strip()]})
 def plan_activity(self):
  a=next((a for a in self.world.get('owned_assets',[]) if a['id']==self.owned.currentData()),None)
  if not a:return
  choices=a.get('profile',{}).get('activities',['private_meeting']);purpose,ok=QInputDialog.getItem(self,'Activity purpose','Choose a supported activity',choices,0,False)
  if not ok:return
  people=self.world['npcs']+self.world.get('social_contacts',[])+[e for e in self.world['employees'] if e['status']=='EMPLOYED' and self.world['entities'].get(e['entity'],{}).get('controlled')]
  guests,ok=QInputDialog.getText(self,'Attendees','Comma-separated IDs: '+', '.join(p['id']+' ('+p['name']+')' for p in people))
  if not ok or not guests:return
  budget,ok=QInputDialog.getDouble(self,'Activity budget','GBP; reserved now, refunded if cancelled; minimum costs apply',1000,.01,1e10,2)
  if not ok:return
  delay,ok=QInputDialog.getInt(self,'Scheduled hour','Simulation hours from now',24,0,720)
  if not ok:return
  publicity,ok=QInputDialog.getItem(self,'Publicity','Choose public coverage or private attendance',['PRIVATE','PUBLIC'],0,False)
  if not ok:return
  opportunity=None
  if purpose=='business_trip':
   invitations=[o for o in self.world.get('networking_opportunities',[]) if o['status']=='OPEN']
   if not invitations:return
   selected,ok=QInputDialog.getItem(self,'Business forum','Attend an existing invitation',[o['id']+' · '+o['name']+' · '+o['location'] for o in invitations],0,False)
   if not ok:return
   opportunity=selected.split(' · ')[0]
  self.terminal.send('lifestyle_schedule',dict(asset=a['id'],purpose=purpose,guests=[g.strip() for g in guests.split(',') if g.strip()],budget=str(budget),delay_hours=delay,publicity=publicity,opportunity=opportunity))
 def service_policy(self):
  if not self.owned.currentData():return
  staffing,ok=QInputDialog.getItem(self,'Service staffing','Crew / household contractor staffing; reduced staffing saves 20% of base operating costs but lowers event quality',['FULL','REDUCED'],0,False)
  if not ok:return
  security,ok=QInputDialog.getItem(self,'Security','Enhanced security adds 10% of base operating costs',['STANDARD','ENHANCED'],0,False)
  if ok:self.terminal.send('asset_services',{'asset':self.owned.currentData(),'staffing':staffing,'security':security})
 def repair_asset(self):
  incident=next((i for i in self.world.get('asset_incidents',[]) if i['asset']==self.owned.currentData() and i['status']=='OPEN'),None)
  if incident:self.terminal.send('asset_repair',{'incident':incident['id']})
 def refresh(self,world):
  if not world:return
  self.world=world;self.populate(self.owner,[(e['name'],e['id']) for e in world.get('entities',{}).values() if e['controlled'] and e['kind']!='fund']);owner=self.owner.currentData();self.populate(self.catalogue,[(f"{c['name']} · £{c['price']} · £{c['monthly_cost']}/month · resale {c['sale_hours']/24:g} days",c['id']) for c in world.get('lifestyle_catalogue',[])]);assets=[a for a in world.get('owned_assets',[]) if a['owner']==owner];self.populate(self.owned,[(a['name'],a['id']) for a in assets if a['status']=='OWNED']);self.buy.setEnabled(bool(self.catalogue.count()));self.sell.setEnabled(bool(self.owned.count()));lines=[str(i) for i in world.get('asset_incidents',[]) if i['owner']==owner]+['Reputation: '+str(world.get('personal_reputation',{}))]+[str(e) for e in world.get('social_events',[])[-10:] if e['owner']==owner]
  for a in assets:lines.append(f"{a['name']} · {a['status']}\nAcquired {a['acquired']}\nPurchase £{a['purchase_price']}; current value £{a['valuation']}; running costs paid £{a['running_paid']}; unpaid £{a['unpaid']}\nSale {a['sale']}\nRealised result {a['realised']}")
  for c in world.get('property_contracts',[]):
   if c['owner']==owner:lines.append(f"Rental {c['tenant_name']} · {c['status']} · £{c['rent']}/month · collected £{c['paid']}")
  self.details.setPlainText(f"Owned asset valuation £{world['metrics'][owner]['owned_assets']}\n"+'\n\n'.join(lines) if owner else 'No account available')
