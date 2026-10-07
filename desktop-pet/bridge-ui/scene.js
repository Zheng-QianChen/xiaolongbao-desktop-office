// Scene arrangement is local presentation state, never a task/notification update.
const WIDTH=720, HEIGHT=460, STORAGE='wang-bun-scene-v1';
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
export function createScene(canvas,{onChange=()=>{}}={}){
  let mode='free', positions={}, selected=null, drag=null, records=[],locked=false;
  const scratch=document.createElement('canvas');scratch.width=321;scratch.height=255;
  const pick=scratch.getContext('2d',{willReadFrequently:true});
  try{const saved=JSON.parse(localStorage.getItem(STORAGE));
    if(saved?.mode==='house')mode='house';
    if(saved?.positions&&typeof saved.positions==='object'){
      for(const [key,p] of Object.entries(saved.positions).slice(0,512))
        if(p&&Number.isFinite(p.x)&&Number.isFinite(p.y))positions[key]={x:p.x,y:p.y};
    }
  }catch{}
  function save(){try{localStorage.setItem(STORAGE,JSON.stringify({mode,positions}));}catch{}}
  function bound(p,scale){return{x:clamp(p.x,0,WIDTH-321*scale),y:clamp(p.y,35,HEIGHT-255*scale-12)};}
  function point(e){const b=canvas.getBoundingClientRect();return{x:(e.clientX-b.left)*WIDTH/b.width,y:(e.clientY-b.top)*HEIGHT/b.height};}
  function hit(p){
    for(const r of [...records].reverse()){
      const x=(p.x-r.x)/r.scale,y=(p.y-r.y)/r.scale;
      if(x<0||y<0||x>=321||y>=255)continue;
      pick.clearRect(0,0,321,255);r.paint(pick);
      if(pick.getImageData(Math.floor(x),Math.floor(y),1,1).data[3]>40)return r;
    }
  }
  function finish(cancel=false){
    if(!drag)return;
    if(cancel){if(drag.previous)positions[drag.key]=drag.previous;else delete positions[drag.key];}
    const pointer=drag.pointer;drag=null;
    if(canvas.hasPointerCapture(pointer))canvas.releasePointerCapture(pointer);
    canvas.classList.remove('dragging');save();onChange();
  }
  canvas.addEventListener('pointerdown',e=>{
    if(locked||mode!=='free'||e.button!==0||drag)return;
    const p=point(e),r=hit(p);if(!r)return;
    selected=r.key;drag={key:r.key,pointer:e.pointerId,dx:p.x-r.x,dy:p.y-r.y,scale:r.scale,previous:positions[r.key]&&{...positions[r.key]}};
    canvas.setPointerCapture(e.pointerId);canvas.classList.add('dragging');canvas.focus();e.preventDefault();onChange();
  });
  canvas.addEventListener('pointermove',e=>{
    const p=point(e);
    if(drag&&drag.pointer===e.pointerId){positions[drag.key]=bound({x:p.x-drag.dx,y:p.y-drag.dy},drag.scale);onChange();}
    else canvas.style.cursor=!locked&&mode==='free'&&hit(p)?'grab':'default';
  });
  canvas.addEventListener('pointerup',e=>{if(drag?.pointer===e.pointerId)finish();});
  canvas.addEventListener('pointercancel',()=>finish(true));
  canvas.addEventListener('lostpointercapture',()=>finish(true));
  canvas.addEventListener('keydown',e=>{
    if(e.key==='Escape'){finish(true);return;}
    const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];
    const r=records.find(r=>r.key===selected);
    if(locked||mode!=='free'||!delta||!r||drag)return;
    const step=e.shiftKey?20:5,p=positions[r.key]??r;positions[r.key]=bound({x:p.x+delta[0]*step,y:p.y+delta[1]*step},r.scale);
    e.preventDefault();save();onChange();
  });
  return{
    get mode(){return mode;},get selected(){return selected;},
    taskAt(event){return hit(point(event))?.key;},
    get locked(){return locked;},
    setLocked(value){if(locked===Boolean(value))return;finish(true);locked=Boolean(value);canvas.style.cursor='default';onChange();},
    setMode(value){finish(true);mode=value==='house'?'house':'free';canvas.style.cursor='default';save();onChange();},
    reset(){if(locked)return;finish(true);positions={};selected=null;save();onChange();},
    cancel(){finish(true);selected=null;},
    leader(){return mode==='free'?bound(positions.leader??{x:16,y:168},1):{x:10,y:188};},
    position(key,fallback,scale=1/3){return mode==='free'?bound(positions[key]??fallback,scale):fallback;},
    setRecords(next){records=next;},
    selection(ctx,r){if(mode!=='free'||r.key!==selected)return;
      ctx.save();ctx.strokeStyle='#2f827b';ctx.lineWidth=2;ctx.setLineDash([4,4]);ctx.beginPath();
      ctx.ellipse(r.x+160*r.scale,r.y+235*r.scale,112*r.scale,17*r.scale,0,0,Math.PI*2);ctx.stroke();ctx.restore();
    },
  };
}

