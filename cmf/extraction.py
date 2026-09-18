"""Native PDF / local Tesseract extraction with page coordinates and evidence."""
import csv
import hashlib
import io
import json
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import pdfplumber
import pypdfium2


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text).upper()
                   if not unicodedata.combining(c))


def number(text):
    text = text.strip().replace('\u00a0', '').replace(' ', '')
    if re.fullmatch(r'\(?-?\d+(?:[,.]\d+)?\)?', text) is None:
        raise ValueError(f'Not an unambiguous number: {text!r}')
    value = float(text.strip('()').replace(',', '.'))
    return -value if text.startswith('(') else value


def lines(words):
    rows = []
    for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
        match = next((r for r in reversed(rows[-5:]) if abs(r[0]['top'] - w['top']) < 3.5), None)
        if match is None:
            rows.append([w])
        else:
            match.append(w)
    return [sorted(r, key=lambda w: w['x0']) for r in rows]


def numeric_groups(row, width):
    """Spaces inside amounts differ from gaps separating financial columns."""
    groups = []
    for w in row:
        w=dict(w,text=w['text'].strip())
        if not re.fullmatch(r'[()\d,.−-]+', w['text']):
            continue
        if groups and w['x0'] - groups[-1][-1]['x1'] < width * .008:
            groups[-1].append(w)
        else:
            groups.append([w])
    result = []
    for group in groups:
        try:
            result.append((number(''.join(w['text'].replace('−', '-') for w in group)),
                           group[0]['x0'], group[-1]['x1']))
        except ValueError:
            pass
    return result


def read_pages(path, cache):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    target = cache / f'{digest}-v2.json'
    if target.exists():
        return json.loads(target.read_text(encoding='utf-8')), digest
    cache.mkdir(parents=True, exist_ok=True)
    pages = []
    with pdfplumber.open(path) as pdf:
        renderer = None
        try:
            for i, p in enumerate(pdf.pages):
                words = p.extract_words(x_tolerance=2)
                text = p.extract_text(x_tolerance=2) or ''
                method = 'native'
                # Image-only tables can coexist with short text headers.
                image_area = sum((im['x1']-im['x0'])*(im['bottom']-im['top']) for im in p.images)
                if len(text.strip()) < 150 or (image_area > p.width*p.height*.6 and len(text)<500):
                    if renderer is None:
                        renderer = pypdfium2.PdfDocument(path)
                    with tempfile.TemporaryDirectory() as tmp:
                        img = Path(tmp) / 'page.png'
                        bitmap = renderer[i].render(scale=3)
                        image = bitmap.to_pil()
                        image.save(img)
                        try:
                            # Remove table rules before OCR: bold amounts enclosed
                            # by borders are otherwise often omitted by Tesseract.
                            import cv2
                            raster=cv2.imread(str(img),cv2.IMREAD_GRAYSCALE)
                            binary=cv2.threshold(raster,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]
                            horizontal=cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(80,1)))
                            vertical=cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,80)))
                            raster[cv2.dilate(horizontal|vertical,cv2.getStructuringElement(cv2.MORPH_RECT,(2,2)))>0]=255
                            cv2.imwrite(str(img),raster)
                            result = subprocess.run(['tesseract', str(img), 'stdout', '-l', 'fra', '--psm', '6', 'tsv'],
                                                    capture_output=True, text=True, encoding='utf-8', check=True, timeout=120)
                            words = []
                            for item in csv.DictReader(io.StringIO(result.stdout), delimiter='\t'):
                                if item['text'].strip() and float(item['conf']) >= 0:
                                    x,y,w,h = [float(item[k])/3 for k in ('left','top','width','height')]
                                    words.append(dict(text=item['text'], x0=x,x1=x+w,top=y,bottom=y+h,conf=float(item['conf'])))
                            text = '\n'.join(' '.join(w['text'] for w in row) for row in lines(words))
                            method = 'ocr'
                        except (FileNotFoundError, subprocess.SubprocessError) as exc:
                            method = 'ocr_failed'
                            text += f'\nOCR unavailable: {type(exc).__name__}'
                        finally:
                            image.close()
                            bitmap.close()
                pages.append(dict(page=i+1,width=p.width,height=p.height,text=text,words=words,method=method))
        finally:
            if renderer is not None:
                renderer.close()
    target.write_text(json.dumps(pages,ensure_ascii=False), encoding='utf-8')
    return pages, digest


