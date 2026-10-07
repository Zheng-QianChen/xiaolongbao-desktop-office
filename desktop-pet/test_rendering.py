import unittest
from PIL import Image
from rendering import pixel_sprite,geometry


class RenderingTests(unittest.TestCase):
    def test_thin_line_coverage_survives_integer_reduction(self):
        # A 1px dark line should not wink out as it moves within a 3px block.
        samples=[]
        for x in range(3):
            image=Image.new('RGBA',(3,3),'white')
            for y in range(3):image.putpixel((x,y),(0,0,0,255))
            samples.append(pixel_sprite(image,(1,1)).getpixel((0,0)))
        self.assertEqual(samples,[(170,170,170,255)]*3)

    def test_runtime_dimensions_preserve_native_and_third_scale(self):
        from family import BIG,BIG_WIDTH,SMALL,SMALL_WIDTH
        from asset_config import FRAME_WIDTH,FRAME_HEIGHT
        self.assertEqual((BIG_WIDTH,BIG),(FRAME_WIDTH,FRAME_HEIGHT))
        self.assertEqual((SMALL_WIDTH*3,SMALL*3),(FRAME_WIDTH,FRAME_HEIGHT))

    def test_alpha_never_blends_with_color_key(self):
        image=Image.new('RGBA',(5,1))
        image.putdata([(255,255,255,a) for a in [0,40,127,128,254]])
        displayed=pixel_sprite(image,(10,2))
        self.assertEqual({displayed.getpixel((x,0))[3] for x in range(10)},{0,255})
        self.assertEqual(image.getpixel((4,0))[3],254)  # source asset is unchanged

    def test_completion_layout_has_integer_geometry(self):
        self.assertEqual(geometry(440,455.0,2560,1080),'440x455+1060+312')
        self.assertEqual(geometry(440,455.6,2560,1080),'440x456+1060+312')


if __name__=='__main__':unittest.main()
