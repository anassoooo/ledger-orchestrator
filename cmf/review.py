"""Explain every unresolved target without declaring undetected rows absent."""
import csv


def build_review(coverage,annual,config,issues):
    rows=[]
    for cell in coverage['cells']:
        if cell['status']=='populated_this_run':
            continue
        year,code=cell['year'],cell['code']
        data=annual[year]
        record=data['records'].get(code)
        presence=data.get('presence',{}).get(code,{})
        linked=[i for i in issues if i.get('year')==year and i.get('code')==code]
        children=config['children'].get(code,[])
        blocked=[c for c in children if not data['records'].get(c,{}).get('approved')]
        if cell['status']=='conflict':
            reason='Valeur existante différente, conservée'
            action='Arbitrer le conflit entre les deux montants du rapport'
            category='conflit_existant'
        elif cell['status']=='existing_not_revalidated':
            reason='Valeur antérieure non revalidée par cette exécution'
            action='Rapprocher la valeur existante de sa source'
            category='valeur_existante'
        elif record and any(c['status']=='blocked' for c in record.get('note_checks',[])):
            failed=[c for c in record['note_checks'] if c['status']=='blocked']
            reason='Contrôle arithmétique source échoué : '+', '.join(str(c.get('delta'))+' TND' for c in failed)
            action='Comparer bilan et note avant décision ; ne pas ajuster le montant'
            category='incoherence_source'
        elif children:
            reason='Total non calculable avec les détails actuellement validés'
            action='Fiabiliser les composantes et rapprocher le total publié'
            category='total_bloque'
        elif record:
            reason='Montant extrait mais preuve ou contrôle insuffisant'
            action='Rechercher une corroboration ou résoudre le contrôle bloquant'
            category='preuve_insuffisante'
        elif presence.get('status')=='absent_on_native_balance_page':
            reason='Rubrique absente de la page de bilan native dont les dates et les codes ont été contrôlés'
            action='Conserver la cellule vide ; ne pas conclure à un montant nul ou à une absence dans toutes les notes'
            category='absent_du_bilan_natif'
        elif presence.get('status')=='present':
            reason='Code présent dans le bilan natif, mais aucun montant admissible extrait'
            action='Examiner la ligne et ses colonnes ; distinguer un tiret, un blanc et un montant non reconnu'
            category='ligne_presente_sans_montant'
        else:
            reason='Aucun montant admissible détecté pour cette rubrique'
            action='Vérifier la présence dans le PDF ; absence de détection ne signifie pas zéro'
            category='non_detecte'
        rows.append(dict(**cell,category=category,reason=reason,action=action,
                         source=record.get('source','') if record else presence.get('source',f'sources/STAR/{year}.pdf'),
                         page=record.get('page','') if record else presence.get('page',''),
                         presence_evidence=presence,
                         dependencies=blocked,issue_types=[i['type'] for i in linked]))
    return rows


def export_review(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream,delimiter=';')
        writer.writerow(['Exercice','Feuille','Cellule','Rubrique','Catégorie','Motif','Action','Source','Page','Dépendances non validées'])
        for r in rows:
            writer.writerow([r['year'],r['sheet'],r['cell'],r['code'],r['category'],r['reason'],
                             r['action'],r['source'],r['page'],', '.join(r['dependencies'])])
