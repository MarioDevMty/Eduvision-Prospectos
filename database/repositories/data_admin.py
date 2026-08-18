from database.connection import get_connection
from services.data_validation import validate_email_address
from services.normalization import normalize_email, normalize_text

ORGANIZATION_TYPES=('INSTITUCION_EDUCATIVA','EMPRESA','DEPENDENCIA_GOBIERNO','MUNICIPIO','ASOCIACION','PROVEEDOR','OTRO')


def _audit(c,user_id,entity_type,entity_id,action,field_name='',old_value=None,new_value=None):
    c.execute("""INSERT INTO audit_log (user_id,entity_type,entity_id,action,field_name,old_value,new_value)
                 VALUES (?,?,?,?,?,?,?)""",
              (user_id,entity_type,entity_id,action,field_name or None,
               None if old_value is None else str(old_value),None if new_value is None else str(new_value)))


def get_organization_management_summary(organization_id:int)->dict|None:
    with get_connection() as c:
        org=c.execute('SELECT * FROM organizations WHERE id=?',(organization_id,)).fetchone()
        if org is None:return None
        cc=c.execute("""SELECT COUNT(*) total,SUM(CASE WHEN status<>'BAJA' THEN 1 ELSE 0 END) active,
                        SUM(CASE WHEN status='BAJA' THEN 1 ELSE 0 END) inactive FROM campuses WHERE organization_id=?""",
                     (organization_id,)).fetchone()
        tc=c.execute("""SELECT COUNT(*) total,SUM(CASE WHEN status<>'BAJA' THEN 1 ELSE 0 END) active,
                        SUM(CASE WHEN status<>'BAJA' AND campus_id IS NULL THEN 1 ELSE 0 END) direct_active
                        FROM contacts WHERE organization_id=?""",(organization_id,)).fetchone()
        ae=c.execute("""SELECT COUNT(*) FROM emails e WHERE e.status='ACTIVO' AND
                      ((e.entity_type='CAMPUS' AND e.entity_id IN (SELECT id FROM campuses WHERE organization_id=?)) OR
                       (e.entity_type='CONTACT' AND e.entity_id IN (SELECT id FROM contacts WHERE organization_id=?)))""",
                     (organization_id,organization_id)).fetchone()[0]
        ie=c.execute("""SELECT COUNT(*) FROM emails e WHERE e.status<>'ACTIVO' AND
                      ((e.entity_type='CAMPUS' AND e.entity_id IN (SELECT id FROM campuses WHERE organization_id=?)) OR
                       (e.entity_type='CONTACT' AND e.entity_id IN (SELECT id FROM contacts WHERE organization_id=?)))""",
                     (organization_id,organization_id)).fetchone()[0]
    d=dict(org); d.update({'campuses_total':cc['total'] or 0,'campuses_active':cc['active'] or 0,
        'campuses_inactive':cc['inactive'] or 0,'contacts_total':tc['total'] or 0,'contacts_active':tc['active'] or 0,
        'direct_contacts_active':tc['direct_active'] or 0,'active_emails':ae or 0,'inactive_emails':ie or 0}); return d


