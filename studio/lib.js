// ============================================================
// unizom リール・スタジオ 共通部品（2026-09-29）
// 毎週の場面コード（scenes.js）はこの部品を使って「場面の絵だけ」を書く。
// テロップの書式・字幕・切り替え・時間割はここで統一する（量産に見えないよう画風は場面側で変える）。
//
// 画面: 1080×1920。右190px・下420pxはリールの操作ボタンに隠れる＝文字を置かない。
// 場面関数の形: function(t, d, mk) … t=場面内の秒, d=場面の長さ, mk=各文の読み始め秒（mk[1]=2文目）
// 背景は場面側で塗る（塗らなければ透明＝下に動画を合成できる。冒頭の実写動画で使う）
// ============================================================
const W = 1080, H = 1920;
const RED = '#D63036', INK = '#111';
const cv = document.getElementById('c'), g = cv.getContext('2d');
const IMG = {};

// ---- 文字の位置の記録（機械の検査用・2026-09-29）----
// window.AUDIT が配列の間、描いた文字の画面上の箱を記録する。重なり・安全域（右190px・下420px）へのはみ出しを見つけるため。
const _fillText = g.fillText.bind(g);
g.fillText = function(txt, x, y, mw){
  if (window.AUDIT && g.globalAlpha > 0.3 && String(txt).trim()){
    const m = g.measureText(txt), T = g.getTransform();
    const pts = [[x - m.actualBoundingBoxLeft, y - m.actualBoundingBoxAscent], [x + m.actualBoundingBoxRight, y + m.actualBoundingBoxDescent]]
      .map(([px,py]) => [T.a*px + T.c*py + T.e, T.b*px + T.d*py + T.f]);
    window.AUDIT.push({txt: String(txt), x0: Math.min(pts[0][0],pts[1][0]), y0: Math.min(pts[0][1],pts[1][1]),
                       x1: Math.max(pts[0][0],pts[1][0]), y1: Math.max(pts[0][1],pts[1][1])});
  }
  return mw === undefined ? _fillText(txt, x, y) : _fillText(txt, x, y, mw);
};
function auditIssues(){
  const A = window.AUDIT || [], out = [];
  for (const b of A){
    if (b.zone) continue;
    if (b.y1 > 1510) out.push(`下420pxの帯に文字「${b.txt}」(下端y=${b.y1|0})`);
    if (b.x1 > 900) out.push(`右190pxの帯に文字「${b.txt}」(右端x=${b.x1|0})`);
    if (b.x0 < 20 || b.y0 < 20) out.push(`画面の外へ文字「${b.txt}」`);
  }
  for (let i=0;i<A.length;i++) for (let j=i+1;j<A.length;j++){
    const a=A[i], b=A[j]; if (a.txt===b.txt) continue;
    if ((a.zone && b.cap) || (b.zone && a.cap) || (a.cap && b.cap) || (a.zone && b.zone)) continue;
    const ox = Math.min(a.x1,b.x1) - Math.max(a.x0,b.x0), oy = Math.min(a.y1,b.y1) - Math.max(a.y0,b.y0);
    if (ox > 6 && oy > 6) out.push(`文字が重なっている「${a.txt}」と「${b.txt}」`);
  }
  return [...new Set(out)];
}
window.auditIssues = auditIssues;

function loadImg(k, src){ return new Promise((r, j)=>{ const i=new Image(); i.onload=()=>{IMG[k]=i;r();}; i.onerror=()=>j(new Error('画像が読めない: '+src)); i.src=src; }); }
window.ready = (async()=>{
  const f = new FontFace('NJP', 'url(a/njp.ttf)', {weight:'100 900'});
  await f.load(); document.fonts.add(f);
  const man = await (await fetch('assets.json')).json();
  await Promise.all(Object.entries(man).map(([k,s])=>loadImg(k,'a/'+s)));
  window.TIMING = await (await fetch('timing.json')).json();
  buildTimeline(); makePaper();
  return true;
})();

let SC = [];
function buildTimeline(){ let t=0; SC = TIMING.map(s=>{ const o={id:s.id,start:t,dur:s.scene,voice:s.voice,mk:(s.marks||[0]).map(m=>m+0.25)}; t+=s.scene; return o; }); window.TOTAL=t; }