def balance(pages, year, source):
    records, issues = {}, []
    for page in pages:
        text = normalize(page['text'])
        if page['page'] > 5:
            continue
        rowlist = lines(page['words'])
        code_count = sum(bool(re.match(r'^(AC|CP|PA)\s*\d', normalize(' '.join(w['text'] for w in row)))) for row in rowlist)
        if code_count < 8:
            continue
        asset = text.count('AC') > text.count('PA')
        # The page must identify N then N-1; no year is inferred from filename alone.
        dates = re.findall(r'31\s*/\s*12\s*/\s*(20\d\d)',text)
        if dates[-2:] != [str(year),str(year-1)]:
            issues.append(dict(type='year_header_unverified',page=page['page'],year=year))
            continue
        unit = 'TND' if 'DINAR' in text and 'MILLIER' not in text else None
        if not asset and unit is None:
            unit = next((r['unit'] for r in records.values() if r['unit']), None)
        active = None
        for row_index,row in enumerate(rowlist):
            label = ' '.join(w['text'] for w in row)
            norm = normalize(label)
            match = re.match(r'^(AC|CP|PA)\s*(\d{1,3})\b',norm)
            code = match.group(1)+match.group(2) if match else None
            if norm.strip()=='ACS':
                code='AC5'
            if 'TOTAL' in norm and 'ACTIF' in norm and 'PASSIF' not in norm:
                code = 'TOTAL_ASSET'
            elif 'TOTAL' in norm and 'CAPITAUX' in norm and 'PASSIF' in norm:
                code = 'TOTAL_EQUITY_LIABILITY'
            elif 'TOTAL' in norm and 'CAPITAUX' in norm and 'AVANT' in norm:
                code = 'EQUITY' if 'AFFECTATION' in norm else 'EQUITY_BEFORE'
            elif re.search(r'TOTAL (DU )?PASSIF',norm):
                code = 'TOTAL_LIABILITY'
            groups = numeric_groups([w for w in row if w['x0'] > page['width']*.36],page['width'])
            expected = 4 if asset else 2
            # Some PDFs put the first total one text line above its label.
            if code=='TOTAL_EQUITY_LIABILITY' and len(groups)==1 and row_index:
                prior=rowlist[row_index-1]
                upper=numeric_groups(prior,page['width'])
                if len(upper)==1 and all(re.fullmatch(r'[\d,.]+',w['text']) for w in prior) and upper[0][1]<groups[0][1]:
                    groups=upper+groups
            if code and len(code)<=3:
                active = code if len(groups)!=expected else None
            if not code and active and len(groups)==expected and not re.search('[A-HJ-Z]',norm):
                code = active
                active = None
            if not code or len(groups)!=expected:
                continue
            value, previous = groups[-2][0], groups[-1][0]
            evidence = dict(code=code,year=year,value=value,previous=previous,unit=unit,
                            source=source,page=page['page'],method=page['method'],source_label=label,
                            bbox=[row[0]['x0'],min(w['top'] for w in row),row[-1]['x1'],max(w['bottom'] for w in row)])
            if code in records and records[code]['value'] != value:
                issues.append(dict(type='duplicate_source_conflict',code=code,year=year,values=[records[code]['value'],value]))
                records[code]['ambiguous'] = True
            else:
                records[code] = evidence
    return records,issues


def premiums(pages, year, source):
    result = {}
    for page in pages:
        text = normalize(page['text'])
        if 'CATEGOR' not in text or 'PRIMES EMISES' not in text:
            continue
        if str(year) not in text or 'DINAR' not in text:
            continue
        nonvie = ('AUTOMOBILE' in text or re.search(r'\bAUTO\b',text)) and 'GROUPE' in text
        if not nonvie and not ('VIE' in text and 'DECES' in text):
            continue
        rowlist=lines(page['words'])
        for row_index,row in enumerate(rowlist):
            label = ' '.join(w['text'] for w in row)
            if not normalize(label).startswith('PRIMES EMISES'):
                continue
            values = numeric_groups([w for w in row if w['x0']>page['width']*.20],page['width'])
            names = ['GROUPE','A_TRAVAIL','INCENDIE','RISQUES_DIVERS','TRANSPORT','AVIATION','AUTOMOBILE','ACCEPTATION','TOTAL_NONVIE'] if nonvie else ['VIE_EPARGNE','DECES','MIXTE','ACCEPTATION_VIE','TOTAL_VIE']
            # Wrapped numbers are grouped by x coordinate within the prime row's
            # vertical band, excluding the next financial measure.
            if not nonvie and len(values)!=5:
                nearby=[w for w in page['words'] if row[0]['top']-8<=w['top']<=row[0]['top']+8 and w['x0']>page['width']*.40 and re.fullmatch(r'[\d,.]+',w['text'])]
                if nearby:
                    clusters=[]
                    for w in sorted(nearby,key=lambda w:w['x0']):
                        if clusters and w['x0']<=max(x['x1'] for x in clusters[-1])+page['width']*.008:
                            clusters[-1].append(w)
                        else: clusters.append([w])
                    values=[]
                    for cluster in clusters:
                        raw=''.join(w['text'] for line in lines(cluster) for w in line)
                        values.append((number(raw),min(w['x0'] for w in cluster),max(w['x1'] for w in cluster)))
            if not nonvie and len(values)==4:
                # Blank acceptation stays absent; validate the disclosed three
                # branches against the separately published life total.
                names=['VIE_EPARGNE','DECES','MIXTE','TOTAL_VIE']
            if len(values)!=len(names):
                continue
            for name,(value,x0,x1) in zip(names,values):
                result[name]=dict(code=name,year=year,value=value,unit='TND',source=source,page=page['page'],
                                  source_label=label,method=page['method'],bbox=[x0,row[0]['top'],x1,max(w['bottom'] for w in row)])
    return result
