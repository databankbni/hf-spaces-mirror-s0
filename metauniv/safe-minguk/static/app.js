
const $=id=>document.getElementById(id);
// 방어심층: 사용자 유래 값을 innerHTML에 넣기 전 HTML 이스케이프(서버 안전화와 이중 방어)
function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
let ADDR="", DIS=null, CHOICES=[], META=null, _last={};
let SIM=null, SCH=[], CUR=null, _pm=null;
let SEED=0;   // 시나리오 변형 시드. '다른 상황' 버튼이 +1 → variant%n 이 반드시 다음 변형으로 순환
let CATMAP={}, TTX=null, TSTAGE=0, TSCORES=[], TEVALS=[], TROLE='', TSURP=false;
let DISASTERS=[], PICKMODE=null, CITIZEN_OK=[], UPCOMING=[];   // 대상(국민/기관) → 재난 선택 흐름
const KEYMETERS=[["인명피해",false],["대피완료율",true],["통제율",true],["주민혼란",false],["재산피해",false]];
const SAMPLES=["서울 관악구 신림동","충북 청주시 오송","경북 포항시","부산 해운대구","경북 경주시"];

function show(id){['sc-addr','sc-cat','sc-exp','sc-pick','sc-citizen','sc-gen','sc-mode','sc-ttx','sc-train','sc-sim','sc-debrief'].forEach(s=>$(s).classList.toggle('on',s===id))}
function toCat(){show('sc-cat')}
function toAddr(){show('sc-addr')}

// 0) 주소
function go(){ ADDR=$('addr').value.trim(); resolveRegion(); }
function goEmpty(){ ADDR=""; resolveRegion(); }
function clearAddrErr(){ const e=$('addr-err'); if(e){e.textContent='';e.classList.remove('on');} const i=$('addr'); if(i)i.classList.remove('err'); }
function showAddrErr(input){
  const e=$('addr-err');
  if(e){ e.innerHTML=`⚠ '<b>${(input||'').replace(/[<>]/g,'')}</b>' 지역을 찾을 수 없습니다. 정확한 <b>시·군·구</b> 또는 도로명 주소를 입력해 주세요. <span class="ae-ex">예) 천안시 · 서울 관악구 · 경북 포항시</span>`; e.classList.add('on'); }
  const i=$('addr'); if(i){ i.classList.add('err'); i.focus(); i.select(); }
  window.scrollTo({top:0,behavior:'smooth'});
}
function goHome(){ show('sc-addr'); window.scrollTo({top:0}); }

const SIGTX={green:'평시',yellow:'주의',red:'경계'};
const MONTHNM={1:'1월',2:'2월',3:'3월',4:'4월',5:'5월',6:'6월',7:'7월',8:'8월',9:'9월',10:'10월',11:'11월',12:'12월'};
const CAUSECOL={'호우':'#4a86ff','태풍':'#8a6bff','태풍·호우':'#6b7bff','강풍':'#22a7c0','풍랑·강풍':'#2ac0a7','폭염':'#f2913b','대설':'#9fb2d6','한파':'#5bd6ff','지진':'#c0563b','낙뢰':'#d0a53b'};
function ccol(n){return CAUSECOL[n]||'#7a8db0';}
let TOPID=null, TOP_TTX=null, DASH={}, HAZ={};

let _loadTimer=null;
function showLoad(){
  const el=$('loadov'); if(!el) return;
  el.classList.add('on'); el.setAttribute('aria-hidden','false');
  const msgs=['기상청 단기예보·특보 조회 중…','행안부 재해 통계연보 조회 중…','지역 위험 프로파일 구성 중…'];
  let i=0; $('loads').textContent=msgs[0];
  _loadTimer=setInterval(()=>{ i=(i+1)%msgs.length; $('loads').textContent=msgs[i]; },1200);
}
function hideLoad(){
  const el=$('loadov'); if(el){ el.classList.remove('on'); el.setAttribute('aria-hidden','true'); }
  if(_loadTimer){ clearInterval(_loadTimer); _loadTimer=null; }
}
async function resolveRegion(){
  clearAddrErr(); showLoad();
  let d;
  try{ d=await (await fetch('/api/resolve?address='+encodeURIComponent(ADDR))).json(); }
  catch(e){ hideLoad(); console.error('resolve failed',e); alert('지역 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.'); return; }
  // 오타·존재하지 않는 지역 → 대시보드로 넘어가지 않고 재입력 유도(엉뚱한 실시간 데이터 차단)
  if(d.unresolved){ hideLoad(); showAddrErr(d.input); return; }
  const r=d.region, live=d.live||{}, ds=d.disasters||[];
  DISASTERS=ds; DASH=d.dash||{}; HAZ=d.hazards||{}; CITIZEN_OK=d.citizen||[]; UPCOMING=d.upcoming||[];
  CATMAP={}; ds.forEach(x=>CATMAP[x.id]={name:x.name,icon:x.icon,ttx:x.ttx,mode:x.mode,depth:x.depth});
  const play=ds.filter(x=>x.depth==='playable');
  TOPID=((play.find(x=>x.recommended))||play[0]||{}).id||null;
  TOP_TTX=((play.find(x=>x.ttx))||{}).id||TOPID;
  try{ renderLoc(r,live); }catch(e){ console.error('loc',e); }
  try{ renderRisk(r,live,ds); }catch(e){ console.error('risk',e); }
  const topName=(CATMAP[TOPID]||{}).name||'추천 재난';
  $('dcta-s').textContent=`현재 이 지역 위험 1순위는 '${topName}'입니다. 지역·상황에 맞춘 훈련을 지금 바로 시작해 보세요.`;
  show('sc-cat'); window.scrollTo({top:0});
  hideLoad();
}

function gradeOf(w){ // 등급어 → 색 클래스
  if(/경보|매우나쁨|높음|위급/.test(w)) return 'g-bad';
  if(/주의|나쁨|경계/.test(w)) return 'g-warn';
  return 'g-good';
}
function gaugeSVG(score,color){
  const p=Math.max(0,Math.min(100,Math.round(score)));
  const th=Math.PI*(1-p/100), x=(100+80*Math.cos(th)).toFixed(1), y=(100-80*Math.sin(th)).toFixed(1);
  return `<svg class="gsvg" viewBox="0 0 200 120">
    <path d="M20,100 A80,80 0 0 1 180,100" fill="none" stroke="#1e3050" stroke-width="14" stroke-linecap="round"/>
    <path d="M20,100 A80,80 0 0 1 ${x},${y}" fill="none" stroke="${color}" stroke-width="14" stroke-linecap="round"/>
    <text x="100" y="88" text-anchor="middle" font-size="42" font-weight="900" fill="${color}">${p}</text>
    <text x="100" y="110" text-anchor="middle" font-size="13" fill="#9fb2d6">/ 100</text></svg>`;
}

// 대상(실시간 대응 체험 / 기관 도상훈련) 선택 → 재난 선택 화면
function goCitizen(){ show('sc-exp'); window.scrollTo({top:0}); }   // 실시간 체험 = 국민/상황실 이원화
function expPick(m){ PICKMODE=m; openPick(); }
function goAgency(){ PICKMODE='ttx'; openPick(); }
function openPick(){
  const m=PICKMODE, isTTX=m==='ttx', isCit=m==='citizen';
  $('pick-title').textContent=isTTX?'🏛 기관 도상훈련 (TTX) — 훈련할 재난 선택'
    :isCit?'👤 국민 대응 체험 — 훈련할 재난 선택':'⚡ 실시간 대응 체험 — 훈련할 재난 선택';
  $('pick-sub').innerHTML=isTTX
    ? '실제 <b>안전한국훈련·을지연습</b> 방식으로 도상훈련할 재난을 고르세요. (도상훈련은 순차 확대 중)'
    : isCit
    ? '재난 상황에서 <b>내 목숨을 지키는 개인 대응</b>을 1인칭으로 체험합니다. 채점 기준 = <b>행정안전부 국민행동요령</b>.'
    : '실시간 무전·신고를 받으며 대응을 체험할 재난을 고르세요.';
  const avail=(x)=> isTTX ? !!x.ttx : isCit ? CITIZEN_OK.includes(x.id) : (x.depth==='playable');
  const cards=DISASTERS.map(x=>{
    const ok=avail(x);
    const pct=Math.round((x.relevance||0)*100);
    const col=pct>=60?'var(--bad)':pct>=40?'var(--warn)':'var(--good)';
    const rec=(ok&&x.recommended)?`<span class="pill rec">지역 추천</span>`:'';
    const note=ok?`<span class="pill play">${isTTX?'도상훈련 가능':'체험 가능'}</span>`:`<span class="pill scaf">준비 중</span>`;
    return `<div class="dcard ${ok?'':'dim'}" ${ok?`onclick="pickGo('${x.id}')"`:''}>
      ${rec}<div class="ic">${x.icon}</div><h3>${x.name}</h3><p>${x.summary||''}</p>
      <div class="risk" title="지역 위험도 ${pct}%"><i style="width:${pct}%;background:${col}"></i></div>
      <div class="ft">${note}</div></div>`;
  });
  const up=(UPCOMING||[]).map(u=>`<div class="dcard dim">
      <div class="ic">${u.icon}</div><h3>${u.name}</h3><p>${u.note||''}</p>
      <div class="ft"><span class="pill scaf">준비 중</span> <span class="pill cat">${u.cat||''}</span></div></div>`);
  $('pick-cat').innerHTML=cards.join('')+up.join('');
  show('sc-pick'); window.scrollTo({top:0});
}
function pickGo(id){
  SEED=Math.floor(Math.random()*1e5);
  if(PICKMODE==='ttx') startTTX(id); else if(PICKMODE==='citizen') startCitizen(id); else startDis(id);
}

