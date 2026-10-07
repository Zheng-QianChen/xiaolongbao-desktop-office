"""Runtime alpha testing for crisp pixel sprites on Tk's color-key surface."""
from PIL import Image

COLOR_KEY='#010203'


def pixel_sprite(image,size):
    """Keep native artwork; apply binary coverage in the renderer, not the file."""
    width,height=size
    integer_reduction=(image.width>width and image.height>height
                       and image.width%width==0 and image.height%height==0
                       and image.width//width==image.height//height)
    # Integrate each exact pixel block for tiny workers. Nearest sampling can
    # discard a thin outline entirely when it moves by one source pixel.
    sampler=Image.Resampling.BOX if integer_reduction else Image.Resampling.NEAREST
    resized=image.convert('RGBA').resize(size,sampler)
    # Tk blends fractional alpha against the canvas BEFORE Windows color-keying.
    # Pixel sprites need coverage to be either opaque or transparent.
    coverage=resized.getchannel('A').point(lambda value:255 if value>=128 else 0)
    resized.putalpha(coverage)
    return resized


def geometry(width,height,screen_width,screen_height):
    width=max(1,round(width));height=max(1,round(height))
    return f'{width}x{height}+{max(0,(screen_width-width)//2)}+{max(0,(screen_height-height)//2)}'
