// お手本：2026-09-29 インソール好評発売中（のみさん「とてもいい感じ」）
// 画風の割り振り：実写AI動画 → 設計図の線画 → 実写切り抜き＋引き出し線 → 生成り紙の分解図 → クレヨン手描き → AI背景＋実物
// 使う画像キー（assets.json）: duo（ペア・切り抜き）, side（側面・切り抜き）, pkg（パッケージ）, logo（実物ロゴ）, bg（締めのAI背景）

// ---- 冒頭：実写AI動画の上に文字だけ（背景を塗らない＝透明） ----
function sHook(t, d){
  topShade(900, .55);
  const a1=eo(seg(t,0.15,0.45)), a2=eo(seg(t,0.95,1.25));
  headline(['長靴の中で、'], 470, a1, 118, (1-a1)*30);
  const sh = t>1.0 && t<2.4 ? Math.sin(t*38)*6*(1-seg(t,1.6,2.4)) : 0;
  g.save(); g.translate(sh,0); headline(['足が動く。'], 620, a2, 132, (1-a2)*30); g.restore();
  underline(330,750,655,seg(t,1.2,1.6));
}

// ---- つま先：設計図風の線画（長靴の断面） ----
const BOOT = pathPts([['M',180,560],['L',172,1070],['C',170,1120,190,1152,240,1152],['L',840,1152],['C',905,1152,948,1120,948,1070],['C',948,1010,915,985,860,975],['C',760,958,640,950,560,925],['C',500,905,462,860,452,800],['L',446,560]]);
const FOOT = pathPts([['M',240,560],['L',236,1040],['C',234,1090,252,1118,290,1120],['C',400,1122,560,1122,700,1122],['C',770,1122,812,1112,826,1090],['C',836,1068,822,1050,790,1043],['C',700,1025,610,1000,555,965],['C',480,915,420,860,398,790],['L',394,560]]);
function insoleProfile(x0){
  const top=[[x0,1080],[x0+8,1096],[x0+30,1124],[x0+120,1122],[x0+230,1100],[x0+330,1110],[x0+470,1126],[x0+560,1129],[x0+612,1132],[x0+640,1140]];
  return top.concat([[x0+650,1150],[x0,1150]]);
}
function sToe(t, d, mk){
  const s2 = mk[1];
  bgBlueprint();
  const z = 1 + 0.18*eio(seg(t,s2,d));
  g.save(); g.translate(860,1060); g.scale(z,z); g.translate(-860,-1060);
  const pIns = eio(seg(t,s2-1.3,s2-0.4));
  const slide = 60*eio(seg(t,0.9,1.6)) * (1-pIns);
  const lift  = -24*pIns;
  g.save(); fillPts(BOOT); g.clip();
  g.save(); g.beginPath(); g.rect(560,880,420,300); g.clip();
  g.strokeStyle='rgba(214,48,54,.55)'; g.lineWidth=5;
  for(let k=-400;k<600;k+=22){ g.beginPath(); g.moveTo(560+k,1180); g.lineTo(560+k+300,880); g.stroke(); }
  g.restore();
  const F = shift(FOOT, slide, lift);
  g.fillStyle='#0d1a2b'; fillPts(F); g.fill();
  g.fillStyle='rgba(150,200,255,.16)'; fillPts(F); g.fill();
  if(pIns>0){ const x0 = lerp(-700, 196, pIns); const P = insoleProfile(x0);
    g.fillStyle=RED; fillPts(P); g.fill();
    g.save(); fillPts(P); g.clip(); g.fillStyle='#1b1b1f'; g.fillRect(x0-20,1070,720,34); g.restore();
    g.strokeStyle='rgba(255,255,255,.9)'; g.lineWidth=4; fillPts(P); g.stroke(); }
  g.restore();
  g.lineJoin='round'; g.lineCap='round';
  g.strokeStyle='#e9f1ff'; g.lineWidth=9; drawPartial(BOOT, eo(seg(t,0.0,1.0))); g.stroke();
  g.save(); g.setLineDash([16,12]); g.strokeStyle='rgba(170,210,255,.95)'; g.lineWidth=5;
  drawPartial(shift(FOOT,slide,lift), eo(seg(t,0.3,1.1))); g.stroke(); g.restore();
  label('すき間', 590, 845, eo(seg(t,0.4,0.8))*(1-seg(t,s2-1.5,s2-1.1)), RED, 50, 'left', '#0d1a2b');
  const ar = seg(t,0.95,1.3)*(1-seg(t,s2-1.6,s2-1.3));
  if(ar>0){ for(const yy of [1000,1060]) arrow(600,yy,760+30*ar,yy,RED,10,ar); label('ずるっ',610,955,ar,RED,64,'left','#0d1a2b'); }
  g.restore();
  const dm = eo(seg(t,s2-0.7,s2-0.2));
  if(dm>0){ const zc=(x,y)=>[860+(x-860)*z, 1060+(y-1060)*z];
    const [ax,ay]=zc(846,1128), [bx,by]=zc(846,1152);
    leader([[ax+10,ay],[ax+150,ay]],dm); leader([[bx+10,by],[bx+150,by]],dm);
    arrow(ax+130,ay-70,ax+130,ay-8,'#fff',4,dm); arrow(bx+130,by+70,bx+130,by+8,'#fff',4,dm);
    label('約7mm', Math.min(ax+118, 870), ay-86, dm, '#fff', 58, 'right', '#0d1a2b'); }   // 右190pxの帯に入れない
  kicker('つま先', 250, eo(seg(t,0.2,0.5)));
  headline(['極厚 約7mm'], 420, eo(seg(t,0.35,0.7)), 116);
  underline(300,780,452,seg(t,0.6,1.0));
  caption(['つま先は約7mmの極厚。','すき間を埋めて、前滑りを抑えます。'], capA(t,d));
}

