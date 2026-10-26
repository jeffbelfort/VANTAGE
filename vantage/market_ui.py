"""Native Market Explorer: same projected data, filters, and existing trade actions."""
import json,math
from PyQt6.QtCore import Qt,QPointF,QRectF
from PyQt6.QtGui import QPainter,QColor,QPen
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QComboBox,QLineEdit,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QStackedWidget,QPlainTextEdit,QScrollArea,QToolTip)
from .markets import screen_rows,recorded_history,NUMERIC_FILTERS
RANGES={'1D':24,'5D':120,'1M':720,'3M':2160,'6M':4320,'1Y':8760,'All':math.inf}

class HistoryChart(QWidget):
 def __init__(self):
  super().__init__();self.instrument=None;self.range='5D';self.bars=[];self.setMinimumHeight(260);self.setMouseTracking(True)
 def set_instrument(self,ins):self.instrument=ins;self.update()
 def paintEvent(self,event):
  p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.fillRect(self.rect(),QColor('#121d25'));p.setPen(QColor('#adc6ce'))
  if not self.instrument:p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'No execution history');return
  i=self.instrument;tick=i.get('chart_tick',max([b['t'] for b in i.get('history',[])] or [0]));bars=[b for b in recorded_history(i,tick) if b['t']>tick-RANGES[self.range]];self.bars=bars
  if not bars:p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'No retained history in this timeframe');return
  candles=all(all(b.get(k) is not None for k in ('o','h','l','c')) and float(b['h'])>=max(float(b['o']),float(b['c'])) and float(b['l'])<=min(float(b['o']),float(b['c'])) for b in bars)
  values=[float(b[k]) for b in bars for k in (('l','h') if candles else ('c',))];lo=min(values);hi=max(values);pad=max(.01,(hi-lo)*.05);lo-=pad;hi+=pad;left=15;right=self.width()-80;top=40;bottom=self.height()-30;y=lambda n:bottom-(n-lo)/(hi-lo)*(bottom-top);x=lambda n:left+(n+.5)/len(bars)*(right-left)
  p.drawText(15,22,f"{i['symbol']} · {self.range} · {'Hourly OHLC' if candles else 'Close-only line'} · SIMULATED")
  for n in range(5):
   v=lo+(hi-lo)*n/4;p.setPen(QPen(QColor('#2b3b46'),1));p.drawLine(QPointF(left,y(v)),QPointF(right,y(v)));p.setPen(QColor('#91a7b4'));p.drawText(QPointF(right+8,y(v)+4),f'{v:.2f}')
  previous=None
  for n,b in enumerate(bars):
   point=QPointF(x(n),y(float(b['c'])));color=QColor('#64d9ac' if not candles or float(b['c'])>=float(b['o']) else '#ef8494');p.setPen(QPen(color,1))
   if candles:p.drawLine(QPointF(x(n),y(float(b['h']))),QPointF(x(n),y(float(b['l']))));p.fillRect(QRectF(x(n)-(right-left)/len(bars)*.27,min(y(float(b['o'])),y(float(b['c']))),max(.5,(right-left)/len(bars)*.54),max(1,abs(y(float(b['o']))-y(float(b['c']))))),color)
   elif previous is not None:p.drawLine(previous,point)
   previous=point
  p.setPen(QColor('#91a7b4'));p.drawText(15,self.height()-8,f"{len(bars)} retained observations · Available history only"+(' · Includes model prehistory' if any(b.get('quality')=='MODEL' or b['t']<0 for b in bars) else ' · Observed simulation OHLC'))
 def mouseMoveEvent(self,event):
  if not self.bars:return
  index=max(0,min(len(self.bars)-1,int((event.position().x()-15)/max(1,self.width()-95)*len(self.bars))));b=self.bars[index];QToolTip.showText(event.globalPosition().toPoint(),f"Simulation hour {b['t']} · close {float(b['c']):.4f}",self)

