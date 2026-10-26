"""Native monetary-policy terminal. All controls call authoritative engine actions."""
from PyQt6.QtCore import Qt,QPointF
from PyQt6.QtGui import QPainter,QPen,QColor,QPolygonF
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTabWidget,QComboBox,QDoubleSpinBox,QPushButton,QPlainTextEdit,QTreeWidget,QTreeWidgetItem,QCheckBox,QGridLayout
from .presentation import describe

class YieldPlot(QWidget):
 def __init__(self):super().__init__();self.series=[];self.setMinimumHeight(210)
 def set_data(self,series):self.series=series;self.update()
 def paintEvent(self,event):
  painter=QPainter(self);painter.fillRect(self.rect(),QColor('#0c1726'));points=[point for _,data in self.series for point in data]
  if not points:painter.setPen(QColor('#b0c0d0'));painter.drawText(20,30,'No published observations');return
  xmin=min(x for x,y in points);xmax=max(x for x,y in points);ymin=min(y for x,y in points)-.15;ymax=max(y for x,y in points)+.15;left=55;top=15;width=max(1,self.width()-75);height=max(1,self.height()-45)
  for n in range(5):
   y=top+height*n/4;painter.setPen(QColor('#293e54'));painter.drawLine(QPointF(left,y),QPointF(left+width,y));painter.setPen(QColor('#9eafc0'));painter.drawText(QPointF(3,y+4),f'{ymax-(ymax-ymin)*n/4:.2f}')
  for colour,data in self.series:
   painter.setPen(QPen(QColor(colour),2));poly=QPolygonF([QPointF(left+(x-xmin)/max(1,xmax-xmin)*width,top+(ymax-y)/max(.01,ymax-ymin)*height) for x,y in data]);painter.drawPolyline(poly)