// ── 국민 모드(1인칭 개인 생존 대응) ──────────────────────────
let CIT=null;
const CIT_DANGER={correct:-12,partial:14,wrong:34};
function dColor(d){ return d<30?'#2bd17e':d<60?'#f2b53b':'#ff5d5d'; }
function dLabel(d){ return d<30?'안전':d<60?'주의':d<80?'위험':'치명'; }
function dangerBar(d){
  return `<div class="dgauge"><div class="dg-top"><span>🫀 생존 위험도</span><b style="color:${dColor(d)}">${Math.round(d)} <small>${dLabel(d)}</small></b></div>
    <div class="dg-track"><i style="width:${Math.max(3,d)}%;background:${dColor(d)}"></i></div></div>`;
}
async function startCitizen(id){
  showLoad();
  const seed=Math.floor(Math.random()*1e6);
  let d;
  try{ d=await (await fetch('/api/citizen_start?disaster='+id+'&seed='+seed+'&address='+encodeURIComponent(ADDR))).json(); }
  catch(e){ hideLoad(); alert('시나리오를 불러오지 못했습니다.'); return; }
  hideLoad();
  if(!d||d.error||!d.steps){ alert('이 재난의 국민 체험은 준비 중입니다.'); return; }
  CIT={id:id, data:d, choices:[], step:0, danger:(d.start_danger||22), variant:d.variant||0};
  show('sc-citizen'); window.scrollTo({top:0}); renderCit();
}
function renderCit(){
  const c=CIT, d=c.data, i=c.step, s=d.steps[i], n=d.steps.length;
  const intro=i===0?`<div class="cit-intro">${d.intro}</div>`:'';
  const real=(i===0&&d.reality)?`<div class="cit-real">📊 <b>이 지역 실제 데이터</b> — ${d.reality}<span class="cit-realsrc">행안부 침수흔적도·인명피해우려지역</span></div>`:'';
  const opts=s.options.map((o,oi)=>`<button class="cit-opt" onclick="pickCit(${oi})">${o.t}</button>`).join('');
  $('cit-body').innerHTML=`
    <div class="cit-head"><span class="cit-ic">${d.icon}</span><div>
      <div class="cit-name">${d.name} · 국민 대응 체험</div>
      <div class="cit-prog">상황 ${i+1} / ${n} · 시나리오 ${(c.variant+1)}/${d.variant_total}</div></div></div>
    <div id="cit-gauge">${dangerBar(c.danger)}</div>
    ${intro}${real}<div class="cit-sit sc-${d.disaster}">${s.sit}</div><div class="cit-opts">${opts}</div>`;
}
function pickCit(oi){
  const c=CIT, s=c.data.steps[c.step], o=s.options[oi];
  c.choices[c.step]=oi;
  c.danger=Math.max(0,Math.min(100,c.danger+(CIT_DANGER[o.v]||34)));
  $('cit-gauge').innerHTML=dangerBar(c.danger);
  const cls=o.v==='correct'?'ok':o.v==='partial'?'mid':'bad';
  const vt={correct:'✅ 적절한 대응',partial:'△ 아쉬운 선택',wrong:'✗ 위험한 선택'}[o.v];
  const btns=[...document.querySelectorAll('.cit-opt')];
  btns.forEach((b,bi)=>{ b.disabled=true; if(bi===oi) b.classList.add(cls); if(s.options[bi].v==='correct') b.classList.add('showok'); });
  if(o.v==='wrong'){ const w=document.querySelector('.wrap'); if(w){ w.classList.add('flash-bad'); setTimeout(()=>w.classList.remove('flash-bad'),450);} }
  const last=c.step>=c.data.steps.length-1;
  const fb=document.createElement('div'); fb.className='cit-fb '+cls;
  fb.innerHTML=`<b>${vt}</b> ${o.fb}<div class="cit-next"><button onclick="citNext()">${last?'생존 결과 보기 →':'다음 상황 →'}</button></div>`;
  $('cit-body').appendChild(fb); fb.scrollIntoView({behavior:'smooth',block:'center'});
}
async function citNext(){
  const c=CIT;
  if(c.step < c.data.steps.length-1){ c.step++; renderCit(); window.scrollTo({top:0}); return; }
  showLoad();
  let r;
  try{ r=await (await fetch('/api/citizen_run',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({disaster:c.id,choices:c.choices,address:ADDR,variant:c.variant})})).json(); }
  catch(e){ hideLoad(); alert('채점에 실패했습니다.'); return; }
  hideLoad(); citResult(r);
}
function citResult(r){
  const gcol={A:'#2bd17e',B:'#7db4ff',C:'#f2b53b',D:'#ff5d5d'}[r.grade]||'#7db4ff';
  const oc={'생존':'#2bd17e','부상 위험':'#f2b53b','사망 위기':'#ff5d5d'}[r.outcome]||'#7db4ff';
  const rows=(r.results||[]).map((x,i)=>{
    const cls=x.verdict==='correct'?'ok':x.verdict==='partial'?'mid':'bad';
    const vt={correct:'✅',partial:'△',wrong:'✗'}[x.verdict]||'';
    const corr=x.verdict==='correct'?'':`<div class="cit-corr">✔ 권장 행동: ${x.correct}</div>`;
    return `<div class="cit-row ${cls}"><div class="cit-rn">${i+1}</div><div class="cit-rbody">
      <div class="cit-rs">${x.sit}</div><div class="cit-rc">${vt} 내 선택: ${x.chosen}</div>${corr}
      <div class="cit-rf">${x.fb}</div></div></div>`;
  }).join('');
  $('cit-body').innerHTML=`
    <div class="cit-outcome" style="border-color:${oc}">
      <div class="cit-oc" style="color:${oc}">${r.outcome}</div>
      <div class="cit-ocd">${r.outcome_desc}</div>${dangerBar(r.final_danger)}</div>
    <div class="cit-result">
      <div class="cit-score" style="border-color:${gcol}"><div class="cit-grade" style="color:${gcol}">${r.grade}</div>
        <div class="cit-pct">${r.score}점</div></div>
      <div class="cit-verdict">${r.verdict}</div></div>
    <h3 class="cit-h">🔎 단계별 강평</h3>${rows}
    <div class="cit-guidewrap"></div>
    <div class="cit-actions"><button onclick="startCitizen(CIT.id)">↻ 다른 시나리오로 다시</button>
      <button class="ghost" onclick="openPick()">다른 재난 →</button>
      <button class="ghost" onclick="goHome()">처음으로</button></div>`;
  if(r.guideline&&r.guideline.title){
    const g=r.guideline;
    const sec=(t,a)=>a&&a.length?`<div class="gsec"><h5>${t}</h5><ul>${a.map(x=>`<li>${x}</li>`).join('')}</ul></div>`:'';
    document.querySelector('.cit-guidewrap').innerHTML=`<div class="d-guide-box">
      <div class="gh">📘 ${g.title} <span class="tag">실제 대응법 · 국민행동요령</span></div>
      ${sec('사전 대비',g.before)}${sec('재난 시 행동',g.during)}${sec('대피 요령',g.evacuate)}
      ${g.shelter_hint?`<div class="ghint">📍 ${g.shelter_hint}</div>`:''}
      <div class="gsrc">출처: ${g.source||''}</div></div>`;
  }
}

function renderLoc(r,live){
  const tags=(r.tags||[]).map((t,i)=>`<span class="dl-tag c${i%4}">${t}</span>`).join('');
  const wanted=['temp','rain','wind','air','warn'];   // 강수 포함 5종
  const cards=(live.cards||[]).filter(c=>wanted.includes(c.key))
    .sort((a,b)=>wanted.indexOf(a.key)-wanted.indexOf(b.key)).map(c=>`
    <div class="dl-live"><div class="dl-liv-l">${c.icon} ${c.label}</div>
      <div class="dl-liv-v">${c.value}</div><div class="dl-liv-s ${c.source==='live'?'ok':''}">${c.status_label}</div></div>`).join('');
  $('dloc').innerHTML=`
    <div class="dl-top">
      <div class="dl-left">
        <span class="dl-loc"><span class="dl-pin">📍</span>${esc(r.label)}${r.matched?'':' <span class="small">· 일반</span>'}</span>
        <div class="dl-tags">${tags}</div>
      </div>
      <span class="dl-edit" onclick="toAddr()">주소 변경 ›</span>
    </div>
    <div class="dl-live-row">
      <div class="dl-rt"><span class="dl-dot ${live.has_key?'on':''}"></span>실시간 연동 데이터 <span class="dl-as">${live.as_of||''} 기준</span></div>
      <div class="dl-lives">${cards}</div>
    </div>`;
}

