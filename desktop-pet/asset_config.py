"""Runtime sprite metadata, independent of the optional artwork build tools."""
from app_paths import ROOT

OUT = ROOT/'assets/animation-frames-v9'
COUNTS = {'entry':4, 'typing':4, 'blink':4, 'drink':8, 'closing':8,
          'walk':8, 'waiting':4, 'failure':4, 'easter':8}
FRAME_WIDTH, FRAME_HEIGHT, LEFT_PADDING = 321, 255, 32
