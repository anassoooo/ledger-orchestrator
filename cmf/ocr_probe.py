"""Diagnostic only: compare local OCR readings; never writes accounting records."""
import argparse
import json
import subprocess
import tempfile
import io
from pathlib import Path
import pypdfium2
from PIL import Image,ImageOps
import pdfplumber
from cmf.cell_ocr import ROWS


def embedded_crop(page,box):
    """Reassemble intersecting image strips before cropping a diagnostic row."""
    left,top,right,bottom=box
    bands=[im for im in page.images if im['top']<bottom and im['bottom']>top
           and im['x0']<right and im['x1']>left]
    if not bands:
        return None
    scale=max(im['srcsize'][0]/im['width'] for im in bands)
    canvas=Image.new('RGB',(round((right-left)*scale),round((bottom-top)*scale)),'white')
    for band in bands:
        raw=band['stream'].get_data()
        size=band['srcsize']
        embedded=Image.frombytes('RGB',size,raw) if len(raw)==size[0]*size[1]*3 else Image.open(io.BytesIO(raw))
        x0,y0=max(left,band['x0']),max(top,band['top'])
        x1,y1=min(right,band['x1']),min(bottom,band['bottom'])
        fx,fy=size[0]/band['width'],size[1]/band['height']
        tile=embedded.crop((round((x0-band['x0'])*fx),round((y0-band['top'])*fy),
                            round((x1-band['x0'])*fx),round((y1-band['top'])*fy))).convert('RGB')
        dest=(round((x0-left)*scale),round((y0-top)*scale),round((x1-left)*scale),round((y1-top)*scale))
        resized=tile.resize((dest[2]-dest[0],dest[3]-dest[1]),Image.Resampling.LANCZOS)
        canvas.paste(resized,dest[:2])
        resized.close()
        tile.close()
        embedded.close()
    return canvas


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('pdf',type=Path)
    parser.add_argument('--raw',action='store_true',help='Read original embedded image pixels instead of a page rendering')
    parser.add_argument('--codes',nargs='+',default=['AC21','AC22','AC311','AC312','AC322','AC323','AC33','AC74','AC7'])
    args=parser.parse_args()
    doc=pypdfium2.PdfDocument(args.pdf)
    bitmap=doc[1].render(scale=6)
    image=bitmap.to_pil().convert('L')
    original=pdfplumber.open(args.pdf)
    source_page=original.pages[1]
    sx,sy=image.width/1072,image.height/1516
    with tempfile.TemporaryDirectory() as temp:
        target=Path(temp)/'crop.png'
        for code in args.codes:
            y=ROWS[code]
            results={}
            for lang in ['eng','fra']:
                for name,left,right in [('row',525,970),('net',765,864)]:
                    if args.raw:
                        px0,py0,px1,py1=left/1072*source_page.width,(y-7)/1516*source_page.height,right/1072*source_page.width,(y+7)/1516*source_page.height
                        assembled=embedded_crop(source_page,(px0,py0,px1,py1))
                        if assembled is None:
                            results[lang+'_'+name]='no_embedded_image'
                            continue
                        crop=assembled.convert('L')
                        crop=crop.resize((crop.width*3,crop.height*3),Image.Resampling.LANCZOS)
                        assembled.close()
                    else:
                        crop=image.crop((round(left*sx),round((y-8)*sy),round(right*sx),round((y+8)*sy)))
                    crop=ImageOps.expand(crop,border=30,fill=255)
                    crop.save(target)
                    text=subprocess.run(['tesseract',str(target),'stdout','-l',lang,'--psm','7'],capture_output=True,text=True,check=True,timeout=20).stdout.strip()
                    results[lang+'_'+name]=text
                    crop.close()
            print(json.dumps(dict(code=code,readings=results)),flush=True)
    image.close()
    bitmap.close()
    doc.close()
    original.close()


if __name__=='__main__':
    main()