function renderRisk(r,live,ds){
  const sg=live.signal||{level:'green',score:30,label:'',reasons:[]};
  const top=ds.find(x=>x.depth==='playable')||ds[0]||{};
  const cards=live.cards||[];
  const air=cards.find(c=>c.key==='air')||{}, warn=cards.find(c=>c.key==='warn')||{}, wind=cards.find(c=>c.key==='wind')||{};
  const topG=top.relevance>=0.7?'높음':top.relevance>=0.45?'보통':'낮음';
  const airG=((air.value||'').match(/매우나쁨|나쁨|보통|좋음/)||['보통'])[0];
  const wTxt=warn.value||'특보 없음';
  const windG=/경보/.test(wTxt)?'경보':/주의보/.test(wTxt)?'주의':'양호';
  const briefs=[
    {ic:top.icon||'⚠',n:top.name||'지역 위험',s:(top.name||'재난')+' 발생 위험도',g:topG,
     d:top.name?`이 지역은 ${top.name} 위험도가 ${topG==='높음'?'높습니다':topG==='보통'?'평년 수준입니다':'낮은 편입니다'}.`:'지역 위험도 정보'},
    {ic:'🌬',n:'강풍·폭풍',s:'바람·기상특보',g:windG,
     d:windG==='양호'?'현재 특보 없이 안정적입니다.':`${wTxt} 발효 — 순간풍속 증가에 유의하세요.`},
    {ic:'🌫',n:'미세먼지',s:'대기질',g:airG,
     d:airG==='좋음'?'야외 활동에 적합한 수준입니다.':airG==='보통'?'대체로 양호한 수준입니다.':airG==='나쁨'?'민감군은 실외활동을 줄이세요.':'실외활동을 자제해야 합니다.'},
  ];
  const bc=briefs.map(b=>`
    <div class="rb-card"><div class="rb-h"><span class="rb-ic">${b.ic}</span>
      <div><div class="rb-n">${b.n}</div><div class="rb-sub">${b.s}</div></div></div>
      <div class="rb-grade ${gradeOf(b.g)}">${b.g}</div><div class="rb-desc">${b.d}</div></div>`).join('');
  const gcol=sg.level==='red'?'#ff5d5d':sg.level==='yellow'?'#f2b53b':'#2bd17e';
  $('d-risk').innerHTML=`
    <div class="rk-rowA">
      <div class="rk-region">
        <div class="rk-rh">📍 지역 프로필 / 내 위치</div>
        ${mapEmbed(r)}
        <div class="rk-meta">${r.org?'<div>🏛 '+r.org+'</div>':''}<div>⚠ 상시 위험: ${(r.tags||[]).slice(0,3).join(' · ')||'일반'}</div></div>
        <div class="rk-note">${r.note||'지역 위치 기준으로 시나리오가 지역화됩니다.'}</div>
      </div>
      <div class="rk-gauge">
        <div class="rk-gt">종합 위험지수 <span class="rk-badge ${sg.level}">${SIGTX[sg.level]}</span></div>
        ${gaugeSVG(sg.score||30,gcol)}
        <div class="rk-glab">${sg.label}</div>
        <div class="rk-gsub">기상·재난 데이터 종합 분석 · ${(sg.reasons||[]).join(' · ')}</div>
      </div>
      <div class="rk-brief">
        <div class="rk-bt">오늘의 핵심 브리핑</div>
        <div class="rk-bcards">${bc}</div>
      </div>
    </div>
    ${renderBoard(live)}
    ${renderHazards()}
    <div class="rk-rowB">
      ${renderStat(r)}
      ${renderMonth(r)}
    </div>
    ${renderAdvisory(live,wTxt)}`;
  refineMap(r);
}

function mapEmbed(r){ return `<div id="rk-mapbox">${mapInner(r,r.lat,r.lon,r.geo==='point')}</div>`; }
function mapInner(r,la,lo,precise){
  if(la==null||lo==null){
    return `<div class="rk-map"><span class="rk-pin">📍</span><div class="rk-rlab">${r.label}</div><div class="rk-sido">${r.sido||''}</div></div>`;
  }
  const dlon=precise?0.028:0.60, dlat=precise?0.020:0.42;
  const bbox=`${(lo-dlon).toFixed(4)},${(la-dlat).toFixed(4)},${(lo+dlon).toFixed(4)},${(la+dlat).toFixed(4)}`;
  const src=`https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${la},${lo}`;
  const note=precise?'':`<div class="rk-mapnote">※ 시·도 광역 위치 — 정밀 위치 확인 중…</div>`;
  return `<div class="rk-mapwrap"><div class="rk-maplab">${r.label}<span>${r.sido||''}</span></div>
    <iframe class="rk-mapfr" src="${src}" loading="lazy" title="${r.label} 지도" referrerpolicy="no-referrer"></iframe></div>${note}`;
}
async function refineMap(r){
  // 큐레이션(정밀 좌표)이 아니면 브라우저에서 시군구 중심을 지오코딩해 정밀 갱신(실패 시 시도 폴백 유지).
  if(r.geo==='point') return;
  const q=((r.sido||'')+' '+(r.sigungu||'')).trim()||r.label; if(!q) return;
  try{
    const u='https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=kr&q='+encodeURIComponent(q);
    const j=await (await fetch(u,{headers:{'Accept':'application/json'}})).json();
    if(j&&j[0]&&j[0].lat){ const box=document.getElementById('rk-mapbox'); if(box) box.innerHTML=mapInner(r,+j[0].lat,+j[0].lon,true); }
  }catch(e){ /* 네트워크 실패 시 시도 폴백 지도 그대로 */ }
}
function renderBoard(live){
  const b=(live&&live.board)||[];
  if(!b.length) return '';
  const lv={green:'안전',yellow:'주의',red:'경계'};
  const basis=live.board_live?'기상청 실시간 + 지역 위험도 종합':'데모 샘플 기준(키 연동 시 실시간)';
  const cells=b.map(x=>`<div class="db ${x.level}">
    <div class="db-ic">${x.icon}</div><div class="db-n">${x.name}</div>
    <div class="db-lv ${x.level}">${lv[x.level]||'-'}</div><div class="db-r">${x.reason}</div></div>`).join('');
  return `<div class="rk-board"><div class="rk-bt2">🚦 재난 유형별 신호등 <span class="rk-sub2">${basis}</span></div>
    <div class="db-row">${cells}</div></div>`;
}
function renderHazards(){
  const H=HAZ||{}; const pts=H.points||[]; const sh=H.shelters||[];
  const pbadge=H.status==='curated'?'<span class="rk-hb live">재해이력 기반</span>':H.status==='live'?'<span class="rk-hb live">실데이터</span>':'<span class="rk-hb pend">연동 예정</span>';
  let ptHtml;
  if(pts.length){
    const chips=pts.map(p=>`<span class="hz"><b>${p.icon||'📍'} ${p.name}</b><i>${p.type}${p.role?' · '+p.role:''}</i></span>`).join('');
    const hist=H.hist?`<div class="rk-hh">📌 ${H.hist}</div>`:'';
    ptHtml=`<div class="rk-ht">🎯 이 지역 주요 위험지점 ${pbadge}</div><div class="hz-wrap">${chips}</div>${hist}
      <div class="rk-hsrc">출처: 재해연보·인명피해우려지역·침수흔적도 — 이 지점들이 훈련 시나리오에 반영됩니다.</div>`;
  } else {
    ptHtml=`<div class="rk-ht">🎯 이 지역 주요 위험지점 ${pbadge}</div><div class="rk-hpend">${H.note||'공유플랫폼 위험지점 API 활용신청 후 연동됩니다.'}</div>`;
  }
  let fhHtml='';
  const fh=H.flood;
  if(fh&&(fh.events||[]).length){
    const ev=fh.events.map(e=>`<span class="fh-ev">${e.yr} ${e.nm}${e.depth?` <b>${e.depth}m</b>`:''}</span>`).join('');
    fhHtml=`<div class="rk-ht">🌊 이 지역 실제 침수 이력 <span class="rk-hb live">실데이터</span><span class="rk-sub2">누적 ${(fh.count||0).toLocaleString()}건</span></div>
      <div class="fh-wrap">${ev}</div>
      <div class="rk-hsrc">출처: 행정안전부 재난안전데이터공유플랫폼 — 침수흔적도. 이 이력이 훈련 시나리오에 반영됩니다.</div>`;
  }
  let shHtml='';
  if(sh.length){
    const items=sh.map(s=>`<span class="hz"><b>🏫 ${s.name}</b><i>수용 ${(+s.cap||0).toLocaleString()}명</i></span>`).join('');
    shHtml=`<div class="rk-ht">🏫 가까운 지진옥외대피소 <span class="rk-hb live">실데이터</span><span class="rk-sub2">${H.sigungu} ${H.shelter_total}곳 중 상위</span></div>
      <div class="hz-wrap">${items}</div>
      <div class="rk-hsrc">출처: 행정안전부 재난안전데이터공유플랫폼 — 지진옥외대피소(전국 11,187곳).</div>`;
  }
  const secs=[ptHtml,fhHtml,shHtml].filter(Boolean).map(s=>`<div class="hz-sec">${s}</div>`).join('');
  if(!secs) return '';
  const nPt=pts.length, nSh=(H.shelter_total||sh.length), nFh=(fh&&fh.count)||0;
  const sum=[nPt?`위험지점 ${nPt}`:'',nFh?`침수이력 ${nFh}건`:'',nSh?`대피소 ${nSh}곳`:''].filter(Boolean).join(' · ');
  return `<details class="haz-fold"><summary>📍 이 지역 위험지점·침수이력·대피소 <span class="rk-hb live">실데이터</span> <span class="hz-sum">${sum}</span></summary>
    <div class="rk-haz">${secs}</div></details>`;
}
function _statLive(){return DASH&&DASH.status==='live';}
function knum(n){n=+n||0; if(n>=10000)return (n/10000).toFixed(n%10000===0?0:1).replace(/\.0$/,'')+'만'; if(n>=1000)return (n/1000).toFixed(1).replace(/\.0$/,'')+'천'; return n.toLocaleString();}
function renderStat(r){
  const sido=(DASH&&DASH.sido)||'';
  const sgg=(r&&r.sigungu)||'';
  const badge=_statLive()?'<span class="rk-hb live">실데이터</span>':'<span class="rk-hb pend">연동 예정</span>';
  const head=`${sido?sido+' ':''}광역 재해 통계 <span class="rk-sub2">시·도 단위</span> ${badge}`;
  if(!_statLive()){
    return `<div class="rk-stat"><div class="rk-sh">${head}</div>
      <div class="rk-pnote">${(DASH&&DASH.note)||'행안부 통계연보 활용신청 후 연동됩니다.'}</div></div>`;
  }
  const S={}; (DASH.summary||[]).forEach(x=>S[x.label]=x.value);
  const ys=(DASH.yearly||[]).filter(y=>y.y); const mx=Math.max(...ys.map(y=>y.vic||0),1);
  const bars=ys.map(y=>`<div class="yb" title="${y.y}년 이재민 ${(+y.vic||0).toLocaleString()}명${y.top?' · 최다원인 '+y.top:''}">
      <div class="yb-val">${knum(y.vic)}</div>
      <div class="yb-bar" style="height:${Math.max(4,Math.round((y.vic||0)/mx*100))}%;background:${ccol(y.top||'')}"></div>
      <div class="yb-lab">'${(y.y||'').slice(2)}</div></div>`).join('');
  const legend=[...new Set(ys.map(y=>y.top).filter(Boolean))].map(c=>`<span class="lg"><i style="background:${ccol(c)}"></i>${c}</span>`).join('');
  return `<div class="rk-stat">
    <div class="rk-sh">${head}</div>
    <div class="rk-tiles">
      <div class="tile"><div class="tv">${S['누적 이재민']||'-'}</div><div class="tl">누적 이재민(${sido||'광역'})</div></div>
      <div class="tile"><div class="tv">${S['반복 피해 유형']||'-'}</div><div class="tl">반복 피해 유형(1위)</div></div>
      <div class="tile"><div class="tv">${S['누적 인명피해']||'-'}</div><div class="tl">누적 인명피해</div></div>
    </div>
    <div class="ybars">${bars}</div>
    <div class="lg-row">연도별 이재민 수(명) · 막대 색 = 그 해 최다 재해 원인 &nbsp; ${legend}</div>
    <div class="rk-scap">※ 출처: <b>행정안전부 재해통계연보</b>(시·도 단위 집계). 위 수치는 <b>${sido||'해당 시·도'} 전체</b> 기준이며, ${sgg?'<b>'+sgg+'</b> 등 ':''}시·군·구 세부 통계는 국가 차원에서 미개방입니다.</div>
  </div>`;
}

