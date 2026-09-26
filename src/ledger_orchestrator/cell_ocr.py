"""STAR 2025 scanned balance profile. Geometry only; no financial values embedded."""
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
import pypdfium2
from PIL import ImageOps,ImageEnhance

# Coordinates on a 1072 x 1516 reference rendering, verified against page 2.
# Two passes must agree before an OCR value becomes a candidate.
ROWS={'AC12':230,'AC1':262,'AC21':314,'AC22':330,'AC2':348,'AC31':398,
      'AC311':415,'AC312':430,'AC32':454,'AC322':487,'AC323':509,'AC33':525,
      'AC331':542,'AC332':559,'AC334':572,'AC336':588,'AC34':615,'AC3':639,
      'AC510':748,'AC530':764,'AC531':780,'AC541':802,'AC5':823,
      'AC61':875,'AC611':894,'AC612':910,'AC613':937,'AC62':953,'AC63':969,
      'AC631':985,'AC632':1010,'AC633':1031,'AC6':1065,'AC71':1115,'AC72':1132,
      'AC721':1149,'AC73':1180,'AC731':1198,'AC732':1212,'AC733':1230,'AC74':1247,
      'AC7':1283,'TOTAL_ASSET':1314}


def read_scanned_asset(path,cache):
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    saved=cache/f'{digest}-cell-v1.json'
    if saved.exists(): return json.loads(saved.read_text(encoding='utf-8'))
    records={}
    doc=pypdfium2.PdfDocument(path)
    try:
        page=doc[1]
        bitmap=page.render(scale=4)
        image=bitmap.to_pil().convert('L')
        sx,sy=image.width/1072,image.height/1516
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            def recognize(box,psm,kind='digits'):
                crop=image.crop(tuple(round(v*s) for v,s in zip(box,[sx,sy,sx,sy])))
                crop=ImageEnhance.Contrast(crop).enhance(1.4)
                crop=ImageOps.expand(crop,border=20,fill=255)
                target=tmp/'cell.png'
                crop.save(target)
                args=['tesseract',str(target),'stdout','-l','fra','--psm',str(psm)]
                if kind=='digits': args+=['-c','tessedit_char_whitelist=0123456789']
                text=subprocess.run(args,check=True,capture_output=True,text=True,encoding='utf-8',timeout=20).stdout.strip()
                crop.close()
                return text
            # Verify the exact expected page profile before using its row geometry.
            header=recognize((520,145,975,169),7,'text')
            title=recognize((460,77,710,119),6,'text')
            dates=re.findall(r'31[/1]12/(20\d\d)',header.replace(' ',''))
            if dates!=['2025','2024'] or 'dinar' not in title.lower():
                return {'records':{},'error':'cell_profile_header_unverified','header':header,'title':title}
            for code,y in ROWS.items():
                vals=[]
                evidence=[]
                for left,right in [(765,864),(872,969)]:
                    box=(left,y-6,right,y+7)
                    a=recognize(box,7)
                    b=recognize(box,6)
                    evidence.append(dict(bbox_reference=box,psm7=a,psm6=b))
                    vals.append(int(a) if re.fullmatch(r'\d{1,12}',a) and a==b else None)
                if vals[0] is not None and vals[1] is not None:
                    records[code]=dict(code=code,year=2025,value=vals[0],previous=vals[1],unit='TND',
                                       source='sources/STAR/2025.pdf',page=2,method='ocr_cells',source_label=code,
                                       bbox=[765/1.8,(y-6)/1.8,969/1.8,(y+7)/1.8],
                                       ocr_evidence=evidence,profile='STAR-2025-actif-v1')
        image.close()
        bitmap.close()
    finally:
        doc.close()
    result={'records':records,'header':header,'title':title}
    saved.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
