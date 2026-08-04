const names={prepare:"准备条件",device:"识别设备",firmware:"核对固件",risk:"风险确认",execute:"执行刷机",result:"查看结果"};
const endpoints={prepare:["运行准备检查","/api/v1/preflight",{}],device:["识别唯一设备","/api/v1/device/identify",{}],firmware:["核对固件","/api/v1/firmware/inspect",null],risk:["制作并刷入","/api/v1/operations",{}]};
const phases=document.querySelector("#phases"),message=document.querySelector("#message"),details=document.querySelector("#details"),button=document.querySelector("#action"),exportButton=document.querySelector("#export"),fileRow=document.querySelector("#file-row"),filename=document.querySelector("#filename"),loginActions=document.querySelector("#login-actions"),loginStart=document.querySelector("#login-start"),loginComplete=document.querySelector("#login-complete"),loginQr=document.querySelector("#login-qr");
let state;
function render(value){
  state=value;
  phases.innerHTML=Object.entries(names).map(([key,label])=>`<li class="${key===value.phase?'active':''}">${label}</li>`).join("");
  message.textContent=value.message||"无法确认";
  details.textContent=JSON.stringify({状态:value.status,设备:value.device,固件:value.firmware,证据:value.evidence,操作:value.operation},null,2);
  fileRow.hidden=value.phase!=="firmware";
  loginActions.hidden=value.phase!=="device";
  loginComplete.hidden=!value.qr_available||value.login_status==="verifying";
  loginStart.textContent=value.login_status==="failed"?"重新生成登录二维码":"生成登录二维码";
  loginStart.disabled=value.login_status==="verifying";
  loginQr.hidden=!value.qr_available;
  exportButton.hidden=value.phase!=="result"||!value.operation_id;
  if(value.qr_available&&!loginQr.src)loginQr.src=`/api/v1/device/login-qr?t=${Date.now()}`;
  if(!value.qr_available){loginQr.removeAttribute("src");loginQr.hidden=true;}
  if(value.phase==="execute"||value.phase==="result"){button.disabled=true;button.textContent="只读查询";return;}
  const action=endpoints[value.phase];button.disabled=!action;button.textContent=action?action[0]:"不可操作";
}
async function call(path,body){const response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const value=await response.json();if(!response.ok)throw new Error(value.error||"操作失败");render(value);}
loginStart.addEventListener("click",async()=>{loginStart.disabled=true;try{loginQr.removeAttribute("src");await call("/api/v1/device/login/start",{});}catch(error){message.textContent=error.message;}finally{loginStart.disabled=false;}});
loginComplete.addEventListener("click",async()=>{loginComplete.disabled=true;try{await call("/api/v1/device/login/complete",{});}catch(error){message.textContent=error.message;}finally{loginComplete.disabled=false;}});
exportButton.addEventListener("click",()=>{if(state&&state.operation_id)location.href=`/api/v1/operations/${state.operation_id}/export`;});
button.addEventListener("click",async()=>{button.disabled=true;try{if(state.phase==="risk"&&state.operation_id){await call(`/api/v1/operations/${state.operation_id}/start`,{});return;}const [,,preset]=endpoints[state.phase];const body=state.phase==="firmware"?{filename:filename.value}:preset;const before=state.phase;await call(endpoints[before][1],body);if(before==="risk"&&state.operation_id){button.disabled=false;button.textContent="启动已建立的操作";}}catch(error){message.textContent=error.message;button.disabled=false;}});
async function refresh(){try{const response=await fetch("/api/v1/session",{cache:"no-store"});if(!response.ok)throw new Error();render(await response.json());}catch(error){message.textContent="本机服务无法读取";}}
refresh();setInterval(refresh,1000);