function renderMonth(r){
  const mo=new Date().getMonth()+1;
  const sido=(DASH&&DASH.sido)||'';
  const badge=_statLive()?'<span class="rk-hb live">실데이터</span>':'<span class="rk-hb pend">연동 예정</span>';
  const feat=MONTHCAL[mo]||'';
  if(!_statLive() || !(DASH.cause_rank||[]).length){
    return `<div class="rk-month"><div class="rk-sh">이달의 재난 경향 (${mo}월) ${badge}</div>
      <div class="rk-pnote">재난 유형 비중은 활용신청 후 연동됩니다.<br>📌 ${mo}월 유의 재해: ${feat}</div></div>`;
  }
  const m=DASH.month||{}; const share=m.share||0;
  const donut=`<div class="donut" style="background:conic-gradient(#4a86ff ${share*3.6}deg,#1b2c48 0)">
    <div class="donut-in"><b>${share}%</b><span>${mo}월 비중</span></div></div>`;
  const rank=(DASH.cause_rank||[]).slice(0,5).map((c,i)=>`
    <div class="crk"><span class="crk-i">${i+1}</span><span class="crk-n">${c.name}</span>
      <div class="crk-bar"><i style="width:${c.pct}%;background:${ccol(c.name)}"></i></div><span class="crk-p">${c.pct}%</span></div>`).join('');
  return `<div class="rk-month">
    <div class="rk-sh">이달의 재난 경향 (${mo}월) ${badge}<span class="rk-sub2">전국 월별 · ${sido||'광역'} 유형비중</span></div>
    <div class="rk-mgrid">
      <div class="rk-donut">${donut}<div class="rk-dl"><b>전국</b> ${mo}월 발생비중<br>(최대피해월 ${m.peak?MONTHNM[m.peak]:'-'})</div></div>
      <div class="rk-rank"><div class="rk-rt">${sido||'광역'} 재난 유형 비중 <span class="rk-sub2">시·도 단위</span></div>${rank}</div>
    </div>
    <div class="rk-feat">📌 <b>${mo}월 주요 특징</b> — ${feat} 시기로 관련 위험이 높습니다.</div>
    <div class="rk-scap">※ 도넛=<b>전국</b> 월별 발생비중, 유형 비중=<b>${sido||'해당 시·도'} 전체</b> 기준(시·군·구 세부 미개방).</div>
  </div>`;
}

// 이번 달 유의 재해(계절 재난 월력) + 현재 특보 기반 행안부 국민행동요령 안내
const MONTHCAL={1:'대설·한파',2:'대설·한파',3:'산불·건조',4:'산불·황사',5:'산불·가뭄',
  6:'장마·집중호우',7:'집중호우·태풍·폭염',8:'폭염·태풍',9:'태풍·집중호우',10:'태풍·산불',11:'대설·건조',12:'대설·한파'};
const WARNACT={
  '강풍':'순간풍속에 대비해 지붕·간판·비닐하우스 등 시설물을 고정하고, 공사장·해안가·교량 통행에 주의하세요.',
  '호우':'저지대·지하공간 침수에 대비하고, 하천·계곡 접근을 삼가며 외출을 자제하세요.',
  '태풍':'창문을 고정하고 실내에 머무르며, 침수·강풍 위험지역 접근을 피하세요.',
  '폭염':'낮 시간대 야외활동을 피하고 물을 자주 마시며, 취약계층 건강을 확인하세요.',
  '대설':'미끄럼·붕괴 사고에 주의하고 대중교통을 이용하며, 지붕 적설을 점검하세요.',
  '한파':'동파·저체온증에 대비하고 외출을 줄이며, 취약계층 안부를 확인하세요.',
  '건조':'화기 취급에 주의하고 산림 인접지 불씨 관리를 철저히 하세요.'};
function renderAdvisory(live,wTxt){
  const mo=new Date().getMonth()+1;
  const season=MONTHCAL[mo]||'';
  const wtype=Object.keys(WARNACT).find(k=>(wTxt||'').includes(k));
  const cause=(DASH&&(DASH.summary||[]).find(i=>i.label==='반복 피해 유형'));
  const lines=[];
  lines.push(`<li><b>📅 이번 달(${mo}월) 유의 재해</b> — ${season} 시기입니다. 관련 국민행동요령을 미리 숙지하세요.</li>`);
  if(wtype) lines.push(`<li><b>📢 현재 발효 「${wTxt}」</b> — ${WARNACT[wtype]}</li>`);
  else lines.push(`<li><b>📢 현재 특보 없음</b> — 평시 대비 상태이나, 이번 달 유의 재해에 대한 사전 점검을 권장합니다.</li>`);
  if(cause) lines.push(`<li><b>📊 이 지역 과거 최다 재해</b> — <b>${cause.value}</b>(행안부 통계연보). 반복 위험에 대비하세요.</li>`);
  return `<div class="advisory">
    <div class="adv-h">🛡 행안부 안전 안내 <span class="adv-src">국민행동요령 · 재난대비 월력 · 기상청 특보</span></div>
    <ul class="adv-l">${lines.join('')}</ul></div>`;
}