def update_organization(organization_id:int,official_name:str,organization_type:str,subsystem:str,sector:str,
                        relationship_type:str,status:str,user_id:int)->None:
    name=(official_name or '').strip()
    if not name:raise ValueError('El nombre de la organización es obligatorio.')
    if organization_type and organization_type not in ORGANIZATION_TYPES:raise ValueError('Tipo de organización no válido.')
    n=normalize_text(name)
    with get_connection() as c:
        cur=c.execute('SELECT * FROM organizations WHERE id=?',(organization_id,)).fetchone()
        if cur is None:raise ValueError('La organización no existe.')
        if c.execute('SELECT id FROM organizations WHERE normalized_name=? AND id<>? LIMIT 1',(n,organization_id)).fetchone():
            raise ValueError('Ya existe otra organización con el mismo nombre normalizado.')
        vals={'official_name':name,'normalized_name':n,'organization_type':organization_type or None,
              'subsystem':(subsystem or '').strip() or None,'sector':(sector or '').strip() or None,
              'relationship_type':(relationship_type or '').strip() or None,'status':status}
        for f,nv in vals.items():
            if cur[f]!=nv:_audit(c,user_id,'ORGANIZATION',organization_id,'UPDATE',f,cur[f],nv)
        c.execute("""UPDATE organizations SET official_name=?,normalized_name=?,organization_type=?,subsystem=?,sector=?,
                     relationship_type=?,status=?,updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                  (vals['official_name'],vals['normalized_name'],vals['organization_type'],vals['subsystem'],vals['sector'],
                   vals['relationship_type'],vals['status'],user_id,organization_id)); c.commit()


def get_organization_campuses(organization_id:int,include_inactive:bool=True)->list:
    q="""SELECT ca.*,(SELECT GROUP_CONCAT(e.email,' | ') FROM emails e WHERE e.entity_type='CAMPUS' AND e.entity_id=ca.id AND e.status='ACTIVO') active_emails
         FROM campuses ca WHERE ca.organization_id=?"""
    if not include_inactive:q+=" AND ca.status<>'BAJA'"
    q+=' ORDER BY ca.campus_name'
    with get_connection() as c:return c.execute(q,(organization_id,)).fetchall()


def get_campus_management_detail(campus_id:int)->dict|None:
    with get_connection() as c:
        r=c.execute("""SELECT ca.*,o.official_name FROM campuses ca JOIN organizations o ON o.id=ca.organization_id WHERE ca.id=?""",(campus_id,)).fetchone()
        if r is None:return None
        em=c.execute("""SELECT id,email,normalized_email,email_type,is_primary,status,created_at FROM emails
                        WHERE entity_type='CAMPUS' AND entity_id=? ORDER BY CASE WHEN status='ACTIVO' THEN 0 ELSE 1 END,is_primary DESC,id""",
                     (campus_id,)).fetchall()
    d=dict(r);d['emails']=[dict(x) for x in em];return d


def update_campus(campus_id:int,campus_name:str,campus_type:str,campus_code:str,address:str,neighborhood:str,
                  postal_code:str,municipality:str,state:str,website:str,status:str,user_id:int)->None:
    name=(campus_name or '').strip()
    if not name:raise ValueError('El nombre del plantel es obligatorio.')
    with get_connection() as c:
        cur=c.execute('SELECT * FROM campuses WHERE id=?',(campus_id,)).fetchone()
        if cur is None:raise ValueError('El plantel no existe.')
        vals={'campus_name':name,'normalized_name':normalize_text(name),'campus_type':(campus_type or '').strip() or None,
              'campus_code':(campus_code or '').strip() or None,'address':(address or '').strip() or None,
              'neighborhood':(neighborhood or '').strip() or None,'postal_code':(postal_code or '').strip() or None,
              'municipality':(municipality or '').strip() or None,'state':(state or '').strip() or None,
              'website':(website or '').strip() or None,'status':status}
        for f,nv in vals.items():
            if cur[f]!=nv:_audit(c,user_id,'CAMPUS',campus_id,'UPDATE',f,cur[f],nv)
        c.execute("""UPDATE campuses SET campus_name=?,normalized_name=?,campus_type=?,campus_code=?,address=?,neighborhood=?,
                     postal_code=?,municipality=?,state=?,website=?,status=?,updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                  (vals['campus_name'],vals['normalized_name'],vals['campus_type'],vals['campus_code'],vals['address'],vals['neighborhood'],
                   vals['postal_code'],vals['municipality'],vals['state'],vals['website'],vals['status'],user_id,campus_id));c.commit()


