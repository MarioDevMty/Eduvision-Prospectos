from database.connection import get_connection
from services.matching import campus_match_score, contact_match_score
from services.normalization import normalize_email, normalize_phone, normalize_text
from services.data_validation import validate_email_address

ORGANIZATION_TYPES = (
    'INSTITUCION_EDUCATIVA', 'EMPRESA', 'DEPENDENCIA_GOBIERNO',
    'MUNICIPIO', 'ASOCIACION', 'PROVEEDOR', 'OTRO'
)


def get_entity_phones(entity_type: str, entity_id: int) -> list[str]:
    with get_connection() as c:
        rows = c.execute("""SELECT phone FROM phones WHERE entity_type=? AND entity_id=?
                            AND status='ACTIVO' ORDER BY is_primary DESC,id""",
                         (entity_type, entity_id)).fetchall()
    return [r['phone'] for r in rows]


def get_entity_emails(entity_type: str, entity_id: int) -> list[str]:
    with get_connection() as c:
        rows = c.execute("""SELECT email FROM emails WHERE entity_type=? AND entity_id=?
                            AND status='ACTIVO' ORDER BY is_primary DESC,id""",
                         (entity_type, entity_id)).fetchall()
    return [r['email'] for r in rows]


def phone_exists(entity_type: str, entity_id: int, phone: str) -> bool:
    n = normalize_phone(phone)
    if not n:
        return False
    with get_connection() as c:
        r = c.execute("""SELECT id FROM phones WHERE entity_type=? AND entity_id=?
                         AND normalized_phone=? AND status='ACTIVO' LIMIT 1""",
                      (entity_type, entity_id, n)).fetchone()
    return r is not None


def email_exists(entity_type: str, entity_id: int, email: str) -> bool:
    n = normalize_email(email)
    if not n:
        return False
    with get_connection() as c:
        r = c.execute("""SELECT id FROM emails WHERE entity_type=? AND entity_id=?
                         AND normalized_email=? AND status='ACTIVO' LIMIT 1""",
                      (entity_type, entity_id, n)).fetchone()
    return r is not None


def find_organization_by_normalized_name(normalized_name: str):
    with get_connection() as c:
        return c.execute("SELECT * FROM organizations WHERE normalized_name=? LIMIT 1",
                         (normalized_name,)).fetchone()