function renderStd(ds){
  const play=ds.filter(x=>x.depth==='playable'), scaf=ds.filter(x=>x.depth!=='playable');
  $('std-cnt').textContent='추천 '+play.length;
  $('cat').innerHTML=play.map(x=>{
    const pct=Math.round((x.relevance||0)*100);
    const col=pct>=60?'var(--bad)':pct>=40?'var(--warn)':'var(--good)';
    const rec=x.recommended?`<span class="pill rec">지역 추천</span>`:'';
    const tb=x.ttx?`<span class="pill" style="color:#bfe0ff;background:#10254a;border:1px solid #29508f">시뮬+도상</span>`:'';
    return `<div class="dcard" onclick="pickDisaster('${x.id}')">
      ${rec}<div class="ic">${x.icon}</div><h3>${x.name}</h3><p>${x.summary||''}</p>
      <div class="risk" title="지역 위험도 ${pct}%"><i style="width:${pct}%;background:${col}"></i></div>
      <div class="ft"><span class="pill play">플레이 가능</span>${tb}</div></div>`;
  }).join('');
  $('scaf').innerHTML=scaf.map(x=>`<div class="scaf-item" title="확장 예정"><span class="sc-ic">${x.icon}</span><b>${x.name}</b><span class="sc-go">›</span></div>`).join('');
}
function startTop(){ if(TOPID){ SEED=Math.floor(Math.random()*1e5); pickDisaster(TOPID); } }

// 재난 클릭 → 두 방식 있으면 선택, 아니면 바로 시작
function pickDisaster(id){
  SEED=Math.floor(Math.random()*100000);   // 재난 고를 때마다 새 랜덤 변형
  const c=CATMAP[id]||{};
  if(c.ttx){ showMode(id); } else { startDis(id); }
}
function showMode(id){
  DIS=id; const c=CATMAP[id]||{};
  $('m-title').textContent=(c.icon||'')+' '+(c.name||'')+' — 누가 훈련하나요?';
  $('m-sim').onclick=()=>startDis(id);
  $('m-ttx').onclick=()=>startTTX(id);
  show('sc-mode');
}

// 1) 시작 (mode 분기)
async function startDis(id){
  DIS=id;
  META=await (await fetch('/api/start?disaster='+id+'&variant='+SEED+'&address='+encodeURIComponent(ADDR))).json();
  if(META.mode==='sim'){ startSim(); return; }
  CHOICES=[];
  $('t-title').textContent=META.icon+' '+META.name+' 대응 훈련';
  $('t-context').textContent='🗺 '+(META.context||'')+(META.region?'  ·  대상지: '+META.region:'');
  $('t-manual').innerHTML='📑 채점 기준: '+(META.source_manuals.join(' · ')||'표준행동요령');
  renderPhase(META.first_phase, dfltState());
  show('sc-train');
}
function dfltState(){return {"인명피해":0,"재산피해":0,"대피완료율":0,"통제율":0,"주민혼란":10}}
// '다른 상황으로' — SEED를 올려 반드시 다음 변형이 나오게 하고 현재 모드를 재시작
function rerollSim(){ SEED++; startDis(DIS); }
function rerollTTX(){ SEED++; startTTX(DIS); }