// Original miniature cutaway house, painted as UI geometry; pet artwork stays shared.
export function drawHouse(c){
  const rect=(x,y,w,h,color)=>{c.fillStyle=color;c.fillRect(x,y,w,h);};
  const poly=(points,color)=>{c.fillStyle=color;c.beginPath();points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.closePath();c.fill();};
  c.save();
  c.fillStyle='#dce3cf';c.beginPath();c.ellipse(490,438,220,14,0,0,Math.PI*2);c.fill();
  // Timber outline, rear walls, and two warm wooden floors.
  rect(343,112,358,308,'#6e6550');rect(351,115,342,295,'#eee3c7');
  for(let x=359;x<690;x+=22)rect(x,119,1,286,'#e0d2b4');
  rect(351,245,342,18,'#94724f');rect(351,245,342,5,'#c2a071');
  rect(337,409,370,19,'#997451');rect(337,409,370,5,'#d0ac79');rect(330,428,384,7,'#6e6550');
  for(let x=358;x<695;x+=42){rect(x,251,24,1,'#b79165');rect(x,417,24,1,'#bf966a');}
  // Windows reveal a quiet blue sky, split by wooden mullions.
  for(const y of [134,283])for(const x of [373,482,591]){
    rect(x-4,y-4,72,53,'#baa17a');rect(x,y,64,45,'#d2e5dd');
    rect(x+5,y+6,19,3,'#f5f4de');rect(x+31,y,3,45,'#f8efdb');rect(x,y+22,64,3,'#f8efdb');
    rect(x-7,y+45,78,5,'#9c7a53');
  }
  // Chimney and a steep green tiled roof, with a small round loft window.
  rect(627,43,28,53,'#9e8262');rect(621,38,39,9,'#705f4c');rect(636,49,17,3,'#c4a587');rect(628,62,17,3,'#c4a587');
  poly([[325,118],[520,24],[718,118]],'#4e6658');poly([[336,109],[520,32],[708,109]],'#8a9d76');
  for(let row=0;row<4;row++){const y=58+row*14,half=(y-32)*2.31;rect(520-half,y,half*2,3,'#708665');
    for(let x=520-half+16;x<520+half;x+=30)rect(x,y+3,2,9,'#78916a');}
  rect(326,111,389,10,'#5c715c');rect(331,121,379,5,'#c4ab80');
  c.fillStyle='#f8eac3';c.beginPath();c.arc(520,79,18,0,Math.PI*2);c.fill();
  c.strokeStyle='#576652';c.lineWidth=4;c.stroke();rect(518,63,4,32,'#576652');rect(504,77,32,4,'#576652');
  // Porch light and nameplate.
  rect(322,153,4,48,'#79644d');rect(310,152,25,4,'#79644d');rect(313,158,18,21,'#e9c775');rect(310,179,24,4,'#79644d');
  rect(458,112,126,27,'#685f4b');rect(461,115,120,21,'#f1e3bf');
  c.fillStyle='#53644f';c.font='bold 12px "Microsoft YaHei UI",sans-serif';c.textAlign='center';c.fillText('望 包 小 屋',521,130);
  // Low desks are below the actors; paws and laptops remain visible.
  for(const y of [212,365])for(const x of [363,473,583]){
    rect(x+6,y+9,5,23,'#937354');rect(x+87,y+9,5,23,'#937354');
    rect(x,y,99,9,'#b28c5e');rect(x,y,99,3,'#d2b07a');
  }
  // A tiny plant beside the porch and two stacked books.
  rect(299,400,24,23,'#bc8b65');rect(296,397,30,6,'#d7a579');rect(310,366,3,32,'#708967');
  poly([[311,386],[290,376],[292,365],[309,374]],'#92a37a');poly([[312,379],[330,363],[337,367],[326,381]],'#758f6c');
  rect(355,396,35,6,'#8eab9a');rect(359,389,29,7,'#c3a37c');
  c.restore();
}
