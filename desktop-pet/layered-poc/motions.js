// All character poses use the same rig. Times are sampled on a 10/12 fps grid.
export const CLIPS=[
  ['idle','休息待机',4,true,'轻呼吸、摇尾与偶尔眨眼'],
  ['entry','进入工作',3,false,'电脑落下 → 开盖 → 戴眼镜 → 落爪'],
  ['typing','持续工作',12,true,'交替敲键盘，加载花旋转，随机喝水和眨眼'],
  ['blink','工作眨眼',1,true,'双眼同步闭合，保持异色眼与水平眼睑'],
  ['drink','喝水',3.5,false,'停下黑爪，端杯、喝水、放杯，再回键盘'],
  ['waiting','等待确认',4,true,'停止打字，用漫画气泡显示当前任务等候确认'],
  ['closing','完成收工',3.5,false,'合电脑、摘下透明眼镜，放好后准备离开'],
  ['walk','走向大包子',3,false,'先转向大包子，再四爪交替走；抵达时转回跟随朝向'],
  ['following','跟随待机',4,true,'抵达大包子身后，停步呼吸'],
  ['return','返回工位',4.5,false,'完整转身 → 背对镜头返回 → 抵达工位后转回电脑'],
  ['unread','未读提醒',20/12,true,'感叹号、蓄力、抛物线腾空与落地挤压'],
  ['read','已读落稳 · 猫咪下棋',8,false,'落地收稳 → 猫咪对坐 → 从棋盒隔空取子 → 悬停蓄力、加速落子'],
  ['failed','任务失败',3,true,'技能就绪！每次失败抽一次：天下劫 80% / 连星 15% / 取势 5%'],
  ['disconnected','连接断开',5,false,'推开电脑 → 软软地摊成一滩 → 灵魂冒出 → Wi-Fi 断开'],
  ['easter','眼镜彩蛋',4.5,false,'换上画着睁大眼睛的镜片；摘下来时，印在眼镜上的眼睛保持不动'],
].map(([id,label,duration,loop,description])=>({id,label,duration,loop,description}));
export const clipById=Object.fromEntries(CLIPS.map(c=>[c.id,c]));
export const clamp=(v,a=0,b=1)=>Math.min(b,Math.max(a,v));
export const lerp=(a,b,u)=>a+(b-a)*clamp(u);
export const smooth=v=>{const u=clamp(v);return u*u*(3-2*u);};
export const quantize=(t,fps=12)=>Math.floor((Math.max(0,t)+1e-8)*fps)/fps;
export const skillForRoll=roll=>roll<.8?3:roll<.95?2:1;
export function seededRoll(seed){let n=(seed+0x6D2B79F5)|0;n=Math.imul(n^n>>>15,n|1);n^=n+Math.imul(n^n>>>7,n|61);return ((n^n>>>14)>>>0)/4294967296;}
const point=(a,b,u)=>({x:lerp(a.x,b.x,smooth(u)),y:lerp(a.y,b.y,smooth(u))});
export function blinkAt(age){
  if(age<0||age>=.5)return 1;
  if(age>=.2-1e-8&&age<=.3+1e-8)return 0;
  const k=age*12,values=[1,.65,.16,0,.16,.65,1];
  return lerp(values[Math.floor(k)],values[Math.min(6,Math.floor(k)+1)],k%1);
}
export function bounce(t){
  const age=(t%(20/12))*1.65/(20/12);let sy=1,y=0;
  if(age<.22)sy=1-.10*smooth(age/.22);
  else if(age<1.20){
    const u=(age-.22)/.98;y=-4*82*u*(1-u);sy=.99+.10*Math.abs(2*u-1)**2;
    if(u<.08)sy=lerp(.90,sy,smooth(u/.08));
  }else if(age<1.33)sy=lerp(1.09,.88,smooth((age-1.20)/.13));
  else {const u=(age-1.33)/.32;sy=lerp(.88,1,smooth(u))+.025*Math.sin(Math.PI*u);}
  return {x:0,y,sx:1/sy,sy,rotation:0};
}
export function createAnimator(rig){
  const parts=Object.fromEntries(rig.layers.map(l=>[l.id,l]));
  const white=parts.paw_front_white,black=parts.paw_front_black,glasses=parts.glasses,cup=parts.cup;
  const rest=l=>({x:l.x,y:l.y}),work=l=>({x:l.work[0],y:l.work[1]});
  const worn=rest(glasses),laid={x:83,y:203};
  const grip=g=>({white:{x:g.x-white.w+3,y:g.y+14,z:23},black:{x:g.x+glasses.w-3,y:g.y+14,z:24}});
  function sample(action,time,options={}){
    const {fps=12,amplitude=.6,breathing=true,blinking=true,random=true,seed=1,scarf=false}=options;
    const t=quantize(time,fps),a=clipById[action]??clipById.idle;
    const p={action:a.id,t,fps,actorRole:options.role??'leader',scarf,amplitude,breath:breathing?Math.sin(t*Math.PI/1.7)*amplitude:0,
      eye:blinking?blinkAt((t+1.5+(seed%3)/fps)%5):1,lookX:0,lookY:0,
      body:{x:0,y:0,sx:1,sy:1,rotation:0},desk:false,dropY:0,deskX:0,deskY:0,open:1,cat:0,chess:0,agentName:options.agentName??'演示 Agent',
      glasses:null,cup:null,paws:{white:rest(white),black:rest(black)},rear:{},
      tail:Math.sin(t*1.8)*.065*amplitude,tailSwing:Math.sin(t*1.8)*.22*amplitude,
      yaw:0,pitch:0,prone:0,soul:0,wifi:0,skill:null,
      flower:false,alert:null,magic:0,magicEye:1,phase:a.label};
    function atDesk(){p.desk=true;p.glasses={...worn,alpha:1,mode:'worn'};p.cup={...rest(cup),rotation:0};p.paws={white:work(white),black:work(black)};}
    function type(){
      atDesk();p.flower=true;
      for(const [key,offset] of [['white',0],['black',Math.PI]])p.paws[key].y-=Math.max(0,Math.sin(t*Math.PI*6+offset))*(1+3*amplitude);
    }
    function drink(dt){
      atDesk();p.flower=true;p.phase='端杯喝水';
      const start={x:cup.x,y:cup.y},sip={x:124,y:171};
      const u=dt<.6?0:dt<1.4?smooth((dt-.6)/.8):dt<2.2?1:1-smooth((dt-2.2)/.8);
      const pos=point(start,sip,u);p.cup={...pos,rotation:dt>=1.4&&dt<2.2?-.08:0};
      const hand={x:pos.x+23,y:pos.y+8,z:24};
      p.paws.black=dt<.6?{...point(work(black),hand,dt/.6),z:24}:dt<3?hand:{...point(hand,work(black),(dt-3)/.5),z:24};
      if(dt>=3.4){p.cup={...start,rotation:0};p.paws.black=work(black);}
      if(dt>1.4&&dt<2.2)p.eye=Math.min(p.eye,blinkAt(dt-1.5));
    }
    function finish(dt,egg){
      atDesk();p.phase=dt<1.3?'合上电脑':dt<2.6?'摘下眼镜':'放好眼镜';
      p.open=1-smooth((dt-.5)/.8);
      if(dt<1.3){
        const target=dt<.5?{x:112,y:164}:{x:lerp(112,126,(dt-.5)/.8),y:lerp(164,197,(dt-.5)/.8)};
        p.paws.white={...point(work(white),target,dt/.5),z:dt>=.35?35:23};
      }else if(dt<1.8){
        const hands=grip(worn);p.paws.white={...point({x:126,y:197},hands.white,(dt-1.3)/.5),z:41};
        p.paws.black={...point(work(black),hands.black,(dt-1.3)/.5),z:41};
      }else{
        const g=point(worn,laid,(dt-1.8)/.8);p.glasses={...g,alpha:1,mode:'held',front:true};p.paws=grip(g);
        const release=egg?3.8:2.8;
        if(dt>=release){p.paws.white={...point(p.paws.white,rest(white),(dt-release)/.6),z:41};p.paws.black={...point(p.paws.black,rest(black),(dt-release)/.6),z:41};}
      }
      if(egg){p.magic=1;p.magicEye=1;p.phase=dt<1.8?'戴着画有大眼睛的眼镜':dt<2.8?'摘下来，眼睛还在镜片上':'原来眼睛是画的';}
    }
    switch(a.id){
      case 'entry':{
        p.desk=true;p.cup={...rest(cup),rotation:0};p.open=smooth((t-.9)/.75);p.phase=t<.9?'电脑落下':t<1.65?'打开电脑':t<2.5?'戴上眼镜':'前爪落到键盘';
        p.dropY=t<.6?-230*(1-(t/.6)**2):t<.9?-7*Math.sin(Math.PI*(t-.6)/.3):0;
        if(options.reuseComputer){p.dropY=0;if(t<1.65)p.glasses={...laid,alpha:1,mode:'held',front:true};}
        if(t>=1.4){
          // Lift outside the screen, move above its top edge, then settle on face.
          const pickup={x:150,y:211},aboveRight={x:150,y:100},aboveFace={x:worn.x,y:100};
          const g=t<1.9?point(pickup,aboveRight,(t-1.4)/.5):t<2.25?point(aboveRight,aboveFace,(t-1.9)/.35):point(aboveFace,worn,(t-2.25)/.35);
          p.glasses={...g,alpha:smooth((t-1.4)/.15),mode:t<2.6?'held':'worn',front:true};
          const hands=grip(g),reach=smooth((t-1.4)/.2);
          p.paws.white={...point(rest(white),hands.white,reach),z:19};p.paws.black={...point(rest(black),hands.black,reach),z:19};
          if(t>=2.6){p.paws.white={...point(hands.white,work(white),(t-2.6)/.4),z:23};p.paws.black={...point(hands.black,work(black),(t-2.6)/.4),z:23};}
          if(t>=2.6)p.paws.black.z=24;
        }break;
      }
      case 'typing':{
        type();
        // Repeatable pseudo-random per-agent schedule, independent of redraw rate.
        const period=11+seed%4,cycle=Math.floor(t/period),start=6+((seed*17+cycle*7)%24)/12;
        const age=t%period-start;if(random&&age>=0&&age<3.5)drink(age);
        break;
      }
      case 'blink':type();p.eye=blinkAt(t%1);p.phase='同步眨眼';break;
      case 'drink':drink(clamp(t,0,3.5));break;
      case 'waiting':
        atDesk();p.lookX=Math.sin(t*1.2)*1.5;p.lookY=-.7;p.body.rotation=Math.sin(t*.9)*.006;
        p.alert='confirmation';break;
      case 'closing':finish(t,false);break;
      case 'easter':finish(t,true);break;
      case 'walk':case 'return':{
        const goingBack=a.id==='return';
        // A full articulated turn, travel, then turn to the destination. No sprite mirroring.
        p.yaw=goingBack?2.705*smooth(t/1.25)*(1-smooth((t-3.2)/1.2)):.85*smooth(t/.7)*(1-smooth((t-2.25)/.65));
        p.phase=goingBack?(t<1.25?'转身，露出侧面和背面':t<3.2?'背对镜头回工位':'转回电脑，准备开工'):(t<.6?'转向大包子':t<2.3?'走向大包子':'抵达，转回跟随朝向');
        const gait=t*Math.PI*3;p.body.y=-Math.abs(Math.sin(gait))*2;p.tail=Math.sin(gait)*.08;p.tailSwing=Math.sin(gait)*.22;
        for(const [key,phase] of [['white',0],['black',Math.PI]]){
          p.paws[key].x+=Math.sin(gait+phase)*2;p.paws[key].y-=Math.max(0,Math.sin(gait+phase))*4;
        }
        p.rear={paw_rear_far:{x:Math.sin(gait+Math.PI)*2,y:-Math.max(0,Math.sin(gait+Math.PI))*3},paw_rear_near:{x:Math.sin(gait)*2,y:-Math.max(0,Math.sin(gait))*3}};
        break;
      }
      case 'following':p.tail=Math.sin(t*2.2)*.065;p.tailSwing=Math.sin(t*2.2)*.24;break;
      case 'unread':p.body=bounce(t);p.alert='!';p.breath=0;break;
      case 'read':{
        const start=options.landingFrom??{y:-30,sx:1,sy:1,rotation:0,x:0};
        if(t<.5){p.body={...start,y:start.y*(1-(t/.5)**2),sx:lerp(start.sx,1,smooth(t/.5)),sy:lerp(start.sy,1,smooth(t/.5))};}
        else{const u=clamp((t-.5)/.5);p.body.sy=1-.10*Math.sin(Math.PI*u);p.body.sx=1/p.body.sy;}
        p.breath=0;p.cat=p.actorRole==='leader'?smooth((t-1)/.9):0;p.chess=Math.max(0,t-2);
        p.yaw=.68*p.cat;p.body.x+=70*p.cat;
        p.phase=t<1?'落地收稳':p.actorRole==='worker'?'已读待机':t<2?'与猫咪对坐':'隔空落子';break;
      }
      case 'failed':
        atDesk();p.eye=Math.min(p.eye,.68);p.body.y=smooth(t/.8)*2;
        if(t<.6)p.body.x=Math.sin(t*35)*3*(1-t/.6);
        p.skill=skillForRoll(options.failureRoll??seededRoll(seed));break;
      case 'disconnected':{
        atDesk();p.flower=false;p.eye=0;
        p.deskX=-84*smooth((t-.15)/.7);p.deskY=18*smooth((t-.15)/.7);
        const collapse=smooth((t-.9)/1.2);p.prone=collapse;p.pitch=collapse*Math.PI/2;p.breath=0;
        p.glasses={...point(worn,{x:-25,y:246},t/.6),alpha:1,mode:'held',front:true};
        p.paws.white=point(work(white),{x:101,y:220},t/.65);p.paws.black=point(work(black),{x:186,y:220},t/.65);
        p.body.x=collapse*7;p.body.y=collapse*5;
        p.soul=smooth((t-2.15)/1.8);p.wifi=smooth((t-3.8)/.5);
        p.phase=t<.9?'推开电脑':t<2.1?'软软地摊成一滩':t<3.3?'灵魂慢慢冒出来':'Wi-Fi 已断开';break;
      }
    }
    if(options.manualBlink!==undefined)p.eye=Math.min(p.eye,blinkAt(t-options.manualBlink));
    return p;
  }
  function transformFor(layer,p){
    let {x,y,w,h}=layer,rotation=0,visible=true,alpha=1,z=rig.layers.indexOf(layer);
    if(['alternate','effect','companion'].includes(layer.group))visible=false;
    if(layer.group==='scarf'&&!p.scarf)visible=false;
    if(layer.group==='desk'||layer.group==='closed'){
      visible=p.desk;y+=p.dropY+p.deskY;x+=p.deskX;
      if(layer.group==='closed')visible=false; // One hinged surface replaces the mismatched closed sprite.
    }
    if(layer.id==='glasses'){
      visible=!!p.glasses;if(visible){x=p.glasses.x;y=p.glasses.y;alpha=p.glasses.alpha;if(p.glasses.mode==='held')z=p.glasses.front?40:22.8;}
    }
    if(layer.id==='cup'){visible=!!p.cup;if(visible){x=p.cup.x;y=p.cup.y;rotation=p.cup.rotation;z=23.5;}}
    if(layer.group==='paw'){
      const paw=p.paws[layer.id==='paw_front_white'?'white':'black'];x=paw.x;y=paw.y;z=paw.z??z;
    }
    if(p.rear[layer.id]){x+=p.rear[layer.id].x;y+=p.rear[layer.id].y;}
    if(layer.group==='eye'){
      // Close inside the lenses instead of hiding the closed lids under the lower frame.
      const offset=14*(1-p.eye);x+=p.lookX;y+=p.lookY+offset;
      if(layer.role==='color'){h*=p.eye;if(p.eye<.03)visible=false;}
    }
    if(layer.id.startsWith('brow_')||layer.id==='mouth'){x+=p.lookX;y+=p.lookY;}
    if(layer.id==='tail'){rotation=p.tail;const root=239;w*=1+p.tailSwing;x=root+(x-root)*(1+p.tailSwing);}
    if(layer.id==='scarf_back')rotation=Math.sin(p.t*1.8+.4)*.035*p.amplitude;
    return {x,y,w,h,rotation,visible:visible&&alpha>.001,alpha,z};
  }
  return {sample,transformFor,parts};
}