// ── AI 맞춤 시나리오 생성 ──
let GEN=null;
function openGen(){ $('g-out').innerHTML=''; show('sc-gen'); }
async function generateScenario(){
  const inst=$('g-inst').value.trim(), dis=$('g-dis').value.trim(), con=$('g-con').value.trim();
  if(!inst||!dis){ alert('기관 성격과 재난 유형을 입력해 주세요.'); return; }
  const b=$('g-btn'); b.disabled=true; b.textContent='시나리오 생성 중…';
  try{
    GEN=await (await fetch('/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({institution:inst,disaster:dis,concept:con,use_llm:true})})).json();
    $('gen-aitag').innerHTML = GEN.ai_available
      ? '<span class="aidot on">● AI 생성 활성(LLM 키 연결)</span>'
      : '<span class="aidot off">● 규칙 기반 초안(서버에 LLM 키 설정 시 AI 정밀 생성)</span>';
    renderGenScenario();
  } finally { b.disabled=false; b.textContent='✨ 맞춤 시나리오 생성'; }
}
function renderGenScenario(){
  const st=GEN.stage;
  const srcbadge = GEN.source==='ai'
    ? '<span class="genbadge ai">AI 생성</span>' : '<span class="genbadge rule">규칙 초안</span>';
  $('g-out').innerHTML=`
    <div class="gen-head">${srcbadge}<b>${GEN.icon||'⚠'} ${GEN.title||''}</b>
      <span class="gen-prof">${esc(GEN.profile_label||'')} · ${esc(GEN.disaster_label||'')}</span></div>
    <div class="ttx-intro"><div class="role">🎖 ${GEN.role||''}</div></div>
    <div class="inj"><div class="ih">${st.clock||'발생 직후'} · 상황 부여</div>
      <div class="it">${st.title||''}</div><div class="ix">${st.inject||''}</div></div>
    <div class="task">▶ ${st.task||'초기 대응방안을 우선순위대로 서술하세요.'}</div>
    <textarea class="ans" id="g-ans" placeholder="예) ① 상황전파·비상연락  ② 인명 대피·인원확인  ③ 현장통제·2차피해 차단  ④ 유관기관 공조·보고"></textarea>
    <button class="subt" id="g-sub" onclick="submitGen()">📝 대응방안 제출 · 평가받기</button>
    <div id="g-res"></div>`;
  $('g-out').scrollIntoView({behavior:'smooth',block:'start'});
}
async function submitGen(){
  const ans=$('g-ans').value.trim();
  if(ans.length<5){ alert('대응방안을 먼저 작성해 주세요.'); return; }
  const b=$('g-sub'); b.disabled=true; b.textContent='AI 평가관이 표준요소와 대조 중…';
  const st=GEN.stage;
  const r=await (await fetch('/api/generate_eval',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({elements:st.elements,answer:ans,title:st.title,model_answer:st.model_answer,
      inject:st.inject,task:st.task,use_llm:true})})).json();
  renderGenResult(r);
}
function renderGenResult(r){
  const col=r.score>=85?'var(--good)':r.score>=70?'#bfe0ff':r.score>=55?'var(--warn)':'var(--bad)';
  const lvl={full:'반영',partial:'부분',none:'누락'};
  const els=r.elements.map(e=>`<div class="elem">
     <span class="lv ${e.level}">${lvl[e.level]}</span>
     <div><div class="ed">${e.desc} <span class="small">(${e.weight}점)</span></div>
       <div class="er">${e.reason||''}</div>${e['근거']?`<div class="eg">📑 ${e['근거']}</div>`:''}</div></div>`).join('');
  const g5=r.grade5||{}; const g5col=g5.score>=5?'var(--good)':g5.score>=4?'#bfe0ff':g5.score>=3?'var(--warn)':'var(--bad)';
  $('g-res').innerHTML=`
    <div class="tscore"><span class="big" style="color:${col}">${r.score}<span style="font-size:16px">/100</span></span>
      ${g5.grade?`<span class="gr5" style="background:${g5col}">공식등급 ${g5.grade} <b>${g5.score}점</b></span>`:''}
      <span class="eng">평가: ${r.engine}</span></div>
    ${renderIndicators(r.indicators)}
    <h4 style="font-size:13px;color:var(--sub);margin:6px 0 4px">표준 대응요소 반영도</h4>${els}
    ${(r.missed&&r.missed.length)?`<div class="reveal" style="border-left:3px solid var(--bad)"><b style="color:var(--bad)">놓친·약한 요소</b>${r.missed.join(' · ')}</div>`:''}
    <div style="background:#10254a;border:1px solid #29508f;border-radius:10px;padding:12px 14px;margin-top:10px;font-size:13.5px">🧭 ${r.coach||''}</div>
    <div class="model"><b>📘 모범답안 (표준매뉴얼 기준)</b>${r.model_answer||''}</div>
    <div class="btnrow" style="margin-top:14px"><button class="pri" onclick="renderGenScenario()">↻ 같은 시나리오 재훈련</button><button onclick="openGen()">새 시나리오 만들기</button></div>`;
  $('g-res').scrollIntoView({behavior:'smooth',block:'nearest'});
}

function renderPhase(phase, state){
  $('t-clock').textContent='🕒 '+(phase.clock||'');
  $('t-progress').textContent=`${CHOICES.length+1} / ${META.total_phases} 단계`;
  renderMeters(state); renderSteps();
  const gt=phase.golden_time_min?`<span class="pill" style="background:#33290c;color:var(--warn)">⏱ 골든타임 ${phase.golden_time_min}분</span>`:'';
  $('t-body').innerHTML=`<div class="inject">${phase.inject}</div>
    <div class="q">${phase.question} ${gt}</div>
    <div id="opts">${phase.options.map(o=>`<button class="opt" onclick="choose('${o.id}')">${o.text}</button>`).join('')}</div>`;
}
function metersHTML(state){
  return KEYMETERS.map(([k,hi])=>{
    const v=state[k]??0, pct=Math.max(0,Math.min(100,k.includes('율')?v:v*2));
    const good=hi? v>=50 : v<=15; const col=good?'var(--good)':(hi? (v>=25?'var(--warn)':'var(--bad)') : (v<=30?'var(--warn)':'var(--bad)'));
    return `<div class="meter"><div class="top"><span>${k}</span><span class="v" style="color:${col}">${v}${k.includes('율')?'%':''}</span></div>
      <div class="bar"><i style="width:${pct}%;background:${col}"></i></div></div>`;
  }).join('');
}
function renderMeters(state){ $('t-meters').innerHTML=metersHTML(state); }
function renderMetersTo(state,el){ $(el).innerHTML=metersHTML(state); }

// ── 재난안전상황실 시뮬(침수) ──
const WMAX=140;
function startSim(){
  SIM=META; SCH=[]; _pm=null; CUR=META.current;
  $('s-room').textContent=(META.region||'재난안전')+' 재난안전상황실';
  $('s-ctx').textContent=(META.variant_label?'🎲 '+META.variant_label+'  ·  ':'')+(META.context||'');
  $('s-manual').innerHTML='📑 채점 기준: '+((META.source_manuals||[]).join(' · ')||'표준행동요령')+'  ·  종료 후 실제 국민행동요령 제공';
  renderSim(); show('sc-sim');
}
function renderSim(){
  const c=CUR;
  $('s-clock').textContent='🕒 '+c.clock;
  $('s-prog').textContent='대응 #'+(c.idx+1)+' 진행 중';
  $('s-dot').style.color=c.danger.color;
  $('s-danger').textContent='위험단계 '+c.danger.label; $('s-danger').style.color=c.danger.color;
  renderFeed(c.feed);
  renderMon(c.monitor,c.danger,c.water,{golden:c.golden_min,deadline:c.deadline});
  renderDec(c.focal);
}
function renderFeed(feed){
  const el=$('s-feed');
  el.innerHTML=(feed||[]).map(f=>`<div class="fd ${f.kind}"><span class="tm">${f.clock}</span>${f.text}</div>`).join('');
  el.scrollTop=el.scrollHeight;
}
function renderMon(mon,danger,water,gt){
  const wp=Math.min(100,Math.round(water/WMAX*100));
  let h=`<div class="gauge"><div class="gl"><span class="t">🌊 하천 수위</span>
    <span class="v" style="color:${danger.color}">${water}cm <span style="font-size:12px">▲</span></span></div>
    <div class="track"><i style="width:${wp}%;background:${danger.color}"></i></div></div>`;
  if(gt&&gt.golden){ h+=`<div class="gt"><span>⏱</span><span class="lab">현 상황 골든타임</span>
    <span class="cd">${gt.golden}분 · ~${gt.deadline}</span></div>`; }
  const bar=(t,v)=>{const col=v>=50?'var(--good)':v>=25?'var(--warn)':'var(--bad)';
    return `<div class="mbar"><div class="top"><span>${t}</span><span>${v}%</span></div>
      <div class="bar"><i style="width:${Math.min(100,v)}%;background:${col}"></i></div></div>`;};
  h+=bar('🏃 대피완료율',mon['대피완료율'])+bar('🚧 통제율',mon['통제율']);
  const ch=k=>(_pm&&_pm[k]!==mon[k])?'flash':'';
  h+=`<div class="cnts">
    <div class="cnt ${ch('인명피해')}"><div class="n" style="color:var(--bad)">${mon['인명피해']}</div><div class="l">💔 인명피해</div></div>
    <div class="cnt ${ch('구조')}"><div class="n" style="color:var(--good)">${mon['구조']}</div><div class="l">🆘 구조</div></div>
    <div class="cnt ${ch('주민혼란')}"><div class="n" style="color:var(--warn)">${mon['주민혼란']}</div><div class="l">😨 주민혼란</div></div>
  </div>`;
  $('s-mon').innerHTML=h;
  _pm=Object.assign({},mon);
}
function renderDec(f){
  if(!f){ $('s-dec').style.display='none'; return; }
  $('s-dec').style.display='block';
  const num='①②③④⑤';
  $('s-dec').innerHTML=`<div class="dh">▶ 지금 결정</div><div class="nm">🚨 ${f.label}</div>
    <div class="iv">${f.inject}</div>
    ${f.options.map((o,i)=>`<button class="opt" onclick="decide('${o.id}')"><b>${num[i]||(i+1)}</b>${o.text}</button>`).join('')}`;
}
async function decide(id){
  document.querySelectorAll('#s-dec .opt').forEach(b=>b.disabled=true);
  SCH.push(id);
  const r=await (await fetch('/api/sim_run',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({disaster:DIS,choices:SCH,address:ADDR,variant:SIM.variant,use_llm:true})})).json();
  if(r.finished){
    _last=r;
    renderFeed(r.feed); renderMon(r.monitor,r.danger,r.water,null);
    $('s-dec').style.display='none'; $('s-prog').textContent='상황 종료';
    setTimeout(()=>toDebrief(r),850); return;
  }
  CUR=r.current; renderSim();
}
function renderSteps(){
  let s=''; for(let i=0;i<META.total_phases;i++) s+=`<div class="s ${i<CHOICES.length?'done':''}"></div>`;
  $('t-steps').innerHTML=s;
}
async function choose(optId){
  const trial=[...CHOICES, optId];
  const r=await run(trial);
  const t=r.timeline[r.timeline.length-1];
  document.querySelectorAll('#opts .opt').forEach(b=>b.disabled=true);
  const cls={correct:'sel-correct',partial:'sel-partial',wrong:'sel-wrong'}[t.chosen.rubric];
  [...document.querySelectorAll('#opts .opt')].forEach(b=>{ if(b.textContent===t.chosen.text) b.classList.add(cls); });
  const badge={correct:'적절',partial:'보완 필요',wrong:'부적절'}[t.chosen.rubric];
  $('opts').insertAdjacentHTML('afterend',
    `<div class="reveal" id="rv"><b><span class="pill ${t.chosen.rubric}">${badge}</span></b>${t.chosen.why}</div>`);
  renderMeters(t.state_after);
  CHOICES=trial; renderSteps();
  if(r.finished){
    $('rv').insertAdjacentHTML('beforeend',`<div style="margin-top:10px"><button class="next" onclick="toDebrief()">훈련 강평 보기 →</button></div>`);
  } else {
    // 인라인 JSON 주입 금지 — 상황 텍스트에 따옴표가 있어도 안 깨지도록 _last에서 읽는다
    $('rv').insertAdjacentHTML('beforeend',`<button class="next" onclick="nextPhase()">다음 상황 →</button>`);
  }
}
function nextPhase(){ renderPhase(_last.next_phase, lastState()); }
async function run(choices){ const r=await (await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({disaster:DIS,choices,address:ADDR})})).json(); _last=r; return r; }
function lastState(){ return _last.state||dfltState(); }

