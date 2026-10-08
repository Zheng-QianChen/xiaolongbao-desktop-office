"""Runtime sprite metadata, independent of the optional artwork build tools."""
from app_paths import ROOT

OUT = ROOT/'assets/animation-frames-v9'
COUNTS = {'entry':4, 'typing':4, 'blink':4, 'drink':8, 'closing':8,
          'walk':8, 'waiting':4, 'failure':4, 'easter':8}
FRAME_WIDTH, FRAME_HEIGHT, LEFT_PADDING = 321, 255, 32

# The art thread exports on a padded canvas. Keep its model origin unchanged
# so ghosts, the pushed laptop and the chessboard are never clipped/scaled down.
EXTENDED = ROOT/'assets/animation-frames-v10'
EXTENDED_SIZE = (480, 440)
EXTENDED_ORIGIN = (55, 130)
EXTENDED_CLIPS = {'disconnected':(60,5), 'return':(54,4.5),
                  'walk':(36,3), 'read':(96,8)}

def extended_frame(name, age):
    count,duration=EXTENDED_CLIPS[name]
    return name,min(count-1,max(0,int(age/duration*count)))
