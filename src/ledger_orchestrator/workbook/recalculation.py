"""Recalculate in LibreOffice while preserving the original workbook structure."""

import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import openpyxl

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'


def recalculate(path):
    """Only import result caches from LibreOffice, never its altered styles/formulas."""
    with tempfile.TemporaryDirectory() as temp:
        dest=Path(temp)/'recalculated'
        dest.mkdir()
        profile=(Path(temp)/'profile').as_uri()
        run=subprocess.run(['libreoffice',f'-env:UserInstallation={profile}','--headless','--convert-to','xlsx',
                            '--outdir',str(dest),str(path)],capture_output=True,text=True,timeout=120)
        calc=dest/path.name
        if run.returncode or not calc.exists():
            raise RuntimeError(f'LibreOffice recalculation failed: {run.stdout} {run.stderr}')
        values=openpyxl.load_workbook(calc,data_only=True)
        formulas=openpyxl.load_workbook(path,data_only=False)
        replacement={}
        with zipfile.ZipFile(path) as zin:
            for index,sheet in enumerate(formulas,1):
                part=f'xl/worksheets/sheet{index}.xml'
                tree=ET.fromstring(zin.read(part))
                for cell in tree.iter(f'{{{NS}}}c'):
                    if cell.find(f'{{{NS}}}f') is None:
                        continue
                    coord=cell.attrib['r']
                    value=values[sheet.title][coord].value
                    for old in list(cell):
                        if old.tag in (f'{{{NS}}}v',f'{{{NS}}}is'):
                            cell.remove(old)
                    if value is None or value=='':
                        cell.set('t','str')
                        ET.SubElement(cell,f'{{{NS}}}v').text=''
                    elif isinstance(value,(int,float)):
                        cell.attrib.pop('t',None)
                        ET.SubElement(cell,f'{{{NS}}}v').text=str(value)
                    elif isinstance(value,str) and value.startswith(('#REF!','#DIV/0!','#VALUE!','#NAME?','#NUM!')):
                        raise RuntimeError(f'Recalculation error {sheet.title}!{coord}: {value}')
                    else:
                        cell.set('t','str')
                        ET.SubElement(cell,f'{{{NS}}}v').text=str(value)
                replacement[part]=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
            staged=Path(temp)/'result.xlsx'
            with zipfile.ZipFile(staged,'w',zipfile.ZIP_DEFLATED) as zout:
                for member in zin.infolist():
                    zout.writestr(member,replacement.get(member.filename,zin.read(member.filename)))
        path.write_bytes(staged.read_bytes())