// ── 도상훈련 TTX (서술형) ──
async function startTTX(id){
  DIS=id; TSTAGE=0; TSCORES=[]; TEVALS=[]; TSURP=false;
  TTX=await (await fetch('/api/ttx_start?disaster='+id+'&variant='+SEED+'&address='+encodeURIComponent(ADDR)+'&role='+encodeURIComponent(TROLE))).json();
  $('x-title').textContent=(TTX.icon||'📝')+' '+TTX.title;
  $('x-role').innerHTML='🎖 '+(TTX.role||'')+(TTX.variant_label?` &nbsp;·&nbsp; <span style="color:var(--accent2)">🎲 ${TTX.variant_label}</span>`:'');
  $('x-intro').textContent=TTX.intro||'';
  renderScenReqs(); renderRolePick(); renderResources();
  renderTTXStage();
  show('sc-ttx');
}
// 1-1-3 시나리오 5요건 충족 배지
function renderScenReqs(){
  const rq=TTX.scenario_reqs||[]; if(!rq.length){ $('x-scenreq').innerHTML=''; return; }
  const met=rq.filter(r=>r.met).length;
  const chips=rq.map(r=>`<span class="sq ${r.met?'on':'off'}" title="${(r.note||'').replace(/"/g,'')}">${r.met?'✓':'△'} ${r.label}</span>`).join('');
  const gtxt=met>=5?'매우우수 요건 충족(5/5)':met>=4?`우수 요건(${met}/5)`:`요건 ${met}/5`;
  $('x-scenreq').innerHTML=`<div class="scenreq">
    <div class="sq-h">🧩 공식 시나리오 요건 <span class="sq-b">평가지표 1-1-3</span> <span class="sq-g">${gtxt}</span></div>
    <div class="sq-row">${chips}</div></div>`;
}
// P4 다역할(2-3) — 역할 선택 시 책무·중점이 바뀐다(관점만, 채점 불변)
function renderRolePick(){
  const sel=(TTX.selected_role||{}).key, roles=TTX.roles||[];
  const chips=roles.map(r=>`<span class="rchip${r.key===sel?' on':''}" onclick="pickRole('${r.key}')">${r.label}</span>`).join('');
  const cur=TTX.selected_role||{};
  $('x-rolepick').innerHTML=`<div class="rolepick">
    <div class="rh">🎭 나의 역할 <span class="rb">2-3 다역할</span></div>
    <div class="rchips">${chips}</div>
    <div class="rduty"><b>${cur.label||''}</b> — ${cur.duty||''}<br><span class="rfocus">▸ 이 역할의 중점: ${cur.focus||''}</span></div>
  </div>`;
}
function pickRole(k){ if(k===((TTX.selected_role||{}).key))return; TROLE=k; startTTX(DIS); }
// P5 동원자원 체크리스트(2-2-4) — 실 대피소·펌프장 + 표준 인력·협약기관
function renderResources(){
  const R=TTX.resources||{}; const esc=s=>String(s||'');
  const shel=(R.shelters||[]).map(s=>`<li><label><input type="checkbox">${esc(s.name)}${s.cap?` <span class="rc">(수용 ${s.cap.toLocaleString()}명)</span>`:''}</label></li>`).join('')
    || '<li class="rmut">이 시군구 지진옥외대피소 데이터 없음</li>';
  const pumps=(R.pumps||[]).map(p=>`<li><label><input type="checkbox">${esc(p)}</label></li>`).join('')
    || '<li class="rmut">배수펌프장 실데이터 미확인 — 이동식 배수펌프 동원</li>';
  const per=(R.personnel||[]).map(p=>`<li><label><input type="checkbox">${esc(p)}</label></li>`).join('');
  const ag=(R.agencies||[]).map(a=>`<li><label><input type="checkbox">${esc(a)}</label></li>`).join('');
  $('x-resources').innerHTML=`<details class="resbox"><summary>🧰 동원 가능 자원 체크리스트 <span class="rb">2-2-4</span> <span class="rmut">— 상황판단회의 안건 ③ 확인용</span></summary>
    <div class="rgrid">
      <div class="rcol"><div class="rct">🏫 대피소 <span class="rtag live">실데이터</span></div><ul>${shel}</ul></div>
      <div class="rcol"><div class="rct">💧 배수시설 <span class="rtag live">실데이터</span></div><ul>${pumps}</ul></div>
      <div class="rcol"><div class="rct">👷 동원 인력 <span class="rtag std">표준편성</span></div><ul>${per}</ul></div>
      <div class="rcol"><div class="rct">🤝 협약·유관기관 <span class="rtag std">표준체계</span></div><ul>${ag}</ul></div>
    </div>
    <div class="rsrc">실데이터: 행안부 지진옥외대피소·인명피해우려지역(배수시설) · 표준: 재난안전대책본부 편성·유관기관 협조체계(공개)</div>
  </details>`;
}
function renderTTXStage(){
  const st=TTX.stages[TSTAGE];
  const ex=(st.examples&&st.examples.length)
    ? `<div class="chips" style="margin:0 0 8px">✍️ 예시 답안 채우기 &nbsp;${st.examples.map((e,i)=>`<span class="chip" onclick="fillEx(${i})">${e.label}</span>`).join('')}</div>`
    : '';
  const mt=st.meeting;
  const meeting=mt?`<div class="meeting">
      <div class="mh">🧩 ${mt.title} — 대책본부 대응방침 토의</div>
      <div class="mi">${mt.intro}</div>
      <ol class="magenda">${mt.agenda.map(a=>`<li>${a}</li>`).join('')}</ol>
      <div class="mb">📑 ${mt.basis}</div></div>`:'';
  $('x-stage').innerHTML=`
    <div class="inj"><div class="ih">${st.clock||''} · 상황 부여 ${TSTAGE+1}/${TTX.total_stages}</div>
      <div class="it">${st.title}</div><div class="ix">${st.inject}</div></div>
    ${meeting}
    <div class="task">▶ 상황판단회의 결정에 따라, ${st.task}</div>
    ${ex}
    <textarea class="ans" id="x-ans" placeholder="예) ① 지하차도·저지대 즉시 통제…  ② 반지하 선제 대피 방송…  ③ 재난문자·유관기관 전파…"></textarea>
    <button class="subt" id="x-sub" onclick="submitTTX()">📝 대응방안 제출 · 평가받기</button>
    <div id="x-res"></div>`;
}
function fillEx(i){ $('x-ans').value=TTX.stages[TSTAGE].examples[i].answer; $('x-ans').focus(); }
async function submitTTX(){
  const ans=$('x-ans').value.trim();
  if(ans.length<5){ alert('대응방안을 먼저 작성해 주세요.'); return; }
  $('x-sub').disabled=true; $('x-sub').textContent='AI 평가관이 표준매뉴얼과 대조 중…';
  const r=await (await fetch('/api/ttx_eval',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({disaster:DIS,stage:TSTAGE,answer:ans,address:ADDR,variant:TTX.variant,use_llm:true,role:TROLE})})).json();
  TSCORES.push(r.score); TEVALS.push(r);
  renderTTXResult(r);
}
function renderTTXResult(r){
  const col=r.score>=85?'var(--good)':r.score>=70?'#bfe0ff':r.score>=55?'var(--warn)':'var(--bad)';
  const lvl={full:'반영',partial:'부분',none:'누락'};
  const last=TSTAGE>=TTX.total_stages-1;
  const els=r.elements.map(e=>`<div class="elem">
     <span class="lv ${e.level}">${lvl[e.level]}</span>
     <div><div class="ed">${e.desc} <span class="small">(${e.weight}점)</span></div>
       <div class="er">${e.reason||''}</div><div class="eg">📑 ${e['근거']||''}</div></div></div>`).join('');
  const g5=r.grade5||{}; const g5col=g5.score>=5?'var(--good)':g5.score>=4?'#bfe0ff':g5.score>=3?'var(--warn)':'var(--bad)';
  $('x-res').innerHTML=`
    <div class="tscore"><span class="big" style="color:${col}">${r.score}<span style="font-size:16px">/100</span></span>
      ${g5.grade?`<span class="gr5" style="background:${g5col}">공식등급 ${g5.grade} <b>${g5.score}점</b></span>`:''}
      <span class="eng">평가: ${r.engine}</span></div>
    ${renderIndicators(r.indicators)}
    <h4 style="font-size:13px;color:var(--sub);margin:6px 0 4px">표준 대응요소 반영도</h4>${els}
    ${(r.missed&&r.missed.length)?`<div class="reveal" style="border-left:3px solid var(--bad)"><b style="color:var(--bad)">놓친·약한 요소</b>${r.missed.join(' · ')}</div>`:''}
    <div style="background:#10254a;border:1px solid #29508f;border-radius:10px;padding:12px 14px;margin-top:10px;font-size:13.5px">🧭 ${r.coach||''}</div>
    ${r.role_note?`<div class="reveal" style="border-left:3px solid var(--accent2)"><b>🎭 ${r.role_note.label} 관점</b> ${r.role_note.focus}</div>`:''}
    ${renderRegionRef(r.region_reflection)}
    <div class="model"><b>📘 모범답안 (표준매뉴얼 기준)</b>${r.model_answer||''}</div>
    ${lastBtn(last)}`;
  $('x-res').scrollIntoView({behavior:'smooth',block:'nearest'});
}
function lastBtn(last){
  if(!last) return `<button class="subt" style="margin-top:14px;width:100%" onclick="nextTTXStage()">다음 상황 부여 →</button>`;
  if(TTX.surprise && !TSURP) return `<button class="subt surp" style="margin-top:14px;width:100%" onclick="startSurprise()">⚡ 불시 돌발상황 대응 (2-1-4) →</button>`;
  return `<button class="subt" style="margin-top:14px;width:100%" onclick="ttxDone()">🏁 도상훈련 종료 · 총평</button>`;
}
function nextTTXStage(){ TSTAGE++; renderTTXStage(); window.scrollTo({top:0,behavior:'smooth'}); }
// ── 돌발 불시메시지(2-1-4) ──
function startSurprise(){
  const s=TTX.surprise; if(!s){ ttxDone(); return; }
  $('x-stage').innerHTML=`
    <div class="inj surp-inj"><div class="ih">⚡ 불시 돌발상황 · 통제관 부여 <span class="surp-b">평가지표 2-1-4</span></div>
      <div class="it">${s.icon||'⚡'} ${s.title}</div><div class="ix">${s.inject}</div></div>
    <div class="task">▶ ${s.task}</div>
    <textarea class="ans" id="x-sans" placeholder="예) ① 대체 통신수단 확보…  ② 인명·우선순위 재조정…  ③ 수기 기록·복구 후 보고…"></textarea>
    <button class="subt surp" id="x-ssub" onclick="submitSurprise()">⚡ 돌발 대응 제출 · 평가받기</button>
    <div id="x-res"></div>`;
  window.scrollTo({top:0,behavior:'smooth'});
}
async function submitSurprise(){
  const ans=$('x-sans').value.trim();
  if(ans.length<5){ alert('돌발상황 대응을 먼저 작성해 주세요.'); return; }
  $('x-ssub').disabled=true; $('x-ssub').textContent='AI 평가관이 돌발대응을 판정 중…';
  const r=await (await fetch('/api/ttx_surprise_eval',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({disaster:DIS,answer:ans,address:ADDR,variant:TTX.variant,use_llm:true,role:TROLE})})).json();
  TSURP=true; TSCORES.push(r.score); TEVALS.push(r);
  renderTTXResult(r);   // 동일 결과 UI(공식등급·지표대조 포함), last=true라 종료 버튼
}
const G5COL={'매우우수':'var(--good)','우수':'#7fc4ff','보통':'var(--warn)','미흡':'#ff9d6b','매우미흡':'var(--bad)'};
function renderIndicators(inds){
  if(!inds||!inds.length) return '';
  const rows=inds.map(i=>{
    const c=G5COL[i.grade]||'var(--sub)';
    return `<div class="ind">
      <div class="ind-h"><span class="ind-code">${i.code.replace('-INMYEONG','·인명').replace('-SUSEUP','·수습')}</span>
        <span class="ind-t">${i.title}</span>
        <span class="ind-g" style="background:${c}">${i.grade} ${i.grade_score}점</span></div>
      <div class="ind-d">${i.grade_desc||''}</div>
      ${(i.missed&&i.missed.length)?`<div class="ind-m">▸ 보완: ${i.missed.join(' · ')}</div>`:''}</div>`;
  }).join('');
  return `<div class="indbox"><div class="indbox-h">📋 공식 평가지표 대조 <span class="indbox-s">「2026 안전한국훈련 평가지표」 기준 획득 등급</span></div>${rows}</div>`;
}
function renderRegionRef(rr){
  if(!rr||!rr.length) return '';
  const li=rr.map(r=>`<li>${r.reflected?'<b style="color:var(--good)">✔ 반영</b>':'<b style="color:var(--bad)">✘ 미반영</b>'} ${r.label} — <span style="color:var(--sub)">${r.advice||''}</span></li>`).join('');
  return `<div class="reveal" style="border-left:3px solid var(--accent2)"><b>🛰 지역 재난안전데이터 반영도</b>
    <ul style="margin:6px 0 0;padding-left:18px;font-size:12.5px;line-height:1.6">${li}</ul></div>`;
}
function grade5js(s){ return s>=90?['매우우수',5]:s>=75?['우수',4]:s>=55?['보통',3]:s>=35?['미흡',2]:['매우미흡',1]; }
function ttxDone(){
  // 상황부여(본 훈련)와 돌발 불시메시지(2-1-4)를 분리 집계 — 성격이 다른 평가라 평균에 섞지 않는다
  const stageE=TEVALS.filter(e=>!e.surprise), surpE=TEVALS.find(e=>e.surprise);
  const ss=stageE.map(e=>e.score);
  const avg=Math.round(ss.reduce((a,b)=>a+b,0)/(ss.length||1));
  const [sg,sgn]=grade5js(avg);
  const col=avg>=85?'var(--good)':avg>=70?'#bfe0ff':avg>=55?'var(--warn)':'var(--bad)';
  const g5col=sgn>=5?'var(--good)':sgn>=4?'#7fc4ff':sgn>=3?'var(--warn)':'var(--bad)';
  // 전 응답(상황부여+돌발)의 공식 평가지표 대조 병합
  const agg={}; TEVALS.forEach(e=>(e.indicators||[]).forEach(i=>{ (agg[i.code]=agg[i.code]||{t:i.title,s:0,n:0}); agg[i.code].s+=i.score; agg[i.code].n++; }));
  const inds=Object.entries(agg).map(([code,v])=>{const s=Math.round(v.s/v.n);const g=grade5js(s);return{code,title:v.t,grade:g[0],gs:g[1]};}).sort((a,b)=>a.code<b.code?-1:1);
  const indChips=inds.map(i=>`<div class="mind"><span class="mind-c">${i.code.replace('-INMYEONG','·인명').replace('-SUSEUP','·수습')}</span><span class="mind-t">${i.title}</span><span class="mind-g" style="background:${G5COL[i.grade]||'#888'}">${i.grade} ${i.gs}점</span></div>`).join('');
  const surpLine=surpE?`<div class="done-surp">⚡ 돌발 불시메시지 대응 <span class="ds-b">2-1-4</span> — <b style="color:${G5COL[(grade5js(surpE.score))[0]]}">${surpE.score}점 · ${(grade5js(surpE.score))[0]}</b> <span class="small">(${surpE.title||''})</span></div>`:'';
  $('x-stage').innerHTML=`<div class="tscore"><span class="big" style="color:${col}">${avg}<span style="font-size:16px">/100</span></span>
      <span class="gr5" style="background:${g5col}">공식등급 ${sg} <b>${sgn}점</b></span>
      <span class="eng">도상훈련 종합</span></div>
    <p class="lead">${ss.length}개 상황부여 평균 <b>${avg}점</b> · 단계별 ${ss.join(' · ')}점</p>
    ${surpLine}
    ${inds.length?`<div class="mindbox"><div class="mind-h">📋 공식 평가지표 종합 대조 <span class="small">「2026 안전한국훈련 평가지표」 기준</span></div>${indChips}</div>`:''}
    <div class="btnrow"><button class="pri" onclick="openReport('ttx')">📄 훈련 결과보고서</button><button onclick="rerollTTX()">🎲 다른 상황</button><button onclick="startTTX(DIS)">↻ 같은 상황 재훈련</button><button onclick="toCat()">다른 재난 선택</button></div>`;
  window.scrollTo({top:0,behavior:'smooth'});
}
// 결과보고서 — 새 창에서 인쇄/PDF 저장 가능한 공무원 평가보고서
async function openReport(mode){
  const body=(mode==='ttx')
    ? {mode:'ttx',disaster:DIS,address:ADDR,variant:(TTX&&TTX.variant)||0,stages:TEVALS,role:TROLE}
    : {mode:'sim',disaster:DIS,address:ADDR,sim:_last};
  const w=window.open('','_blank');
  if(w) w.document.write('<p style="font-family:sans-serif;padding:40px">결과보고서 생성 중…</p>');
  const html=await (await fetch('/api/report',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)})).text();
  if(w){ w.document.open(); w.document.write(html); w.document.close(); }
}

