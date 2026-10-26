"""Verified socket-free Qt Widgets terminal, sharing the complete financial engine."""
import json,math,sys,os
from pathlib import Path
from PyQt6.QtCore import Qt,QTimer,QRectF,QPointF,QUrl
from PyQt6.QtGui import QColor,QPainter,QPen,QFont,QIcon,QKeySequence,QShortcut
from PyQt6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QComboBox,QLineEdit,QDoubleSpinBox,QSpinBox,QCheckBox,QTableWidget,QTableWidgetItem,QHeaderView,QStackedWidget,QListWidget,QSplitter,QFrame,QFormLayout,QMessageBox,QDialog,QDialogButtonBox,QInputDialog,QTextEdit,QPlainTextEdit,QFileDialog,QAbstractItemView,QScrollArea)
from .bridge import Bridge,ROOT
from .engine import CAREERS

def gbp(v):return 'Not loaded' if v is None else f'£{float(v or 0):,.2f}'
def local(v,c='GBP'):return f'{c} {float(v or 0):,.4f}'
def number(v):return float(v or 0)
GREEN='#64d9ac';RED='#ef8494'
STYLE='''
QWidget{background:#10171e;color:#d5e2e9;font-family:"DejaVu Sans";font-size:11px;}
QMainWindow{background:#0c1319;} QLabel#Brand{font-size:22px;font-weight:700;letter-spacing:4px;color:#e0f5e9;padding:8px 0;}
QLabel#Sub{color:#718b9a;font-size:9px;letter-spacing:1px;} QLabel#Title{font-size:25px;font-weight:500;padding:7px 0;}
QLabel#MetricValue{font-size:23px;font-family:"DejaVu Sans Mono";padding:5px 0;color:#e0ecef;}
QLabel#MetricLabel{font-size:9px;color:#8ba3b1;letter-spacing:1px;} QLabel#Notice{background:#1c352b;color:#9ce1be;padding:10px;border:1px solid #35634f;border-radius:4px;}
QFrame#Panel{background:#151f28;border:1px solid #2b3b46;border-radius:5px;} QFrame#Panel QLabel{background:transparent;}
QPushButton{background:#21303a;border:1px solid #3a4e5b;border-radius:4px;padding:8px 13px;font-weight:500;} QPushButton:hover{background:#304450;border-color:#607b89;} QPushButton:disabled{color:#526573;}
QPushButton#Primary{background:#58cfa2;border-color:#58cfa2;color:#0e241a;font-weight:600;} QPushButton#Primary:hover{background:#79e4b9;}
QPushButton#Danger{background:#64313f;border-color:#9f5162;color:#f7b9c2;}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit{background:#101922;border:1px solid #354b59;border-radius:3px;padding:7px;selection-background-color:#315d49;}
QComboBox::drop-down{border:0;width:20px;} QComboBox QAbstractItemView{background:#1b2a33;selection-background-color:#2b4c3d;}
QListWidget{background:#10191f;border:0;outline:0;padding:8px;} QListWidget::item{padding:11px 12px;color:#8fa8b7;border-radius:3px;} QListWidget::item:selected{background:#1c3d30;color:#8ee6bc;border-left:2px solid #65d9a9;}
QTableWidget{background:#151f28;alternate-background-color:#17242e;gridline-color:#2a3c47;border:0;selection-background-color:#244338;outline:0;} QTableWidget::item{padding:9px 10px;border-bottom:1px solid #253641;} QHeaderView::section{background:#111c24;color:#87a4b5;border:0;border-bottom:1px solid #304550;padding:10px;font-size:9px;} QTableCornerButton::section{background:#111c24;border:0;}
QScrollBar:vertical{background:#101a21;width:7px;} QScrollBar::handle:vertical{background:#3b515e;min-height:20px;border-radius:3px;} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
QCheckBox{padding:6px;color:#9cb4bf;} QSplitter::handle{background:#263c46;width:3px;} QStatusBar{background:#101b22;color:#6f8b9d;font-size:9px;}
QDialog{background:#111c24;} QToolTip{color:#d5e2e9;background:#24353f;border:1px solid #4c697a;}
'''

def label(text,name=None):
 w=QLabel(text)
 if name:w.setObjectName(name)
 return w

def button(text,callback,primary=False):
 b=QPushButton(text);b.clicked.connect(callback)
 if primary:b.setObjectName('Primary')
 return b

def panel(title):
 f=QFrame();f.setObjectName('Panel');layout=QVBoxLayout(f);layout.setContentsMargins(18,16,18,16);layout.setSpacing(13);layout.addWidget(label(title,'MetricLabel'));return f,layout

def spin(value=0,max_value=1e15,decimals=2):
 s=QDoubleSpinBox();s.setRange(0,max_value);s.setDecimals(decimals);s.setValue(float(value));s.setGroupSeparatorShown(True);s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons);return s

def table(headers):
 t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers);t.verticalHeader().hide();t.setAlternatingRowColors(True);t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);t.setShowGrid(False);t.setMinimumHeight(150);return t

def rows(t,data):
 if getattr(t,'_rendered_rows',None)==data:return
 t._rendered_rows=data
 selected=t.currentRow();t.setUpdatesEnabled(False);t.setRowCount(len(data))
 for r,row in enumerate(data):
  for c,val in enumerate(row):
   item=QTableWidgetItem(str(val));t.setItem(r,c,item)
   if str(val).startswith('-£'):item.setForeground(QColor(RED))
 if 0<=selected<len(data):t.selectRow(selected)
 t.setUpdatesEnabled(True)

class CandleChart(QWidget):
 def __init__(self):super().__init__();self.instrument=None;self.setMinimumHeight(290)
 def set_instrument(self,ins):self.instrument=ins;self.update()
 def paintEvent(self,event):
  p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.fillRect(self.rect(),QColor('#121d25'))
  if not self.instrument:p.setPen(QColor('#839cac'));p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Create a career to open the market');return
  ins=self.instrument;bars=ins['history'][-70:];lo=min(number(ins['price']),min(b['l'] for b in bars))*.995;hi=max(number(ins['price']),max(b['h'] for b in bars))*1.005;left=15;right=self.width()-75;top=50;bottom=self.height()-32
  if hi<=lo:return
  y=lambda n:bottom-(n-lo)/(hi-lo)*(bottom-top)
  p.setFont(QFont('DejaVu Sans',10));p.setPen(QColor('#c5d8e4'));p.drawText(16,25,ins['symbol']+'   '+local(ins['price'],ins.get('currency','GBP'))+'   ·  EXECUTION')
  p.setFont(QFont('DejaVu Sans Mono',8))
  for i in range(5):
   v=lo+(hi-lo)*i/4;p.setPen(QPen(QColor('#2a3b46'),1,Qt.PenStyle.DashLine));p.drawLine(QPointF(left,y(v)),QPointF(right,y(v)));p.setPen(QColor('#7a95a6'));p.drawText(QPointF(right+10,y(v)+4),f'{v:.2f}')
  width=(right-left)/len(bars)
  for i,b in enumerate(bars):
   x=left+(i+.5)*width;color=QColor(GREEN if b['c']>=b['o'] else RED);p.setPen(QPen(color,1));p.drawLine(QPointF(x,y(b['h'])),QPointF(x,y(b['l'])));p.fillRect(QRectF(x-width*.27,min(y(b['o']),y(b['c'])),max(1,width*.54),max(1,abs(y(b['o'])-y(b['c'])))),color)
  last=number(ins['price']);p.setPen(QPen(QColor('#3f9f7a'),1,Qt.PenStyle.DashLine));p.drawLine(QPointF(left,y(last)),QPointF(right,y(last)));p.fillRect(QRectF(right,y(last)-10,70,20),QColor('#24583f'));p.setPen(QColor('#b1edc8'));p.drawText(QPointF(right+6,y(last)+4),f'{last:.2f}');p.setPen(QColor('#688697'));p.drawText(16,self.height()-10,'HOURLY MODEL CANDLES  ·  CORRELATED MARKET / SECTOR FACTORS  ·  UTC')

class CareerDialog(QDialog):
 def __init__(self,parent):
  super().__init__(parent);self.setWindowTitle('VANTAGE — New career');self.setMinimumWidth(500);layout=QVBoxLayout(self);layout.setContentsMargins(32,27,32,27);layout.setSpacing(18)
  layout.addWidget(label('VANTAGE','Brand'));layout.addWidget(label('A world of capital. Entirely yours.','Title'));intro=label('Create a persistent local world. Real company identities, independent execution markets and local accounting.');intro.setWordWrap(True);layout.addWidget(intro)
  form=QFormLayout();self.name=QLineEdit('My Vantage');self.career=QComboBox();self.career.addItems(CAREERS);self.capital=spin(5000);self.seed=QSpinBox();self.seed.setRange(0,2147483647);self.seed.setValue(42)
  for title,w in [('Career name',self.name),('Starting mandate',self.career),('Capital / institutional book · GBP',self.capital),('Deterministic world seed',self.seed)]:form.addRow(title,w)
  self.career.currentTextChanged.connect(lambda c:self.capital.setValue(float(CAREERS[c])));layout.addLayout(form);note=label('Institutional capital belongs to the book. The manager receives £5,000 personal capital.');note.setWordWrap(True);note.setObjectName('Sub');layout.addWidget(note)
  controls=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel);create=controls.addButton('Create local world',QDialogButtonBox.ButtonRole.AcceptRole);create.setObjectName('Primary');controls.accepted.connect(self.accept);controls.rejected.connect(self.reject);layout.addWidget(controls)
 def payload(self):return dict(name=self.name.text(),career=self.career.currentText(),capital=str(self.capital.value()),seed=self.seed.value())

