/* Factory controls call the original native protocol; this adapter adds lifecycle
   ownership, safe name rendering, file-save confirmation and a bounded preview. */
'use strict';
let ended=false, unsaved=false, inflight=false, lastState={};
const byId=id=>document.getElementById(id);
const feedback=message=>{byId('feedback').textContent=message;};
const errors={native_session_ended:'Camera session ended. Return to Kadence and reopen UnitV2 training.',
  no_native_training_sample_yet:'No face has been accepted yet. Face the camera, then try Save again.',
  save_or_finish_current_training_first:'Save the current training first, or Finish to discard it.',
  one_person_at_a_time:'Keep just one person in view before training.',
  native_save_not_verified:'Save was not verified. Previous files have an onboard backup. Keep this page open and retry Save.',
  native_name_already_saved:'Choose a different name; this name is already saved.'};
async function api(path,data={}){
  const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),10000);
  try{
    const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal:controller.signal});
    const value=await r.json();
    if(!r.ok)throw Error(errors[value.error]||value.error||'UnitV2 request failed.');
    return value;
  }finally{clearTimeout(timer);}
}
function end(message){ended=true;document.querySelectorAll('button,input').forEach(e=>e.disabled=true);feedback(message);byId('preview').getContext('2d').clearRect(0,0,640,480);}
// Factory HTML concatenates names into attributes. Keep its selection behaviour,
// but use DOM values so spaces, quotes and non-ASCII names remain literal text.
face_recognition_btn_add_cb=function(name){
  if(face_recognition_type_count>=10)return;
  const div=document.createElement('div');div.className='trainning-input';
  const choose=document.createElement('button');choose.className='btn-trainning';choose.type='button';choose.setAttribute('aria-label','Select profile');choose.onclick=()=>face_recognition_type_selected(choose);
  const input=document.createElement('input');input.value=name||'face_'+face_recognition_type_count;input.maxLength=80;input.onchange=()=>face_recognition_type_val_change(input);
  div.append(choose,input);byId('dynamic_func_area').append(div);face_recognition_type_count++;
  face_recognition_type_selected(choose);
};
// Observe the factory XHR responses without replacing its train/stop/save protocol.
const originalOpen=XMLHttpRequest.prototype.open,originalSend=XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open=function(method,url,...rest){this.nativeCommand=url==='/data_to_device';return originalOpen.call(this,method,url,...rest);};
XMLHttpRequest.prototype.send=function(body){
  if(this.nativeCommand){
    if(inflight||ended)return;
    inflight=true;this.timeout=10000;
    document.querySelectorAll('#add,#save,#face_recognition_train').forEach(e=>e.disabled=true);
    this.addEventListener('loadend',()=>{
      inflight=false;document.querySelectorAll('#add,#save,#face_recognition_train').forEach(e=>e.disabled=ended);
      let result;try{result=JSON.parse(this.responseText);}catch{result={};}
      if(this.status!==200){feedback(errors[result.error]||result.error||'Command did not complete. Check the live status before retrying.');
        face_recognition_btn_train_flag=lastState.training?1:0;byId('face_recognition_train').textContent=lastState.training?'stop':'train';}
      else if(result.message){feedback(result.message);if(result.message.includes('saved and verified'))byId('saved').textContent=result.message;}
    });
  }
  return originalSend.call(this,body);
};
function draw(image,result){
  const context=byId('preview').getContext('2d');context.drawImage(image,0,0,640,480);
  const faces=result.face||(result.status?[result]:[]);
  for(const face of faces){
    if(!['x','y','w','h'].every(k=>Number.isFinite(face[k])))continue;
    context.strokeStyle=result.status?'#ffcd65':'#62e4ba';context.lineWidth=3;context.strokeRect(face.x,face.y,face.w,face.h);
    context.font='18px system-ui';context.fillStyle=context.strokeStyle;
    const score=Number.isFinite(face.match_prob)?` · ${(face.match_prob*100).toFixed(1)}%`:'';
    context.fillText((face.name||'unidentified')+score,Math.max(3,face.x),Math.max(20,face.y-7));
  }
}
async function loop(){
  while(!ended){
    try{
      lastState=await api('/native/state');unsaved=lastState.unsaved;
      byId('saved').textContent=unsaved?'Unsaved training · click Save to commit onboard.':lastState.message;
      const result=lastState.result||{};
      byId('score').textContent=lastState.training?`Native training: ${lastState.accepted} accepted frame(s) · ${result.status||'waiting for a face'}`:
        (result.face||[]).map(f=>f.name+(Number.isFinite(f.match_prob)?` · ${(f.match_prob*100).toFixed(1)}% native match`:'')).join(' / ')||'No fresh native face match.';
      const r=await fetch('/native/frame',{cache:'no-store',signal:AbortSignal.timeout(5000)});
      if(r.ok){const image=await createImageBitmap(await r.blob());draw(image,result);image.close();}
      else if(r.status===401||r.status===409)throw Error(errors.native_session_ended);
    }catch(e){end(e.message+' Reopen from Kadence if needed.');break;}
    await new Promise(resolve=>setTimeout(resolve,300));
  }
}
byId('finish').onclick=async()=>{
  if(unsaved&&!confirm('Finish without saving this training? Previously saved onboard profiles are kept.'))return;
  try{await api('/native/finish');end('Camera stopped. Return to Kadence, refresh Profiles, then run Live Recognition Check.');}
  catch(e){end(e.message);}
};
window.addEventListener('beforeunload',event=>{if(unsaved&&!ended){event.preventDefault();event.returnValue='';}});
window.addEventListener('pagehide',()=>{fetch('/native/finish',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',keepalive:true}).catch(()=>{});});
(async()=>{
  try{const data=await api('/data_from_device');(data.faces||[]).forEach(face=>face_recognition_btn_add_cb(face.name));
    feedback('Live native recognition. Select a profile to train, or test an existing match.');await loop();}
  catch(e){end(e.message);}
})();