// Fixed event demo: statuses and unread flags remain independent from animations.
export const OFFICE_DURATION=65;
export const OFFICE_STAGES=['工作','等待确认','继续工作','部分完成','全部完成','部分已读','全部已读','返回工位','异常','恢复'];
export function officeAt(time){
  const t=time%OFFICE_DURATION;let phase=0;
  const workers=[0,1,2].map(i=>({id:i,name:`演示 Agent ${i+1}`,action:'typing',age:t+2*i,travel:0,unread:false,completed:false,desk:'open',summary:'正在整理任务',readAt:Infinity}));
  for(const w of workers){
    if(t<3){w.action='entry';w.age=t;}
    if(t>=9&&t<13&&w.id===1){w.action='waiting';w.age=t-9;w.summary='等待确认';}
    const done=18+w.id*4,read=33+w.id*2;
    if(t>=done&&t<45){
      w.completed=true;w.unread=t<read;w.readAt=read;w.desk='closed';w.summary=w.unread?'任务完成 · 未读':'结果已读';
      const age=t-done;
      if(age<3.5){w.action='closing';w.age=age;}
      else if(age<6.5){w.action='walk';w.age=age-3.5;w.travel=smooth((age-4.1)/1.7);}
      else{w.action=t>=read?'read':'following';w.age=t>=read?t-read:age-6.5;w.travel=1;}
    }
    if(t>=45&&t<49.5){w.action='return';w.age=t-45;w.travel=1-smooth((t-46.25)/1.95);w.desk='closed';w.summary='背对镜头回工位';}
    if(t>=49.5&&t<52.5){w.action='entry';w.age=t-49.5;w.summary='继续工作';w.reuseComputer=true;}
    if(t>=52.5&&t<59.5&&w.id!==2){w.action=w.id===0?'failed':'disconnected';w.age=t-52.5;w.summary=w.id===0?'任务失败 · 技能就绪':'连接断开 · 吐魂中';}
  }
  if(t>=9)phase=1;if(t>=13)phase=2;if(t>=18)phase=3;if(t>=26)phase=4;if(t>=33)phase=5;if(t>=37)phase=6;if(t>=45)phase=7;if(t>=52.5)phase=8;if(t>=59.5)phase=9;
  const unread=workers.some(w=>w.unread);
  const leader=unread?{action:'unread',age:t-18}:t>=37&&t<45?{action:'read',age:t-37,landingFrom:bounce(19)}:workers.some(w=>['entry','typing'].includes(w.action))?{action:'typing',age:t}: {action:'idle',age:t};
  if(t<3){leader.action='entry';leader.age=t;}
  return {time:t,phase,label:OFFICE_STAGES[phase],workers,leader,unread};
}
