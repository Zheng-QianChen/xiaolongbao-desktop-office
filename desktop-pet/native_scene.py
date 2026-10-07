"""Presentation-only placement and miniature house for the transparent Tk pet."""
import json
import math
from pathlib import Path


class NativeScene:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.mode = 'free'
        self.locked = False
        self.desktop_scale = 100
        self.positions = {}
        try:
            saved = json.loads(self.path.read_text(encoding='utf-8')) if self.path else {}
            if isinstance(saved, dict):
                self.mode = 'house' if saved.get('mode') == 'house' else 'free'
                self.locked = saved.get('locked') is True
                if type(saved.get('desktop_scale')) is int and saved['desktop_scale'] in (50,75,100,125,150):
                    self.desktop_scale = saved['desktop_scale']
                positions = saved.get('positions', {})
                if isinstance(positions, dict):
                    for key, xy in list(positions.items())[:512]:
                        if (isinstance(xy, list) and len(xy) == 2 and
                                all(isinstance(n, (int, float)) and math.isfinite(n) for n in xy)):
                            self.positions[key] = xy
        except (OSError, ValueError):
            pass

    def save(self):
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'mode': self.mode, 'positions': self.positions, 'locked': self.locked,
                                         'desktop_scale': self.desktop_scale}), encoding='utf-8')
        temporary.replace(self.path)

    def position(self, key, fallback, width, height, size, centered=False):
        x, y = self.positions.get(key, fallback) if self.mode == 'free' else fallback
        left, top = (size[0]/2, size[1]/2+40) if centered else (12, 65)
        right = width-size[0]/2 if centered else width-size[0]-8
        bottom = height-size[1]/2-35 if centered else height-size[1]-12
        return [max(left, min(right, x)), max(top, min(bottom, y))]


def draw_house(canvas, columns, rows):
    """Draw below sprites; each room aligns with native desk coordinates +80px."""
    canvas.delete('house')
    left, right, top = 318, 338+columns*110, 111
    bottom = 125+(rows-1)*130+124
    mid = (left+right)/2
    def rect(x, y, w, h, color):
        canvas.create_rectangle(x,y,x+w,y+h,fill=color,outline='',tags='house')
    def poly(points,color):
        canvas.create_polygon(*points,fill=color,outline='',tags='house')
    rect(left,top,right-left,bottom-top,'#74644e')
    rect(left+7,top+4,right-left-14,bottom-top-10,'#eee3c7')
    for x in range(left+16,right-8,22):rect(x,top+5,1,bottom-top-12,'#e0d2b4')
    for row in range(rows):
        y=125+row*130
        for col in range(columns):
            x=330+col*110
            rect(x+18,y+8,66,48,'#bba07a');rect(x+22,y+12,58,40,'#d2e5dd')
            rect(x+48,y+12,3,40,'#f8efdb');rect(x+22,y+31,58,3,'#f8efdb')
            rect(x+13,y+55,76,4,'#9c7a53')
            rect(x+4,y+72,96,8,'#c2a071');rect(x+10,y+80,5,13,'#937354');rect(x+89,y+80,5,13,'#937354')
        rect(left,y+120,right-left,10,'#9c7650');rect(left,y+120,right-left,3,'#d0ac79')
    rect(right-65,50,24,37,'#9e8262');rect(right-69,46,32,8,'#705f4c')
    poly([left-13,112,mid,44,right+13,112],'#4e6658')
    poly([left-5,106,mid,51,right+5,106],'#8a9d76')
    for y in [73,87,101]:
        half=(y-51)*(right-left)/110
        rect(mid-half,y,half*2,3,'#708665')
    rect(left-13,108,right-left+26,9,'#5c715c')
    rect(mid-57,99,114,27,'#685f4b');rect(mid-54,102,108,21,'#f1e3bf')
    canvas.create_text(mid,113,text='望 包 小 屋',fill='#53644f',font=('Microsoft YaHei UI',-12,'bold'),tags='house')
    rect(left-10,bottom+5,right-left+20,8,'#74644e')
    rect(left-23,151,4,34,'#79644d');rect(left-32,150,20,4,'#79644d');rect(left-30,155,16,19,'#e9c775')
    rect(left-51,bottom-16,23,25,'#bd8b65');rect(left-54,bottom-20,29,6,'#d7a579')
    rect(left-41,bottom-47,3,27,'#708967')
    poly([left-40,bottom-36,left-58,bottom-46,left-57,bottom-56,left-41,bottom-47],'#92a37a')
    poly([left-39,bottom-40,left-21,bottom-58,left-15,bottom-51,left-26,bottom-38],'#758f6c')
    canvas.tag_lower('house')
