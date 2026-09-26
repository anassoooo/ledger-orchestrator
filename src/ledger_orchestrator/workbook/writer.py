"""Constrained workbook writer with guarded accounting totals."""
import copy
import re
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from ledger_orchestrator.workbook.recalculation import recalculate


def set_column_width(sheet,index,width):
    """Split grouped dimensions without expanding a range through column XFD."""
    dimensions=sheet.column_dimensions
    for key,dim in list(dimensions.items()):
        if dim.min<=index<=dim.max:
            del dimensions[key]
            for first,last in [(dim.min,index-1),(index,index),(index+1,dim.max)]:
                if first>last:
                    continue
                clone=copy.copy(dim)
                clone.index=get_column_letter(first)
                clone.min,clone.max=first,last
                if first==last==index:
                    clone.width=width
                dimensions[clone.index]=clone
            return
    dimensions[get_column_letter(index)].width=width


def guarded_sum(refs):
    args=','.join(refs)
    return f'=IF(COUNT({args})={len(refs)},SUM({args}),"")'


def write_workbook(template,path,config,annual):
    wb=openpyxl.load_workbook(template)
    if wb['TAF_G1']['A51'].value!='STAR' or wb['TAF_G3']['B1'].value!='STAR':
        raise ValueError('Unrecognized template: STAR section moved')
    original={(s.title,c.coordinate):(c.value,copy.copy(c._style)) for s in wb for row in s for c in row}
    writes=[]
    issues=[]
    allowed=set()
    addresses={}
    for year in annual:
        set_column_width(wb['TAF_G1'],2036-year,19)
        set_column_width(wb['TAF_G3'],year-2008,18)
    support=None
    if config['extend_template']:
        if 'STAR_Details' in wb:
            raise ValueError('Use the original template; STAR_Details already exists')
        support=wb.create_sheet('STAR_Details')
        support.append(['Compléments du bilan STAR (TND)','Libellé',2023,2024,2025])
        support.freeze_panes='C2'
        support.column_dimensions['A'].width=25
        support.column_dimensions['B'].width=72
        for col in 'CDE': support.column_dimensions[col].width=20
        for c in support[1]:
            c.font=Font(bold=True,color='FFFFFF')
            c.fill=PatternFill('solid',fgColor='17365D')
            c.alignment=Alignment(wrap_text=True)
        support.row_dimensions[1].height=34
    known=set(config['asset_rows'])|set(config['liability_rows'])
    extra=sorted({k for data in annual.values() for k in data['records'] if k not in known})
    if support:
        for i,code in enumerate(extra,2):
            record=next(d['records'][code] for d in annual.values() if code in d['records'])
            label=re.sub(r'\s+[-(]?\d[\d\s.,()-]*$','',record['source_label']).strip()
            support.cell(i,1,code)
            support.cell(i,2,label[:120])
            support.cell(i,2).alignment=Alignment(wrap_text=True)
            support.row_dimensions[i].height=30
    def put(sheet,coord,value,year,code,sources=None,replace_formula=False):
        cell=wb[sheet][coord]
        old=cell.value
        if old is not None and old!=value and not (replace_formula and cell.data_type=='f'):
            issues.append(dict(type='existing_cell_conflict',sheet=sheet,cell=coord,year=year,code=code,existing=old,proposed=value))
            return False
        if old!=value:
            cell.value=value
            cell.number_format='#,##0;[Red](#,##0);0'
            allowed.add((sheet,coord))
            writes.append(dict(sheet=sheet,cell=coord,year=year,code=code,old=old,new=value,sources=sources or []))
        return True
    for year,data in annual.items():
        for code,row in config['asset_rows'].items():
            addresses[year,code]=('TAF_G1',f'{get_column_letter(2028-year)}{row}')
        for code,row in config['liability_rows'].items():
            if code=='PA710' and not config['extend_template']:
                issues.append(dict(type='template_label_mismatch',year=year,code=code,
                                   existing=wb['TAF_G1']['I85'].value,expected='Report de commissions reçues des réassureurs'))
                continue
            addresses[year,code]=('TAF_G1',f'{get_column_letter(2036-year)}{row}')
        if support:
            for i,code in enumerate(extra,2):
                addresses[year,code]=('STAR_Details',f'{get_column_letter(year-2020)}{i}')
        done=set()
        def emit(code):
            if code in done:
                return True
            if code not in data['validation']['eligible'] or (year,code) not in addresses:
                return False
            record=data['records'].get(code)
            if not record or not record.get('approved',False):
                return False
            deps=data['validation']['dependencies'].get(code)
            sheet,coord=addresses[year,code]
            if deps:
                if not all(emit(c) for c in deps):
                    issues.append(dict(type='total_dependency_missing',year=year,code=code))
                    return False
                refs=[f"'{addresses[year,c][0]}'!{addresses[year,c][1]}" for c in deps]
                value=guarded_sum(refs)
            else:
                value=record['value']
            success=put(sheet,coord,value,year,code,[record])
            if success: done.add(code)
            return success
        for code in data['records']:
            emit(code)
        for code,record in data['branches'].items():
            if not all(s.get('approved',False) for s in record['sources']):
                continue
            coord=f'{get_column_letter(year-2008)}{config["branch_rows"][code]}'
            put('TAF_G3',coord,record['value'],year,code,record['sources'])
        col=get_column_letter(year-2008)
        # Display full TND amounts instead of Excel's overflow markers (####).
        for row,refs in [(9,[f'{col}{r}' for r in range(4,9)]),(11,[f'{col}10']),(12,[f'{col}9',f'{col}11'])]:
            # Explicitly authorized totals: preserve formulas but add missing-input guard.
            put('TAF_G3',f'{col}{row}',guarded_sum(refs),year,f'TOTAL_{row}',replace_formula=True)
    # Correct only the STAR labels for which the mapping explicitly changes code.
    if config['extend_template']:
        for cell,label in [('I58',"CP6 Résultat de l'exercice"),('I71','PA360 Autres provisions techniques (vie)'),
                           ('I85','PA710 Report de commissions reçues des réassureurs')]:
            wb['TAF_G1'][cell]=label
            allowed.add(('TAF_G1',cell))
    for (sheet,coord),(value,style) in original.items():
        if (sheet,coord) not in allowed:
            cell=wb[sheet][coord]
            if cell.value!=value or cell._style!=style:
                raise RuntimeError(f'Unexpected modification: {sheet}!{coord}')
    wb.save(path)
    recalculate(path)
    reopened=openpyxl.load_workbook(path,data_only=False)
    for (sheet,coord),(value,style) in original.items():
        if (sheet,coord) not in allowed and reopened[sheet][coord].value!=value:
            raise RuntimeError(f'Export changed {sheet}!{coord}')
    return writes,issues
