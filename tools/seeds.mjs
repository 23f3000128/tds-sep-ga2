import seedrandom from 'seedrandom';
const email=(process.argv[2]||'').trim().toLowerCase(), v='';
const C="abcdefghijklmnopqrstuvwxyz0123456789";
const rs=(r,n)=>Array.from({length:n},()=>C[Math.floor(r()*C.length)]).join('');
const fnv=s=>{let t=2166136261;for(const ch of s.trim().toLowerCase())t=Math.imul(t^ch.charCodeAt(0),16777619)>>>0;return t};
const out={email};
// Q1 httpbin
{const t=fnv(email);out.q1={tag:`http-${t.toString(16)}`,quantity:2+t%19,status:[400,404,418,422][t%4]};}
// Q3
{const r=seedrandom(`q-fastapi-metrics-cors-server#${email}#${v}`);out.q3={allowedOrigin:`https://dash-${rs(r,6)}.example.com`};}
// Q4
{const r=seedrandom(`q-oauth-jwks-verify-server#${email}#${v}`);out.q4={iss:'https://idp.exam.local',aud:`tds-${rs(r,8)}.apps.exam.local`};}
// Q5
{const r=seedrandom(`q-config-precedence-server#${email}#${v}`);const M=["port","workers","debug","log_level","api_key"],j=["debug","info","warning","error"];
const pick=p=>p[Math.floor(r()*p.length)],ni=(a,b)=>a+Math.floor(r()*(b-a+1));
const c=()=>{let p={};for(const h of M)if(r()<.5){if(h==="port")p[h]=ni(8000,9000);else if(h==="workers")p[h]=ni(1,16);else if(h==="debug")p[h]=r()<.5;else if(h==="log_level")p[h]=pick(j);else p[h]=`key-${rs(r,10)}`}return p};
out.q5={yaml:c(),dotenv:c(),osenv:c()};}
// Q7
{const r=seedrandom(`q-deploy-analytics-platform-server#${email}#${v}`);out.q7={apiKey:`ak_${rs(r,24)}`};}
// Q11
{const r=seedrandom(`q-api-idempotency-pagination-server#${email}#${v}`);const o=(a,b)=>a+Math.floor(r()*(b-a+1));out.q11={total:o(40,60),rateLimit:o(15,20)};}
// Q12
{const r=seedrandom(`q-middleware-ratelimit-cors-server#${email}#${v}`);out.q12={allowedOrigin:`https://app-${rs(r,6)}.example.com`,bucket:8+Math.floor(r()*8)};}
// Q14
{const t=fnv(email);out.q14={install:40+t%31,compile:10+t%11,test:15+t%16};}
// Q15
{const t=fnv(email);out.q15={model:`ga2-assistant-${t.toString(16)}`,system:`You are the deployment assistant for project ${t.toString(16)}. Give concise answers and never invent commands.`,temperature:[.1,.2,.3][t%3],num_ctx:[2048,4096][t%2],seed:10+t%990,num_predict:64+t%65};}
console.log(JSON.stringify(out,null,1));
