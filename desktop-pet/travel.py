"""Stable desk slots and bounded walking, independent of Tk visibility."""
import math
from dataclasses import dataclass
from presentation_layout import reunion_offset
from asset_config import extended_frame

SPEED=105.0

def desk_position(slot,columns,capacity):
    local=slot%capacity
    return [330+(local%columns)*110,45+(local//columns)*130]

def follow_position(index,leader,count=1):
    ox,oy=reunion_offset(index,count,120)
    return [leader[0]-140+ox,leader[1]+115+oy]

@dataclass
class Position:
    xy: list
    moving: bool=False
    gait: float=0

class Travel:
    def __init__(self):self.positions={}

    def update(self,workers,leader,columns,capacity,dt,now,desk_resolver=None,follow_resolver=None):
        self.positions={key:pos for key,pos in self.positions.items() if key in workers.items}
        followers=[]
        for worker in sorted(workers.items.values(),key=lambda w:w.slot):
            if worker.completed:
                followers.append(worker.key)
        for key,worker in workers.items.items():
            desk=desk_resolver(worker) if desk_resolver else desk_position(worker.slot,columns,capacity)
            following=worker.phase in {'departing','following'}
            index=followers.index(key) if following else 0
            target=(follow_resolver(worker,index) if follow_resolver else follow_position(index,leader,len(followers))) if following else desk
            if key not in self.positions:
                # Fresh workers start at their desk; restored followers at the leader.
                initial=target if worker.phase=='following' else desk
                self.positions[key]=Position(initial[:])
            pos=self.positions[key]
            if worker.state=='disconnected':
                pos.moving=False
                continue
            dx,dy=target[0]-pos.xy[0],target[1]-pos.xy[1]
            distance=math.hypot(dx,dy)
            step=min(distance,SPEED*max(0,min(.25,dt)))
            pos.moving=distance>.6 and step>0
            if step:
                pos.xy[0]+=dx/distance*step;pos.xy[1]+=dy/distance*step
                pos.gait+=step/SPEED
            if distance<=step+.6:
                pos.xy[:]=target
                if worker.phase!='returning' or now-worker.phase_at>=4.5:
                    worker.arrive(now)

def phase_frame(worker,now,position):
    """One frame policy shared by playback and previews."""
    age=max(0,now-worker.phase_at)
    if worker.state=='disconnected':return extended_frame('disconnected',age)
    if worker.phase=='returning':return extended_frame('return',age)
    if position and position.moving:return extended_frame('walk',age)
    phase=worker.phase
    if phase in {'departing','following','returning'}:return 'rest',0
    if phase=='closing':
        from workstations import CLOSING_DURATION
        return ('easter' if worker.easter_egg else 'closing'),min(7,int(age/CLOSING_DURATION*8))
    if worker.state=='running':
        if phase=='drop':return 'rest',0
        if phase=='open':return 'entry',min(2,int(age/.65*3))
        if phase=='glasses':return 'entry',2
        if phase=='blink':return 'blink',min(3,int(age/.5*4))
        if phase=='drink':return 'drink',min(7,int(age/2.4*8))
        return 'typing',int(age*8)%4
    if worker.has_computer:
        if worker.state in {'waiting','review'}:
            t=age%4
            return 'waiting',min(3,int(t/.6*4)) if t<.6 else 3
        if worker.state=='failed':return 'failure',min(3,int(age/.9*4))
        return 'waiting',0
    return 'rest',0
