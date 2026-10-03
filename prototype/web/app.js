let csrf='',busy=false,recorder=null,chunks=[],timer=null;
const messages=document.querySelector('#messages');
const mic=document.querySelector('#mic');
function bubble(text,role='assistant'){
 const el=document.createElement('article');el.className='message '+role;
 const label=document.createElement('div');label.className='agent-label';label.textContent=role==='user'?'TÚ':'NOEMA';
 const p=document.createElement('div');p.textContent=text;el.append(label,p);messages.append(el);messages.scrollTop=messages.scrollHeight;return el;
}
async function api(path,body){
 const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Noema-Local':'1','X-CSRF-Token':csrf},body:JSON.stringify(body||{})});
 const data=await response.json();if(!response.ok)throw new Error(data.detail||'No se pudo completar la solicitud');return data;
}
function speak(text){
 if(!document.querySelector('#read-aloud').checked||!window.speechSynthesis)return;
 const voices=speechSynthesis.getVoices().filter(v=>v.localService&&v.lang.startsWith('es'));
 if(!voices.length){document.querySelector('#voice-status').textContent='No hay voz española local instalada; respuesta disponible en texto.';return;}
 speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(text);utterance.voice=voices[0];utterance.lang='es';speechSynthesis.speak(utterance);
}
async function send(text){
 if(busy||!text.trim())return;if(!csrf){bubble('La sesión se está iniciando; vuelve a intentar.');return;}busy=true;document.querySelector('#send').disabled=true;bubble(text,'user');document.querySelector('#message').value='';
 try{
  const result=await api('/api/chat',{message:text});const el=bubble(result.message);speak(result.message);
  document.querySelector('#source').textContent=result.source;document.querySelector('#intent').textContent=result.intent;
  document.querySelector('#epistemic').textContent=result.scm.epistemic_status;document.querySelector('#scm').textContent=JSON.stringify(result.scm,null,2);
  if(result.action){const button=document.createElement('button');button.className='confirm';button.textContent='Confirmar: '+result.action.label;
   button.onclick=async()=>{button.disabled=true;try{const receipt=await api('/api/confirm',{action_id:result.action.id});bubble(receipt.message);button.textContent='Simulación verificada';}catch(e){bubble(e.message);button.disabled=false;}};el.append(button);}
 }catch(e){bubble('No pude completar la solicitud. '+e.message);}finally{busy=false;document.querySelector('#send').disabled=false;}
}
document.querySelector('#composer').addEventListener('submit',e=>{e.preventDefault();send(document.querySelector('#message').value);});
document.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>send(b.dataset.prompt));
document.querySelector('#cases').onclick=async()=>{try{const response=await fetch('/api/cases',{headers:{'X-CSRF-Token':csrf}});const d=await response.json();if(!response.ok)throw new Error(d.detail);bubble(d.cases.length?d.cases.map(c=>`${c.id}: ${c.reason} · pendiente local`).join('\n'):'No hay solicitudes en esta sesión demo.');}catch(e){bubble(e.message);}};
document.querySelector('#home').onclick=()=>document.querySelector('#message').focus();
mic.onclick=async()=>{
 let activeStream=null;
 if(recorder&&recorder.state==='recording'){recorder.stop();return;}
 try{
  if(!window.MediaRecorder)throw new Error('Este navegador no admite grabación; puedes escribir.');
  const stream=await navigator.mediaDevices.getUserMedia({audio:true});activeStream=stream;chunks=[];recorder=new MediaRecorder(stream);
  recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
  recorder.onstop=async()=>{clearTimeout(timer);stream.getTracks().forEach(t=>t.stop());mic.classList.remove('recording');mic.textContent='◉ Hablar con Noema';mic.disabled=true;
   document.querySelector('#voice-status').textContent='Transcribiendo en tu equipo…';
   try{const data=new FormData();data.append('audio',new Blob(chunks,{type:recorder.mimeType}),'voice.webm');const response=await fetch('/api/transcribe',{method:'POST',headers:{'X-Noema-Local':'1','X-CSRF-Token':csrf},body:data});const out=await response.json();if(!response.ok)throw new Error(out.detail);document.querySelector('#transcript').value=out.text;document.querySelector('#voice-review').hidden=false;document.querySelector('#voice-status').textContent='Revisa el texto antes de enviarlo.';}catch(e){bubble(e.message);document.querySelector('#voice-status').textContent='Puedes continuar escribiendo.';}finally{mic.disabled=false;chunks=[];}
  };
  recorder.start();mic.classList.add('recording');mic.textContent='■ Terminar grabación';document.querySelector('#voice-status').textContent='Grabando · máximo 30 segundos';timer=setTimeout(()=>{if(recorder.state==='recording')recorder.stop();},30000);
 }catch(e){if(activeStream)activeStream.getTracks().forEach(t=>t.stop());document.querySelector('#voice-status').textContent='Micrófono no disponible. Puedes escribir.';}
};
document.querySelector('#send-transcript').onclick=()=>{const text=document.querySelector('#transcript').value;document.querySelector('#voice-review').hidden=true;send(text);};
document.querySelector('#cancel-transcript').onclick=()=>{document.querySelector('#voice-review').hidden=true;document.querySelector('#transcript').value='';};
api('/api/session').then(d=>{csrf=d.csrf;}).catch(e=>bubble('No se pudo iniciar la sesión local: '+e.message));