def create_organization(official_name: str, subsystem: str | None, sector: str | None,
                        relationship_type: str | None, status: str, user_id: int,
                        organization_type: str | None = None) -> dict:
    n = normalize_text(official_name)
    if not n:
        raise ValueError('El nombre de la organización es obligatorio.')
    if organization_type and organization_type not in ORGANIZATION_TYPES:
        raise ValueError('Tipo de organización no válido.')
    existing = find_organization_by_normalized_name(n)
    if existing:
        return {'created': False, 'id': existing['id'], 'existing_name': existing['official_name']}
    with get_connection() as c:
        cur = c.execute("""INSERT INTO organizations
            (official_name,normalized_name,organization_type,subsystem,sector,relationship_type,status,created_by,updated_by)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (official_name.strip(), n, organization_type or None, subsystem or None, sector or None,
             relationship_type or None, status, user_id, user_id))
        c.commit()
        oid = cur.lastrowid
    return {'created': True, 'id': oid, 'existing_name': None}


def get_campus_detail(campus_id: int) -> dict | None:
    with get_connection() as c:
        r = c.execute("""SELECT ca.*,o.official_name FROM campuses ca
                         JOIN organizations o ON o.id=ca.organization_id WHERE ca.id=? LIMIT 1""",
                      (campus_id,)).fetchone()
    if r is None:
        return None
    d = dict(r)
    d['phones'] = get_entity_phones('CAMPUS', campus_id)
    d['emails'] = get_entity_emails('CAMPUS', campus_id)
    return d


def analyze_campus_duplicates(organization_id: int, campus_name: str,
                              municipality: str | None, phone: str | None) -> list[dict]:
    with get_connection() as c:
        rows = c.execute("SELECT * FROM campuses WHERE organization_id=? AND status<>'BAJA'",
                         (organization_id,)).fetchall()
    out = []
    for r in rows:
        phones = get_entity_phones('CAMPUS', r['id'])
        a = campus_match_score(new_name=campus_name, new_municipality=municipality,
                               new_phone=phone, existing_name=r['campus_name'],
                               existing_municipality=r['municipality'], existing_phones=phones)
        if a['level'] != 'BAJA':
            out.append({'id': r['id'], 'campus_name': r['campus_name'],
                        'campus_type': r['campus_type'], 'municipality': r['municipality'],
                        'state': r['state'], 'address': r['address'], 'phones': ', '.join(phones),
                        'status': r['status'], **a})
    return out


def create_campus(organization_id: int, campus_name: str, campus_type: str | None,
                  municipality: str | None, state: str | None, address: str | None,
                  status: str, user_id: int, parent_campus_id: int | None = None) -> int:
    with get_connection() as c:
        cur = c.execute("""INSERT INTO campuses
            (organization_id,parent_campus_id,campus_name,normalized_name,campus_type,municipality,state,address,status,created_by,updated_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (organization_id, parent_campus_id, campus_name.strip(), normalize_text(campus_name),
             campus_type or None, municipality or None, state or None, address or None,
             status, user_id, user_id))
        c.commit()
        return cur.lastrowid


def add_campus_alias(campus_id: int, alias: str, user_id: int) -> bool:
    campus = get_campus_detail(campus_id)
    n = normalize_text(alias)
    if not campus or not n or normalize_text(campus['campus_name']) == n:
        return False
    with get_connection() as c:
        if c.execute("""SELECT id FROM organization_aliases WHERE campus_id=? AND normalized_alias=? AND active=1""",
                     (campus_id, n)).fetchone():
            return False
        c.execute("""INSERT INTO organization_aliases
                     (organization_id,campus_id,alias,normalized_alias,source,active,confirmed_by)
                     VALUES (?,?,?,?,'FUSION_MANUAL',1,?)""",
                  (campus['organization_id'], campus_id, alias.strip(), n, user_id))
        c.commit()
    return True


def merge_campus_data(campus_id: int, incoming_data: dict, selected_fields: list[str],
                      user_id: int, save_alias: bool = True) -> dict:
    existing = get_campus_detail(campus_id)
    if not existing:
        raise ValueError('El plantel no existe.')
    allowed = {'campus_type','municipality','state','address','status'}
    updated = []
    with get_connection() as c:
        for f in selected_fields:
            if f not in allowed:
                continue
            nv = incoming_data.get(f) or None
            if nv == existing.get(f):
                continue
            c.execute(f"UPDATE campuses SET {f}=?,updated_at=CURRENT_TIMESTAMP,updated_by=? WHERE id=?",
                      (nv, user_id, campus_id))
            updated.append(f)
        c.commit()
    pa = False
    if incoming_data.get('phone') and not phone_exists('CAMPUS', campus_id, incoming_data['phone']):
        add_phone('CAMPUS', campus_id, incoming_data['phone'], 'INSTITUCIONAL', user_id, False); pa=True
    ea = False
    if incoming_data.get('email') and not email_exists('CAMPUS', campus_id, incoming_data['email']):
        add_email('CAMPUS', campus_id, incoming_data['email'], 'INSTITUCIONAL', user_id, False); ea=True
    aa = add_campus_alias(campus_id, incoming_data.get('campus_name',''), user_id) if save_alias else False
    return {'fields_updated': updated, 'phone_added': pa, 'email_added': ea, 'alias_added': aa}


def _resolve_contact_scope(campus_id: int | None, organization_id: int | None) -> tuple[int, int | None]:
    if campus_id is not None:
        with get_connection() as c:
            r = c.execute("SELECT organization_id FROM campuses WHERE id=?", (campus_id,)).fetchone()
        if r is None:
            raise ValueError('El plantel seleccionado no existe.')
        oid = int(r['organization_id'])
        if organization_id is not None and int(organization_id) != oid:
            raise ValueError('El plantel no pertenece a la organización seleccionada.')
        return oid, int(campus_id)
    if organization_id is None:
        raise ValueError('El contacto debe pertenecer a una organización.')
    with get_connection() as c:
        if c.execute("SELECT id FROM organizations WHERE id=?", (organization_id,)).fetchone() is None:
            raise ValueError('La organización seleccionada no existe.')
    return int(organization_id), None


def get_contact_detail(contact_id: int) -> dict | None:
    with get_connection() as c:
        r = c.execute("""SELECT co.id,co.organization_id,co.campus_id,co.full_name,co.position,co.area,co.notes,co.status,
                         ca.campus_name,o.official_name,
                         CASE WHEN co.campus_id IS NULL THEN 'ORGANIZACION' ELSE 'PLANTEL' END contact_scope
                         FROM contacts co JOIN organizations o ON o.id=co.organization_id
                         LEFT JOIN campuses ca ON ca.id=co.campus_id WHERE co.id=? LIMIT 1""",
                      (contact_id,)).fetchone()
    if r is None:
        return None
    d = dict(r); d['phones']=get_entity_phones('CONTACT',contact_id); d['emails']=get_entity_emails('CONTACT',contact_id)
    return d


def analyze_contact_duplicates(campus_id: int | None, full_name: str, phone: str | None,
                               email: str | None, organization_id: int | None = None) -> list[dict]:
    oid, cid = _resolve_contact_scope(campus_id, organization_id)
    with get_connection() as c:
        if cid is None:
            rows = c.execute("""SELECT id,full_name,position,area,status FROM contacts
                                WHERE organization_id=? AND campus_id IS NULL AND status<>'BAJA'""", (oid,)).fetchall()
        else:
            rows = c.execute("""SELECT id,full_name,position,area,status FROM contacts
                                WHERE organization_id=? AND campus_id=? AND status<>'BAJA'""", (oid,cid)).fetchall()
    out=[]
    for r in rows:
        ph=get_entity_phones('CONTACT',r['id']); em=get_entity_emails('CONTACT',r['id'])
        a=contact_match_score(new_name=full_name,new_phone=phone,new_email=email,
                              existing_name=r['full_name'],existing_phones=ph,existing_emails=em)
        if a['level']!='BAJA':
            out.append({'id':r['id'],'full_name':r['full_name'],'position':r['position'],'area':r['area'],
                        'phones':', '.join(ph),'emails':', '.join(em),'status':r['status'],**a})
    rank={'EXACTA':1,'MUY_ALTA':2,'ALTA':3,'POSIBLE':4}
    out.sort(key=lambda x:(rank.get(x['level'],99),-x['name_score']))
    return out


def create_contact(campus_id: int | None, full_name: str, position: str | None, area: str | None,
                   notes: str | None, status: str, user_id: int,
                   organization_id: int | None = None) -> int:
    name=(full_name or '').strip()
    if not name:
        raise ValueError('El nombre del contacto es obligatorio.')
    oid,cid=_resolve_contact_scope(campus_id,organization_id)
    with get_connection() as c:
        cur=c.execute("""INSERT INTO contacts
            (organization_id,campus_id,full_name,position,area,notes,status,created_by,updated_by)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (oid,cid,name,position or None,area or None,notes or None,status,user_id,user_id))
        c.commit(); return cur.lastrowid


def merge_contact_data(contact_id: int, incoming_data: dict, selected_fields: list[str], user_id: int) -> dict:
    existing=get_contact_detail(contact_id)
    if not existing: raise ValueError('El contacto seleccionado no existe.')
    if incoming_data.get('organization_id') is not None and int(incoming_data['organization_id'])!=int(existing['organization_id']):
        raise ValueError('No se puede fusionar un contacto entre organizaciones distintas.')
    inc_cid = int(incoming_data['campus_id']) if incoming_data.get('campus_id') is not None else None
    ex_cid = int(existing['campus_id']) if existing['campus_id'] is not None else None
    if 'campus_id' in incoming_data and inc_cid != ex_cid:
        raise ValueError('La coincidencia no pertenece al mismo ámbito.')
    allowed={'full_name','position','area','notes','status'}; updated=[]
    with get_connection() as c:
        for f in selected_fields:
            if f not in allowed: continue
            nv=incoming_data.get(f) or None; ov=existing.get(f)
            if nv==ov: continue
            c.execute(f"UPDATE contacts SET {f}=?,updated_at=CURRENT_TIMESTAMP,updated_by=? WHERE id=?",(nv,user_id,contact_id))
            c.execute("""INSERT INTO audit_log (user_id,entity_type,entity_id,action,field_name,old_value,new_value)
                         VALUES (?,'CONTACT',?,'UPDATE',?,?,?)""",(user_id,contact_id,f,ov,nv))
            updated.append(f)
        c.commit()
    pa=False; p=(incoming_data.get('phone') or '').strip()
    if p and not phone_exists('CONTACT',contact_id,p): add_phone('CONTACT',contact_id,p,'DIRECTO',user_id,False); pa=True
    ea=False; e=(incoming_data.get('email') or '').strip()
    if e and not email_exists('CONTACT',contact_id,e): add_email('CONTACT',contact_id,e,'DIRECTO',user_id,False); ea=True
    return {'fields_updated':updated,'phone_added':pa,'email_added':ea}


def add_phone(entity_type: str, entity_id: int, phone: str, phone_type: str,
              user_id: int, is_primary: bool=False) -> int:
    if phone_exists(entity_type,entity_id,phone): return 0
    with get_connection() as c:
        cur=c.execute("""INSERT INTO phones (entity_type,entity_id,phone,normalized_phone,phone_type,is_primary,created_by)
                         VALUES (?,?,?,?,?,?,?)""",
                      (entity_type,entity_id,phone.strip(),normalize_phone(phone),phone_type,int(is_primary),user_id))
        c.commit(); return cur.lastrowid


def add_email(entity_type: str, entity_id: int, email: str, email_type: str,
              user_id: int, is_primary: bool=False) -> int:
    ok,reason=validate_email_address(email)
    if not ok: raise ValueError(reason)
    if email_exists(entity_type,entity_id,email): return 0
    with get_connection() as c:
        cur=c.execute("""INSERT INTO emails (entity_type,entity_id,email,normalized_email,email_type,is_primary,created_by)
                         VALUES (?,?,?,?,?,?,?)""",
                      (entity_type,entity_id,email.strip(),normalize_email(email),email_type,int(is_primary),user_id))
        c.commit(); return cur.lastrowid


def get_organizations() -> list:
    with get_connection() as c:
        return c.execute("""SELECT id,official_name,organization_type,subsystem,sector,relationship_type,status
                            FROM organizations ORDER BY official_name""").fetchall()


def get_campuses(organization_id: int | None=None) -> list:
    q="""SELECT ca.id,ca.organization_id,ca.campus_name,ca.campus_type,ca.municipality,ca.state,ca.status,o.official_name
         FROM campuses ca JOIN organizations o ON o.id=ca.organization_id"""; params=[]
    if organization_id is not None: q += " WHERE ca.organization_id=?"; params.append(organization_id)
    q += " ORDER BY o.official_name,ca.campus_name"
    with get_connection() as c: return c.execute(q,tuple(params)).fetchall()


def get_contacts(campus_id: int | None=None, organization_id: int | None=None,
                 direct_only: bool=False) -> list:
    q="""SELECT co.id,co.organization_id,co.campus_id,co.full_name,co.position,co.area,co.status,
         ca.campus_name,o.official_name,CASE WHEN co.campus_id IS NULL THEN 'ORGANIZACION' ELSE 'PLANTEL' END contact_scope
         FROM contacts co JOIN organizations o ON o.id=co.organization_id LEFT JOIN campuses ca ON ca.id=co.campus_id WHERE 1=1"""; p=[]
    if campus_id is not None: q+=' AND co.campus_id=?'; p.append(campus_id)
    if organization_id is not None: q+=' AND co.organization_id=?'; p.append(organization_id)
    if direct_only: q+=' AND co.campus_id IS NULL'
    q+=' ORDER BY o.official_name,CASE WHEN co.campus_id IS NULL THEN 0 ELSE 1 END,ca.campus_name,co.full_name'
    with get_connection() as c: return c.execute(q,tuple(p)).fetchall()
