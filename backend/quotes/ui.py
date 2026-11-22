"""Single-file demo page: upload two quote PDFs, compare, click a value to see its source."""

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>QuoteLens</title>
<style>
:root{--bg:#fff;--fg:#14181f;--mut:#5b6472;--line:#dfe3ea;--acc:#1f3a5f;--warn:#9a5b00;--bad:#b3261e;--ok:#1b6e3c}
@media(prefers-color-scheme:dark){:root{--bg:#12161c;--fg:#e8ebf0;--mut:#9aa3b2;--line:#2b323d;--acc:#8fb4e8;--warn:#e0a84a;--bad:#f2867f;--ok:#6cc58c}}
body{font:14px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg);margin:0;padding:20px;max-width:980px;margin:auto}
h1{font-size:20px;color:var(--acc);margin:0 0 4px}p.s{color:var(--mut);margin:0 0 16px}
.row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px}input,button{font:inherit;padding:7px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
button{background:var(--acc);color:var(--bg);cursor:pointer;border:0}table{border-collapse:collapse;width:100%;margin-top:12px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}th{color:var(--mut);font-weight:600}
td.v{cursor:pointer}td.v:hover{outline:2px solid var(--acc)}.flag{color:var(--warn);font-size:12px}.bad{color:var(--bad)}.ok{color:var(--ok)}
pre{white-space:pre-wrap;border:1px solid var(--line);border-radius:6px;padding:10px;max-height:240px;overflow:auto}mark{background:#ffe08a;color:#000}
#err{color:var(--bad)}.wrap{overflow-x:auto}
</style></head><body>
<h1>QuoteLens</h1><p class="s">Compare two commercial insurance quotes. Every value links to the exact text it came from; values that cannot be verified are flagged. Demo only: use sample documents, not real client data.</p>
<div class="row"><input id="t" placeholder="tenant id" value="demo_corp"><input id="k" type="password" placeholder="api key"></div>
<div class="row"><input id="f1" type="file" accept="application/pdf"><input id="f2" type="file" accept="application/pdf"><button id="go">Compare</button></div>
<div id="err"></div><div class="wrap" id="out"></div><h3 id="srch" hidden>Source text</h3><pre id="src" hidden></pre>
<script>
const $=id=>document.getElementById(id), esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const H=()=>({"X-Tenant-Id":$("t").value,"X-Api-Key":$("k").value});
const money=n=>n==null?"-":"$"+Number(n).toLocaleString("en-US");
async function api(path,opt={}){const r=await fetch("/api/v3/quotes"+path,{...opt,headers:{...H(),...(opt.headers||{})}});
 const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(typeof j.detail==="string"?j.detail:"request failed ("+r.status+")");return j}
async function up(file){const fd=new FormData();fd.append("file",file);return api("/upload",{method:"POST",body:fd})}
const pagesCache={};
async function show(qid,cite){if(!pagesCache[qid])pagesCache[qid]=(await api("/"+qid)).pages;
 const t=pagesCache[qid][cite.page-1];$("srch").hidden=$("src").hidden=false;$("srch").textContent="Source text, page "+cite.page;
 $("src").innerHTML=esc(t.slice(0,cite.start))+"<mark>"+esc(t.slice(cite.start,cite.end))+"</mark>"+esc(t.slice(cite.end))}
$("go").onclick=async()=>{$("err").textContent="";$("out").innerHTML="";
 try{const a=$("f1").files[0],b=$("f2").files[0];if(!a||!b)throw new Error("choose two PDF files");
  const [qa,qb]=await Promise.all([up(a),up(b)]);const c=await api("/compare",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({quote_ids:[qa.id,qb.id]})});
  let h="<table><tr><th>Coverage</th>"+c.quotes.map(q=>"<th>"+esc(q.name)+"</th>").join("")+"<th>Flags</th></tr>";
  c.rows.forEach((r,ri)=>{h+="<tr><td>"+esc(r.coverage.replace(/_/g," "))+"</td>";
   c.quotes.forEach((q,qi)=>{const v=r.by_quote[q.id];h+=v?`<td class="v" data-r="${ri}" data-q="${q.id}">${money(v.limit)} limit<br>${money(v.deductible)} deductible<br><span class="${v.verified?"ok":"bad"}">${v.verified?"verified":"unverified"}</span></td>`:'<td class="bad">not quoted</td>'});
   h+="<td>"+r.flags.map(f=>'<div class="flag">'+esc(f)+"</div>").join("")+"</td></tr>"});
  $("out").innerHTML=h+"</table>";
  $("out").querySelectorAll("td.v").forEach(td=>td.onclick=()=>show(td.dataset.q,c.rows[td.dataset.r].by_quote[td.dataset.q].limit_cite));
 }catch(e){$("err").textContent=e.message}};
</script></body></html>"""
