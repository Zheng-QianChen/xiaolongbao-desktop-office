// Animate the approved PNG parts. Spatial coordinates guide occlusion only;
// no lit mesh or replacement 3D character is composited into the animation.
import {smooth,lerp,clamp} from './motions.js?v=8';
export function createLayerTurn(rig,images,animator,hidden){
 const W=400,H=290,canvas=document.createElement('canvas');canvas.width=W;canvas.height=H;const c=canvas.getContext('2d');
 const face=document.createElement('canvas');face.width=W;face.height=H;const f=face.getContext('2d');
 const C=163,R=91,parts=Object.fromEntries(rig.layers.map(l=>[l.id,l]));
 const tailSoft=document.createElement('canvas');tailSoft.width=80;tailSoft.height=54;
 {const t=tailSoft.getContext('2d');t.imageSmoothingEnabled=false;t.drawImage(images.tail,0,0,80,54);t.globalCompositeOperation='destination-in';const g=t.createLinearGradient(0,0,18,0);g.addColorStop(0,'transparent');g.addColorStop(1,'#fff');t.fillStyle=g;t.fillRect(0,0,80,54);}
 function orbit(x,z,a){return {x:C+x*Math.cos(a)-z*Math.sin(a),depth:x*Math.sin(a)+z*Math.cos(a)};}
 function rect(im,r){c.save();c.globalAlpha*=r.alpha??1;if(r.rotation){c.translate(r.x+r.w/2,r.y+r.h*.7);c.rotate(r.rotation);c.translate(-r.x-r.w/2,-r.y-r.h*.7);}if(r.flip){c.translate(r.x+r.w,r.y);c.scale(-1,1);c.drawImage(im,0,0,r.w,r.h);}else c.drawImage(im,r.x,r.y,r.w,r.h);c.restore();}
 function faceLayer(l,p,a){
  if(hidden.has(l.id))return;
  const r=animator.transformFor(l,p);if(!r.visible&&l.id!=='face_patch')return;
  const im=images[l.id];f.globalAlpha=(l.opacity??1)*(1-smooth((p.prone-.25)/.5));
  for(let u=0;u<im.width;u++){
   const phi0=Math.asin(clamp((r.x+r.w*u/im.width-C)/R,-.999,.999)),phi1=Math.asin(clamp((r.x+r.w*(u+1)/im.width-C)/R,-.999,.999));
   if(Math.cos((phi0+phi1)/2-a)<=0)continue;
   const x0=C+R*Math.sin(phi0-a),x1=C+R*Math.sin(phi1-a);
   f.drawImage(im,u,0,1,im.height,x0,r.y,Math.max(.2,x1-x0)+.1,r.h);
  }
 }
 function render(p){
  c.clearRect(0,0,W,H);c.imageSmoothingEnabled=false;
  const a=p.yaw||0,back=smooth((Math.abs(a)-.7)/2),side=Math.abs(Math.sin(a)),prone=p.prone||0;
  c.save();c.translate(C,225);c.scale(1+.24*prone,1-.70*prone);c.translate(-C,-225);
  const queue=[];
  for(const id of ['paw_rear_far','paw_rear_near','paw_front_white','paw_front_black','horn_left','horn_right']){
   if(hidden.has(id))continue;const l=parts[id],r=animator.transformFor(l,p),horn=id.startsWith('horn'),front=l.group==='paw';
   const pos=orbit(l.x+l.w/2-C,horn?52:front?57:-51,a),scale=clamp(1+(pos.depth-(horn?52:front?57:-51))*.0017,.77,1.12);
   r.w=l.w*scale*(horn?1-.20*side:1);r.h=l.h*scale;r.x=pos.x-r.w/2;
   r.y=l.y+(l.h-r.h)+(horn?-(pos.depth-52)*.06-40*back:(pos.depth-(front?57:-51))*.055);
   if(!horn){r.y+=(p.rear[id]?.y??0)+(front?(p.paws[id==='paw_front_white'?'white':'black'].y-l.y):0);if(!front){r.x+=id==='paw_rear_near'?-8*side:5*side;r.y+=4*side;}}
   r.flip=horn&&Math.cos(a)<-.35;r.rotation=horn?(id==='horn_left'?-.10:.10)*prone:0;
   queue.push({z:pos.depth<0?3:horn?12:16,draw:()=>rect(images[id],r)});
  }
  if(!hidden.has('tail'))queue.push({z:back>.16?11:0,draw:()=>{
   // The rear root stays high enough to separate it from the hind feet.
   const root=[lerp(239,194,back),lerp(185,190,back)],m=[lerp(1,1.02,back),lerp(0,-.16,back),lerp(0,.25,back),lerp(1,.90,back)];
   c.save();c.translate(...root);c.rotate(p.tail*.6);c.transform(...m,0,0);c.globalAlpha=1-back;c.drawImage(images.tail,-6,-40,80,54);c.globalAlpha=back;c.drawImage(tailSoft,-6,-40,80,54);c.restore();
  }});
  for(const [i,id] of ['dorsal_fin_top','dorsal_fin_middle','dorsal_fin_bottom'].entries()){
   if(hidden.has(id))continue;const l=parts[id];
   const r={x:lerp(l.x,149,back),y:lerp(l.y,89+i*27,back),w:lerp(l.w,31,back)*(1+.10*side),h:lerp(l.h,28,back),alpha:1};
   queue.push({z:back>.12?10:2,draw:()=>{if(back>.1){const crop=5*back;c.save();c.translate(r.x+r.w/2,r.y+r.h/2);c.rotate(-1.15*back);c.drawImage(images[id],crop,0,images[id].width-crop,images[id].height,-r.w/2+crop,-r.h/2,r.w-crop,r.h);c.restore();}else rect(images[id],r);}});
  }
  queue.push({z:7,draw:()=>{if(!hidden.has('body'))c.drawImage(images.body_blank,71,54,184,163);}});
  queue.push({z:9,draw:()=>{
   f.clearRect(0,0,W,H);f.imageSmoothingEnabled=false;
   for(const id of ['face_patch','brow_left','brow_right','mouth','eye_left_color','eye_left_lid','eye_right_color','eye_right_lid'])faceLayer(parts[id],p,a);
   f.globalAlpha=1;f.globalCompositeOperation='destination-in';f.drawImage(images.body_blank,71,54,184,163);f.globalCompositeOperation='source-over';c.drawImage(face,0,0);
  }});
  if(!hidden.has('side_cross')){
   const sideNormal=Math.sin(.60+a),x=C+Math.cos(.60+a)*R;
   if(sideNormal>.12)queue.push({z:9.5,draw:()=>{const w=24*Math.min(1.15,sideNormal/Math.sin(.60));rect(images.side_cross,{x:x-w/2,y:139,w,h:36,alpha:1});}});
  }
  if(p.scarf){for(const id of ['scarf_back','scarf_front'])if(!hidden.has(id)){const l=parts[id],r={...l,w:l.w*(.55+.45*Math.abs(Math.cos(a)))};r.x=C-r.w/2;queue.push({z:id==='scarf_back'?4:15,draw:()=>rect(images[id],r)});}}
  queue.sort((a,b)=>a.z-b.z).forEach(item=>item.draw());c.restore();return canvas;
 }
 return {render,orbit,kind:'layered-png'};
}