// 3) 강평 + 실제 대응법
function toDebrief(r){
  r=r||_last;
  $('d-dec').textContent=r.decision_score; $('d-out').textContent=r.outcome_score; $('d-tot').textContent=r.total;
  const g=r.grade||''; const col=r.total>=85?'var(--good)':r.total>=70?'#bfe0ff':r.total>=55?'var(--warn)':'var(--bad)';
  const gd=$('d-grade'); gd.textContent=g; gd.style.background=col; gd.style.color=r.total>=70&&r.total<85?'#0a1f3d':'#06210f';
  if(r.total<55){gd.style.color='#fff'}
  const db=r.debrief||{};
  $('d-eng').textContent=r.debrief_engine||'';
  $('d-verdict').textContent=db.verdict||'';
  $('d-did').innerHTML=(db.did_well||[]).map(x=>`<li>${x}</li>`).join('')||'<li class="muted">없음</li>';
  $('d-missed').innerHTML=(db.missed||[]).map(x=>`<li>${x}</li>`).join('')||'<li class="muted">없음 — 전 단계 적절</li>';
  $('d-coach').innerHTML='🧭 '+(db.coach||'');
  renderGuide(r.guideline);
  show('sc-debrief');
}
function renderGuide(g){
  if(!g||!g.title){ $('d-guide').style.display='none'; return; }
  $('d-guide').style.display='block';
  const sec=(t,arr)=>arr&&arr.length?`<div class="gsec"><h5>${t}</h5><ul>${arr.map(x=>`<li>${x}</li>`).join('')}</ul></div>`:'';
  $('d-guide').innerHTML=`<div class="gh">📘 ${g.title} <span class="tag">실제 대응법 · 공개 독트린</span></div>
    ${sec('사전 대비', g.before)}${sec('재난 시 행동', g.during)}${sec('대피 요령', g.evacuate)}
    ${g.shelter_hint?`<div class="ghint">📍 ${g.shelter_hint}</div>`:''}
    <div class="gsrc">출처: ${g.source||''}</div>`;
}
function restart(){ startDis(DIS); }