class Terminal(QMainWindow):
 def __init__(self,path=None,onboard=True):
  super().__init__();self.setWindowTitle('VANTAGE' if __import__('vantage.paths',fromlist=['RELEASE']).RELEASE else 'VANTAGE — DEVELOPMENT — SEPARATE SAVE');self.setWindowIcon(QIcon(str(ROOT/'static'/'icon.svg')));self.resize(1560,980);self.setMinimumSize(1100,740);self.setStyleSheet(STYLE)
  self.bridge=Bridge(path,self);self.bridge.response.connect(self.receive);self.bridge.progress.connect(lambda text:self.notice.setText(text));self.pending={};self.seq=0;self.world=None;self.snapshot={};self.symbol='NVDA';self.active='personal';self.chains=[];self.selected_contract=None;self.current_page='Overview';self.position_data=[];self.order_data=[];self.loan_data=[];self.company_data=[];self.market_data=[];self.saves_data=[]
  central=QWidget();root=QHBoxLayout(central);root.setContentsMargins(0,0,0,0);root.setSpacing(0);self.setCentralWidget(central)
  sidebar=QWidget();sidebar.setFixedWidth(264);sl=QVBoxLayout(sidebar);sl.setContentsMargins(0,0,0,0);sl.setSpacing(0)
  self.nav=QListWidget();self.page_names=['Overview','Trading','Markets','Portfolio','Options','Banking','Risk','Institutions','Investors','Newswire','Corporate Actions','Communications','Investigations','Career','Administration','Settings','Financial Statements','Institutional Operations','Oversight','Bank Management'];self.nav.addItems(self.page_names);self.nav.currentTextChanged.connect(self.navigate);self.nav.setParent(self);self.nav.hide();root.addWidget(sidebar)
  body=QWidget();bl=QVBoxLayout(body);bl.setContentsMargins(22,12,22,12);bl.setSpacing(15);root.addWidget(body,1)
  top=QHBoxLayout();self.breadcrumb=label('Workspace / Overview');top.addWidget(self.breadcrumb);top.addStretch();self.accounts=QComboBox();self.accounts.setMinimumWidth(220);self.accounts.currentIndexChanged.connect(self.change_account);top.addWidget(self.accounts);top.addWidget(button('New career',self.new_career));bl.addLayout(top)
  clock=QHBoxLayout();clock.addWidget(label('GLOBAL MARKETS','Sub'));self.time_label=label('NO WORLD');clock.addWidget(self.time_label);clock.addStretch();self.speed=QComboBox();self.speed.addItems(['1h / cycle','6h / cycle','1d / cycle']);self.speed.currentIndexChanged.connect(lambda i:self.send('control',{'speed':[1,6,24][i]}));clock.addWidget(self.speed);self.pause=button('▶ Resume',lambda:self.send('control',{'paused':not self.world['paused']}) if self.world else None);clock.addWidget(self.pause);clock.addWidget(button('+ 1 hour',lambda:self.send('advance',{'hours':1})));clock.addWidget(button('+ 1 day',lambda:self.send('advance',{'hours':24})));bl.addLayout(clock)
  self.title=label('Portfolio overview','Title');bl.addWidget(self.title);self.notice=label('Execution prices evolve independently of archived exchange references. Every committed action saves locally.','Notice');self.notice.setWordWrap(True);bl.addWidget(self.notice)
  self.metric_values={};metricrow=QHBoxLayout()
  for key,title in [('equity','NET LIQUIDATION VALUE'),('profit','INVESTMENT P&L'),('cash','AVAILABLE CASH'),('gross','GROSS EXPOSURE')]:
   f,l=panel(title);value=label('£0.00','MetricValue');self.metric_values[key]=value;l.addWidget(value);metricrow.addWidget(f)
  bl.addLayout(metricrow);self.stack=QStackedWidget();bl.addWidget(self.stack,1);self.pages={};self.build_pages();self.build_employee_workspace()
  from .navigation_ui import NativeWorkspaceNavigation
  self.navigation=NativeWorkspaceNavigation(self.page_names,lambda route:self.nav.setCurrentRow(self.page_names.index(route)),self.command);sl.addWidget(self.navigation);self.nav.setCurrentRow(0)
  self.statusBar().showMessage('Engine connected   ·   SQLite transactional saves   ·   GBP base currency   ·   NO REAL-MONEY TRADING   ·   v0.7.0-phase-a')
  QShortcut(QKeySequence('Alt+T'),self,activated=lambda:self.nav.setCurrentRow(1));QShortcut(QKeySequence('Alt+P'),self,activated=lambda:self.nav.setCurrentRow(3));QShortcut(QKeySequence('Ctrl+K'),self,activated=self.command)
  self.refresh_timer=QTimer(self);self.refresh_timer.timeout.connect(lambda:self.send('state',get=True));self.refresh_timer.start(4000);self.send('state',get=True)
  if onboard and self.bridge.engine.state is None:QTimer.singleShot(100,self.new_career)
 def build_employee_workspace(self):
  from .employee_ui import EmployeePanel
  from PyQt6.QtWidgets import QScrollArea
  self.page_names.append('Employees');self.nav.addItem('Employees');self.employee_panel=EmployeePanel(self);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.employee_panel);self.add_page('Employees').addWidget(scroll)
  from .research_ui import ResearchPanel
  self.page_names.append('Research');self.nav.addItem('Research');self.research_panel=ResearchPanel(self);self.add_page('Research').addWidget(self.research_panel)
  from .corporate_ui import CorporatePanel
  self.page_names.append('Corporate Structure');self.nav.addItem('Corporate Structure');self.corporate_panel=CorporatePanel(self);self.add_page('Corporate Structure').addWidget(self.corporate_panel)
  from .ma_ui import MAPanel
  self.page_names.append('Company Acquisitions');self.nav.addItem('Company Acquisitions');self.ma_panel=MAPanel(self);self.add_page('Company Acquisitions').addWidget(self.ma_panel)
  self.page_names.append('My Companies');self.nav.addItem('My Companies');self.my_companies_panel=MAPanel(self,owned=True);self.add_page('My Companies').addWidget(self.my_companies_panel)
  from .wealth_ui import WealthPanel
  self.page_names.append('Wealth & Lifestyle');self.nav.addItem('Wealth & Lifestyle');self.wealth_panel=WealthPanel(self);self.add_page('Wealth & Lifestyle').addWidget(self.wealth_panel)
  from .executive_ui import ExecutivePanel
  self.page_names.append('Executive Office');self.nav.addItem('Executive Office');self.executive_panel=ExecutivePanel(self);executive_scroll=QScrollArea();executive_scroll.setWidgetResizable(True);executive_scroll.setWidget(self.executive_panel);self.add_page('Executive Office').addWidget(executive_scroll)
  from .living_world_ui import LivingWorldPanel
  self.page_names.append('Financial Crime');self.nav.addItem('Financial Crime');self.living_world_panel=LivingWorldPanel(self);crime_scroll=QScrollArea();crime_scroll.setWidgetResizable(True);crime_scroll.setWidget(self.living_world_panel);self.add_page('Financial Crime').addWidget(crime_scroll)
  from .office_ui import OfficePanel
  self.page_names.append('Property & offices');self.nav.addItem('Property & offices');self.office_panel=OfficePanel(self);self.add_page('Property & offices').addWidget(self.office_panel)
  self.pages['Trading'].layout().addWidget(button('Request Analysis / Research',lambda:self.nav.setCurrentRow(self.page_names.index('Research'))))
  from .federal_reserve_ui import FederalReservePanel
  self.page_names.append('Federal Reserve');self.nav.addItem('Federal Reserve');self.fed_panel=FederalReservePanel(self);self.add_page('Federal Reserve').addWidget(self.fed_panel)
 def add_page(self,name):
  p=QWidget();l=QVBoxLayout(p);l.setContentsMargins(0,0,0,0);l.setSpacing(15);self.pages[name]=p;self.stack.addWidget(p);return l
 def send(self,action,p=None,get=False,callback=None,force_full=False):
  if callable(get) and callback is None:callback=get;get=False
  if action=='state' and get:
   existing=next((id for id,(pending_action,_) in self.pending.items() if pending_action=='state'),None)
   if existing is not None:return existing
  self.seq+=1;i=str(self.seq);self.pending[i]=(action,callback);self.bridge.request(i,json.dumps({'path':'/api/'+action,'method':'GET' if get else 'POST','body':p or {},'view':('banking' if self.current_page in ('Bank Management','Banking') else 'trading' if self.current_page in ('Trading','Portfolio','Options','Risk') else 'full') if not force_full else 'full','key':__import__('uuid').uuid4().hex}));return i
 def receive(self,id,encoded):
  action,callback=self.pending.pop(id,('state',None));r=json.loads(encoded)
  if action in ('block_quote','block_accept') and hasattr(self,'block_quote_button'):
   self.block_quote_button.setEnabled(True);self.block_quote_button.setText('Institutional inventory-backed block RFQ')
  if not r['ok']:self.notice.setText('Action failed: '+r['data']['error']);self.notice.setStyleSheet('color:#f2a5b2;background:#3c2531;border-color:#754654;');return
  data=r['data'];result=data.get('result') if action!='state' else None
  if action=='state':self.apply(data)
  elif 'state' in data:self.apply(data['state'])
  if action not in ('state','chain'):
   rejected=isinstance(result,dict) and result.get('status')=='REJECTED'
   text=('Rejected: '+result.get('reason','')) if rejected else ('Credit application declined by underwriting' if action=='loan' and not result.get('approved') else (result.get('message','') if isinstance(result,dict) else '') or action.replace('_',' ').capitalize()+' completed and saved')
   self.notice.setText(text);self.notice.setStyleSheet('color:#f2a5b2;background:#3c2531;' if rejected else '')
  if callback:callback(result if result is not None else data)
  received=data if action=='state' else data.get('state',{})
  if received.get('_partial') and self.current_page not in ('Bank Management','Banking','Trading','Portfolio','Options','Risk'):self.send('state',get=True)
 def navigate(self,name):
  previous_page=self.current_page
  if name not in self.pages:return
  if hasattr(self,'navigation'):self.navigation.sync_page(name)
  from .navigation_ui import navigation_label,workspace_for,WORKSPACES
  display=navigation_label(name);group=next(label for id,label,_,_ in WORKSPACES if id==workspace_for(name))
  self.current_page=name;self.stack.setCurrentWidget(self.pages[name]);self.title.setText({'Overview':'Portfolio overview','Trading':'Trading desk','Options':'Options laboratory'}.get(name,display));self.breadcrumb.setText(group+'  /  '+display)
  if self.world:
   panel={'Federal Reserve':self.fed_panel,'Employees':self.employee_panel,'Research':self.research_panel,'Wealth & Lifestyle':self.wealth_panel,'Property & offices':self.office_panel,'Financial Crime':self.living_world_panel,'Executive Office':self.executive_panel,'Corporate Structure':self.corporate_panel,'Company Acquisitions':self.ma_panel,'My Companies':self.my_companies_panel}.get(name)
   if panel:panel.refresh(self.world)
  if previous_page!=name:self.send('state',get=True)
 def new_career(self):
  dialog=CareerDialog(self)
  if dialog.exec()==QDialog.DialogCode.Accepted:self.send('create',dialog.payload())
 def change_account(self):
  a=self.accounts.currentData()
  if a:self.active=a;self.render()
 def command(self):
  from .navigation_ui import navigation_label
  names={navigation_label(route):route for route in self.page_names}
  value,ok=QInputDialog.getItem(self,'Workspace search','Open workspace',list(names),0,True)
  if ok:
   value=names.get(value,value)
   if value in self.page_names:self.nav.setCurrentRow(self.page_names.index(value))
   elif self.world and value.upper() in self.world['instruments']:self.symbol=value.upper();self.trade_symbols.setCurrentText(self.symbol);self.nav.setCurrentRow(1)
 def build_pages(self):
  overview=self.add_page('Overview');self.overview_split=QSplitter(Qt.Orientation.Horizontal);overview.addWidget(self.overview_split)
  left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(0,0,0,0);self.overview_chart=CandleChart();f,l=panel('MARKET PULSE  /  VANTAGE 100');l.addWidget(self.overview_chart);ll.addWidget(f,2);self.overview_positions=table(['INSTRUMENT','QUANTITY','MARKET VALUE','UNREALISED P&L']);ll.addWidget(self.overview_positions,1);self.overview_split.addWidget(left)
  right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(0,0,0,0);f,l=panel('ECONOMIC CONDITIONS');self.economy=label('');self.economy.setWordWrap(True);l.addWidget(self.economy);rl.addWidget(f);f,l=panel('THE WIRE  /  FICTIONAL WORLD');self.overview_wire=QTextEdit();self.overview_wire.setReadOnly(True);l.addWidget(self.overview_wire);rl.addWidget(f,1);self.overview_split.addWidget(right);self.overview_split.setSizes([850,380])
  trading=self.add_page('Trading');split=QSplitter(Qt.Orientation.Horizontal);trading.addWidget(split);center=QWidget();cl=QVBoxLayout(center);cl.setContentsMargins(0,0,0,0);self.trade_symbols=QComboBox();self.trade_symbols.currentTextChanged.connect(self.choose_symbol);cl.addWidget(self.trade_symbols);self.chart=CandleChart();cl.addWidget(self.chart,2);self.trade_positions=table(['INSTRUMENT','QUANTITY','MARK','VALUE','UNREALISED P&L']);cl.addWidget(self.trade_positions,1);split.addWidget(center)
  f,l=panel('ORDER TICKET  /  SIMULATED');f.setMinimumWidth(285);form=QFormLayout();self.order_side=QComboBox();self.order_side.addItems(['Buy Long','Sell Owned','Sell Short','Buy to Cover']);self.order_type=QComboBox();self.order_type.addItems(['market','limit','stop','stop_limit','trailing','bracket']);self.order_qty=spin(10,1e15,0);self.order_limit=spin(100);self.order_stop=spin(95);self.order_trail=spin(5,99,2);self.order_take=spin(110);self.order_loss=spin(90);self.order_margin=QCheckBox('Margin financing (required automatically for Sell Short / Buy to Cover)')
  for title,w in [('Side',self.order_side),('Order type',self.order_type),('Quantity',self.order_qty),('Limit / GBP',self.order_limit),('Stop / GBP',self.order_stop),('Trail / %',self.order_trail),('Take profit',self.order_take),('Stop loss',self.order_loss)]:form.addRow(title,w)
  self.order_algo=QComboBox();self.order_algo.addItems(['MARKET','TWAP','VWAP','POV','ICEBERG']);self.order_algo.currentTextChanged.connect(lambda value:self.order_type.setCurrentText('limit') if value=='ICEBERG' else None);self.order_hours=QSpinBox();self.order_hours.setRange(2,744);self.order_hours.setValue(24);self.order_pov=spin(.1,.5,3);self.order_pov.setMinimum(.001);self.order_display=spin(1000,1e15,0);self.order_tif=QComboBox();self.order_tif.addItems(['GTC','IOC','FOK']);form.addRow('Execution strategy',self.order_algo);form.addRow('Schedule hours',self.order_hours);form.addRow('POV fraction',self.order_pov);form.addRow('Iceberg displayed quantity',self.order_display);form.addRow('Time in force',self.order_tif)
  self.order_urgency=QComboBox();self.order_urgency.addItems(['NORMAL','PATIENT','URGENT']);self.order_maxpart=spin(.25,1,3);self.order_maxpart.setMinimum(.001);self.order_slippage=spin(100,5000,1);self.order_after=QComboBox();self.order_after.addItems(['CARRY','PAUSE','CANCEL']);form.addRow('Urgency',self.order_urgency);form.addRow('Max modeled participation',self.order_maxpart);form.addRow('Arrival slippage guard · bps',self.order_slippage);form.addRow('After active-hour window',self.order_after);self.order_urgency.currentTextChanged.connect(lambda u:self.order_maxpart.setValue({'NORMAL':.25,'PATIENT':.1,'URGENT':.5}[u]))
  self.block_quote_button=button('Institutional inventory-backed block RFQ',self.native_block_quote);l.addWidget(self.block_quote_button);l.addWidget(button('Market institutions / AUM and cash',self.show_institutional_market))
  self.order_limit.setDecimals(4);self.order_stop.setDecimals(4);self.order_take.setDecimals(4);self.order_loss.setDecimals(4);self.order_form=form;self.order_type.currentTextChanged.connect(self.order_fields);self.order_fields();l.addLayout(form);l.addWidget(self.order_margin);l.addWidget(button('Place simulated order ↗',self.place_order,True));self.order_note=label('Fills include spreads, market impact and fees. Liquidity is shared per simulation hour.');self.order_note.setWordWrap(True);self.order_note.setObjectName('Sub');l.addWidget(self.order_note);self.native_depth=table(['BID QTY','BID','ASK','ASK QTY']);self.native_depth.setMaximumHeight(240);self.native_depth.cellClicked.connect(self.depth_select);l.addWidget(self.native_depth);l.addStretch();ticket_scroll=QScrollArea();ticket_scroll.setWidgetResizable(True);ticket_scroll.setWidget(f);split.addWidget(ticket_scroll);split.setSizes([900,320])
  from .market_ui import MarketPanel
  markets=self.add_page('Markets');self.market_panel=MarketPanel(self);markets.addWidget(self.market_panel);self.market_search=self.market_panel.search;self.market_table=self.market_panel.table
  portfolio=self.add_page('Portfolio');self.positions=table(['INSTRUMENT','QUANTITY','MARK','MARKET VALUE','UNREALISED P&L','COST']);portfolio.addWidget(self.positions,2);portfolio.addWidget(button('Close selected position',self.close_position));self.orders=table(['ID','INSTRUMENT','SIDE / TYPE','FILLED / TOTAL','LEVEL','STATUS']);portfolio.addWidget(self.orders,1);self.order_page=QSpinBox();self.order_page.setRange(0,100000);self.order_page.setPrefix('Order page (100 rows) ');self.order_page.valueChanged.connect(lambda:self.render_order_rows());portfolio.addWidget(self.order_page);self.execution_detail=QPlainTextEdit();self.execution_detail.setReadOnly(True);self.execution_detail.setMaximumHeight(180);portfolio.addWidget(self.execution_detail);self.orders.cellClicked.connect(lambda row,col:self.show_execution_detail(row));actions=QHBoxLayout();actions.addWidget(button('Cancel selected order',self.cancel_order));actions.addWidget(button('Modify selected order level',self.modify_order));actions.addStretch();portfolio.addLayout(actions)
  options=self.add_page('Options');head=QHBoxLayout();self.option_under=QComboBox();head.addWidget(self.option_under);self.option_days=QSpinBox();self.option_days.setRange(1,730);self.option_days.setValue(30);head.addWidget(label('Days to expiry'));head.addWidget(self.option_days);head.addWidget(button('Generate theoretical chain',self.generate_chain,True));head.addStretch();options.addLayout(head);strategyrow=QHBoxLayout();strategyrow.addWidget(label('Atomic strategies / uses contracts below'))
  for kind,title in [('straddle','Buy long straddle'),('strangle','Buy long strangle'),('protective_put','Buy shares + protective put')]:strategyrow.addWidget(button(title,lambda _,k=kind:self.option_strategy(k)))
  options.addLayout(strategyrow);self.option_chain=table(['CALL Δ','CALL PREMIUM','STRIKE','PUT PREMIUM','PUT Δ']);self.option_chain.cellClicked.connect(self.select_option);options.addWidget(self.option_chain);foot=QHBoxLayout();self.option_choice=label('Select a call or put premium. Model European cash-settled contracts; 100 shares per contract.');self.option_choice.setWordWrap(True);foot.addWidget(self.option_choice,1);self.option_qty=spin(1,100000,0);self.option_qty.setMaximumWidth(110);foot.addWidget(self.option_qty);foot.addWidget(button('Buy selected contract',self.buy_option,True));options.addLayout(foot)
  banking=self.add_page('Banking');top=QHBoxLayout();f,l=panel('APPLY FOR A TERM LOAN');form=QFormLayout();self.bank_choice=QComboBox();self.loan_amount=spin(1000);self.loan_months=QSpinBox();self.loan_months.setRange(1,360);self.loan_months.setValue(12);form.addRow('Lending bank',self.bank_choice);form.addRow('Principal · GBP',self.loan_amount);form.addRow('Term · months',self.loan_months);l.addLayout(form);l.addWidget(button('Submit underwritten application',self.apply_loan,True));self.credit_label=label('');self.credit_label.setWordWrap(True);l.addWidget(self.credit_label);top.addWidget(f);self.bank_table=table(['BANK','LIQUIDITY','LOAN BOOK','EQUITY']);top.addWidget(self.bank_table,2);banking.addLayout(top);savingrow=QHBoxLayout();self.savings_amount=spin(1000);savingrow.addWidget(label('Savings transfer / GBP'));savingrow.addWidget(self.savings_amount);savingrow.addWidget(button('Deposit to savings',lambda:self.savings_transfer('deposit')));savingrow.addWidget(button('Withdraw savings',lambda:self.savings_transfer('withdraw')));self.savings_info=label('');savingrow.addWidget(self.savings_info,1);banking.addLayout(savingrow);self.loans=table(['ID','BANK','BALANCE','APR','PAYMENT','STATUS']);banking.addWidget(self.loans);banking.addWidget(button('Repay selected facility',self.repay_loan))
  risk=self.add_page('Risk');self.risk_table=table(['RISK MEASURE','VALUE','MODEL / INTERPRETATION']);risk.addWidget(self.risk_table);stress=QHBoxLayout();stress.addWidget(label('Parallel price shock %'));self.stress=QSpinBox();self.stress.setRange(-80,80);self.stress.setValue(-20);self.stress.valueChanged.connect(self.render_risk);stress.addWidget(self.stress);self.stress_label=label('');stress.addWidget(self.stress_label,1);risk.addLayout(stress);note=label('Parametric normal approximation: 25% volatility, 0.35 common correlation. Marked-value option exposure understates nonlinear risk. The stress preview is linear and changes no balances.');note.setWordWrap(True);risk.addWidget(note)
  self.fund_type=QComboBox();self.fund_type.addItems(['investment_fund','hedge_fund','private_equity','credit_fund'])
  institutions=self.add_page('Institutions');f,l=panel('ESTABLISH A SEGREGATED FUND');form=QFormLayout();self.fund_name=QLineEdit('New Vantage Fund');self.fund_seed=spin(1000);form.addRow('Fund name',self.fund_name);form.addRow('Mandate type',self.fund_type);form.addRow('Personal seed · GBP',self.fund_seed);l.addLayout(form);l.addWidget(button('Create investment fund',lambda:self.send('fund',{'name':self.fund_name.text(),'amount':str(self.fund_seed.value()),'fund_type':self.fund_type.currentText()}),True));institutions.addWidget(f);self.funds=table(['FUND','ACTUAL NAV','CASH','UNITS','NAV / UNIT','MONTHLY BUDGET']);institutions.addWidget(self.funds);institutions.addWidget(button('Set selected fund operating budget',self.fund_budget));institutions.addWidget(button('Market institutions / AUM and cash',self.show_institutional_market))
  investors=self.add_page('Investors');self.npcs=table(['INVESTOR','AVAILABLE WEALTH','TRUST','RISK PREFERENCE']);investors.addWidget(self.npcs);form=QFormLayout();self.investor_fund=QComboBox();self.investor_choice=QComboBox();self.sub_amount=spin(10000);form.addRow('Fund',self.investor_fund);form.addRow('Investor',self.investor_choice);form.addRow('Allocation · GBP',self.sub_amount);investors.addLayout(form);buttons=QHBoxLayout();buttons.addWidget(button('Request investor subscription',self.subscribe,True));buttons.addWidget(button('Redeem investor units',self.redeem));buttons.addWidget(button('Publish NAV statement',self.report));investors.addLayout(buttons);self.ownership=table(['INVESTOR','UNITS','OWNERSHIP','ACTUAL REDEMPTION VALUE']);self.investor_fund.currentIndexChanged.connect(self.render_ownership);investors.addWidget(self.ownership);self.redemption_queue=table(['REQUEST','INVESTOR','ENTITLEMENT','PAID','STILL OWED / STATUS']);investors.addWidget(self.redemption_queue)
  self.investor_evidence=label('');self.investor_evidence.setWordWrap(True);investors.addWidget(self.investor_evidence);self.investor_detail=table(['INVESTOR','SUBSCRIBED / OPENING BASIS','UNITS / OWNERSHIP','VALUE / PERFORMANCE','REDEMPTIONS PAID / DUE','LATEST DECISION']);investors.addWidget(self.investor_detail)
  news=self.add_page('Newswire');self.wire=QTextEdit();self.wire.setReadOnly(True);news.addWidget(self.wire)
  corporate=self.add_page('Corporate Actions');self.corporations=table(['SYMBOL','COMPANY','REVENUE','PROFIT','DEBT','SHARES']);corporate.addWidget(self.corporations);actions=QHBoxLayout()
  for kind,title in [('earnings','Profit warning'),('dividend','Cash dividend'),('split','2:1 share split')]:actions.addWidget(button(title,lambda _,k=kind:self.corporate(k)))
  corporate.addLayout(actions);corporate.addWidget(label('Select a company. Each scenario changes fundamentals, accounting and news.'))
  communications=self.add_page('Communications');commrow=QHBoxLayout();self.comm_fund=QComboBox();self.comm_recipient=QComboBox();self.comm_intent=QComboBox();self.comm_intent.addItems(['Verified investor update','Discuss risk preferences','Disclose corrected NAV']);commrow.addWidget(self.comm_fund);commrow.addWidget(self.comm_recipient);commrow.addWidget(self.comm_intent);commrow.addWidget(button('Send structured communication',self.communicate,True));communications.addLayout(commrow);self.inbox=QTextEdit();self.inbox.setReadOnly(True);communications.addWidget(self.inbox)
  investigation=self.add_page('Investigations');self.cases=table(['CASE','STATUS','EVIDENCE','OPENED']);investigation.addWidget(self.cases);self.claims=table(['PUBLISHED','ACTUAL NAV','REPORTED NAV','GAP','STATUS','EVIDENCE']);investigation.addWidget(self.claims)
  career=self.add_page('Career');self.career_info=label('');self.career_info.setWordWrap(True);career.addWidget(self.career_info);self.career_choice=QComboBox();self.career_choice.addItems(CAREERS);career.addWidget(self.career_choice);career.addWidget(button('Change mandate, preserve books',lambda:self.send('admin',{'op':'career','career':self.career_choice.currentText()})));career.addWidget(button('Start a separate career',self.new_career,True));career.addStretch()
  admin=self.add_page('Administration');actions=QHBoxLayout();actions.addWidget(button('Adjust account capital',self.admin_cash,True));actions.addWidget(button('Set execution price',self.admin_price));actions.addWidget(button('Set policy rate',self.admin_rate));actions.addWidget(button('Advance simulation',self.admin_advance));actions.addWidget(button('Economic scenario',self.admin_scenario));actions.addWidget(button('Reconcile ledger',lambda:self.send('reconcile')));admin.addLayout(actions);self.journal=table(['TIME','DESCRIPTION','DOUBLE-ENTRY LINES']);admin.addWidget(self.journal);self.audit=table(['TIME','ACTION','DETAIL']);admin.addWidget(self.audit)
  settings=self.add_page('Settings');self.saves=table(['NAME','SAVE ID','UPDATED']);settings.addWidget(self.saves);actions=QHBoxLayout();actions.addWidget(button('Load selected world',self.load_save));actions.addWidget(button('Create consistent backup',lambda:self.send('backup')));actions.addWidget(button('Restore a backup',self.restore));settings.addLayout(actions);note=label('User-specific local save storage\nEvery successful action saves atomically. Backups retain 20 snapshots.\nNative compatibility terminal shares the engine and saves with the React terminal.\nAlt T: trading  ·  Alt P: portfolio  ·  Ctrl K: workspace search\nExecution markets and scenario news are independent of real exchanges. Advanced unsupported systems are documented in KNOWN_LIMITATIONS.md.');note.setWordWrap(True);settings.addWidget(note)
  statement=self.add_page('Financial Statements');self.statement_summary=label('');self.statement_summary.setWordWrap(True);statement.addWidget(self.statement_summary);self.statement_table=table(['TIME','DESCRIPTION','CASH CHANGE','RUNNING CASH','POSTINGS']);statement.addWidget(self.statement_table)
  ops=self.add_page('Institutional Operations');form=QFormLayout();self.ops_name=QLineEdit('Native operating subsidiary');self.ops_seed=spin(1000);self.ops_source=QComboBox();self.ops_destination=QComboBox();self.ops_kind=QComboBox();self.ops_kind.addItems(['loan','service','consulting','distribution','equity','collateral']);self.ops_kind.addItem('Unauthorised appropriation','appropriation');self.ops_amount=spin(100);self.ops_override=QCheckBox('Record disputed governance override');form.addRow('New legal entity',self.ops_name);form.addRow('Capital from selected account · GBP',self.ops_seed);ops.addLayout(form);ops.addWidget(button('Create funded subsidiary',lambda:self.send('entity_create',{'parent':self.active,'name':self.ops_name.text(),'capital':str(self.ops_seed.value())}),True));form=QFormLayout();form.addRow('Source property',self.ops_source);form.addRow('Recipient',self.ops_destination);form.addRow('Classification',self.ops_kind);form.addRow('Amount / declared value · GBP',self.ops_amount);ops.addLayout(form);ops.addWidget(self.ops_override);ops.addWidget(button('Submit institutional instruction',self.native_instruction,True));self.native_transactions=table(['REFERENCE','SOURCE / DESTINATION','CLASSIFICATION','AMOUNT','STATUS']);ops.addWidget(self.native_transactions)
  oversight=self.add_page('Oversight');form=QFormLayout();self.oversight_entity=QComboBox();self.native_case=QComboBox();self.native_concern=QLineEdit('Request documented transaction review');form.addRow('Institution',self.oversight_entity);form.addRow('Observable concern',self.native_concern);form.addRow('Proceeding',self.native_case);oversight.addLayout(form);oversight.addWidget(button('Register documented concern',lambda:self.send('complaint',{'entity':self.oversight_entity.currentData(),'reason':self.native_concern.text()})));self.case_respond=button('Provide preserved records',lambda:self.send('case_response',{'id':self.native_case.currentData(),'response':'provide_records'}));oversight.addWidget(self.case_respond);oversight.addWidget(button('Appoint administrator',self.native_administration));self.native_cases=table(['CASE','ENTITY','STAGE','EVIDENCE INDEX','DEADLINE']);oversight.addWidget(self.native_cases)
  banks=self.add_page('Bank Management');form=QFormLayout();self.player_bank_choice=QComboBox();self.player_bank_info=label('Select a bank, capitalise it through its direct parent, and apply for a licence.');self.player_bank_info.setWordWrap(True);self.player_bank_choice.currentIndexChanged.connect(self.native_bank_render);form.addRow('Player-owned bank',self.player_bank_choice);banks.addLayout(form);banks.addWidget(self.player_bank_info);banks.addWidget(button('Apply / review banking licence',lambda:self.send('bank_licence',{'entity':self.player_bank_choice.currentData()})));self.bank_seed=spin(100000);form=QFormLayout();form.addRow('Capital injection from direct parent · GBP',self.bank_seed);banks.addLayout(form);banks.addWidget(button('Submit capital injection',self.native_bank_capital));self.bank_deposit_rate=spin(2,20);self.bank_lending_rate=spin(8,50);self.bank_max_loan=spin(10000);self.bank_reserve=spin(10,100);self.bank_lending=QCheckBox('Accept authorised loan applications');self.bank_lending.setChecked(True);form=QFormLayout();form.addRow('Savings APR · %',self.bank_deposit_rate);form.addRow('Lending APR · %',self.bank_lending_rate);form.addRow('Maximum loan · GBP',self.bank_max_loan);form.addRow('Reserves · % of deposits (minimum 10)',self.bank_reserve);banks.addLayout(form);banks.addWidget(self.bank_lending);banks.addWidget(button('Save banking products',lambda:self.send('bank_policy',{'entity':self.player_bank_choice.currentData(),'deposit_rate':self.bank_deposit_rate.value(),'lending_rate':self.bank_lending_rate.value(),'max_loan':str(self.bank_max_loan.value()),'reserve_ratio':self.bank_reserve.value()/100,'lending_enabled':self.bank_lending.isChecked()})));self.bank_customer=QComboBox();self.bank_customer_product=QComboBox();self.bank_customer_product.addItems(['current','savings']);self.bank_customer_amount=spin(1000);form=QFormLayout();form.addRow('Controlled customer account',self.bank_customer);form.addRow('Account product',self.bank_customer_product);form.addRow('Customer amount · GBP',self.bank_customer_amount);banks.addLayout(form);banks.addWidget(button('Open / deposit customer funds',lambda:self.send('bank_customer_transfer',{'account':self.bank_customer.currentData(),'bank':self.player_bank_choice.currentData(),'product':self.bank_customer_product.currentText(),'amount':str(self.bank_customer_amount.value()),'direction':'deposit'})));banks.addWidget(button('Withdraw customer funds',lambda:self.send('bank_customer_transfer',{'account':self.bank_customer.currentData(),'bank':self.player_bank_choice.currentData(),'product':self.bank_customer_product.currentText(),'amount':str(self.bank_customer_amount.value()),'direction':'withdraw'})));banks.addWidget(button('Request 12-month loan for customer',lambda:self.send('loan',{'account':self.bank_customer.currentData(),'bank':self.player_bank_choice.currentData(),'amount':str(self.bank_customer_amount.value()),'months':12})));self.player_bank_customers=table(['CUSTOMER','PRODUCT','BALANCE']);self.player_bank_loans=table(['BORROWER','OUTSTANDING','APR','STATUS']);banks.addWidget(self.player_bank_customers);banks.addWidget(self.player_bank_loans)
 def native_bank_capital(self):
  entity=self.player_bank_choice.currentData()
  if not entity:return
  parent=self.world['entities'][entity]['parent']
  if QMessageBox.question(self,'Bank capital','Transfer '+gbp(self.bank_seed.value())+' from the bank’s direct parent as equity?')==QMessageBox.StandardButton.Yes:self.send('related',{'source':parent,'destination':entity,'kind':'equity','amount':str(self.bank_seed.value())})
 def native_bank_render(self):
  if not self.world:return
  entity=self.player_bank_choice.currentData();b=self.world.get('player_banks',{}).get(entity,{})
  self.player_bank_info.setText('Licence: '+b.get('licence','UNLICENSED')+' · Minimum capital: '+gbp(b.get('required_capital',100000))+'\nCash '+gbp(b.get('cash',0))+' · Deposits '+gbp(b.get('deposits',0))+' · Operating capital '+gbp(b.get('equity',b.get('cash',0)))+' · Available after reserves '+gbp(b.get('available_liquidity',0))+'\nInterest income '+gbp(b.get('interest_income',0))+' · Interest expense '+gbp(b.get('interest_expense',0))+' · Profit '+gbp(b.get('profit',0))+' · Accounts '+str(b.get('accounts',0))+' · Defaults '+str(b.get('defaults',0)))
  signature=(entity,b.get('deposit_rate',2),b.get('lending_rate',8),b.get('max_loan',10000),b.get('reserve_ratio',.1),b.get('lending_enabled',True))
  if getattr(self,'_bank_policy_loaded',None)!=signature:
   for widget,key,default in [(self.bank_deposit_rate,'deposit_rate',2),(self.bank_lending_rate,'lending_rate',8),(self.bank_max_loan,'max_loan',10000)]:widget.setValue(float(b.get(key,default)))
   self.bank_reserve.setValue(float(b.get('reserve_ratio',.1))*100);self.bank_lending.setChecked(b.get('lending_enabled',True));self._bank_policy_loaded=signature
  selected=self.bank_customer.currentData();self.bank_customer.blockSignals(True);self.bank_customer.clear()
  for account in self.bridge.engine.controlled_accounts():
   if account!=entity:self.bank_customer.addItem(self.world['entities'].get(account,{}).get('name',account),account)
  if self.bank_customer.findData(selected)>=0:self.bank_customer.setCurrentIndex(self.bank_customer.findData(selected))
  self.bank_customer.blockSignals(False)
  def customer_name(account):return next((n['name'] for n in self.world['npcs'] if 'npc_'+n['id']==account),self.world['entities'].get(account,{}).get('name',account))
  rows(self.player_bank_customers,[[c.get('identity',{}).get('name',customer_name(c['account']))+' / '+c.get('identity',{}).get('kind','unclassified'),c['product'],gbp(c['balance'])] for c in b.get('customer_accounts',[])]);rows(self.player_bank_loans,[[customer_name(l['account']),gbp(l['balance']),str(l['rate'])+'%',l['status']] for l in b.get('loans_detail',[])])
 def native_instruction(self):self.send('related',{'source':self.ops_source.currentData(),'destination':self.ops_destination.currentData(),'kind':self.ops_kind.currentData() or self.ops_kind.currentText(),'amount':str(self.ops_amount.value()),'fair_value':str(self.ops_amount.value()),'rate':5,'months':12,'disclosed':True,'mode':'override' if self.ops_override.isChecked() else 'ordinary'})
 def native_administration(self):
  entity=self.oversight_entity.currentData()
  if entity and QMessageBox.question(self,'Administration','Suspend ordinary authority and realise actual assets for creditors?')==QMessageBox.StandardButton.Yes:self.send('administration',{'entity':entity})
 def apply(self,snapshot):
  partial=snapshot.get('_partial',False);self._last_snapshot_partial=bool(partial)
  if partial:
   if not self.world or self.world['id']!=snapshot['world']['id']:return self.send('state',get=True,force_full=True)
   snapshot={**self.snapshot,**snapshot,'world':{**self.world,**snapshot['world']}};snapshot.pop('_partial',None)
   if 'market_marks' in snapshot['world']:
    snapshot['world']['instruments']={symbol:{**ins,**snapshot['world']['market_marks'].get(symbol,{})} for symbol,ins in self.world['instruments'].items()};snapshot['world'].pop('market_marks')
  previous_world=self.world['id'] if self.world else None;self.snapshot=snapshot;self.world=snapshot.get('world');self.saves_data=snapshot.get('saves',[]);rows(self.saves,[[s['name'],s['id'],s['updated'][:19]] for s in self.saves_data])
  if not self.world:return
  w=self.world
  previous_bank=self.player_bank_choice.currentData();self.player_bank_choice.blockSignals(True);self.player_bank_choice.clear()
  for entity in w.get('entities',{}).values():
   if entity['kind']=='bank' and entity['controlled']:self.player_bank_choice.addItem(entity['name'],entity['id'])
  if self.player_bank_choice.findData(previous_bank)>=0:self.player_bank_choice.setCurrentIndex(self.player_bank_choice.findData(previous_bank))
  self.player_bank_choice.blockSignals(False);self.native_bank_render()
  if previous_world!=w['id']:self.active='book' if 'book' in w['metrics'] else 'personal'
  accounts=[('Personal account','personal')]+[(f['name'],f['id']) for f in w['funds']]+[(e['name'],e['id']) for e in w.get('entities',{}).values() if e['controlled'] and e['kind'] in ('company','holding','credit_fund','bank')]
  if self.active not in w['metrics']:self.active='personal'
  self.accounts.blockSignals(True);self.accounts.clear()
  for name,id in accounts:self.accounts.addItem(name,id)
  self.accounts.setCurrentIndex(self.accounts.findData(self.active));self.accounts.blockSignals(False)
  for combo in [self.ops_source,self.ops_destination,self.oversight_entity]:
   selected=combo.currentData();combo.blockSignals(True);combo.clear()
   for title,id in accounts:combo.addItem(title,id)
   if combo.findData(selected)>=0:combo.setCurrentIndex(combo.findData(selected))
   combo.blockSignals(False)
  current=self.native_case.currentData();self.native_case.clear()
  for case in w.get('legal_cases',[]):self.native_case.addItem(case['id']+' / '+case['stage'],case['id'])
  if self.native_case.findData(current)>=0:self.native_case.setCurrentIndex(self.native_case.findData(current))
  self.case_respond.setEnabled(bool(w.get('legal_cases')))
  symbols=list(w['instruments']);self.symbol=self.symbol if self.symbol in symbols else symbols[0];self.trade_symbols.blockSignals(True);self.trade_symbols.clear();self.trade_symbols.addItems(symbols);self.trade_symbols.setCurrentText(self.symbol);self.trade_symbols.blockSignals(False)
  self.option_under.blockSignals(True);previous=self.option_under.currentText();self.option_under.clear();self.option_under.addItems(symbols);self.option_under.setCurrentText(previous or self.symbol);self.option_under.blockSignals(False)
  for combo,items in [(self.bank_choice,[(b['name'],b['id']) for b in w['banks']]),(self.investor_fund,[(f['name'],f['id']) for f in w['funds']]),(self.investor_choice,[(n['name'],n['id']) for n in w['npcs']]),(self.comm_fund,[(f['name'],f['id']) for f in w['funds']]),(self.comm_recipient,[(n['name'],n['id']) for n in w['npcs']])]:
   current=combo.currentData();combo.blockSignals(True);combo.clear()
   for title,id in items:combo.addItem(title,id)
   if combo.findData(current)>=0:combo.setCurrentIndex(combo.findData(current))
   combo.blockSignals(False)
  if previous_world!=w['id']:self.chains=[];self.selected_contract=None;self.choose_symbol(self.symbol)
  self.render()
 def render(self):
  if not self.world:return
  for name,panel in [('Federal Reserve',self.fed_panel),('Employees',self.employee_panel),('Research',self.research_panel),('Wealth & Lifestyle',self.wealth_panel),('Property & offices',self.office_panel),('Financial Crime',self.living_world_panel),('Executive Office',self.executive_panel),('Corporate Structure',self.corporate_panel),('Company Acquisitions',self.ma_panel),('My Companies',self.my_companies_panel)]:
   if self.current_page==name or not getattr(panel,'world',None):panel.refresh(self.world)
  w=self.world;m=w['metrics'][self.active];self.time_label.setText(w['time'][:16].replace('T',' ')+' UTC');self.pause.setText('▶ Resume' if w['paused'] else 'Ⅱ Pause');self.speed.blockSignals(True);self.speed.setCurrentIndex([1,6,24].index(w['speed']));self.speed.blockSignals(False)
  for key,value in self.metric_values.items():value.setText(gbp(m['available_cash'] if key=='cash' else m[key]));value.setStyleSheet('color:'+ (RED if number(m[key])<0 else GREEN if key=='profit' and number(m[key])>0 else '#e0ecef'))
  positions=[p for p in w['positions'].values() if p['account']==self.active];rows(self.overview_positions,[[p['symbol'],p['qty'],gbp(p['value']),gbp(p['pnl'])] for p in positions]);rows(self.trade_positions,[[p['symbol'],p['qty'],local(p['price'],p.get('currency','GBP')),gbp(p['value']),gbp(p['pnl'])] for p in positions]);rows(self.positions,[[p['symbol'],p['qty'],local(p['price'],p.get('currency','GBP')),gbp(p['value']),gbp(p['pnl']),gbp(p['cost'])] for p in positions]);self.position_data=positions
  self.chart.set_instrument(w['instruments'][self.symbol]);self.depth_rows=w['instruments'][self.symbol].get('depth',[]);rows(self.native_depth,[[r.get('bid_qty',r['qty']),r.get('bid') or '—',r.get('ask') or '—',r.get('ask_qty',r['qty'])] for r in self.depth_rows]);self.overview_chart.set_instrument(w['instruments'].get('NVDA',w['instruments'][self.symbol]));macro=w['macro'];self.economy.setText(f"Policy interest rate     {macro['rate']:.2f}%\n\nAnnual inflation        {macro['inflation']:.2f}%\n\nGDP growth              {macro['growth']:.2f}%\n\nCredit stress           {macro['stress']:.0f} / 100")
  if not getattr(self,'_last_snapshot_partial',False) or self.current_page=='Markets':self.render_markets()
  self.render_order_rows();rows(self.bank_table,[[b['name'],gbp(b['cash']),gbp(b['loans']),gbp(b['equity'])] for b in w['banks']]);self.credit_label.setText(f"Credit score {w['credit']} / 850\nTotal debt {gbp(m['debt'])}\nInterest expense {gbp(m['interest'])}");self.loan_data=[l for l in w['loans'] if l['account']==self.active];rows(self.loans,[[l['id'],l['bank'],gbp(l['balance']),f"{l['rate']:.2f}%",gbp(l['payment']),l['status']] for l in self.loan_data]);self.savings_info.setText('Savings assets '+gbp(m['savings'])+' / rate '+f"{max(0,macro['rate']-1):.2f}%");self.render_risk()
  rows(self.funds,[[f['name'],gbp(w['metrics'][f['id']]['equity']),gbp(w['metrics'][f['id']]['cash']),f['units'],gbp(number(w['metrics'][f['id']]['equity'])/max(1e-8,number(f['units']))),gbp(f.get('monthly_expenses',0))] for f in w['funds']]);rows(self.npcs,[[n['name'],gbp(n['wealth']),f"{n['trust']}/100",n['risk']] for n in w['npcs']]);self.render_ownership()
  wire='\n\n'.join(n.get('publication','SCENARIO')+' / '+n['time'][:16]+' / '+n['category']+'\n'+n['title']+'\n'+n['body'] for n in w['news']);self.wire.setPlainText(wire);self.overview_wire.setPlainText(wire)
  self.company_data=[i for i in w['instruments'].values() if i['sector'] not in ('Index','Commodities','Fixed income')];rows(self.corporations,[[i['symbol'],i['name'],gbp(i['fundamentals']['revenue']),gbp(i['fundamentals']['profit']),gbp(i['fundamentals']['debt']),str(i['fundamentals']['shares'])] for i in self.company_data]);self.inbox.setPlainText('\n\n'.join(m['sender']+' / '+m['time'][:16]+'\n'+m['subject']+'\n'+m['body'] for m in w['messages']));rows(self.cases,[[c['id'],c['status'],c['evidence'],c['time'][:16]] for c in w['investigations']]);rows(self.claims,[[c['time'][:16],gbp(c['actual']),gbp(c['reported']),gbp(c['gap']),c['status'],c['evidence']] for c in w['claims']]);self.career_info.setText(f"{w['name']}\n\nMandate: {w['career']}\nReputation: {w['reputation']}/100\nCredit score: {w['credit']}\nWorld age: {w['tick']/24:.1f} simulation days\n\nChanging your mandate does not create capital or erase obligations.");rows(self.journal,[[j['time'][:16],j['description'],' | '.join(k+': '+v for k,v in j['lines'].items())] for j in w['journal']]);rows(self.audit,[[a['time'][:16],a['action'],json.dumps(a['detail'])] for a in w['audit']])
  report=w['statements'][self.active];self.statement_summary.setText('CAPITAL '+gbp(report['capital'])+'  +  INCOME '+gbp(report['income'])+'  −  EXPENSES '+gbp(report['total_expenses'])+'  +  VALUATION '+gbp(report['valuation'])+'  =  NET ASSETS '+gbp(report['reported_equity'])+'\nReconciliation difference '+gbp(report['difference'])+' · '+str(report['total_entries'])+' total entries. Most recent 100 shown.');rows(self.statement_table,[[r['time'][:16],r['description'],gbp(r['cash_change']),gbp(r['running_cash']),json.dumps(r['lines'])] for r in report['entries']])
  self.investor_evidence.setText('\n'.join(f['name']+': management '+str(f['management'])+'% / performance '+str(f['performance'])+'% · '+str(len(w.get('investor_relations',{}).get(f['id'],{}).get('investors',[])))+' investor records; use ownership and redemption tables for settlement status.' for f in w['funds']))
  rows(self.native_transactions,[[r['id'],r['source']+' → '+r['destination'],r['classification']+' / '+r['kind'],gbp(r['amount']),r['status']] for r in w.get('related_transactions',[])]);rows(self.native_cases,[[c['id'],c['entity'],c['stage'],c['score'],c['deadline']] for c in w.get('legal_cases',[])])
  if self.chains:self.render_chain()
 def render_markets(self):
  if not self.world:return
  self.market_panel.refresh(self.world);self.market_data=self.market_panel.matches
 def render_risk(self):
  if not self.world:return
  m=self.world['metrics'][self.active];rows(self.risk_table,[['Net exposure',gbp(m['net']),'Long minus short marked assets'],['Leverage',f"{m['leverage']:.2f}×",'Gross exposure / equity'],['Drawdown',f"{m['drawdown']*100:.2f}%",'Capital-flow adjusted'],['1-day 95% VaR',gbp(m['var95']),'Normal approximation'],['1-day expected shortfall',gbp(m['es95']),'Normal approximation'],['Maintenance margin',gbp(number(m['equity_gross'])*.25),'25% equity/option gross; Treasury DV01 is separate'],['Liquid margin buffer',gbp(number(m['liquid_equity'])-number(m['equity_gross'])*.25),'Excludes locked fund investment value'],['Fund investment asset',gbp(m['investment']),'Actual fund NAV ownership']]);self.stress_label.setText('Estimated P&L '+gbp(number(m['market'])*self.stress.value()/100))
 def render_ownership(self):
  if not self.world:return
  id=self.investor_fund.currentData();f=next((f for f in self.world['funds'] if f['id']==id),None)
  if not f:rows(self.ownership,[]);return
  names={n['id']:n['name'] for n in self.world['npcs']};names.update(personal='You / seed',sponsor='Institutional sponsor',admin='Administrative capital');self.ownership_data=list(f['investors']);rows(self.redemption_queue,[[r['id'],r['investor'],gbp(r['amount']),gbp(r['paid']),gbp(r['remaining'])+' / '+r['status']] for r in self.world.get('redemptions',[]) if r['fund']==id]);nav=number(self.world['metrics'][id]['equity']);total=max(1e-8,number(f['units']));rows(self.ownership,[[names.get(id,id),units,f'{number(units)/total*100:.2f}%',gbp(number(units)/total*nav)] for id,units in f['investors'].items()])
  records=self.world.get('investor_relations',{}).get(id,{}).get('investors',[])
  rows(self.investor_detail,[[r['name'],gbp(r['recorded_subscriptions'])+' / '+gbp(r['opening_basis']),r['units']+' / '+f"{r['ownership']*100:.2f}%",gbp(r['value'])+' / '+('Unknown basis' if r['net_performance'] is None else gbp(r['net_performance'])),gbp(r['redemptions_paid'])+' / '+gbp(r['redemptions_due']),'; '.join((r.get('last_decision') or {}).get('reasons',[])) or 'Not yet reviewed'] for r in records])
 def order_fields(self):
  kind=self.order_type.currentText()
  for widget,types in [(self.order_limit,('limit','stop_limit')),(self.order_stop,('stop','stop_limit')),(self.order_trail,('trailing',)),(self.order_take,('bracket',)),(self.order_loss,('bracket',))]:
   visible=kind in types;widget.setVisible(visible);self.order_form.labelForField(widget).setVisible(visible)
 def choose_symbol(self,symbol):
  if self.world and symbol in self.world['instruments']:
   self.symbol=symbol;price=number(self.world['instruments'][symbol]['price']);self.order_limit.setValue(price);self.order_stop.setValue(price*.95);self.order_take.setValue(price*1.1);self.order_loss.setValue(price*.95);self.chart.set_instrument(self.world['instruments'][symbol])
 def market_trade(self,row,col):self.symbol=self.market_data[row]['symbol'];self.trade_symbols.setCurrentText(self.symbol);self.nav.setCurrentRow(1)
 def depth_select(self,row,col):
  r=self.depth_rows[row];side='sell' if col<2 else 'buy';price=r.get('bid' if side=='sell' else 'ask')
  if price:self.order_side.setCurrentIndex(0 if side=='buy' else 1);self.order_type.setCurrentText('limit');self.order_limit.setValue(float(price))
 def place_order(self):
  if self.world:self.send('order',dict(**({'execution_clock':'ACTIVE','urgency':self.order_urgency.currentText(),'max_participation':self.order_maxpart.value(),'max_slippage_bps':self.order_slippage.value(),'after_window':self.order_after.currentText()} if self.order_algo.currentText() in ('TWAP','VWAP','POV') else {}),account=self.active,symbol=self.symbol,side='buy' if self.order_side.currentIndex() in (0,3) else 'sell',intent=['buy_long','sell_long','sell_short','buy_to_cover'][self.order_side.currentIndex()],type=self.order_type.currentText(),qty=str(self.order_qty.value()),limit=str(self.order_limit.value()),stop=str(self.order_stop.value()),trail=str(self.order_trail.value()),take=str(self.order_take.value()),loss=str(self.order_loss.value()),margin=self.order_margin.isChecked() or self.order_side.currentIndex() in (2,3),execution_algo=self.order_algo.currentText(),execution_hours=self.order_hours.value() if self.order_algo.currentText() in ('TWAP','VWAP','POV') else 0,participation=self.order_pov.value(),display_qty=str(self.order_display.value()) if self.order_algo.currentText()=='ICEBERG' else None,tif=self.order_tif.currentText()))
 def selected(self,table,data):return data[table.currentRow()] if 0<=table.currentRow()<len(data) else None
 def show_institutional_market(self):
  if self.order_side.currentIndex() in (2,3):self.notice.setText('Use the exchange Sell Short / Buy to Cover ticket; block RFQs support owned-share transfers only.');return
  if not self.world:return
  dialog=QDialog(self);dialog.setWindowTitle('Institutional market · client AUM is not dealer cash');dialog.resize(950,650);layout=QVBoxLayout(dialog);view=QPlainTextEdit();view.setReadOnly(True);view.setPlainText(json.dumps(self.world.get('institutional_economy',[]),indent=2));layout.addWidget(view);dialog.exec()
 def native_block_quote(self):
  if not self.world:return
  if any(action in ('block_quote','block_accept') for action,_ in self.pending.values()):return
  index=self.order_side.currentIndex()
  if index not in (0,1):self.notice.setText('Block quotes support Buy and Sell Owned. Use exchange orders for Sell Short or Buy to Cover.');return
  if self.active=='personal' and index==0:self.notice.setText('Select an institutional account for block purchases, or use the exchange buy ticket. Personal owned-share block sales are supported.');return
  account=self.active;symbol=self.symbol
  def preview(q):
   if account!=self.active or symbol!=self.symbol:self.notice.setText('Block quote returned for the previous account/instrument. Request a fresh quote for the current ticket.');return
   if q['status']!='OPEN':QMessageBox.information(self,'Block liquidity',q.get('reason','No funded block counterparty is currently available.'));return
   text=f"{q['account']}: {q['side'].upper()} {q['offered']} / {q['requested']} {q['symbol']} at {q['currency']} {q['price']}; approximately GBP {q['estimated_consideration_gbp']} plus fees. Quote resources will be checked again."
   if QMessageBox.question(self,'Accept inventory-backed block',text)==QMessageBox.StandardButton.Yes:
    if hasattr(self,'block_quote_button'):self.block_quote_button.setEnabled(False);self.block_quote_button.setText('Executing block…')
    self.send('block_accept',{'id':q['id']})
  if hasattr(self,'block_quote_button'):self.block_quote_button.setEnabled(False);self.block_quote_button.setText('Requesting block quote…')
  self.notice.setText('Requesting an inventory-backed block quote; no cash or shares reserved.')
  self.send('block_quote',{'account':account,'symbol':symbol,'side':'buy' if index==0 else 'sell','qty':str(self.order_qty.value())},callback=preview)
 def close_position(self):
  p=self.selected(self.positions,self.position_data)
  if p:self.send('order',dict(account=self.active,symbol=p['symbol'],side='sell' if number(p['qty'])>0 else 'buy',intent='sell_long' if number(p['qty'])>0 else 'buy_to_cover',qty=str(abs(number(p['qty']))),margin=number(p['qty'])<0))
 def render_order_rows(self):
  if not self.world:return
  w=self.world;page=self.order_page.value();self.order_data=[o for o in w['orders'] if o['account']==self.active][page*100:(page+1)*100];rows(self.orders,[[o['id'],o['symbol'],(o.get('intent') or o['side']).replace('_',' ').upper()+' / '+o['type'],o['filled']+' / '+o['qty'],'MKT' if o['type']=='market' else o.get('limit',''),w.get('order_diagnostics',{}).get(o['id'],{}).get('status',o['status'])+(' · '+o['reason'] if o.get('reason') else '')] for o in self.order_data])
 def show_execution_detail(self,row):
  if 0<=row<len(self.order_data):
   order=self.order_data[row];self.execution_detail.setPlainText(json.dumps(self.world.get('order_diagnostics',{}).get(order['id'],{'status':order['status'],'reason':order.get('reason')}),indent=2))
 def cancel_order(self):
  o=self.selected(self.orders,self.order_data)
  if o:self.send('cancel',{'id':o['id']})
 def modify_order(self):
  o=self.selected(self.orders,self.order_data)
  if o:
   key='limit' if o['type']=='limit' else 'stop';v,ok=QInputDialog.getDouble(self,'Modify order','New '+key+' level',number(o.get(key,0)),.01,1e12,2)
   if ok:self.send('modify',{'id':o['id'],key:v})
 def generate_chain(self):self.send('chain',{'symbol':self.option_under.currentText(),'days':self.option_days.value()},callback=self.chain_ready)
 def chain_ready(self,chain):self.chains=chain;self.render_chain()
 def render_chain(self):
  quotes=self.world.get('option_quotes',{});rows(self.option_chain,[[f"{r['call']['greeks']['delta']:.3f}",gbp(quotes.get(r['call']['symbol'],r['call'])['price']),r['strike'],gbp(quotes.get(r['put']['symbol'],r['put'])['price']),f"{r['put']['greeks']['delta']:.3f}"] for r in self.chains])
 def select_option(self,row,col):
  if not self.chains:return
  self.selected_contract=self.chains[row]['call' if col<=1 else 'put']['symbol'];q=self.world['option_quotes'][self.selected_contract];self.option_choice.setText(self.selected_contract+' / '+gbp(q['price'])+' per share\n'+ '  '.join(k.upper()+f' {v:.4f}' for k,v in q['greeks'].items() if k!='price'))
 def option_strategy(self,kind):self.send('strategy',{'account':self.active,'symbol':self.option_under.currentText(),'days':self.option_days.value(),'contracts':int(self.option_qty.value()),'strategy':kind})
 def buy_option(self):
  if self.selected_contract:self.send('order',{'account':self.active,'symbol':self.selected_contract,'qty':str(self.option_qty.value()),'side':'buy'})
 def savings_transfer(self,direction):self.send('savings',{'account':self.active,'bank':self.bank_choice.currentData(),'amount':str(self.savings_amount.value()),'direction':direction})
 def communicate(self):
  intent=['update','risk','disclose'][self.comm_intent.currentIndex()]
  self.send('communicate',{'intent':intent,'recipient':self.comm_recipient.currentData(),'fund':self.comm_fund.currentData()})
 def apply_loan(self):self.send('loan',{'account':self.active,'bank':self.bank_choice.currentData(),'amount':str(self.loan_amount.value()),'months':self.loan_months.value()})
 def repay_loan(self):
  loan=self.selected(self.loans,self.loan_data)
  if loan:
   amount,ok=QInputDialog.getDouble(self,'Loan repayment','Amount / GBP',number(loan['payment']),.01,1e15,2)
   if ok:self.send('repay',{'id':loan['id'],'amount':str(amount)})
 def subscribe(self):
  if self.investor_fund.currentData():self.send('subscribe',{'fund':self.investor_fund.currentData(),'investor':self.investor_choice.currentData(),'amount':str(self.sub_amount.value())})
 def redeem(self):
  id=self.investor_fund.currentData()
  if not id:return
  investor=self.ownership_data[self.ownership.currentRow()] if 0<=self.ownership.currentRow()<len(getattr(self,'ownership_data',[])) else self.investor_choice.currentData()
  if investor in ('sponsor','admin'):self.notice.setText('Sponsor/admin units require their designated capital workflow.');return
  fund=next(f for f in self.world['funds'] if f['id']==id);owned=number(fund['investors'].get(investor,0));fm=self.world['metrics'][id]
  units,ok=QInputDialog.getDouble(self,'Redemption instruction',f"Destination: {'Personal account' if investor=='personal' else investor}\nOwned units {owned:,.8f} · actual fund NAV {gbp(fm['equity'])}\nAvailable liquidity {gbp(fm['available_cash'])}. Unpaid amounts remain claims.\nUnits to redeem",min(1000,owned),.00000001,max(.00000001,owned),8)
  if ok:self.send('redeem',{'fund':id,'investor':investor,'units':str(units),'queue':True},callback=self.redemption_ready)
 def redemption_ready(self,r):
  if r['investor']=='personal':self.accounts.setCurrentIndex(self.accounts.findData('personal'));self.nav.setCurrentRow(3)
  self.notice.setText(f"{r['status']}: destination {r['destination_account']}; £{float(r.get('paid',r['amount'])):,.2f} paid, £{float(r.get('remaining',0)):,.2f} still owed. Personal cash £{float(r['personal_cash']):,.2f}; net assets £{float(r['personal_net_assets']):,.2f}.")
 def report(self):
  id=self.investor_fund.currentData()
  if not id:return
  actual=number(self.world['metrics'][id]['equity']);reported,ok=QInputDialog.getDouble(self,'Investor statement','Reported NAV / GBP (actual '+gbp(actual)+')',actual,.01,1e15,2)
  if ok:
   if reported>actual*1.02 and QMessageBox.question(self,'Fictional misleading statement','Publish an overstatement? It creates evidence and no money.')!=QMessageBox.StandardButton.Yes:return
   self.send('report',{'fund':id,'reported':str(reported)})
 def corporate(self,kind):
  company=self.selected(self.corporations,self.company_data)
  if company and QMessageBox.question(self,'Corporate scenario','Trigger internal scenario '+kind+' for '+company['symbol']+'?')==QMessageBox.StandardButton.Yes:self.send('corporate',{'kind':kind,'symbol':company['symbol']})
 def admin_cash(self):
  amount,ok=QInputDialog.getDouble(self,'Administrative equity adjustment','Signed amount / GBP',1000000,-1e15,1e15,2)
  if ok:
   if amount<0 and QMessageBox.question(self,'Remove capital','Remove '+gbp(-amount)+' from this account?')!=QMessageBox.StandardButton.Yes:return
   self.send('admin',{'op':'cash','account':self.active,'amount':str(amount)})
 def admin_price(self):
  if not self.world:return
  sym,ok=QInputDialog.getItem(self,'Set execution price','Instrument',list(self.world['instruments']),0,False)
  if ok:
   price,ok=QInputDialog.getDouble(self,'Set execution price','Price / GBP',number(self.world['instruments'][sym]['price']),.01,1e12,2)
   if ok:self.send('admin',{'op':'price','symbol':sym,'price':str(price)})
 def admin_scenario(self):
  scenario,ok=QInputDialog.getItem(self,'Economic scenario','Select a persistent market scenario',['rate_hike','credit_crunch','recovery'],0,False)
  if ok:self.send('admin',{'op':'scenario','scenario':scenario})
 def fund_budget(self):
  fund=self.selected(self.funds,self.world['funds'] if self.world else [])
  if fund:
   amount,ok=QInputDialog.getDouble(self,'Institution operating budget','Monthly service and payroll expense / GBP',number(fund.get('monthly_expenses',0)),0,1e15,2)
   if ok:self.send('budget',{'fund':fund['id'],'amount':str(amount)})
 def admin_rate(self):
  rate,ok=QInputDialog.getDouble(self,'Economic model','Policy rate %',self.world['macro']['rate'] if self.world else 4.25,-10,100,2)
  if ok:self.send('admin',{'op':'macro','rate':rate})
 def admin_advance(self):
  hours,ok=QInputDialog.getInt(self,'Advance world','Simulation hours',24,1,744)
  if ok:self.send('advance',{'hours':hours})
 def load_save(self):
  save=self.selected(self.saves,self.saves_data)
  if save:self.chains=[];self.selected_contract=None;self.send('load',{'id':save['id']})
 def restore(self):
  files=[p.name for p in sorted(self.bridge.backup_directory.glob('vantage-*.sqlite'),reverse=True)]
  if not files:self.notice.setText('No backups exist yet.');return
  file,ok=QInputDialog.getItem(self,'Restore database','Backup',files,0,False)
  if ok and QMessageBox.question(self,'Restore all worlds','Restore all worlds to this snapshot? A safety backup is created first.')==QMessageBox.StandardButton.Yes:self.chains=[];self.send('restore',{'file':file,'confirm':'RESTORE'})
 def import_reference(self):
  file,_=QFileDialog.getOpenFileName(self,'Import unverified ECB-format reference XML',str(ROOT),'XML files (*.xml)')
  if file:
   path=Path(file)
   if path.stat().st_size>2*1024*1024:self.notice.setText('Reference import limited to 2 MB');return
   self.send('reference_import',{'xml':path.read_text()})
 def closeEvent(self,event):self.refresh_timer.stop();self.bridge.close();event.accept()

def main():
 from .logging_config import configure
 configure(ROOT);app=QApplication(sys.argv);app.setApplicationName('VANTAGE');app.setOrganizationName('Vantage Local')
 smoke='--smoke-test' in sys.argv
 temporary=__import__('tempfile').TemporaryDirectory(dir=__import__('vantage.paths',fromlist=['runtime_directory']).runtime_directory()) if smoke else None
 try:window=Terminal(str(Path(temporary.name)/'smoke.sqlite') if smoke else None,onboard=not smoke)
 except Exception as exc:QMessageBox.critical(None,'VANTAGE startup failed',str(exc));return 1
 window.show()
 if smoke:
  def finish():
   result={'passed':window.isVisible() and len(window.pages)==30,'desktop':'Qt Widgets','visible':window.isVisible(),'pages':len(window.pages),'engine':True}
   if os.environ.get('VANTAGE_VALIDATION_REPORT'):Path(os.environ['VANTAGE_VALIDATION_REPORT']).write_text(json.dumps(result),encoding='utf-8')
   print(json.dumps(result),flush=True);window.close()
  QTimer.singleShot(500,finish)
 code=app.exec()
 if temporary:temporary.cleanup()
 return code
if __name__=='__main__':sys.exit(main())