def get_organization_contacts(organization_id:int,include_inactive:bool=True)->list:
    q="""SELECT co.*,ca.campus_name,CASE WHEN co.campus_id IS NULL THEN 'ORGANIZACION' ELSE 'PLANTEL' END contact_scope,
         (SELECT GROUP_CONCAT(e.email,' | ') FROM emails e WHERE e.entity_type='CONTACT' AND e.entity_id=co.id AND e.status='ACTIVO') active_emails
         FROM contacts co LEFT JOIN campuses ca ON ca.id=co.campus_id WHERE co.organization_id=?"""
    if not include_inactive:q+=" AND co.status<>'BAJA'"
    q+=' ORDER BY CASE WHEN co.campus_id IS NULL THEN 0 ELSE 1 END,ca.campus_name,co.full_name'
    with get_connection() as c:return c.execute(q,(organization_id,)).fetchall()


def get_contact_management_detail(contact_id:int)->dict|None:
    with get_connection() as c:
        r=c.execute("""SELECT co.*,o.official_name,ca.campus_name FROM contacts co JOIN organizations o ON o.id=co.organization_id
                       LEFT JOIN campuses ca ON ca.id=co.campus_id WHERE co.id=?""",(contact_id,)).fetchone()
        if r is None:return None
        em=c.execute("""SELECT id,email,normalized_email,email_type,is_primary,status,created_at FROM emails
                        WHERE entity_type='CONTACT' AND entity_id=? ORDER BY CASE WHEN status='ACTIVO' THEN 0 ELSE 1 END,is_primary DESC,id""",
                     (contact_id,)).fetchall()
    d=dict(r);d['emails']=[dict(x) for x in em];return d