class FederalReservePanel(QWidget):
 def __init__(self,terminal):
  super().__init__();self.terminal=terminal;self.world=None;layout=QVBoxLayout(self);self.setStyleSheet('FederalReservePanel{background:#0c1726;} QTabBar::tab:selected{background:#293b50;color:#e2c480;}');self.heading=QLabel('FEDERAL RESERVE SYSTEM\nUS monetary policy · simulated institution');self.heading.setStyleSheet('font-size:23px;color:#dcc181;background:#102035;padding:20px;');layout.addWidget(self.heading);self.initialise=QPushButton('Establish Federal Reserve system');self.initialise.clicked.connect(lambda:self.terminal.send('fed_initialize',{}));layout.addWidget(self.initialise);self.tabs=QTabWidget();layout.addWidget(self.tabs)
  self.pages={};self.texts={}
  for name in ['Headquarters','FOMC room','Yield curve & trading','Economic data','Policy laboratory','Policy archive']:
   widget=QWidget();page=QVBoxLayout(widget);self.pages[name]=page;self.tabs.addTab(widget,name)
  indicators=QGridLayout();self.indicator_values={}
  for index,(key,label) in enumerate([('headline','HEADLINE INFLATION'),('core','CORE INFLATION'),('unemployment','UNEMPLOYMENT'),('growth','REAL GDP GROWTH')]):
   widget=QLabel();widget.setStyleSheet('background:#142337;border:1px solid #304355;padding:12px;color:#ddc58e;font-size:17px;');widget.setWordWrap(True);indicators.addWidget(widget,0,index);self.indicator_values[key]=(widget,label)
  self.pages['Headquarters'].addLayout(indicators)
  self.overview=QPlainTextEdit();self.overview.setReadOnly(True);self.pages['Headquarters'].addWidget(self.overview)
  self.bank_controls=QWidget();bank_layout=QVBoxLayout(self.bank_controls);bank_layout.addWidget(QLabel('Authorised bank reserve account — funded transfers, not fund capital'))
  row=QHBoxLayout();self.reserve_amount=QDoubleSpinBox();self.reserve_amount.setRange(1,1e12);self.reserve_amount.setValue(10000);row.addWidget(QLabel('GBP amount'));row.addWidget(self.reserve_amount)
  for kind,label in [('deposit','Deposit reserves'),('withdraw','Convert reserves to cash')]:
   control=QPushButton(label);control.clicked.connect(lambda checked=False,kind=kind:self.terminal.send('fed_reserve',{'account':self.terminal.active,'kind':kind,'amount':str(self.reserve_amount.value())}));row.addWidget(control)
  bank_layout.addLayout(row);self.facility_security=QComboBox();bank_layout.addWidget(self.facility_security);self.facility_face=QDoubleSpinBox();self.facility_face.setRange(100,1e15);self.facility_face.setSingleStep(100);self.facility_face.setValue(10000);row=QHBoxLayout();row.addWidget(QLabel('Treasury collateral / USD face'));row.addWidget(self.facility_face);facility=QPushButton('Request collateralised emergency loan');facility.clicked.connect(lambda:self.terminal.send('fed_facility',{'account':self.terminal.active,'security':self.facility_security.currentData(),'face':str(self.facility_face.value()),'amount':str(self.reserve_amount.value())}));row.addWidget(facility);bank_layout.addLayout(row);bank_layout.addWidget(QLabel('Available only during genuine stress, with 10% collateral haircut and interest. Repay through Banking.'));self.pages['Headquarters'].addWidget(self.bank_controls)
  self.members=QTreeWidget();self.members.setHeaderLabels(['Official','Institution / role','Voting','Latest vote']);self.pages['FOMC room'].addWidget(self.members)
  self.curve=YieldPlot();self.pages['Yield curve & trading'].addWidget(self.curve);self.security=QComboBox();self.pages['Yield curve & trading'].addWidget(self.security);self.security.currentIndexChanged.connect(self.selected_security);self.quote=QLabel();self.quote.setWordWrap(True);self.pages['Yield curve & trading'].addWidget(self.quote);row=QHBoxLayout();self.side=QComboBox();self.side.addItems(['buy','sell']);self.face=QDoubleSpinBox();self.face.setRange(100,1e15);self.face.setDecimals(0);self.face.setSingleStep(100);self.face.setValue(10000);row.addWidget(self.side);row.addWidget(QLabel('Face value / USD'));row.addWidget(self.face);trade=QPushButton('Execute Treasury trade');trade.clicked.connect(self.trade);row.addWidget(trade);self.pages['Yield curve & trading'].addLayout(row);self.holdings=QPlainTextEdit();self.holdings.setReadOnly(True);self.pages['Yield curve & trading'].addWidget(self.holdings)
  self.indicator=QComboBox()
  for key,label in [('headline','Headline inflation'),('core','Core inflation'),('unemployment','Unemployment'),('growth','Real GDP growth'),('wage_growth','Wage growth'),('liquidity','Money-market liquidity')]:self.indicator.addItem(label,key)
  self.indicator.currentIndexChanged.connect(self.render_data);self.pages['Economic data'].addWidget(self.indicator);self.economic_plot=YieldPlot();self.pages['Economic data'].addWidget(self.economic_plot);self.releases=QPlainTextEdit();self.releases.setReadOnly(True);self.pages['Economic data'].addWidget(self.releases)
  note=QLabel('Hypothetical analysis only. This does not change live policy, balances or simulation time.');note.setWordWrap(True);self.pages['Policy laboratory'].addWidget(note);row=QHBoxLayout();self.delta=QDoubleSpinBox();self.delta.setRange(-300,300);self.delta.setSingleStep(25);self.delta.setValue(25);row.addWidget(QLabel('Rate change / basis points'));row.addWidget(self.delta);run=QPushButton('Run hypothetical comparison');run.clicked.connect(lambda:self.terminal.send('fed_scenario',{'delta_bps':self.delta.value(),'months':24},callback=lambda result:self.scenario.setPlainText(describe(result))));row.addWidget(run);self.pages['Policy laboratory'].addLayout(row);self.scenario=QPlainTextEdit();self.scenario.setReadOnly(True);self.pages['Policy laboratory'].addWidget(self.scenario)
  self.sandbox=QCheckBox('Enable live policy sandbox (changes the economy)');self.sandbox.clicked.connect(lambda enabled:self.terminal.send('fed_control',{'kind':'sandbox','enabled':enabled,'confirm':'POLICY SANDBOX'}));self.pages['Policy laboratory'].addWidget(self.sandbox);row=QHBoxLayout();self.live_rate=QDoubleSpinBox();self.live_rate.setRange(.25,15);self.live_rate.setSingleStep(.25);row.addWidget(QLabel('Live target upper bound / %'));row.addWidget(self.live_rate);self.live_apply=QPushButton('Apply live sandbox policy');self.live_apply.clicked.connect(lambda:self.terminal.send('fed_control',{'kind':'override','upper':self.live_rate.value()}));row.addWidget(self.live_apply);self.pages['Policy laboratory'].addLayout(row)
  self.archive=QPlainTextEdit();self.archive.setReadOnly(True);self.pages['Policy archive'].addWidget(self.archive)
 def render_overview(self,f):
  from datetime import datetime
  observed=f['observed'];expectations=f['expectations'];sheet=f['balance_sheet'];meeting=f.get('next_meeting');latest=f.get('latest')
  for key,(widget,label) in self.indicator_values.items():widget.setText(label+'\n'+f'{observed[key]:.2f}%')
  next_date=datetime.fromisoformat(meeting['time']).strftime('%d %B %Y, %H:%M UTC') if meeting else 'No meeting scheduled'
  probabilities=' · '.join(f"{row['change_bps']:+d} bp: {row['probability']*100:.1f}%" for row in expectations['probabilities'])
  lines=['POLICY WATCH','Next FOMC meeting: '+next_date,'Meetings execute automatically as simulation time advances.','','MODEL-IMPLIED EXPECTATIONS',probabilities,f"Expected change: {expectations['expected_change']*100:+.1f} basis points",'Published economic data and policy preferences; these are not traded futures quotes.','','FINANCIAL CONDITIONS',f"Stress: {observed['stress']:.1f} / 100 · Liquidity index: {observed['liquidity']:.1f}",f"Output gap: {observed['output_gap']:+.2f}% · Wage growth: {observed['wage_growth']:.2f}%",'Policy affects financing quickly; output, employment and inflation respond with delays.','','FEDERAL RESERVE BALANCE SHEET — GBP REPORTING EQUIVALENT']
  for key,label in [('cash','Settlement cash'),('treasuries','Treasury securities'),('loans','Liquidity-facility claims'),('reserves','Bank reserve liabilities'),('currency','Currency liabilities'),('net_assets','Net assets')]:lines.append(label+f": £{float(sheet[key]):,.2f}")
  lines+=['','LATEST POLICY ANNOUNCEMENT',str(latest.get('statement','Decision recorded; review the policy archive.')) if latest else 'No policy meeting has occurred in this world yet.','','MODEL SCOPE',f['source']];self.overview.setPlainText('\n'.join(lines))

 def selected_security(self):
  if not self.world or not self.world.get('fed'):return
  q=next((q for q in self.world['fed']['securities'] if q['id']==self.security.currentData()),None)
  if q:self.quote.setText(f"Yield {q['yield_pct']:.3f}% · coupon {q['coupon']:.3f}% · maturity {q['maturity'][:10]}\nClean ${q['clean_price']:.4f} + accrued ${q['accrued_per_100']:.4f} = dirty ${q['dirty_price']:.4f} / $100 face\nModified duration {q['modified_duration']:.2f}. GBP cash settlement; funded dealer inventory or finite primary auction. No Treasury short selling.")
 def trade(self):
  if self.security.currentData():self.terminal.send('treasury_order',{'account':self.terminal.active,'security':self.security.currentData(),'side':self.side.currentText(),'face':str(self.face.value())})
 def render_data(self):
  f=(self.world or {}).get('fed');key=self.indicator.currentData()
  if f:self.economic_plot.set_data([('#d9bd79',[(r['tick']/24,r[key]) for r in f['history'] if r.get(key) is not None])])
 def refresh(self,world):
  self.world=world;f=world.get('fed') if world else None;self.initialise.setVisible(not bool(f));self.tabs.setEnabled(bool(f))
  if not f:return
  authorised=any(bank.get('entity')==self.terminal.active and bank.get('licence')=='AUTHORISED' for bank in world.get('banks',[]));self.bank_controls.setVisible(authorised);selected_collateral=self.facility_security.currentData();self.facility_security.clear()
  for position in f['positions']:
   if position['account']==self.terminal.active:self.facility_security.addItem(position['security']+' · $'+position['face']+' face',position['security'])
  selected_index=self.facility_security.findData(selected_collateral)
  if selected_index>=0:self.facility_security.setCurrentIndex(selected_index)
  self.sandbox.setChecked(bool(f.get('sandbox')));self.live_apply.setEnabled(bool(f.get('sandbox')))
  self.heading.setText(f"FEDERAL RESERVE SYSTEM\nTarget {f['lower']:.2f}–{f['upper']:.2f}% · {f['stance']}");self.render_overview(f);self.members.clear();last={v['member']:v for v in (f.get('latest') or {}).get('votes',[])}
  for member in f['members']:
   vote=last.get(member['id']);item=QTreeWidgetItem([member['name'],member['institution']+' / '+member['office'],'Voting member' if member['voting'] else 'Nonvoting participant',f"{vote['target']:.2f}%" if vote else 'No recorded vote']);item.setToolTip(0,f"Inflation weight {member['inflation_weight']:.2f}; employment weight {member['employment_weight']:.2f}");self.members.addTopLevelItem(item)
  self.curve.set_data([('#d9bd79',[(r['years'],r['yield_pct']) for r in f['curve']])]);selected=self.security.currentData();self.security.blockSignals(True);self.security.clear()
  for q in f['securities']:self.security.addItem(q['name']+' · '+q['maturity'][:10],q['id'])
  index=self.security.findData(selected)
  if index>=0:self.security.setCurrentIndex(index)
  self.security.blockSignals(False);self.selected_security();self.holdings.setPlainText(describe({'account':world['entities'].get(self.terminal.active,{}).get('name',self.terminal.active),'Treasury_holdings':[dict(security=next((q['name'] for q in f['securities'] if q['id']==p['security']),p['security']),face_USD=p['face']) for p in f['positions'] if p['account']==self.terminal.active]}));self.releases.setPlainText(describe(f['releases'][-12:]));self.archive.setPlainText(describe(list(reversed(f['meetings']))));self.render_data()
