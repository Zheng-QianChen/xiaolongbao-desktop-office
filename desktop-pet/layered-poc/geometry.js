// Shared geometry for animation, raster rendering and regression checks.
export function lidGeometry(open,dropY=0,dx=0,dy=0){
  const angle=open*Math.PI/2,A=[57+dx,233+dropY+dy],B=[140+dx,255+dropY+dy];
  const v=[51*Math.cos(angle)-15*Math.sin(angle),-18*Math.cos(angle)-62*Math.sin(angle)];
  const farA=[A[0]+51,A[1]-18],farB=[B[0]+51,B[1]-18];
  const base=[A,farA,farB,B],quad=[[A[0]+v[0],A[1]+v[1]],[B[0]+v[0],B[1]+v[1]],B,A];
  const thickness=[3*Math.sin(angle),-3*Math.cos(angle)];
  return {angle,hinge:[A,B],base,quad,baseBottom:base.map(([x,y])=>[x,y+6]),lidOuter:quad.map(([x,y])=>[x+thickness[0],y+thickness[1]]),baseThickness:6,lidThickness:3};
}
function triangle(c,image,src,dst){
  const [[u0,v0],[u1,v1],[u2,v2]]=src,[[x0,y0],[x1,y1],[x2,y2]]=dst;
  const det=(u1-u0)*(v2-v0)-(u2-u0)*(v1-v0);if(Math.abs(det)<1e-6)return;
  const a=((x1-x0)*(v2-v0)-(x2-x0)*(v1-v0))/det,b=((y1-y0)*(v2-v0)-(y2-y0)*(v1-v0))/det;
  const d=((u1-u0)*(y2-y0)-(u2-u0)*(y1-y0))/det,e=((u1-u0)*(x2-x0)-(u2-u0)*(x1-x0))/det;
  c.save();c.beginPath();c.moveTo(x0,y0);c.lineTo(x1,y1);c.lineTo(x2,y2);c.closePath();c.clip();
  c.transform(a,b,e,d,x0-a*u0-e*v0,y0-b*u0-d*v0);c.drawImage(image,0,0);c.restore();
}
export function drawQuad(c,image,src,dst){
  triangle(c,image,[src[0],src[1],src[2]],[dst[0],dst[1],dst[2]]);
  triangle(c,image,[src[0],src[2],src[3]],[dst[0],dst[2],dst[3]]);
}
export const faceCenter=137.5;
export function statusAnchor(scale=1){return {x:159,y:54};}