// ---- かかと／土踏まず：実写の切り抜き＋赤い引き出し線（暗いスタジオ） ----
function sHeel(t, d, mk){
  bgStudio();
  const split = mk[1] - 0.15;
  if(t < split+0.35){
    const a = t<split ? 1 : 1-seg(t,split,split+0.35);
    const s = lerp(1.30,1.22,eo(seg(t,0,split)));
    g.save(); g.globalAlpha=a; g.translate(540,880); g.scale(s,s); g.translate(-905,-1245); g.drawImage(IMG.duo,0,0); g.restore();
    const p=eo(seg(t,0.5,1.3));
    if(p>0){ g.save(); g.globalAlpha=a; g.translate(540,880); g.rotate(-0.52);
      g.strokeStyle=RED; g.lineWidth=12; g.lineCap='round'; g.shadowColor='rgba(214,48,54,.8)'; g.shadowBlur=24;
      g.beginPath(); g.ellipse(0,0,300,200,0,Math.PI*0.05,Math.PI*0.05+Math.PI*1.9*p); g.stroke(); g.restore(); }
    const la=eo(seg(t,1.1,1.5))*a;
    leader([[330,1060],[250,1160],[120,1160]], la); label('深型ヒールカップ',110,1225,la);
    kicker('かかと', 250, eo(seg(t,0.2,0.5))*a);
    headline(['抜けにくい'], 420, eo(seg(t,0.35,0.7))*a, 116);
    underline(330,750,452,seg(t,0.6,1.0)*a);
    caption(['深型ヒールカップで、','かかとが抜けにくい。'], Math.min(capA(t,d), t<split?1:1-seg(t,split,split+0.2)));
  }
  if(t > split){
    const u=t-split, a=eo(seg(u,0,0.4));
    const s=0.56, ox=540-1800*s/2, oy=900-426*s/2 + (1-a)*40;
    g.save(); g.globalAlpha=a; g.drawImage(IMG.side,ox,oy,1800*s,426*s); g.restore();
    const p=eo(seg(u,0.5,1.2));
    if(p>0){ const x1=ox+640*s, x2=ox+1010*s;
      g.save(); g.globalAlpha=a*0.9; const gl=g.createLinearGradient(x1,0,x2,0); gl.addColorStop(0,'rgba(214,48,54,0)'); gl.addColorStop(.5,'rgba(214,48,54,.95)'); gl.addColorStop(1,'rgba(214,48,54,0)');
      g.strokeStyle=gl; g.lineWidth=16; g.lineCap='round'; g.shadowColor=RED; g.shadowBlur=30;
      g.beginPath(); g.moveTo(x1,oy+300*s); g.quadraticCurveTo((x1+x2)/2,oy+230*s,x1+(x2-x1)*p,oy+300*s); g.stroke(); g.restore();
      const la=eo(seg(u,0.9,1.3)), mx=(x1+x2)/2;
      leader([[mx,oy+320*s],[mx,oy+300*s+170],[mx+150,oy+300*s+170]], la); label('TPUシャンク内蔵',mx-170,oy+300*s+240,la); }
    kicker('土踏まず', 250, a);
    headline(['ねじれを抑える'], 420, a, 112);
    underline(250,830,452,seg(u,0.3,0.7));
    caption(['土踏まずには、ねじれを抑える','TPUシャンク。'], Math.min(eo(seg(u,0.05,0.3)), 1-seg(t,d-0.25,d)));
  }
}

