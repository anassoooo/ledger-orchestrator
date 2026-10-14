"""Header-only OCR diagnostics for six historical PDFs; reuse STAR OCR caches.

Produces unapproved evidence only, without financial amounts, workbook changes,
cache updates, or profile admission. PDF coordinates are physical page points.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess

import pypdfium2


TARGETS = {'COMAR/2016.pdf': [2, 3], 'COMAR/2018.pdf': [1, 2, 3],
           'STAR/2019.pdf': [2, 3], 'ZITOUNA TAKAFUL/2016.pdf': [2, 3],
           'ZITOUNA TAKAFUL/2018.pdf': [1, 2, 3], 'ZITOUNA TAKAFUL/2020.pdf': [2, 3]}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def header_rows(words):
    rows = {}
    for word in words:
        rows.setdefault((word['block_num'], word['par_num'], word['line_num']), []).append(word)
    result = []
    for row in sorted(rows.values(), key=lambda r: min(float(w['top']) for w in r)):
        row.sort(key=lambda w: float(w['left']))
        text = ' '.join(w['text'] for w in row)
        if (re.search(r'^\W*(?:AC(?:\d+|[IL])?\s|CP\s*[\dIL]|AN\w*\s)', text.upper())
                or re.search(r'ACTIFS? INCORPORELS|CAPITAL SOCIAL', text.upper())
                or re.search(r'\b(?:[3-9]\d{3}|\d{5,})\b', text)):
            break
        result.append({'text': text, 'bbox': [min(float(w['left']) for w in row)/3,
                       min(float(w['top']) for w in row)/3,
                       max(float(w['left'])+float(w['width']) for w in row)/3,
                       max(float(w['top'])+float(w['height']) for w in row)/3],
                       'minimum_word_confidence': min(float(w['conf']) for w in row)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('New output directory required')
    inventory_hash = digest(args.inventory)
    items = {d['file']: d for d in json.loads(args.inventory.read_text(encoding='utf-8'))['documents']}
    for name in TARGETS:
        if digest(args.root / 'data/sources' / name) != items[name]['sha256']:
            raise ValueError('Inventory source hash mismatch')
    args.output.mkdir(parents=True)
    results = []
    for name, numbers in TARGETS.items():
        path = args.root / 'data/sources' / name
        with pypdfium2.PdfDocument(path) as pdf:
            for number in numbers:
                page = pdf[number-1]
                bitmap = page.render(scale=3)
                image = bitmap.to_pil().convert('RGB')
                crop = image.crop((0, 0, image.width, round(image.height*.50)))
                target = args.output / (name.replace('/', '_').replace(' ', '_').replace('.pdf', f'_p{number}.png'))
                crop.save(target)
                command = ['tesseract', str(target), 'stdout', '-l', 'fra', '--psm', '6', 'tsv']
                completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', check=True, timeout=60)
                words = [w for w in csv.DictReader(io.StringIO(completed.stdout), delimiter='\t')
                         if w['text'].strip() and float(w['conf']) >= 0]
                results.append({'file': name, 'source_sha256': items[name]['sha256'], 'page': number,
                                'method': 'header_crop_ocr', 'language': 'fra', 'psm': 6, 'scale': 3,
                                'crop_pdf_bbox': [0, 0, page.get_width(), page.get_height()*.5],
                                'header_lines': header_rows(words), 'image': target.name,
                                'image_sha256': digest(target), 'approved': False})
                print(name, number, flush=True)
                crop.close(); image.close(); bitmap.close()
    reused = []
    for year, pages in [(2023, [2, 3]), (2025, [2])]:
        name = f'STAR/{year}.pdf'
        source = args.root / 'data/sources' / name
        source_hash = digest(source)
        if source_hash != items[name]['sha256']:
            raise ValueError('STAR source differs from inventory')
        cache = args.root / 'outputs/cache' / f'{source_hash}-v2.json'
        contents = json.loads(cache.read_text(encoding='utf-8'))
        for number in pages:
            page = contents[number-1]
            if page['page'] != number or page['method'] != 'ocr':
                raise ValueError('Unexpected cached STAR page/method')
            header = re.split(r'\bAC1\s', page['text'], maxsplit=1)[0] if number == 2 else re.split(r'\bCP1\s', page['text'], maxsplit=1)[0]
            reused.append({'file': name, 'page': number, 'source_sha256': source_hash,
                           'cache_file': cache.name, 'cache_sha256': digest(cache),
                           'method': 'existing_ocr_cache', 'header_text': header,
                           'approved': False, 'financial_values_reextracted': 0})
    for name in TARGETS:
        if digest(args.root / 'data/sources' / name) != items[name]['sha256']:
            raise ValueError('Source changed during OCR')
    for record in reused:
        if digest(args.root / 'data/sources' / record['file']) != record['source_sha256']:
            raise ValueError('Cached STAR source changed during inspection')
        if digest(args.root / 'outputs/cache' / record['cache_file']) != record['cache_sha256']:
            raise ValueError('STAR cache changed during inspection')
    if digest(args.inventory) != inventory_hash:
        raise ValueError('Inventory changed during inspection')
    report = {'scope': 'Header-only OCR diagnostics, not financial/profile qualification',
              'inventory_sha256': inventory_hash,
              'new_ocr_pages': len(results), 'existing_ocr_pages_reused': len(reused),
              'production_changes': 0, 'financial_values_extracted': 0,
              'ocr_headers': results, 'reused_headers': reused}
    (args.output / 'evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
