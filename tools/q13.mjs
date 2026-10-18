const email=process.argv[2];
function be(e){let t=2166136261;for(let s of String(e||"").trim().toLowerCase())t=Math.imul(t^s.charCodeAt(0),16777619)>>>0;let r=`job-${t.toString(16)}`,n=[[{response:`Report ${r}: `,done:!1},{thinking:"internal note",response:"",done:!1},{response:`caf\xE9\n`,done:!1},{response:"Ready ✓",done:!0,done_reason:"stop"}],[{response:`Partial ${r}`,done:!1}],[{response:`Draft ${r}`,done:!1},{error:"model unloaded"},{response:"IGNORE",done:!0}]].map((s,c)=>{let d=s.map(a=>JSON.stringify(a)).join(`\n`)+`\n`+(c===1?'{"response":"unfinished':""),l=new TextEncoder().encode(d),i=[];for(let a=0;a<l.length;){let u=Math.min(a+11+a%13,l.length),m=l.findIndex((p,h)=>h>=a&&h<u&&p>=192);m>=0&&(u=m+1),i.push(Array.from(l.slice(a,u),p=>p.toString(16).padStart(2,"0")).join("")),a=u}return i});return{tag:r,streams:n}}
const {streams}=be(email); const out={};
["A","B","C"].forEach((k,i)=>{
  const bytes=Buffer.concat(streams[i].map(h=>Buffer.from(h,'hex')));
  const text=bytes.toString('utf8'); const lines=text.split('\n'); const tail=lines.pop();
  let t="",complete=false,error=null,stopped=false;
  for(const ln of lines){ if(!ln.trim())continue; const o=JSON.parse(ln);
    if(o.error){error=o.error;stopped=true;break}
    if(typeof o.response==='string')t+=o.response;
    if(o.done===true){complete=true;stopped=true;break}}
  out[k]={text:t,complete,error};
});
console.log(JSON.stringify(out));