class MarketPanel(QWidget):
 def __init__(self,terminal):
  super().__init__();self.terminal=terminal;self.world=None;self.filters={};self.world_id=None;self.matches=[];self.page=0;self.selected=None;layout=QVBoxLayout(self);self.stack=QStackedWidget();layout.addWidget(self.stack);browse=QWidget();main=QVBoxLayout(browse);self.stack.addWidget(browse)
  title=QLabel('MARKET EXPLORER · Local simulation prices, not a live exchange feed');main.addWidget(title);grid=QGridLayout();main.addLayout(grid);self.search=QLineEdit();self.search.setPlaceholderText('Search company name or ticker');grid.addWidget(self.search,0,0,1,2);self.search.textChanged.connect(lambda value:self.change('query',value));self.combos={}
  for n,(key,label) in enumerate([('region','Market region'),('country','Country of listing'),('exchange','Exchange'),('sector','Sector'),('industry','Industry')]):
   combo=QComboBox();combo.addItem(label+' · All','');grid.addWidget(combo,1+n//3,n%3);combo.currentIndexChanged.connect(lambda _,key=key,combo=combo:self.change(key,combo.currentData()));self.combos[key]=combo
  self.universe=QComboBox()
  for label,value in [('Active execution markets','active'),('All catalogue identities','all'),('Catalogue only · reference required','catalogue')]:self.universe.addItem(label,value)
  grid.addWidget(self.universe,2,2);self.universe.currentIndexChanged.connect(lambda:self.change('universe',self.universe.currentData()))
  controls=QHBoxLayout();main.addLayout(controls);self.discovery=QComboBox()
  self.lists={'all':('All securities','symbol','asc'),'gainers':('Biggest gainers','change_1d','desc'),'losers':('Biggest losers','change_1d','asc'),'active':('Most actively traded','volume_1d','desc'),'volatile':('Highest volatility','volatility','desc'),'news':('Recently in the news','news_count','desc'),'revision_up':('Positive earnings / guidance','revision','desc'),'revision_down':('Negative earnings / guidance','revision','asc'),'watchlist':('Watchlist','symbol','asc'),'recent':('Recently viewed','recent','asc')}
  for key,(label,_,_) in self.lists.items():self.discovery.addItem(label,key)
  controls.addWidget(self.discovery);self.discovery.currentIndexChanged.connect(self.choose_list);self.sort=QComboBox()
  for key,label in [('symbol','Ticker'),('name','Company'),('price_gbp','Price · GBP'),('change_1d','24H movement'),('change_1w','7D movement'),('volume_1d','Executed volume'),('volatility','Volatility'),('liquidity','Liquidity'),('market_cap_gbp','Market cap'),('recent','Recently viewed')]:self.sort.addItem(label,key)
  controls.addWidget(self.sort);self.sort.currentIndexChanged.connect(lambda:self.change('sort',self.sort.currentData()));self.desc=QPushButton('Reverse sort');self.desc.clicked.connect(lambda:self.change('direction','asc' if self.filters.get('direction')=='desc' else 'desc'));controls.addWidget(self.desc);save=QPushButton('Save screen');save.clicked.connect(lambda:self.terminal.send('market_preferences',{'filters':self.filters}));controls.addWidget(save)
  self.advanced=QWidget();advanced_grid=QGridLayout(self.advanced);self.numeric={}
  for n,(key,field) in enumerate(NUMERIC_FILTERS.items()):
   edit=QLineEdit();edit.setPlaceholderText(key.replace('_',' '));edit.setToolTip(key.replace('_',' ')+' · prices/capitalisation in GBP; rates in percentage points');advanced_grid.addWidget(edit,n//4,n%4);edit.textChanged.connect(lambda value,key=key:self.change(key,value));self.numeric[key]=edit
  for n,(key,options) in enumerate([('news',['positive','negative']),('recommendation',['Buy','Hold','Avoid'])]):
   combo=QComboBox();combo.addItem(key+' · All','')
   for option in options:combo.addItem(option,option)
   combo.currentIndexChanged.connect(lambda _,key=key,combo=combo:self.change(key,combo.currentData()));advanced_grid.addWidget(combo,5,n);self.combos[key]=combo
  toggle=QPushButton('Advanced price / movement / liquidity / valuation / news / research screens');toggle.setCheckable(True);toggle.toggled.connect(self.advanced.setVisible);main.addWidget(toggle);main.addWidget(self.advanced);self.advanced.hide()
  self.count=QLabel();self.count.setWordWrap(True);main.addWidget(self.count);self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels(['Company / ticker','Exchange / industry','Execution price','24H %','7D %','Executed 24H','Volatility %','Market model']);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.table.cellDoubleClicked.connect(lambda row,col:self.open_stock(self.matches[self.page*50+row]['symbol']));main.addWidget(self.table,1);self.table.horizontalHeader().sectionClicked.connect(self.header_sort)
  pages=QHBoxLayout();main.addLayout(pages);self.previous=QPushButton('Previous 50');self.previous.clicked.connect(lambda:self.paginate(-1));pages.addWidget(self.previous);self.next=QPushButton('Next 50');self.next.clicked.connect(lambda:self.paginate(1));pages.addWidget(self.next);self.open_button=QPushButton('Open selected company');self.open_button.clicked.connect(self.open_selected);pages.addWidget(self.open_button)
  detail=QWidget();dl=QVBoxLayout(detail);self.stack.addWidget(detail);back=QPushButton('← Back to market results');back.clicked.connect(lambda:self.stack.setCurrentIndex(0));dl.addWidget(back);self.identity=QLabel();self.identity.setWordWrap(True);dl.addWidget(self.identity);actions=QHBoxLayout();dl.addLayout(actions);self.buy=QPushButton('Buy shares');self.sell=QPushButton('Sell shares');self.options=QPushButton('Open options chain');self.research=QPushButton('Request investment analysis');self.watch=QPushButton('Add / remove watchlist')
  for button in [self.buy,self.sell,self.options,self.research,self.watch]:actions.addWidget(button)
  self.buy.clicked.connect(lambda:self.trade('buy'));self.sell.clicked.connect(lambda:self.trade('sell'));self.options.clicked.connect(self.open_options);self.research.clicked.connect(self.open_research);self.watch.clicked.connect(lambda:self.terminal.send('watchlist',{'symbol':self.selected}));self.chart=HistoryChart();dl.addWidget(self.chart);ranges=QHBoxLayout();dl.addLayout(ranges)
  for label in RANGES:
   button=QPushButton(label);button.clicked.connect(lambda checked=False,label=label:self.set_range(label));ranges.addWidget(button)
  self.details=QPlainTextEdit();self.details.setReadOnly(True);dl.addWidget(self.details,1)
 def change(self,key,value):
  if value is not None:self.filters[key]=value
  self.page=0;self.render()
 def populate(self,combo,items,value):
  combo.blockSignals(True);combo.clear()
  for title,key in items:combo.addItem(title,key)
  index=combo.findData(value);combo.setCurrentIndex(max(0,index));combo.blockSignals(False)
 def refresh(self,world):
  if not world:return
  self.world=world
  if self.world_id!=world['id']:self.world_id=world['id'];self.filters=dict(world.get('market_explorer_preferences',{}));self.selected=None
  explorer=world.get('market_explorer',{});facets=explorer.get('facets',{})
  self.populate(self.combos['region'],[('All supported markets','')]+[(f"{r['name']} · {r['active']} active",r['name']) for r in explorer.get('regions',[])],self.filters.get('region',''))
  for key in ['country','exchange','sector','industry']:self.populate(self.combos[key],[(key+' · All','')]+[(x,x) for x in facets.get(key,[])],self.filters.get(key,''))
  self.search.blockSignals(True);self.search.setText(self.filters.get('query',''));self.search.blockSignals(False)
  for combo,key,default in [(self.universe,'universe','active'),(self.discovery,'list','all'),(self.sort,'sort','symbol')]:
   combo.blockSignals(True);combo.setCurrentIndex(max(0,combo.findData(self.filters.get(key,default))));combo.blockSignals(False)
  for key,edit in self.numeric.items():edit.blockSignals(True);edit.setText(self.filters.get(key,''));edit.blockSignals(False)
  for key in ('news','recommendation'):
   combo=self.combos[key];combo.blockSignals(True);combo.setCurrentIndex(max(0,combo.findData(self.filters.get(key,''))));combo.blockSignals(False)
  self.render()
 def choose_list(self):
  key=self.discovery.currentData();_,sort,direction=self.lists[key];self.filters.update(list=key,sort=sort,direction=direction)
  if key in ('recent','watchlist'):self.filters['universe']='all';self.universe.blockSignals(True);self.universe.setCurrentIndex(self.universe.findData('all'));self.universe.blockSignals(False)
  self.page=0;self.render()
 def render(self):
  if not self.world:return
  try:self.matches=screen_rows(self.world.get('market_explorer',{}).get('rows',[]),self.filters,self.terminal.active,self.world.get('watchlist',[]),self.world.get('recently_viewed',[]))
  except ValueError as error:self.count.setText(str(error));return
  pages=max(1,math.ceil(len(self.matches)/50));self.page=min(self.page,pages-1);visible=self.matches[self.page*50:(self.page+1)*50];self.table.setRowCount(len(visible))
  for row,r in enumerate(visible):
   values=[r['name']+' / '+r['symbol'],str(r['exchange'])+' / '+r['industry'],self.money(r['price'],r['currency']),self.percent(r['change_1d']),self.percent(r['change_1w']),self.value(r['volume_1d']),self.percent(r['volatility']),r['execution_model']]
   for col,value in enumerate(values):self.table.setItem(row,col,QTableWidgetItem(value))
  self.count.setText(f"{len(self.matches)} securities · Page {self.page+1}/{pages}. No matching regional listings means the exchange is not currently supported. Unavailable metrics are not invented.");self.previous.setEnabled(self.page>0);self.next.setEnabled(self.page<pages-1)
  if self.selected:self.render_detail()
 def header_sort(self,column):
  keys=['name','symbol','price_gbp','change_1d','change_1w','volume_1d','volatility',None];key=keys[column]
  if key:self.filters.update(sort=key,direction='asc' if self.filters.get('direction')=='desc' and self.filters.get('sort')==key else 'desc');self.render()
 def paginate(self,step):self.page=max(0,self.page+step);self.render()
 def open_selected(self):
  row=self.table.currentRow()
  if row>=0:self.open_stock(self.matches[self.page*50+row]['symbol'])
 def open_stock(self,symbol):self.selected=symbol;self.stack.setCurrentIndex(1);self.render_detail();self.terminal.send('market_view',{'symbol':symbol})
 def set_range(self,value):self.chart.range=value;self.chart.update()
 def trade(self,side):
  self.terminal.symbol=self.selected;self.terminal.trade_symbols.setCurrentText(self.selected);self.terminal.order_side.setCurrentIndex(0 if side=='buy' else 1);self.terminal.nav.setCurrentRow(self.terminal.page_names.index('Trading'))
 def open_options(self):self.terminal.symbol=self.selected;self.terminal.option_under.setCurrentText(self.selected);self.terminal.nav.setCurrentRow(self.terminal.page_names.index('Options'));self.terminal.generate_chain()
 def open_research(self):self.terminal.symbol=self.selected;self.terminal.nav.setCurrentRow(self.terminal.page_names.index('Research'))
 @staticmethod
 def value(v):return 'Unavailable' if v is None else f'{v:,.2f}'
 @staticmethod
 def percent(v):return 'Unavailable' if v is None else f'{v:.2f}%'
 @staticmethod
 def money(v,currency):return 'Reference required' if v is None else f'{currency} {v:,.4f}'
 def render_detail(self):
  r=next((r for r in self.world.get('market_explorer',{}).get('rows',[]) if r['symbol']==self.selected),None)
  if not r:return
  self.identity.setText(f"{r['name']} · {r['symbol']}\n{r['region']} · {r['exchange']} · {r['sector']} / {r['industry']}\n{self.money(r['price'],r['currency'])} · 24H {self.percent(r['change_1d'])} · 7D {self.percent(r['change_1w'])} · {r['execution_model']}")
  for button in [self.buy,self.sell,self.research]:button.setEnabled(r['active'] and r['status']=='OPEN')
  self.options.setEnabled(r['options_available']);self.watch.setText('Remove from watchlist' if r['symbol'] in self.world.get('watchlist',[]) else 'Add to watchlist');ins=self.world['instruments'].get(r['symbol']);self.chart.set_instrument(ins)
  held=self.world['positions'].get(self.terminal.active+':'+r['symbol'],{});lines=[f"Selected entity: {self.terminal.accounts.currentText()}\nShares {held.get('qty','0')}; value GBP {held.get('value','0')}; cost basis GBP {held.get('cost','0')}; unrealised P&L GBP {held.get('pnl','0')}",f"Executed 24H shares {self.value(r['volume_1d'])}; displayed depth {self.value(r['liquidity'])}; observed volatility {self.percent(r['volatility'])}",f"Market cap GBP {self.value(r['market_cap_gbp'])}; P/E {self.value(r['pe'])}; dividend yield {self.percent(r['dividend_yield'])}",f"Best bid {self.money(r['best_bid'],r['currency'])}; best ask {self.money(r['best_ask'],r['currency'])}; last execution in 24H {r['last_trade_24h'] or 'None recorded'}. Quotes can move without an execution.",'Fundamentals: '+json.dumps((ins or {}).get('fundamentals',{}),indent=2),r['classification_basis']]
  for n in r['news']:lines.append(n['time']+' · '+n['title']+'\n'+n['body'])
  for event in r['revisions']:lines.append(event['publication_time']+' · '+event['kind']+' · '+self.percent(event['severity']*100))
  for report in self.world.get('stock_research',[]):
   if report['symbol']==r['symbol'] and report['entity']==self.terminal.active:lines.append(report['analyst_name']+' · '+report['recommendation']+' · '+('Stale' if report['stale'] else 'Recent')+'\n'+'\n'.join(report['reasoning']))
  self.details.setPlainText('\n\n'.join(lines))