// ---- 通気：生成り紙のフラット分解図（2層＋空気の粒） ----
const SOLE = pathPts([['M',0,320],['C',-80,320,-120,270,-120,200],['C',-120,120,-95,40,-100,-40],['C',-105,-140,-140,-220,-120,-280],['C',-100,-330,-40,-350,10,-345],['C',70,-340,120,-300,125,-230],['C',130,-150,115,-80,100,0],['C',90,100,115,200,110,250],['C',100,300,60,320,0,320]]);
function sAir(t, d, mk){
  const s2 = mk[1];
  bgCream();
  const sep = eio(seg(t,0.6,1.6)), cx=520, cyB=1020, cyT=lerp(1000,800,sep), sc=1.25;
  const B=iso(SOLE,cx,cyB,sc), T=iso(SOLE,cx,cyT,sc);
  g.save(); g.fillStyle='rgba(60,40,20,.18)'; g.filter='blur(18px)'; fillPts(shift(B,10,70)); g.fill(); g.restore();
  const R=rnd(11), holes=[]; for(let i=0;i<46;i++) holes.push([R()*220-110, R()*600-300]);
  const HB=holes.map(h=>iso([h],cx,cyB,sc)[0]);
  slab(B, 34, '#8b8f96', '#5d6168', ()=>{ for(const [x,y] of HB){ g.fillStyle='#c9352f'; g.beginPath(); g.ellipse(x,y,9,5,0,0,7); g.fill(); g.fillStyle='rgba(0,0,0,.45)'; g.beginPath(); g.ellipse(x,y+1,5,3,0,0,7); g.fill(); } });
  if(t>1.0){ HB.forEach(([hx,hy],i)=>{ for(let k=0;k<2;k++){
      const ph=((t-1.0)*0.9 + i*0.137 + k*0.5)%1; const y=hy-ph*520, x=hx+Math.sin(ph*6+i)*14;
      const al=Math.sin(ph*Math.PI)*0.85*seg(t,1.0,1.6)*(1-seg(t,d-0.4,d));
      g.fillStyle=`rgba(255,255,255,${al})`; g.beginPath(); g.arc(x,y,7+4*Math.sin(i),0,7); g.fill();
      g.strokeStyle=`rgba(90,140,200,${al*0.8})`; g.lineWidth=2; g.stroke(); } }); }
  slab(T, 22, '#1c1c20', '#0e0e10', ()=>{ g.strokeStyle='rgba(255,255,255,.07)'; g.lineWidth=2;
      for(let k=-1200;k<1200;k+=14){ g.beginPath(); g.moveTo(k,0); g.lineTo(k+900,1920); g.stroke(); g.beginPath(); g.moveTo(k+900,0); g.lineTo(k,1920); g.stroke(); }
      const R2=rnd(5); for(let i=0;i<22;i++){ const q=iso([[R2()*120-60,-120+R2()*160]],cx,cyT,sc)[0]; g.fillStyle=RED; g.beginPath(); g.ellipse(q[0],q[1],6,3.5,0,0,7); g.fill(); } });
  const l1=eo(seg(t,0.9,1.3)), l2=eo(seg(t,s2-0.1,s2+0.3));
  leader([[cx+60,cyT-30],[cx+130,cyT-150],[cx+300,cyT-150]], l1, INK); label('肌面：3Dメッシュ',cx-90,cyT-175,l1,INK,48);
  leader([[cx-120,cyB+50],[cx-200,cyB+170],[cx+80,cyB+170]], l2, INK); label('通気穴つき 高密度EVA',cx-330,cyB+235,l2,INK,48);
  kicker('通気', 250, eo(seg(t,0.2,0.5)));
  headline(['ムレにも配慮'], 420, eo(seg(t,0.35,0.7)), 116);
  underline(270,810,452,seg(t,0.6,1.0));
  caption(['肌に当たる面は3Dメッシュ。','通気穴つきEVAで、ムレにも配慮。'], capA(t,d));
}