// ---- 補助 ----
const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
const lerp=(a,b,t)=>a+(b-a)*t;
const eo=t=>1-Math.pow(1-clamp(t),3);
const eio=t=>{t=clamp(t);return t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;};
const back=t=>{t=clamp(t);const c1=1.70158,c3=c1+1;return 1+c3*Math.pow(t-1,3)+c1*Math.pow(t-1,2);};
const seg=(t,a,b)=>clamp((t-a)/(b-a));
function rnd(seed){ let s=seed>>>0||1; return ()=>{ s^=s<<13; s^=s>>>17; s^=s<<5; return ((s>>>0)%100000)/100000; }; }
function font(sz,w=900){ return `${w} ${sz}px NJP`; }
function fitText(txt,maxW,sz,w=900){ g.font=font(sz,w); while(g.measureText(txt).width>maxW && sz>24){ sz-=2; g.font=font(sz,w);} return sz; }
function roundRect(x,y,w,h,r){ g.beginPath(); g.moveTo(x+r,y); g.arcTo(x+w,y,x+w,y+h,r); g.arcTo(x+w,y+h,x,y+h,r); g.arcTo(x,y+h,x,y,r); g.arcTo(x,y,x+w,y,r); g.closePath(); }

// ---- 共通テロップ（全場面で同じ書体・同じ作法） ----
function kicker(txt, y, a){           // 赤い札（小見出し）
  if(a<=0) return;
  g.save(); g.globalAlpha=a; g.font=font(44,800);
  const w=g.measureText(txt).width+56, x=540-w/2;
  g.fillStyle=RED; roundRect(x,y-40,w,68,34); g.fill();
  g.fillStyle='#fff'; g.textAlign='center'; g.textBaseline='middle'; g.fillText(txt,540,y-6);
  g.restore();
}
function headline(lines, y, a, sz=108, dy=0){   // 白・極太・黒フチの見出し（幅700pxに自動で収める）
  if(a<=0) return;
  g.save(); g.globalAlpha=a; g.textAlign='center'; g.textBaseline='alphabetic';
  lines.forEach((ln,i)=>{
    const s=fitText(ln,700,sz); g.font=font(s);
    const yy=y+i*(s*1.18)+dy;
    g.lineJoin='round'; g.lineWidth=16; g.strokeStyle='rgba(0,0,0,.85)'; g.strokeText(ln,540,yy);
    g.fillStyle='#fff'; g.fillText(ln,540,yy);
  });
  g.restore();
}
function underline(x1,x2,y,p){ if(p<=0) return; g.save(); g.fillStyle=RED; g.fillRect(x1,y,(x2-x1)*eo(p),12); g.restore(); }
function caption(lines, a){           // 字幕＝ナレーションと同じ文。半透明の黒帯（下端 y=1470）
  if(a<=0) return;
  g.save(); g.globalAlpha=a; let cs=50; g.font=font(cs,700);
  while(Math.max(...lines.map(l=>g.measureText(l).width))>680 && cs>34){ cs-=2; g.font=font(cs,700); }
  const lh=cs*1.4, h=lines.length*lh+44, y0=1470-h;
  let mw=0; lines.forEach(l=>mw=Math.max(mw,g.measureText(l).width));
  const w=Math.min(760,mw+70), x0=540-w/2;
  g.fillStyle='rgba(0,0,0,.62)'; roundRect(x0,y0,w,h,22); g.fill();
  g.fillStyle=RED; g.fillRect(x0,y0+18,8,h-36);
  g.fillStyle='#fff'; g.textAlign='center'; g.textBaseline='middle';
  if (window.AUDIT && a > 0.3) window.AUDIT.push({txt:'（字幕の帯）', zone:true, x0, y0, x1:x0+w, y1:y0+h});
  const n0 = window.AUDIT ? window.AUDIT.length : 0;
  lines.forEach((l,i)=>g.fillText(l,540,y0+22+lh/2+i*lh));
  if (window.AUDIT) for (let k=n0;k<window.AUDIT.length;k++) window.AUDIT[k].cap = true;
  g.restore();
}
function capA(t,dur){ return Math.min(seg(t,0.15,0.4), 1-seg(t,dur-0.25,dur)); }
function label(txt, x, y, a, color='#fff', sz=52, align='left', outline=null){  // 引き出し線の先の文字
  if(a<=0) return; g.save(); g.globalAlpha=a; g.font=font(sz,900); g.textAlign=align;
  if(outline){ g.lineJoin='round'; g.lineWidth=12; g.strokeStyle=outline; g.strokeText(txt,x,y); }
  g.fillStyle=color; g.fillText(txt,x,y); g.restore();
}
function leader(pts, a, color='#fff', w=4){ if(a<=0) return; g.save(); g.globalAlpha=a; g.strokeStyle=color; g.lineWidth=w; g.beginPath(); g.moveTo(pts[0][0],pts[0][1]); pts.slice(1).forEach(p=>g.lineTo(p[0],p[1])); g.stroke(); g.restore(); }

