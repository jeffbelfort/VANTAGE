/* Native transport: coalesce refreshes, surface timeouts, never replay mutations. */
(function(){
 function launch(){const script=document.createElement('script');script.src='app.js';document.body.appendChild(script)}
 if(typeof qt==='undefined'){launch();return}
 new QWebChannel(qt.webChannelTransport,function(channel){
  const bridge=channel.objects.vantage,pending=new Map();let seq=0;const statePending=new Map();
  if(bridge.progress)bridge.progress.connect(function(text){window.dispatchEvent(new CustomEvent('vantage-progress',{detail:text}))});
  bridge.response.connect(function(id,encoded){const request=pending.get(id);if(request){pending.delete(id);clearTimeout(request.timer);try{const r=JSON.parse(encoded);request.resolve({ok:r.ok,json:async()=>r.data})}catch(e){request.reject(e)}}});
  window.fetch=function(path,opts={}){
   if(!String(path).startsWith('/api/'))return Promise.reject(Error('External requests are disabled in native transport'));
   const state=path==='/api/state'&&(opts.method||'GET')==='GET',view=opts.headers?.['X-Vantage-View']||'full';if(state&&statePending.has(view))return statePending.get(view);
   const promise=new Promise((resolve,reject)=>{const id=String(++seq),timer=state?setTimeout(()=>{pending.delete(id);reject(Error('Loading is taking longer than expected. Your save has not been reset; close and relaunch VANTAGE if this persists.'))},60000):null;pending.set(id,{resolve,reject,timer});bridge.request(id,JSON.stringify({path,method:opts.method||'GET',body:opts.body?JSON.parse(opts.body):{},view,key:opts.headers?.['Idempotency-Key']}))});
   if(state){statePending.set(view,promise);promise.then(()=>{statePending.delete(view)},()=>{statePending.delete(view)})}return promise;
  };
  launch();
 });
})();
