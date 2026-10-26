"""Native workspace navigation, independent of simulation and saved-world state.
The hidden legacy route list remains the index/shortcut adapter; this widget is
its user-facing workspace and destination view. Preferences live in this session.
"""
from pathlib import Path
from PyQt6.QtCore import Qt, QSize, QSignalBlocker
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QLabel,QPushButton,QToolButton,QListWidget,QListWidgetItem,QScrollArea

WORKSPACES=[
 ('markets','Markets','Trading',['Overview','Trading','Markets','Options','Research','Risk','Federal Reserve','Newswire']),
 ('corporate','Corporate','My Companies',['My Companies','Company Acquisitions','Corporate Structure','Corporate Actions']),
 ('banking','Banking','Banking',['Banking','Bank Management']),
 ('finance','Finance','Portfolio',['Portfolio','Institutional Operations','Institutions','Investors','Financial Statements','Property & offices','Wealth & Lifestyle']),
 ('people','People & oversight','Executive Office',['Executive Office','Employees','Oversight','Financial Crime','Communications','Investigations','Career']),
 ('system','System','Settings',['Settings','Administration'])]
LABELS={'Company Acquisitions':'Company Marketplace','Bank Management':'Bank operations','Banking':'Accounts & borrowing','Corporate Structure':'Group structure','Corporate Actions':'Listed corporate actions','Institutions':'Create institutions','Administration':'World administration','Oversight':'Oversight & resolution'}
GLYPHS={'markets':'M3 16V5m0 11h18M6 13l4-5 4 3 6-7','corporate':'M8 8V3h8v5M3 21V9h18v12M8 13h1m6 0h1M8 17h1m6 0h1','banking':'M3 8l9-5 9 5H3m3 3v7m6-7v7m6-7v7M3 21h18','finance':'M4 5h16v15H4V5m0 5h16m-5 5h3','people':'M8 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8m-5 9v-3a5 5 0 0 1 10 0v3m3-16a4 4 0 0 1 0 8m0 3a5 5 0 0 1 5 5','system':'M4 6h16M4 12h16M4 18h16M8 3v6m8 0v6m-6 0v6'}
STYLE='''
QWidget#WorkspaceNavigation{background:#121b23;color:#c6d6e0;}
QWidget#NavigationRailViewport,QWidget#NavigationSwitches{background:#0b1219;}
QToolButton#NavigationHome,QToolButton#NavigationSearch{background:transparent;color:#a7bdcb;border:2px solid transparent;border-radius:4px;padding:8px;}
QToolButton#NavigationHome:hover,QToolButton#NavigationSearch:hover{background:#20313e;}
QWidget#NavigationRail{background:#0b1219;border-right:1px solid #293a46;}
QToolButton#WorkspaceSwitch{border:2px solid transparent;border-radius:4px;background:transparent;color:#9eb5c6;font-size:9px;padding:7px 1px;min-height:44px;}
QToolButton#WorkspaceSwitch:hover{background:#20313e;color:#f0f6fa;}
QToolButton#WorkspaceSwitch:checked{background:#1b3c31;color:#8aebc5;border-left:3px solid #65dbb0;}
QToolButton#WorkspaceSwitch:focus,QToolButton#NavigationHome:focus,QToolButton#NavigationSearch:focus,QPushButton#NavigationShortcut:focus,QListWidget#NavigationDestinations:focus{border:2px solid #79e5bf;}
QToolButton#NavigationPin:focus,QPushButton#NavigationFind:focus{border:1px solid #79e5bf;}
QLabel#NavigationBrand{color:#edf4f8;font-size:15px;font-weight:600;letter-spacing:2px;}
QLabel#NavigationHeading{color:#e2edf2;font-size:14px;font-weight:600;}
QLabel#NavigationSubtle{color:#90aabb;font-size:10px;}
QPushButton#NavigationShortcut{border:2px solid transparent;background:transparent;text-align:left;color:#b6cbd8;padding:6px;font-size:10px;min-height:17px;}
QPushButton#NavigationShortcut:hover{background:#213340;}
QPushButton#NavigationShortcut[active=true]{background:#1b382f;color:#87edc7;}
QPushButton#NavigationFind{background:#172630;color:#bbceda;border:1px solid #344b5a;border-radius:4px;padding:8px;font-size:10px;text-align:left;}
QListWidget#NavigationDestinations{background:transparent;border:2px solid transparent;outline:0;color:#b4c8d6;font-size:11px;}
QListWidget#NavigationDestinations::item{padding:9px 6px;border-radius:4px;margin-bottom:3px;}
QListWidget#NavigationDestinations::item:selected{background:#1b382f;color:#87edc7;border-left:2px solid #65dbb0;}
QListWidget#NavigationDestinations::item:hover{background:#20313d;}
QToolButton#NavigationPin{background:transparent;color:#9bb8c9;border:1px solid #344955;border-radius:4px;padding:5px;}
QScrollArea{border:0;background:transparent;}
QScrollBar:vertical{width:7px;background:transparent;}
QScrollBar::handle:vertical{background:#405260;min-height:20px;border-radius:3px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
'''