// ---- 画像（実写の切り抜き・写真）----
function drawImg(key, cx, cy, h, a=1, rot=0){ const im=IMG[key]; if(!im||a<=0) return; const w=h*im.width/im.height; g.save(); g.globalAlpha=a; g.translate(cx,cy); g.rotate(rot); g.drawImage(im,-w/2,-h/2,w,h); g.restore(); }
function coverImg(key, zoom=1, ox=0, oy=0){  // 画面いっぱいに敷く（ぼかさない）
  const im=IMG[key]; const s=Math.max(W/im.width,H/im.height)*zoom; const w=im.width*s,h=im.height*s; g.drawImage(im,540-w/2+ox,960-h/2+oy,w,h); }
function photoCard(key, cx, cy, w, a=1, rot=0){  // 写真を白フチのカードで見せる（ぼかし背景の代わり）
  const im=IMG[key]; if(!im||a<=0) return; const h=w*im.height/im.width; g.save(); g.globalAlpha=a; g.translate(cx,cy); g.rotate(rot);
  g.shadowColor='rgba(0,0,0,.45)'; g.shadowBlur=40; g.shadowOffsetY=16; g.fillStyle='#fff'; g.fillRect(-w/2-18,-h/2-18,w+36,h+36);
  g.shadowColor='transparent'; g.drawImage(im,-w/2,-h/2,w,h); g.restore(); }
function contactShadow(cx, cy, rx, ry, a){ g.save(); g.globalAlpha=a; g.filter='blur(22px)'; g.fillStyle='#000'; g.beginPath(); g.ellipse(cx,cy,rx,ry,0,0,7); g.fill(); g.restore(); }
function sweep(key, cx, cy, h, p){  // 商品の上を光が横切る
  if(p<=0||p>=1) return; const im=IMG[key]; const w=h*im.width/im.height;
  const off=document.createElement('canvas'); off.width=W; off.height=H; const o=off.getContext('2d');
  o.drawImage(im,cx-w/2,cy-h/2,w,h); o.globalCompositeOperation='source-in';
  const lx=lerp(cx-w/2-150,cx+w/2+150,p); const lg=o.createLinearGradient(lx-120,0,lx+120,0);
  lg.addColorStop(0,'rgba(255,255,255,0)'); lg.addColorStop(.5,'rgba(255,245,220,.55)'); lg.addColorStop(1,'rgba(255,255,255,0)');
  o.fillStyle=lg; o.fillRect(0,0,W,H); g.drawImage(off,0,0); }

// ---- 背景の型（画風の素材） ----
function bgBlueprint(){ g.fillStyle='#0d1a2b'; g.fillRect(0,0,W,H); g.save(); g.lineWidth=2;
  g.strokeStyle='rgba(120,170,230,.10)'; for(let x=0;x<=W;x+=40){g.beginPath();g.moveTo(x,0);g.lineTo(x,H);g.stroke();} for(let y=0;y<=H;y+=40){g.beginPath();g.moveTo(0,y);g.lineTo(W,y);g.stroke();}
  g.strokeStyle='rgba(120,170,230,.22)'; for(let x=0;x<=W;x+=200){g.beginPath();g.moveTo(x,0);g.lineTo(x,H);g.stroke();} for(let y=0;y<=H;y+=200){g.beginPath();g.moveTo(0,y);g.lineTo(W,y);g.stroke();} g.restore(); }
