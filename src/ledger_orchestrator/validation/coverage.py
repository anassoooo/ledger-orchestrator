"""Measure target-cell coverage, not number of writes or project progress."""
from collections import Counter
import openpyxl
from ledger_orchestrator.profiles import CompanyProfile


def measure(path,config,years,writes,issues):
    profile=CompanyProfile.from_dict(config)
    workbook=openpyxl.load_workbook(path,data_only=True)
    written={(w['sheet'],w['cell']) for w in writes}
    conflicts={(i['sheet'],i['cell']) for i in issues if i['type']=='existing_cell_conflict'}
    cells=[]
    for year in years:
        for sheet,cell,code in profile.targets(year):
            value=workbook[sheet][cell].value
            status=('conflict' if (sheet,cell) in conflicts else
                    'missing_or_blocked' if value in (None,'') else
                    'populated_this_run' if (sheet,cell) in written else 'existing_not_revalidated')
            cells.append(dict(year=year,sheet=sheet,cell=cell,code=code,status=status))
    summary=[]
    for year in years:
        for sheet in [profile.workbook['balance_sheet'],profile.workbook['premium_sheet']]:
            selected=[c for c in cells if c['year']==year and c['sheet']==sheet]
            counts=dict(Counter(c['status'] for c in selected))
            summary.append(dict(year=year,sheet=sheet,expected_cells=len(selected),counts=counts))
    return dict(basis=f"Configured target cells including totals; no assumption that unpublished rows are zero. {profile.workbook['details_sheet']} excluded.",
                summary=summary,cells=cells)
