"""Constrained workbook writer with guarded accounting totals."""
import copy
import re
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter, column_index_from_string

from ledger_orchestrator.profiles import CompanyProfile
from ledger_orchestrator.workbook.recalculation import recalculate


def set_column_width(sheet,index,width):
    """Split grouped dimensions without expanding a range through column XFD."""
    dimensions=sheet.column_dimensions
    for key,dim in list(dimensions.items()):
        first_column=dim.min or column_index_from_string(key)
        last_column=dim.max or first_column
        if first_column<=index<=last_column:
            del dimensions[key]
            for first,last in [(first_column,index-1),(index,index),(index+1,last_column)]:
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


def guarded_sum(refs,admitted=True):
    args=','.join(refs)
    condition=f'COUNT({args})={len(refs)}'
    if not admitted:
        condition=f'AND(FALSE,{condition})'
    return f'=IF({condition},SUM({args}),"")'


def write_workbook(template,path,config,annual,confirmations=None):
    profile=CompanyProfile.from_dict(config)
    profile.select_years(list(annual))
    layout=profile.workbook
    balance_sheet,premium_sheet=layout['balance_sheet'],layout['premium_sheet']
    wb=openpyxl.load_workbook(template)
    for anchor in layout['anchors']:
        if anchor['sheet'] not in wb or wb[anchor['sheet']][anchor['cell']].value!=anchor['value']:
            raise ValueError(f"Unrecognized template anchor: {anchor['sheet']}!{anchor['cell']}")
    original={(s.title,c.coordinate):(c.value,copy.copy(c._style)) for s in wb for row in s for c in row}
    writes=[]
    issues=[]
    allowed=set()
    addresses={}
    for year in annual:
        for section,width in layout['column_widths'].items():
            sheet=premium_sheet if section=='premium' else balance_sheet
            set_column_width(wb[sheet],column_index_from_string(profile.column(year,section)),width)
    support=None
    if config['extend_template']:
        if layout['details_sheet'] in wb:
            raise ValueError(f"Use the original template; {layout['details_sheet']} already exists")
        support=wb.create_sheet(layout['details_sheet'])
        support.append([layout['details_title'],'Libellé'])
        for year in sorted(config['years']):
            support[f'{profile.column(year,"details")}1']=year
        support.freeze_panes='C2'
        support.column_dimensions['A'].width=25
        support.column_dimensions['B'].width=72
        for year in config['years']: support.column_dimensions[profile.column(year,'details')].width=20
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
    def put(sheet,coord,value,year,code,sources=None,replace_formula=False,computed=None):
        cell=wb[sheet][coord]
        old=cell.value
        # An existing typed total equal to the published or computed total (both
        # reconciled within tolerance) is confirmed, not overwritten and not a conflict.
        if computed is not None and type(old) in (int,float) and old in computed:
            if confirmations is not None:
                confirmations.append(dict(sheet=sheet,cell=coord,year=year,code=code,value=old,sources=sources or []))
            return True
        if old is not None and old!=value and not (replace_formula and cell.data_type=='f'):
            issues.append(dict(type='existing_cell_conflict',sheet=sheet,cell=coord,year=year,code=code,existing=old,proposed=value))
            return False
        if old==value and confirmations is not None:
            confirmations.append(dict(sheet=sheet,cell=coord,year=year,code=code,value=old,sources=sources or []))
        if old!=value:
            cell.value=value
            cell.number_format='#,##0;[Red](#,##0);0'
            allowed.add((sheet,coord))
            writes.append(dict(sheet=sheet,cell=coord,year=year,code=code,old=old,new=value,sources=sources or []))
        return True
    for year,data in annual.items():
        for code,row in config['asset_rows'].items():
            addresses[year,code]=(balance_sheet,f'{profile.column(year,"asset")}{row}')
        for code,row in config['liability_rows'].items():
            exception=layout['extension_only'].get(code)
            if exception and not config['extend_template']:
                issues.append(dict(type='template_label_mismatch',year=year,code=code,
                                   existing=wb[exception['sheet']][exception['cell']].value,expected=exception['expected']))
                continue
            addresses[year,code]=(balance_sheet,f'{profile.column(year,"liability")}{row}')
        if support:
            for i,code in enumerate(extra,2):
                addresses[year,code]=(layout['details_sheet'],f'{profile.column(year,"details")}{i}')
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
                # The published total or the sum of its validated details.
                computed={record['value'],data['validation']['computed'].get(code)}
            else:
                value=record['value']
                computed=None
            success=put(sheet,coord,value,year,code,[record],computed=computed)
            if success: done.add(code)
            return success
        for code in data['records']:
            emit(code)
        admitted_branches=set()
        for code,record in data['branches'].items():
            if not record['sources'] or not all(s.get('approved',False) for s in record['sources']):
                continue
            coord=f'{profile.column(year,"premium")}{config["branch_rows"][code]}'
            if put(premium_sheet,coord,record['value'],year,code,record['sources']):
                admitted_branches.add(code)
        col=profile.column(year,'premium')
        premium_rows={**config['branch_rows'],**{code:t['row'] for code,t in layout['premium_totals'].items()}}
        total_results={}
        def emit_premium_total(code):
            if code in admitted_branches:
                return True
            if code in total_results:
                return total_results[code]
            total=layout['premium_totals'].get(code)
            if total is None:
                return False
            admission=[emit_premium_total(child) for child in total['children']]
            admitted=all(admission)
            refs=[f'{col}{premium_rows[child]}' for child in total['children']]
            # Only explicitly configured totals may replace an existing formula.
            success=put(premium_sheet,f'{col}{total["row"]}',guarded_sum(refs,admitted),year,code,replace_formula=True)
            if not admitted:
                issues.append(dict(type='premium_total_dependency_missing',year=year,code=code,
                                   children=[child for child,ok in zip(total['children'],admission) if not ok]))
            total_results[code]=admitted and success
            return total_results[code]
        for code in layout['premium_totals']:
            emit_premium_total(code)
    # Label corrections belong to the versioned template profile.
    if config['extend_template']:
        for item in layout['label_overrides']:
            wb[item['sheet']][item['cell']]=item['value']
            allowed.add((item['sheet'],item['cell']))
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