// ---- サイズ：クレヨンの手描き（線が揺れる）＋はさみ ----
function sSize(t, d, mk){
  const s2 = mk[1];
  bgKraft();
  const boil=Math.floor(t*8), cx=270, cy=900;
  const S = scalePts(SOLE,cx,cy,1.0);
  g.fillStyle='rgba(40,30,25,.10)'; fillPts(S); g.fill();
  crayon(S, '#2a211b', 12, 100+boil, eo(seg(t,0,0.9)));
  const cut=eo(seg(t,s2-0.2,s2+0.3));
  g.save(); fillPts(S); g.clip(); g.setLineDash([18,14]);
  [0,34,68].forEach((o,i)=>{ g.strokeStyle=i===1?RED:'rgba(214,48,54,.6)'; g.lineWidth=6; g.globalAlpha=cut; g.beginPath(); g.ellipse(cx+3,cy-150,150,190-o,0,Math.PI*1.05,Math.PI*1.95); g.stroke(); });
  g.restore(); g.globalAlpha=1;
  const sp=seg(t,s2+0.3,s2+1.6);
  if(sp>0 && t<s2+2.2){ const ang=Math.PI*1.05+Math.PI*0.9*eio(sp); const x=cx+3+150*Math.cos(ang), y=cy-150+(190-34)*Math.sin(ang);
    g.save(); g.translate(x,y); g.rotate(ang+Math.PI/2); const open=Math.abs(Math.sin(t*14))*0.35;
    g.strokeStyle='#222'; g.lineWidth=7; g.fillStyle='#d9d9d9';
    for(const sgn of [1,-1]){ g.save(); g.rotate(sgn*open); g.beginPath(); g.moveTo(0,0); g.lineTo(70,sgn*6); g.lineTo(0,sgn*14); g.closePath(); g.fill(); g.stroke(); g.beginPath(); g.arc(-34,sgn*16,17,0,7); g.stroke(); g.restore(); }
    g.restore(); }
  const fall=seg(t,s2+1.65,s2+2.4);
  if(fall>0){ g.save(); g.beginPath(); g.ellipse(cx+3,cy-150,150,190-34,0,Math.PI,Math.PI*2); g.lineTo(cx+3+150,cy-150); g.closePath(); g.clip();
    g.translate(0, fall*fall*260); g.globalAlpha=1-fall; g.fillStyle='rgba(214,48,54,.25)'; g.fillRect(cx-160,cy-360,330,220); g.restore(); }
  [['S','23.5〜26.0cm'],['M','25.0〜27.5cm'],['L','26.5〜29.5cm']].forEach(([k,v],i)=>{ const p=back(seg(t,0.4+i*0.25,0.8+i*0.25)); if(p<=0) return;
    const y=660+i*170; const fs=fitText(v,215,40,800); const tw=g.measureText(v).width, cw=40+80+tw+34;
    g.save(); g.translate(545,y); g.scale(p,p);
    g.fillStyle='#fffaf0'; g.strokeStyle='#2a211b'; g.lineWidth=5; roundRect(-40,-60,cw,120,24); g.fill(); g.stroke();
    g.fillStyle=RED; g.beginPath(); g.arc(20,0,44,0,7); g.fill();
    g.fillStyle='#fff'; g.font=font(60,900); g.textAlign='center'; g.textBaseline='middle'; g.fillText(k,20,4);
    g.fillStyle='#2a211b'; g.font=font(fs,800); g.textAlign='left'; g.fillText(v,80,4); g.restore(); });
  kicker('サイズ', 250, eo(seg(t,0.2,0.5)));
  headline(['S・M・L'], 420, eo(seg(t,0.35,0.7)), 120);
  underline(330,750,452,seg(t,0.6,1.0));
  caption(['サイズはS・M・L。','カットラインで調整できます。'], capA(t,d));
}

// ---- 締め：AI背景（夕方の田んぼ）＋実物のインソール・パッケージ＋実物ロゴ ----
function sEnd(t, d){
  coverImg('bg', 1+0.06*eio(seg(t,0,d)));
  topShade(860, .6);
  const pa=eo(seg(t,0.2,0.9));
  contactShadow(560,1360,300,46,0.55*pa);
  const pk=eo(seg(t,0.5,1.2)); drawImg('pkg', 310, 1350-250+(1-pk)*60, 500, pk, -0.06);
  drawImg('duo', 590, 1370-280+(1-pa)*80, 560, pa);
  sweep('duo', 590, 1090, 560, seg(t,1.4,2.3));
  drawImg('logo', 540, 190, 160, eo(seg(t,0.1,0.6)));
  kicker('好評発売中', 360, eo(seg(t,0.3,0.6)));
  headline(['長靴・ウェーダー','専用インソール'], 500, eo(seg(t,0.45,0.85)), 96);
  label('Amazon・楽天で販売中', 540, 700, eo(seg(t,0.9,1.3)), '#fff', 50, 'center', 'rgba(0,0,0,.8)');
  underline(290,790,722,seg(t,1.0,1.4));
}

window.SCENES = {hook:sHook, toe:sToe, heel:sHeel, air:sAir, size:sSize, end:sEnd};
window.TRANSITIONS = {toe:'diag', heel:'iris', air:'up', size:'left', end:'fade'};
