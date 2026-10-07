"""Shared visual desks and a global reunion queue; never changes task identity."""
import math


class PresentationLayout:
    def __init__(self):
        self.desks = {}
        self.origins = {}
        self.gathered = []
        self.return_indices = {}
        self.views = {}

    def update(self, rows):
        """Rows: id, order, gathered and needs_desk. Source is deliberately irrelevant."""
        rows = sorted(rows, key=lambda r:(r['order'], r['id']))
        keys = {r['id'] for r in rows}
        desk_keys = {r['id'] for r in rows if r['needs_desk']}
        gather_keys = {r['id'] for r in rows if r['gathered']}
        self.origins = {k:v for k,v in self.origins.items() if k in keys}
        self.return_indices = {k:v for k,v in self.return_indices.items() if k in keys}
        for index, key in enumerate(self.gathered):
            if key not in gather_keys: self.return_indices[key] = index
        self.gathered = [k for k in self.gathered if k in gather_keys]
        self.gathered.extend(r['id'] for r in rows if r['id'] in gather_keys and r['id'] not in self.gathered)
        self.desks = {k:v for k,v in self.desks.items() if k in desk_keys}
        for row in rows:
            key = row['id']
            if key in desk_keys and key not in self.desks:
                occupied = set(self.desks.values())
                slot = 0
                while slot in occupied: slot += 1
                self.desks[key] = slot
        # Fill a vacancy with the last occupied desk: minimal moves, no empty pages.
        occupied = {slot:key for key,slot in self.desks.items()}
        for vacancy in range(len(occupied)):
            if vacancy in occupied: continue
            last = max(occupied)
            key = occupied.pop(last)
            occupied[vacancy] = key
            self.desks[key] = vacancy
        self.origins.update(self.desks)
        indices = {key:i for i,key in enumerate(self.gathered)}
        self.views = {r['id']:{'desk_slot':self.desks.get(r['id']),
                      'origin_slot':self.origins.get(r['id'], r['order']),
                      'gather_index':indices.get(r['id']),
                      'return_index':self.return_indices.get(r['id'], 0)} for r in rows}
        return self.views

    def pages(self, capacity):
        return max(1, math.ceil(len(self.desks)/capacity))


def reunion_offset(index, count, available_height):
    """One bounded pile even when companions came from many house pages."""
    rows = max(1, math.ceil(count/3))
    step = min(46, max(0, available_height)/max(1, rows-1))
    return (index%3)*46, (index//3)*step