def update_contact(contact_id:int,full_name:str,position:str,area:str,notes:str,status:str,user_id:int)->None:
    name=(full_name or '').strip()
    if not name:raise ValueError('El nombre del contacto es obligatorio.')
    with get_connection() as c:
        cur=c.execute('SELECT * FROM contacts WHERE id=?',(contact_id,)).fetchone()
        if cur is None:raise ValueError('El contacto no existe.')
        vals={'full_name':name,'position':(position or '').strip() or None,'area':(area or '').strip() or None,
              'notes':(notes or '').strip() or None,'status':status}
        for f,nv in vals.items():
            if cur[f]!=nv:_audit(c,user_id,'CONTACT',contact_id,'UPDATE',f,cur[f],nv)
        c.execute("""UPDATE contacts SET full_name=?,position=?,area=?,notes=?,status=?,updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                  (vals['full_name'],vals['position'],vals['area'],vals['notes'],vals['status'],user_id,contact_id));c.commit()


def _add_email(entity_type,entity_id,email_address,email_type,is_primary,user_id):
    ok,reason=validate_email_address(email_address)
    if not ok:raise ValueError(reason)
    n=normalize_email(email_address)
    with get_connection() as c:
        if c.execute("SELECT id FROM emails WHERE entity_type=? AND entity_id=? AND normalized_email=? AND status='ACTIVO' LIMIT 1",
                     (entity_type,entity_id,n)).fetchone():raise ValueError('El correo ya existe como activo en este registro.')
        if is_primary:c.execute('UPDATE emails SET is_primary=0 WHERE entity_type=? AND entity_id=?',(entity_type,entity_id))
        cur=c.execute("""INSERT INTO emails (entity_type,entity_id,email,normalized_email,email_type,is_primary,status,created_by)
                         VALUES (?,?,?,?,?,?,'ACTIVO',?)""",
                      (entity_type,entity_id,email_address.strip().lower(),n,email_type or 'INSTITUCIONAL',int(is_primary),user_id))
        eid=int(cur.lastrowid);_audit(c,user_id,'EMAIL',eid,'CREATE','email',None,email_address.strip().lower());c.commit();return eid


def _update_email(entity_type,email_id,email_address,email_type,is_primary,status,user_id):
    ok,reason=validate_email_address(email_address)
    if not ok:raise ValueError(reason)
    n=normalize_email(email_address)
    with get_connection() as c:
        cur=c.execute('SELECT * FROM emails WHERE id=? AND entity_type=?',(email_id,entity_type)).fetchone()
        if cur is None:raise ValueError('El correo no existe.')
        if c.execute("SELECT id FROM emails WHERE entity_type=? AND entity_id=? AND normalized_email=? AND status='ACTIVO' AND id<>? LIMIT 1",
                     (entity_type,cur['entity_id'],n,email_id)).fetchone():raise ValueError('El correo ya existe como activo en este registro.')
        if is_primary:c.execute('UPDATE emails SET is_primary=0 WHERE entity_type=? AND entity_id=? AND id<>?',(entity_type,cur['entity_id'],email_id))
        vals={'email':email_address.strip().lower(),'normalized_email':n,'email_type':email_type or 'INSTITUCIONAL','is_primary':int(is_primary),'status':status}
        for f,nv in vals.items():
            if cur[f]!=nv:_audit(c,user_id,'EMAIL',email_id,'UPDATE',f,cur[f],nv)
        c.execute('UPDATE emails SET email=?,normalized_email=?,email_type=?,is_primary=?,status=? WHERE id=?',
                  (vals['email'],vals['normalized_email'],vals['email_type'],vals['is_primary'],vals['status'],email_id));c.commit()


def _deactivate(entity_type,email_id,user_id,reason):
    reason=(reason or '').strip()
    if not reason:raise ValueError('El motivo es obligatorio.')
    with get_connection() as c:
        cur=c.execute('SELECT * FROM emails WHERE id=? AND entity_type=?',(email_id,entity_type)).fetchone()
        if cur is None:raise ValueError('El correo no existe.')
        c.execute("UPDATE emails SET status='INACTIVO',is_primary=0 WHERE id=?",(email_id,));
        _audit(c,user_id,'EMAIL',email_id,'DEACTIVATE','status',cur['status'],f'INACTIVO | Motivo: {reason}');c.commit()


def _reactivate(entity_type,email_id,user_id):
    with get_connection() as c:
        cur=c.execute('SELECT * FROM emails WHERE id=? AND entity_type=?',(email_id,entity_type)).fetchone()
        if cur is None:raise ValueError('El correo no existe.')
        ok,reason=validate_email_address(cur['email'])
        if not ok:raise ValueError(f'No puede reactivarse: {reason}')
        c.execute("UPDATE emails SET status='ACTIVO' WHERE id=?",(email_id,));_audit(c,user_id,'EMAIL',email_id,'REACTIVATE','status',cur['status'],'ACTIVO');c.commit()


def _primary(entity_type,email_id,user_id):
    with get_connection() as c:
        cur=c.execute('SELECT * FROM emails WHERE id=? AND entity_type=?',(email_id,entity_type)).fetchone()
        if cur is None:raise ValueError('El correo no existe.')
        if cur['status']!='ACTIVO':raise ValueError('Solo un correo activo puede ser principal.')
        c.execute('UPDATE emails SET is_primary=0 WHERE entity_type=? AND entity_id=?',(entity_type,cur['entity_id']))
        c.execute('UPDATE emails SET is_primary=1 WHERE id=?',(email_id,));_audit(c,user_id,'EMAIL',email_id,'SET_PRIMARY','is_primary',cur['is_primary'],1);c.commit()


def add_validated_email(campus_id,email_address,email_type,is_primary,user_id):return _add_email('CAMPUS',campus_id,email_address,email_type,is_primary,user_id)
def update_email(email_id,email_address,email_type,is_primary,status,user_id):return _update_email('CAMPUS',email_id,email_address,email_type,is_primary,status,user_id)
def deactivate_email(email_id,user_id,reason):return _deactivate('CAMPUS',email_id,user_id,reason)
def reactivate_email(email_id,user_id):return _reactivate('CAMPUS',email_id,user_id)
def set_primary_email(email_id,user_id):return _primary('CAMPUS',email_id,user_id)
def add_validated_contact_email(contact_id,email_address,email_type,is_primary,user_id):return _add_email('CONTACT',contact_id,email_address,email_type,is_primary,user_id)
def update_contact_email(email_id,email_address,email_type,is_primary,status,user_id):return _update_email('CONTACT',email_id,email_address,email_type,is_primary,status,user_id)
def deactivate_contact_email(email_id,user_id,reason):return _deactivate('CONTACT',email_id,user_id,reason)
def reactivate_contact_email(email_id,user_id):return _reactivate('CONTACT',email_id,user_id)
def set_primary_contact_email(email_id,user_id):return _primary('CONTACT',email_id,user_id)


def reset_organization_data(organization_id:int,user_id:int,reason:str)->dict:
    reason=(reason or '').strip()
    if not reason:raise ValueError('El motivo del reinicio es obligatorio.')
    with get_connection() as c:
        org=c.execute('SELECT * FROM organizations WHERE id=?',(organization_id,)).fetchone()
        if org is None:raise ValueError('La organización no existe.')
        campuses=c.execute("SELECT id,status FROM campuses WHERE organization_id=? AND status<>'BAJA'",(organization_id,)).fetchall()
        contacts=c.execute("SELECT id,status FROM contacts WHERE organization_id=? AND status<>'BAJA'",(organization_id,)).fetchall()
        emails=c.execute("""SELECT id,status FROM emails WHERE
          (entity_type='CAMPUS' AND entity_id IN (SELECT id FROM campuses WHERE organization_id=?)) OR
          (entity_type='CONTACT' AND entity_id IN (SELECT id FROM contacts WHERE organization_id=?))""",(organization_id,organization_id)).fetchall()
        phones=c.execute("""SELECT id,status FROM phones WHERE
          (entity_type='CAMPUS' AND entity_id IN (SELECT id FROM campuses WHERE organization_id=?)) OR
          (entity_type='CONTACT' AND entity_id IN (SELECT id FROM contacts WHERE organization_id=?))""",(organization_id,organization_id)).fetchall()
        try:
            c.execute('BEGIN')
            c.execute("""UPDATE emails SET status='INACTIVO',is_primary=0 WHERE
              (entity_type='CAMPUS' AND entity_id IN (SELECT id FROM campuses WHERE organization_id=?)) OR
              (entity_type='CONTACT' AND entity_id IN (SELECT id FROM contacts WHERE organization_id=?))""",(organization_id,organization_id))
            c.execute("""UPDATE phones SET status='INACTIVO',is_primary=0 WHERE
              (entity_type='CAMPUS' AND entity_id IN (SELECT id FROM campuses WHERE organization_id=?)) OR
              (entity_type='CONTACT' AND entity_id IN (SELECT id FROM contacts WHERE organization_id=?))""",(organization_id,organization_id))
            c.execute("UPDATE contacts SET status='BAJA',updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE organization_id=? AND status<>'BAJA'",(user_id,organization_id))
            c.execute("UPDATE campuses SET status='BAJA',updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE organization_id=? AND status<>'BAJA'",(user_id,organization_id))
            for r in campuses:_audit(c,user_id,'CAMPUS',r['id'],'ORGANIZATION_RESET','status',r['status'],f'BAJA | Motivo: {reason}')
            for r in contacts:_audit(c,user_id,'CONTACT',r['id'],'ORGANIZATION_RESET','status',r['status'],f'BAJA | Motivo: {reason}')
            for r in emails:_audit(c,user_id,'EMAIL',r['id'],'ORGANIZATION_RESET','status',r['status'],f'INACTIVO | Motivo: {reason}')
            for r in phones:_audit(c,user_id,'PHONE',r['id'],'ORGANIZATION_RESET','status',r['status'],f'INACTIVO | Motivo: {reason}')
            _audit(c,user_id,'ORGANIZATION',organization_id,'RESET_DATA','organization',org['official_name'],reason);c.commit()
        except Exception:c.rollback();raise
    return {'organization':org['official_name'],'campuses_deactivated':len(campuses),'emails_deactivated':len(emails),
            'phones_deactivated':len(phones),'contacts_deactivated':len(contacts)}
