import {lidGeometry,drawQuad,faceCenter,statusAnchor} from './geometry.js?v=8';
import {createLayerTurn} from './layer-turn.js?v=8';
export function createRenderer(rig,images,animator,hidden=new Set(),spatialData=null){
  const layerTurn=createLayerTurn(rig,images,animator,hidden);
  const palette=['#096c78','#098593','#10a4ad','#18bec5','#43d2d7','#7be2e4','#49c4ca','#25a8b5'];
  function bodyMatrix(c,p,breath=true){
    c.translate(p.body.x,p.body.y);c.translate(160,225);c.rotate(p.body.rotation);
    c.scale(p.body.sx,p.body.sy);c.translate(-160,-225);
    if(breath){c.translate(160,219);c.scale(1+p.breath*.003,1+p.breath*.008);c.translate(-160,-219);}
  }
  function magicEyes(c,p,r){
    if(!p.magic)return;
    c.save();c.globalAlpha*=p.magic;
    // Opaque printed lenses: eye-open and blink parameters never reach this paint.
    for(const [x,color] of [[r.x+25,'#efc679'],[r.x+80,'#8c8295']]){
      c.fillStyle='#fbfaf4';c.beginPath();c.ellipse(x,r.y+22,23,17,0,0,Math.PI*2);c.fill();
      c.fillStyle=color;c.strokeStyle='#48444a';c.lineWidth=2;c.beginPath();c.ellipse(x,r.y+23,12,14,0,0,Math.PI*2);c.fill();c.stroke();
    }
    // Frame is above the printed decal, exactly as on a physical novelty pair.
    c.drawImage(images.glasses,r.x,r.y,r.w,r.h);c.restore();
  }
  function drawBubble(c,text='!',scale=1){
    const anchor=statusAnchor(scale),small=scale<.6,exclaim=text==='!',w=exclaim?(small?84:72):Math.max(168,Math.min(248,text.length*12+24)),h=exclaim?57:43;
    const top=anchor.y-(small?108:88),left=anchor.x-w/2;
    // Reference-shaped stepped balloon; every pointer ends at the crown folds.
    c.save();c.translate(left,top);c.fillStyle='#fffdf8';c.strokeStyle='#39302c';c.lineWidth=3;c.lineJoin='miter';
    c.beginPath();c.moveTo(12,0);c.lineTo(w-12,0);c.lineTo(w-12,5);c.lineTo(w-5,5);c.lineTo(w-5,12);c.lineTo(w,12);c.lineTo(w,h-12);c.lineTo(w-5,h-12);c.lineTo(w-5,h-5);c.lineTo(w-12,h-5);c.lineTo(w-12,h);c.lineTo(w/2+9,h);c.lineTo(w/2,anchor.y-top-4);c.lineTo(w/2-9,h);c.lineTo(12,h);c.lineTo(12,h-5);c.lineTo(5,h-5);c.lineTo(5,h-12);c.lineTo(0,h-12);c.lineTo(0,12);c.lineTo(5,12);c.lineTo(5,5);c.lineTo(12,5);c.closePath();c.fill();c.stroke();
    if(exclaim){c.fillStyle='#cb5148';c.fillRect(w/2-4,9,8,25);c.fillRect(w/2-4,40,8,7);}
    else{c.fillStyle='#48433f';c.textAlign='center';c.textBaseline='middle';c.font='12px "Microsoft YaHei UI"';c.fillText(text,w/2,h/2,w-15);}
    c.restore();
  }
  function skillReady(c,p,anchor){
    if(!hidden.has('skill_ready')){
    c.save();c.translate(anchor.x,anchor.y-29);
    c.beginPath();c.moveTo(0,-22);c.lineTo(22,0);c.lineTo(0,22);c.lineTo(-22,0);c.closePath();c.clip();
    c.drawImage(images.skill_ready,-22,-22,44,44);
    c.restore();
    }
    if(hidden.has('skill_'+p.skill))return;
    c.save();c.fillStyle='#302f34';c.fillRect(215,164,68,68);
    c.drawImage(images['skill_'+p.skill],217,166,64,64);c.restore();
  }
  const ghostMasks=Object.fromEntries(['horn_left','horn_right'].map(id=>{const q=document.createElement('canvas');q.width=images[id].width;q.height=images[id].height;const d=q.getContext('2d');d.drawImage(images[id],0,0);d.globalCompositeOperation='source-in';d.fillStyle='#9dbbc0';d.fillRect(0,0,q.width,q.height);return[id,q];}));
  function soul(c,p){
    if(p.soul<=0)return;
    const x=164+Math.sin(p.t*2)*4,y=205-p.soul*161;
    c.save();c.translate(x,y);c.scale(.3+.7*p.soul,.2+.8*p.soul);c.globalAlpha*=.25+.65*p.soul;
    c.fillStyle='#dfedef';c.strokeStyle='#91acb0';c.lineWidth=1.5;c.beginPath();
    c.moveTo(-26,11);c.bezierCurveTo(-33,-31,33,-31,26,11);c.quadraticCurveTo(22,30,5,39);c.quadraticCurveTo(9,23,-1,27);c.quadraticCurveTo(-10,34,-15,22);c.quadraticCurveTo(-26,27,-26,11);c.fill();c.stroke();
    for(const [id,hx] of [['horn_left',-31],['horn_right',13]])c.drawImage(ghostMasks[id],hx,-36,22,27);
    for(const ex of [-17,5]){c.fillStyle='#a8c2c6';c.beginPath();c.moveTo(ex,-5);c.lineTo(ex+13,-5);c.quadraticCurveTo(ex+13,12,ex+6.5,12);c.quadraticCurveTo(ex,12,ex,-5);c.fill();c.strokeStyle='#779ba2';c.lineWidth=2;c.beginPath();c.moveTo(ex-1,-5);c.lineTo(ex+14,-5);c.stroke();}
    c.restore();
    if(p.wifi){
      c.save();c.translate(x+55,y-2);c.globalAlpha*=p.wifi;c.strokeStyle='#839898';c.lineWidth=3;c.lineCap='round';
      for(const radius of [10,18,26]){c.beginPath();c.arc(0,14,radius,-Math.PI*.79,-Math.PI*.21);c.stroke();}
      c.fillStyle='#839898';c.beginPath();c.arc(0,14,2,0,Math.PI*2);c.fill();c.beginPath();c.moveTo(-22,-13);c.lineTo(19,20);c.stroke();c.restore();
    }
  }
  // The paws are fixed to the cat's torso. Only the chess stones travel.
  const catUnit=document.createElement('canvas');catUnit.width=67;catUnit.height=79;
  {const d=catUnit.getContext('2d');d.imageSmoothingEnabled=false;d.drawImage(images.cat_body,0,0,67,79);d.drawImage(images.cat_paw,40,61,21,13);}
  // Centered perspective: both long edges stay horizontal and the two sides mirror.
  // A shared depth divide also makes distant grid rows progressively closer.
  const boardNearWidth=100,boardFarWidth=58,boardDepth=23,boardPerspective=boardNearWidth/boardFarWidth-1;
  const boardPoint=(u,v)=>{const perspective=1+boardPerspective*v;return [100+boardNearWidth*(u-.5)/perspective,213-boardDepth*(1+boardPerspective)*v/perspective];};
  const gridPoint=(col,row)=>boardPoint(.07+.86*col/18,.10+.80*row/18);
  const stonePositions=[[4,6],[12,11],[8,3],[15,7],[7,13],[12,1]].map(([col,row])=>gridPoint(col,row));
  const stoneBowls=[{x:187,y:238,white:false},{x:39,y:235,white:true}];
  const stoneLandsAt=.80;
  function stone(c,x,y,white){
    c.save();c.lineWidth=1;c.strokeStyle=white?'#9d9484':'#29242d';
    c.fillStyle=white?'#cec5b3':'#25212a';c.beginPath();c.ellipse(x,y+1.4,4.7,1.1,0,0,Math.PI*2);c.fill();c.stroke();
    c.fillStyle=white?'#fffaf0':'#514953';c.beginPath();c.ellipse(x,y-.3,4.7,1.1,0,0,Math.PI*2);c.fill();c.stroke();
    c.fillStyle=white?'#fffef9':'#887e88';c.fillRect(Math.round(x-2),Math.round(y-1),3,1);c.restore();
  }
  function boardKick(phase){
    if(phase<stoneLandsAt)return [0,0];const k=(phase-stoneLandsAt)/(1-stoneLandsAt),decay=(1-k)**2;
    return [Math.sin(k*Math.PI*2)*.8*decay,Math.cos(k*Math.PI*3)*2.7*decay];
  }
  function chessboard(c){
    const A=boardPoint(0,0),B=boardPoint(1,0),C=boardPoint(1,1),D=boardPoint(0,1),lower=p=>[p[0],p[1]+14];
    const polygon=(points,fill)=>{c.fillStyle=fill;c.strokeStyle='#554837';c.lineWidth=1.2;c.beginPath();points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.closePath();c.fill();c.stroke();};
    c.save();c.fillStyle='#3c302323';c.beginPath();c.ellipse(100,233,51,6,0,0,Math.PI*2);c.fill();
    // Mirrored feet and a level front wall retain volume without a sideways yaw.
    for(const [u,v] of [[.1,.86],[.9,.86],[.08,.08],[.92,.08]]){const [x,y]=boardPoint(u,v),s=1/(1+boardPerspective*v);polygon([[x-3.5*s,y+12*s],[x+3.5*s,y+12*s],[x+3.5*s,y+21*s],[x-3.5*s,y+21*s]],'#866343');c.fillStyle='#c39764';c.fillRect(x-2*s,y+13*s,2*s,7*s);}
    polygon([A,B,lower(B),lower(A)],'#c49b66');
    polygon([A,B,C,D],'#efd29b');
    polygon([[A[0],A[1]+11],[B[0],B[1]+11],lower(B),lower(A)],'#99754e');
    c.strokeStyle='#f9e5bd';c.lineWidth=1.5;c.beginPath();c.moveTo(...D);c.lineTo(...A);c.lineTo(...B);c.lineTo(...C);c.stroke();
    const opacity=c.globalAlpha;c.strokeStyle='#a17e50';c.lineWidth=.55;c.globalAlpha*=.67;
    for(let i=0;i<19;i++){c.beginPath();c.moveTo(...gridPoint(i,0));c.lineTo(...gridPoint(i,18));c.moveTo(...gridPoint(0,i));c.lineTo(...gridPoint(18,i));c.stroke();}
    c.globalAlpha=opacity;c.fillStyle='#7a5a39';for(const col of [3,9,15])for(const row of [3,9,15]){const [x,y]=gridPoint(col,row);c.fillRect(Math.round(x),Math.round(y),1.4,1);}
    polygon([[64,216],[136,216],[136,223],[64,223]],'#ad8254');
    c.strokeStyle='#e1bb80';c.lineWidth=1;c.beginPath();c.moveTo(67,218);c.lineTo(133,218);c.stroke();
    c.restore();
  }
  function impact(c,x,y,phase){
    const k=(phase-stoneLandsAt)/(1-stoneLandsAt);if(k<0||k>1)return;
    c.save();c.globalAlpha*=1-k;
    // First-frame star and expanding plane-aligned ring, followed by a few chunky sparks.
    if(k<.38){c.fillStyle='#fff5cc';c.beginPath();c.moveTo(x-16,y);c.lineTo(x-4,y-3);c.lineTo(x,y-13);c.lineTo(x+4,y-3);c.lineTo(x+16,y);c.lineTo(x+4,y+3);c.lineTo(x,y+6);c.lineTo(x-4,y+3);c.closePath();c.fill();}
    c.strokeStyle='#c19544';c.lineWidth=2.2*(1-k)+.7;c.beginPath();c.ellipse(x,y,10+24*k,2.3+5.5*k,0,0,Math.PI*2);c.stroke();
    c.strokeStyle='#fff5cb';c.lineWidth=1.1;c.beginPath();c.ellipse(x,y,7+20*k,1.6+4.6*k,0,0,Math.PI*2);c.stroke();
    for(let i=0;i<6;i++){const a=i*Math.PI/3,px=x+Math.cos(a)*(9+25*k),py=y+Math.sin(a)*(3+6*k)-9*Math.sin(Math.PI*k);c.fillStyle=i%2?'#b99b65':'#ecce83';c.fillRect(Math.round(px),Math.round(py),2+(i%2),2);}
    c.restore();
  }
  function bowl(c,b,front=false){
    const {x,y,white}=b;c.save();c.lineWidth=1.2;c.strokeStyle='#72533b';
    if(!front){
      // A low wooden Go bowl, set just in front of each player's resting paws.
      c.fillStyle='#b58c5e';c.beginPath();c.moveTo(x-15,y);c.lineTo(x-13,y+10);c.lineTo(x-8,y+14);c.lineTo(x+8,y+14);c.lineTo(x+13,y+10);c.lineTo(x+15,y);c.closePath();c.fill();c.stroke();
      c.fillStyle='#e0bb86';c.beginPath();c.ellipse(x,y,15,5.5,0,0,Math.PI*2);c.fill();c.stroke();
      c.fillStyle='#765b42';c.beginPath();c.ellipse(x,y,12.5,3.8,0,0,Math.PI*2);c.fill();
      for(const [dx,dy] of [[-6,-.5],[6,0],[-3,2.5]]){c.save();c.translate(x+dx,y+dy);c.scale(.7,.7);stone(c,0,0,white);c.restore();}
    }else{
      // The front wall occludes the emerging stone until it clears the opening.
      c.fillStyle='#b58c5e';c.beginPath();c.moveTo(x-15,y);c.bezierCurveTo(x-14,y+7,x+14,y+7,x+15,y);c.lineTo(x+13,y+10);c.lineTo(x+8,y+14);c.lineTo(x-8,y+14);c.lineTo(x-13,y+10);c.closePath();c.fill();c.stroke();
      c.strokeStyle='#e0bb86';c.beginPath();c.moveTo(x-10,y+8);c.lineTo(x+10,y+8);c.stroke();
    }
    c.restore();
  }
  function flyingStone(turn,phase){
    const b=stoneBowls[turn%2],[tx,ty]=stonePositions[turn];
    const ease=v=>{const u=Math.max(0,Math.min(1,v));return u*u*(3-2*u);};
    const lift=ease(phase/.20),travel=ease((phase-.28)/.25),drop=Math.max(0,Math.min(1,(phase-.63)/.17));
    const fromY=b.y+3-26*lift;
    return {x:b.x+(tx-b.x)*travel,y:fromY+(ty-34-fromY)*travel-12*Math.sin(Math.PI*travel)+34*drop**2.7,white:b.white,drop};
  }
  function chess(c,p,foreground=false){
    if(!p.cat)return;const u=p.cat,turn=Math.floor(p.chess/1.2)%6,phase=(p.chess%1.2)/1.2;
    c.save();c.globalAlpha*=u;
    if(!foreground){
      c.save();c.translate(...boardKick(phase));chessboard(c);
      for(let i=0;i<turn+(phase>=stoneLandsAt?1:0);i++)stone(c,...stonePositions[i],i%2===1);
      c.restore();
      if(!hidden.has('cat_body')){const bob=Math.sin(p.t*2)*.35;c.drawImage(catUnit,-13-20*(1-u),146+bob,67,79);}
    }else{
      for(const b of stoneBowls)bowl(c,b);
      const [tx,ty]=stonePositions[turn],{x,y,white,drop}=flyingStone(turn,phase);
      if(p.t>=2&&phase<stoneLandsAt){
        c.save();c.globalAlpha*=Math.min(1,phase/.06);c.strokeStyle='#d4b675';c.lineWidth=1;
        c.beginPath();c.ellipse(x,y,9,5,0,0,Math.PI*2);c.stroke();
        for(let i=1;i<=4;i++){const trail=flyingStone(turn,Math.max(0,phase-i*.035));c.fillStyle=i%2?'#d3b879':'#a9c4be';c.globalAlpha=(5-i)*.16*u;c.fillRect(Math.round(trail.x)-1,Math.round(trail.y)-1,2,2);}
        c.globalAlpha=u;
        if(drop>.15){c.fillStyle='#e5c374';c.fillRect(Math.round(x)-1,Math.round(y)-16,2,12);c.fillStyle='#fff5d1';c.fillRect(Math.round(x),Math.round(y)-12,1,10);c.save();c.translate(x,y);c.scale(.9,1+.8*drop);stone(c,0,0,white);c.restore();}
        else stone(c,x,y,white);c.restore();
      }else if(phase>=stoneLandsAt){
        c.save();c.translate(...boardKick(phase));impact(c,tx,ty,phase);c.restore();
      }
      for(const b of stoneBowls)bowl(c,b,true);
    }
    c.restore();
  }
  function drawModel(c,p,{x=0,y=0,scale=1,alpha=1,only=null,effects=true,companion=true}={}){
    c.save();c.translate(x,y);c.scale(scale,scale);c.globalAlpha*=alpha;c.imageSmoothingEnabled=false;
    const playChess=companion&&p.actorRole==='leader'&&!only;
    if(playChess)chess(c,p);
    const blend=Math.abs(p.yaw)>.00001||p.prone>.00001?1:0;
    const ordered=rig.layers.map(layer=>({layer,r:animator.transformFor(layer,p)})).sort((a,b)=>a.r.z-b.r.z);
    for(const {layer,r} of ordered){
      if(layer.id==='body'&&blend&&!only){c.save();bodyMatrix(c,p);c.globalAlpha*=blend;c.drawImage(layerTurn.render(p),0,0);c.restore();}
      if(hidden.has(layer.id)||!r.visible||only&&!only.includes(layer.id))continue;
      c.save();c.globalAlpha*=Math.round((layer.opacity??1)*255)/255*r.alpha;
      const fixed=['desk','closed','cup'].includes(layer.group)||layer.group==='paw'&&p.desk||layer.id==='glasses'&&p.glasses?.mode==='held';
      if(!['desk','closed','cup','work','effect','alternate','companion'].includes(layer.group))c.globalAlpha*=1-blend;
      if(!fixed)bodyMatrix(c,p);
      if(r.rotation){const [px,py]=r.pivot||layer.pivot||[r.x+r.w/2,r.y+r.h*.7];c.translate(px,py);c.rotate(r.rotation);c.translate(-px,-py);}
      if(layer.id==='laptop_screen'||layer.id==='laptop_keyboard'){
        const geometry=lidGeometry(p.open,p.dropY,p.deskX,p.deskY),screen=layer.id==='laptop_screen';
        const lower=screen?geometry.quad:geometry.baseBottom,upper=screen?geometry.lidOuter:geometry.base;
        const polygon=(points,fill)=>{c.fillStyle=fill;c.strokeStyle='#514c58';c.lineWidth=1.1;c.beginPath();points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.closePath();c.fill();c.stroke();};
        // Solid side walls stay connected while the lid rotates around its hinge.
        polygon(lower,'#625e6b');
        for(let i=0;i<4;i++)polygon([lower[i],lower[(i+1)%4],upper[(i+1)%4],upper[i]],i%2?'#77737e':'#625e6b');
        polygon(upper,'#918d98');
        drawQuad(c,images[layer.id],screen?[[1,1],[82,18],[94,85],[16,66]]:[[0,16],[53,0],[136,21],[85,43]],upper);
        c.strokeStyle='#514c58';c.lineWidth=1.3;c.beginPath();upper.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.closePath();c.stroke();
      }
      else c.drawImage(images[layer.id],r.x,r.y,r.w,r.h);
      if(r.extraCross){const e=r.extraCross;c.globalAlpha*=e.alpha;c.drawImage(images.side_cross,e.x,e.y,e.w,e.h);}
      if(layer.id==='glasses')magicEyes(c,p,r);
      c.restore();
    }
    if(playChess)chess(c,p,true);
    if(effects&&!only){
      c.save();bodyMatrix(c,p);
      if(p.flower){
        c.save();c.translate(faceCenter,23);c.rotate(p.t*2.2);c.lineWidth=4.6;c.lineCap='round';
        for(let i=0;i<8;i++){const a=i*Math.PI/4;c.strokeStyle=palette[i];c.beginPath();c.moveTo(Math.cos(a)*7,Math.sin(a)*7);c.lineTo(Math.cos(a)*18,Math.sin(a)*18);c.stroke();}c.restore();
      }
      if(p.alert){
        drawBubble(c,p.alert==='!'?'!':`[${p.agentName}] 等候确认`,scale);
      }
      if(p.skill)skillReady(c,p,statusAnchor(scale));
      c.restore();
      soul(c,p);
    }
    c.restore();
  }
  return {drawModel,drawBubble,layerTurn,catUnit};
}