function bgStudio(){ const gr=g.createRadialGradient(540,900,60,540,900,1150); gr.addColorStop(0,'#3a3b40'); gr.addColorStop(.55,'#1b1c20'); gr.addColorStop(1,'#08080a'); g.fillStyle=gr; g.fillRect(0,0,W,H); }
let PAPER=null;
function makePaper(){ PAPER=document.createElement('canvas'); PAPER.width=W; PAPER.height=H; const p=PAPER.getContext('2d');
  const R=rnd(7); p.fillStyle='#c9a574'; p.fillRect(0,0,W,H);
  for(let i=0;i<60000;i++){ const x=R()*W,y=R()*H,v=R(); p.fillStyle=v<.5?`rgba(90,60,30,${.05+R()*.06})`:`rgba(255,240,210,${.04+R()*.05})`; p.fillRect(x,y,2+R()*2,2+R()*2); }
  for(let i=0;i<140;i++){ const y=R()*H; p.strokeStyle=`rgba(110,80,45,${.05+R()*.05})`; p.lineWidth=1+R()*2; p.beginPath(); p.moveTo(0,y); p.bezierCurveTo(W*.3,y+R()*20-10,W*.7,y+R()*20-10,W,y+R()*16-8); p.stroke(); } }
function bgKraft(){ g.drawImage(PAPER,0,0); }                                   // クラフト紙（クレヨン向き）
function bgCream(){ g.fillStyle='#efe8db'; g.fillRect(0,0,W,H); g.globalAlpha=.25; g.drawImage(PAPER,0,0); g.globalAlpha=1; } // 生成り紙（フラット図解向き）
function topShade(h=900, a=.55){ const gr=g.createLinearGradient(0,0,0,h); gr.addColorStop(0,`rgba(0,0,0,${a})`); gr.addColorStop(1,'rgba(0,0,0,0)'); g.fillStyle=gr; g.fillRect(0,0,W,h); }

// ---- 線（途中まで描ける点列） ----
function bez(p0,p1,p2,p3,n=24){ const o=[]; for(let i=0;i<=n;i++){const t=i/n,u=1-t; o.push([u*u*u*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t*t*t*p3[0], u*u*u*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t*t*t*p3[1]]);} return o; }
function pathPts(cmds){ let pts=[], cur=null; for(const c of cmds){ if(c[0]==='M'||c[0]==='L'){cur=[c[1],c[2]];pts.push(cur);} else if(c[0]==='C'){ const b=bez(cur,[c[1],c[2]],[c[3],c[4]],[c[5],c[6]]); b.shift(); pts=pts.concat(b); cur=[c[5],c[6]]; } } return pts; }
function polyLen(p){ let L=0; for(let i=1;i<p.length;i++) L+=Math.hypot(p[i][0]-p[i-1][0],p[i][1]-p[i-1][1]); return L; }
function drawPartial(p, frac, close=false){ const L=polyLen(p)*clamp(frac); let acc=0; g.beginPath(); g.moveTo(p[0][0],p[0][1]);
  for(let i=1;i<p.length;i++){ const d=Math.hypot(p[i][0]-p[i-1][0],p[i][1]-p[i-1][1]); if(acc+d>=L){ const k=(L-acc)/d; g.lineTo(lerp(p[i-1][0],p[i][0],k),lerp(p[i-1][1],p[i][1],k)); break; } g.lineTo(p[i][0],p[i][1]); acc+=d; }
  if(close && frac>=1) g.closePath(); }
