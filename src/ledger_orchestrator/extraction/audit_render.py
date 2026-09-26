"""Render original source pages for visual audit; no workbook writes."""
from pathlib import Path
import pypdfium2


def main():
    output=Path('outputs/audit_cellules_20260917/pages')
    output.mkdir(parents=True,exist_ok=True)
    for year,pages in [(2023,[36]),(2024,[3]),(2025,[2,3,27,45])]:
        doc=pypdfium2.PdfDocument(f'data/sources/STAR/{year}.pdf')
        try:
            for number in pages:
                page=doc[number-1]
                bitmap=page.render(scale=2)
                im=bitmap.to_pil()
                im.save(output/f'{year}_p{number}.png')
                im.close()
                bitmap.close()
                page.close()
        finally:
            doc.close()


if __name__=='__main__':
    main()
