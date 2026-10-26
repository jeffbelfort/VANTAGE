const fs=require('fs'),path=require('path'),ts=require('typescript');
const files={};
function include(id,file){files[id]=fs.readFileSync(file,'utf8')}
include('react','node_modules/react/cjs/react.production.js');
include('react-dom','node_modules/react-dom/cjs/react-dom.production.js');
include('react-dom/client','node_modules/react-dom/cjs/react-dom-client.production.js');
include('scheduler','node_modules/scheduler/cjs/scheduler.production.js');
files.app=ts.transpileModule(fs.readFileSync('ui/App.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,esModuleInterop:true}}).outputText;
let out='(()=>{const process={env:{NODE_ENV:"production"}},modules={'+Object.entries(files).map(([k,v])=>JSON.stringify(k)+':function(module,exports,require){\n'+v+'\n}').join(',')+'};const cache={};function require(id){if(cache[id])return cache[id].exports;const m=cache[id]={exports:{}};modules[id](m,m.exports,require);return m.exports}require("app")})();';
fs.writeFileSync('static/app.js',out);console.log('Built static/app.js',out.length,'bytes');