function fillPts(p){ g.beginPath(); g.moveTo(p[0][0],p[0][1]); for(const q of p) g.lineTo(q[0],q[1]); g.closePath(); }
function shift(p,dx,dy){ return p.map(q=>[q[0]+dx,q[1]+dy]); }
function scalePts(p,cx,cy,s){ return p.map(([x,y])=>[cx+x*s, cy+y*s]); }
function wobble(p, amp, seed){ const R=rnd(seed); return p.map(([x,y])=>[x+(R()-.5)*amp, y+(R()-.5)*amp]); }
function crayon(p, color, w, seed, frac=1, close=false){ for(let k=0;k<3;k++){ g.strokeStyle=color; g.globalAlpha=k===0?0.95:0.45; g.lineWidth=w-k*3; g.lineCap='round'; g.lineJoin='round'; drawPartial(wobble(p,5,seed+k*17), frac, close); g.stroke(); } g.globalAlpha=1; }
function iso(p,cx,cy,sc,ang=-Math.PI/2.6,squash=0.46){ return p.map(([x,y])=>{ const X=x*Math.cos(ang)-y*Math.sin(ang), Y=x*Math.sin(ang)+y*Math.cos(ang); return [cx+X*sc, cy+Y*sc*squash]; }); }
function slab(pts, th, top, side, deco){ g.fillStyle=side; fillPts(shift(pts,0,th)); g.fill();
  for(let i=0;i<pts.length-1;i++){ const a=pts[i],b=pts[i+1]; g.beginPath(); g.moveTo(a[0],a[1]); g.lineTo(b[0],b[1]); g.lineTo(b[0],b[1]+th); g.lineTo(a[0],a[1]+th); g.closePath(); g.fill(); }
  g.fillStyle=top; fillPts(pts); g.fill(); g.save(); fillPts(pts); g.clip(); deco&&deco(); g.restore(); g.strokeStyle='rgba(0,0,0,.55)'; g.lineWidth=3; fillPts(pts); g.stroke(); }
function arrow(x1,y1,x2,y2,color=RED,w=10,a=1){ if(a<=0) return; g.save(); g.globalAlpha=a; g.strokeStyle=color; g.fillStyle=color; g.lineWidth=w; g.beginPath(); g.moveTo(x1,y1); g.lineTo(x2,y2); g.stroke();
  const an=Math.atan2(y2-y1,x2-x1); g.beginPath(); g.moveTo(x2+Math.cos(an)*w*2,y2+Math.sin(an)*w*2); g.lineTo(x2+Math.cos(an+2.4)*w*2.4,y2+Math.sin(an+2.4)*w*2.4); g.lineTo(x2+Math.cos(an-2.4)*w*2.4,y2+Math.sin(an-2.4)*w*2.4); g.closePath(); g.fill(); g.restore(); }

// ---- 場面の切り替え（type: diag / iris / up / left / fade） ----
function wipeClip(type, p, cx=540, cy=960){ g.beginPath();
  if(type==='diag'){ const x=lerp(-600,W+600,eio(p)); g.moveTo(x-600,0); g.lineTo(x+300,0); g.lineTo(x-300,H); g.lineTo(x-1200,H); g.closePath(); g.rect(-2000,0,Math.max(0,x-600+2000),H); }
  else if(type==='iris'){ g.arc(cx,cy, eio(p)*2300, 0, 7); }
  else if(type==='up'){ const y=lerp(H,0,eio(p)); g.rect(0,y,W,H); }
  else if(type==='left'){ const x=lerp(W,0,eio(p)); g.rect(x,0,W,H); }
  else { g.rect(0,0,W,H); }
  g.clip(); }
const TR = 0.4;
window.render = function(T){
  const SCN = window.SCENES, TRT = window.TRANSITIONS || {};
  g.clearRect(0,0,W,H);
  let i = SC.findIndex(s=>T>=s.start && T<s.start+s.dur); if(i<0) i=SC.length-1;
  const s=SC[i], t=T-s.start;
  if(!SCN[s.id]) throw new Error('場面の関数が無い: '+s.id);
  if(i>0 && t<TR){
    const pv=SC[i-1]; g.save(); SCN[pv.id](t+pv.dur, pv.dur, pv.mk); g.restore();
    const p=t/TR, ty=TRT[s.id]||'fade';
    g.save();
    if(ty==='fade'){ g.globalAlpha=eio(p); } else { wipeClip(ty,p); g.clearRect(0,0,W,H); }
    SCN[s.id](t, s.dur, s.mk); g.restore();
    if(ty==='diag'){ const x=lerp(-600,W+600,eio(p)); g.save(); g.strokeStyle=RED; g.lineWidth=14; g.beginPath(); g.moveTo(x+300,0); g.lineTo(x-300,H); g.stroke(); g.restore(); }
  } else { g.save(); SCN[s.id](t, s.dur, s.mk); g.restore(); }
  // 最後の0.6秒はゆっくり暗く
  const fo=seg(T, TOTAL-0.6, TOTAL); if(fo>0){ g.fillStyle=`rgba(0,0,0,${fo})`; g.fillRect(0,0,W,H); }
  return true;
};
