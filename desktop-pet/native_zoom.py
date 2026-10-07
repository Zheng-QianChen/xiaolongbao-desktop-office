"""Scale a Tk scene while keeping its layout and hit coordinates in logical pixels."""
import copy
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageTk

SCALE_LEVELS = (50, 75, 100, 125, 150)


class ZoomCanvas(tk.Canvas):
    def __init__(self, *args, **kwargs):
        self.zoom = 1.0
        self._scene_options = {}
        self._zoom_images = {}
        self._zoom_fonts = {}
        super().__init__(*args, **kwargs)

    def scaled_font(self, font):
        key = str(font)
        if key not in self._zoom_fonts:
            options = tkfont.Font(root=self, font=font).actual()
            size = options['size']
            options['size'] = (-1 if size < 0 else 1) * max(1, round(abs(size)*self.zoom))
            self._zoom_fonts[key] = tkfont.Font(root=self, **options)
        return self._zoom_fonts[key]

    def measure(self, font, text):
        return self.scaled_font(font).measure(text) / self.zoom

    def linespace(self, font):
        return self.scaled_font(font).metrics('linespace') / self.zoom

    def _display_options(self, options):
        result = dict(options)
        if 'font' in result:
            result['font'] = self.scaled_font(result['font'])
        for name in ('width', 'activewidth', 'disabledwidth'):
            if name in result:
                result[name] = float(result[name])*self.zoom
        if result.get('image') and self.zoom != 1:
            original = result['image']
            key = str(original)
            if key not in self._zoom_images:
                source = ImageTk.getimage(original)
                size = (max(1, round(source.width*self.zoom)), max(1, round(source.height*self.zoom)))
                self._zoom_images[key] = ImageTk.PhotoImage(source.resize(size, Image.Resampling.NEAREST), master=self)
            result['image'] = self._zoom_images[key]
        return result

    def _create(self, itemType, args, kw):
        coords = [float(value)*self.zoom for value in tk._flatten(args)]
        options = dict(kw)
        if itemType in {'line', 'polygon', 'rectangle'}:
            options.setdefault('width', 1)
        item = super()._create(itemType, coords, self._display_options(options))
        self._scene_options[item] = {k: v for k, v in options.items()
                                    if k in {'image', 'font', 'width', 'activewidth', 'disabledwidth'}}
        return item

    def coords(self, *args):
        args = tk._flatten(args)
        if len(args) > 1:
            return super().coords(args[0], *[float(value)*self.zoom for value in args[1:]])
        return [value/self.zoom for value in super().coords(*args)]

    def bbox(self, *args):
        box = super().bbox(*args)
        return tuple(value/self.zoom for value in box) if box else None

    def itemconfigure(self, tagOrId, cnf=None, **kw):
        if cnf is None and not kw or isinstance(cnf, str):
            return super().itemconfigure(tagOrId, cnf, **kw)
        options = dict(cnf or {}, **kw)
        for item in self.find_withtag(tagOrId):
            self._scene_options[item].update({k: v for k, v in options.items()
                if k in {'image', 'font', 'width', 'activewidth', 'disabledwidth'}})
        return super().itemconfigure(tagOrId, self._display_options(options))

    itemconfig = itemconfigure

    def delete(self, *args):
        for tag in args:
            for item in self.find_withtag(tag):
                self._scene_options.pop(item, None)
        return super().delete(*args)

    def set_zoom(self, zoom):
        if zoom == self.zoom:
            return
        ratio = zoom/self.zoom
        self.zoom = zoom
        # Canvas.scale alone does not resize fonts or images. Update those too,
        # and keep only this scale's image cache instead of every visited scale.
        self._zoom_images = {}
        self._zoom_fonts = {}
        super().scale('all', 0, 0, ratio, ratio)
        for item, options in self._scene_options.items():
            super().itemconfigure(item, self._display_options(options))

    def _logical_event(self, callback):
        if not callable(callback):
            return callback
        def wrapped(event):
            logical = copy.copy(event)
            logical.x, logical.y = event.x/self.zoom, event.y/self.zoom
            return callback(logical)
        return wrapped

    def bind(self, sequence=None, func=None, add=None):
        return super().bind(sequence, self._logical_event(func), add)

    def tag_bind(self, tagOrId, sequence=None, func=None, add=None):
        return super().tag_bind(tagOrId, sequence, self._logical_event(func), add)
