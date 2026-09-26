import unittest
from types import SimpleNamespace
from PIL import Image
from ledger_orchestrator.ocr_probe import embedded_crop


class Stream:
    def __init__(self,data):
        self.data=data
    def get_data(self):
        return self.data


class EmbeddedCropTests(unittest.TestCase):
    def test_crossing_strips_preserves_both_parts(self):
        bands=[]
        for top,color in [(0,'red'),(10,'blue')]:
            im=Image.new('RGB',(20,10),color)
            bands.append(dict(top=top,bottom=top+10,x0=0,x1=20,width=20,height=10,
                              srcsize=(20,10),stream=Stream(im.tobytes())))
            im.close()
        result=embedded_crop(SimpleNamespace(images=bands),(2,8,18,12))
        self.assertEqual(result.size,(16,4))
        self.assertEqual(result.getpixel((5,0)),(255,0,0))
        self.assertEqual(result.getpixel((5,3)),(0,0,255))
        result.close()

    def test_missing_image_is_not_a_numeric_zero(self):
        self.assertIsNone(embedded_crop(SimpleNamespace(images=[]),(0,0,10,10)))