def navigation_label(route):return LABELS.get(route,route)
def workspace_for(route):return next((id for id,_,_,pages in WORKSPACES if route in pages),'system')

class NativeWorkspaceNavigation(QWidget):
 def __init__(self,routes,on_navigate,on_search,parent=None):
  super().__init__(parent);self.setObjectName('WorkspaceNavigation');self.setStyleSheet(STYLE);self.routes=list(routes);self.on_navigate=on_navigate;self.page='';self.workspace='';self.positions={};self.remembered={};self.buttons={};self.pinned=[r for r in ('Trading','My Companies','Banking','Portfolio') if r in self.routes]
  root=QHBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0);rail=QWidget();rail.setObjectName('NavigationRail');rail.setFixedWidth(60);rl=QVBoxLayout(rail);rl.setContentsMargins(4,12,4,8);rl.setSpacing(5)
  home=QToolButton();home.setObjectName('NavigationHome');home.setIcon(QIcon(str(Path(__file__).resolve().parent.parent/'static/icon.svg')));home.setIconSize(QSize(25,31));home.setAccessibleName('VANTAGE overview');home.setToolTip('VANTAGE overview');home.clicked.connect(lambda:self.select_page('Overview'));rl.addWidget(home)
  rail_scroll=QScrollArea();rail_scroll.viewport().setObjectName('NavigationRailViewport');rail_scroll.setWidgetResizable(True);rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);switches=QWidget();switches.setObjectName('NavigationSwitches');switch_layout=QVBoxLayout(switches);switch_layout.setContentsMargins(0,0,0,0);switch_layout.setSpacing(5)
  for id,label,home_route,pages in WORKSPACES:
   available=[r for r in pages if r in self.routes];self.remembered[id]=home_route if home_route in self.routes else available[0] if available else None
   button=QToolButton();button.setObjectName('WorkspaceSwitch');button.setCheckable(True);button.setText('People' if id=='people' else label);button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon);button.setAccessibleName(label+' workspace');button.setToolTip(label);button.setEnabled(bool(available) or id=='system');button.setFixedWidth(51)
   image=QPixmap();image.loadFromData(('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="none" stroke="#a7bdcb" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" d="'+GLYPHS[id]+'"/></svg>').encode(),'SVG');button.setIcon(QIcon(image));button.setIconSize(QSize(21,21));button.clicked.connect(lambda checked=False,key=id:self.select_workspace(key));self.buttons[id]=button;switch_layout.addWidget(button)
  switch_layout.addStretch();rail_scroll.setWidget(switches);rl.addWidget(rail_scroll,1)
  search=QToolButton();search.setObjectName('NavigationSearch');search.setText('⌕');search.setAccessibleName('Search all destinations');search.setToolTip('Find a destination · Ctrl+K');search.clicked.connect(on_search);rl.addWidget(search);root.addWidget(rail)
  context=QWidget();layout=QVBoxLayout(context);layout.setContentsMargins(10,17,10,9);layout.setSpacing(11);brand=QLabel('VANTAGE');brand.setObjectName('NavigationBrand');layout.addWidget(brand)
  find=QPushButton('Find a destination    Ctrl K');find.setObjectName('NavigationFind');find.clicked.connect(on_search);layout.addWidget(find)
  pinned_label=QLabel('PINNED');pinned_label.setObjectName('NavigationSubtle');layout.addWidget(pinned_label);self.shortcuts=QWidget();self.shortcut_layout=QVBoxLayout(self.shortcuts);self.shortcut_layout.setContentsMargins(0,0,0,0);self.shortcut_layout.setSpacing(1);layout.addWidget(self.shortcuts)
  self.heading=QLabel();self.heading.setObjectName('NavigationHeading');layout.addWidget(self.heading);self.current=QLabel();self.current.setWordWrap(True);self.current.setObjectName('NavigationSubtle');layout.addWidget(self.current)
  self.destinations=QListWidget();self.destinations.setObjectName('NavigationDestinations');self.destinations.setAccessibleName('Workspace destinations');self.destinations.setWordWrap(True);self.destinations.setTextElideMode(Qt.TextElideMode.ElideNone);self.destinations.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.destinations.currentItemChanged.connect(lambda item,previous:self.select_page(item.data(Qt.ItemDataRole.UserRole)) if item else None);layout.addWidget(self.destinations,1)
  self.pin=QToolButton();self.pin.setObjectName('NavigationPin');self.pin.clicked.connect(self.toggle_pin);layout.addWidget(self.pin);root.addWidget(context,1);self.render_pins();self.sync_page('Overview' if 'Overview' in self.routes else self.routes[0])
 def pages(self,group):
  ordered=next((pages for id,_,_,pages in WORKSPACES if id==group),[])
  return [r for r in ordered if r in self.routes]+[r for r in self.routes if workspace_for(r)==group and r not in ordered]
 def select_workspace(self,group):
  route=self.remembered.get(group) or next(iter(self.pages(group)),None)
  if route:self.select_page(route)
 def select_page(self,route):
  if route not in self.routes:return
  self.sync_page(route);self.on_navigate(route)
 def sync_page(self,route):
  if route not in self.routes:return
  group=workspace_for(route);changed=group!=self.workspace
  if changed:
   if self.workspace:self.positions[self.workspace]=self.destinations.verticalScrollBar().value()
   self.workspace=group
   with QSignalBlocker(self.destinations):
    self.destinations.clear()
    for destination in self.pages(group):
     item=QListWidgetItem(navigation_label(destination));item.setData(Qt.ItemDataRole.UserRole,destination);item.setToolTip(navigation_label(destination));self.destinations.addItem(item)
  self.page=route;self.remembered[group]=route
  with QSignalBlocker(self.destinations):
   for i in range(self.destinations.count()):
    if self.destinations.item(i).data(Qt.ItemDataRole.UserRole)==route:self.destinations.setCurrentRow(i);break
  if changed:self.destinations.verticalScrollBar().setValue(self.positions.get(group,0))
  for id,label,_,_ in WORKSPACES:
   self.buttons[id].setChecked(id==group)
   if id==group:self.heading.setText(label)
  self.current.setText(navigation_label(route));pin_label=('★ Unpin ' if route in self.pinned else '☆ Pin ')+navigation_label(route);self.pin.setText(pin_label.replace('&','&&'));self.pin.setAccessibleName(pin_label);self.pin.setEnabled(route in self.pinned or len(self.pinned)<6)
  for b in self.shortcuts.findChildren(QPushButton):b.setProperty('active',b.property('route')==route);b.style().unpolish(b);b.style().polish(b)
 def toggle_pin(self):
  if self.page in self.pinned:self.pinned.remove(self.page)
  elif len(self.pinned)<6:self.pinned.append(self.page)
  self.render_pins();self.sync_page(self.page)
 def render_pins(self):
  while self.shortcut_layout.count():
   item=self.shortcut_layout.takeAt(0);item.widget().deleteLater()
  for route in self.pinned:
   button=QPushButton(navigation_label(route).replace('&','&&'));button.setAccessibleName(navigation_label(route));button.setObjectName('NavigationShortcut');button.setProperty('route',route);button.setToolTip(navigation_label(route));button.clicked.connect(lambda checked=False,r=route:self.select_page(r));self.shortcut_layout.addWidget(button)
