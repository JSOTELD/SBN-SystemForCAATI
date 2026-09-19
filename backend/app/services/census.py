"""Censo solicitado por el usuario el 13/09/2026, posterior al Excel.

Marco: equipos de cómputo de Libros y El Comercio, según ampliación del usuario.
No aplica sorteo, semilla, margen de error ni asignación proporcional.
Se incluyen condiciones no operativas y sin dato: son parte del censo.
"""
from ..extensions import db
from ..models import Asset, AuditLog, Observation, ResearchSample, ResearchSettings

SITES = ['LOCAL SEDE CENTRAL - EDIFICIO LIBROS', 'LOCAL SEDE CENTRAL - EDIFICIO EL COMERCIO']
TYPES = ['TYPE_1', 'TYPE_2', 'TYPE_3', 'ALL_IN_ONE', 'CPU', 'LAPTOP']
METHOD = 'CENSO_LIBROS_COMERCIO'


def configure_census(user_id):
    from ..models import CensusSnapshot
    if db.session.scalar(db.select(CensusSnapshot.asset_id).limit(1)):
        raise ValueError('El marco censal está congelado para investigación.')
    if db.session.scalar(db.select(Observation.id).limit(1)):
        raise ValueError('Existen observaciones. Conciliar el marco antes de reemplazarlo.')
    assets = db.session.scalars(db.select(Asset).where(Asset.site.in_(SITES), Asset.asset_type.in_(TYPES))
                               .order_by(Asset.asset_type, Asset.sbn)).all()
    if not assets:
        raise ValueError('No hay equipos de cómputo en las sedes del censo.')
    try:
        previous = {s.asset_id: s.sample_code for s in db.session.scalars(db.select(ResearchSample)).all()}
        next_code = max((int(code[2:]) for code in previous.values() if code.startswith('C-')), default=0)
        db.session.query(ResearchSample).delete(synchronize_session=False)
        for asset in assets:
            code = previous.get(asset.id)
            if not code or not code.startswith('C-'):
                next_code += 1
                code = f'C-{next_code:04d}'
            db.session.add(ResearchSample(asset_id=asset.id, sample_code=code,
                                         stratum=asset.asset_type, selected_by=user_id))
        settings = db.session.get(ResearchSettings, 1) or ResearchSettings(id=1)
        settings.target_size = settings.population_size = len(assets)
        settings.site_filter = 'Libros y El Comercio'
        settings.asset_types = TYPES
        settings.executing_units = sorted({a.executing_unit for a in assets if a.executing_unit})
        # Campo heredado: marcador de método, no una semilla aleatoria.
        settings.selection_seed = METHOD
        settings.updated_by = user_id
        db.session.add(settings)
        db.session.add(AuditLog(user_id=user_id, action='CONFIGURE_CENSUS', entity_type='RESEARCH_SAMPLE',
                               details={'sites': SITES, 'population': len(assets), 'method': 'CENSUS',
                                        'excluded_types': ['PRINTER', 'MONITOR', 'KEYBOARD']}))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return len(assets)
