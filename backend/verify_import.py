"""Conciliación de lectura: no modifica activos, muestra ni mediciones."""
import sys
from collections import Counter
from app import create_app
from app.extensions import db
from app.models import Asset, Observation, ResearchSample, ResearchSettings, PatrimonialImport, PatrimonialSourceChunk
from app.services.patrimonial import read_source, import_workbook
from app.validation import sbn, ValidationFailure

app = create_app()
with app.app_context():
    expected, sample, archive = read_source(sys.argv[1])
    actual = {a.sbn: a for a in db.session.scalars(db.select(Asset)).all()}
    assert len(actual) == len(expected) == 5958
    for values in expected:
        a = actual[values['sbn']]
        for key, value in values.items():
            assert getattr(a, key) == value, (a.sbn, key)
        assert not a.barcode_verified and not a.record_updated
    selected = db.session.scalars(db.select(ResearchSample)).all()
    settings = db.session.get(ResearchSettings, 1)
    if settings.selection_seed == 'CENSO_LIBROS_COMERCIO':
        from app.services.census import SITES, TYPES
        expected_ids = {a.id for a in actual.values() if a.site in SITES and a.asset_type in TYPES}
        assert {s.asset_id for s in selected} == expected_ids
        assert len(selected) == settings.target_size == settings.population_size == 1693
        assert len({s.sample_code for s in selected}) == 1693
    else:
        assert {(actual[code].id, label, kind) for code, label, kind in sample} == {(s.asset_id, s.sample_code, s.stratum) for s in selected}
    assert not db.session.scalar(db.select(Observation.id).limit(1))
    record = db.session.scalar(db.select(PatrimonialImport))
    for name, rows in archive.items():
        chunks = db.session.scalars(db.select(PatrimonialSourceChunk).where(PatrimonialSourceChunk.import_hash == record.sha256, PatrimonialSourceChunk.sheet == name).order_by(PatrimonialSourceChunk.first_row)).all()
        assert [row for chunk in chunks for row in chunk.rows] == rows, name
    assert sbn('74089950a001') == '74089950A001'
    for invalid in ['123', '74089950-001', '１２３４５６７８９０１２']:
        try:
            sbn(invalid)
        except ValidationFailure:
            pass
        else:
            raise AssertionError(invalid)
    result = import_workbook(sys.argv[1], selected[0].selected_by)
    assert result['already_imported']
    client = app.test_client()
    assert client.get('/api/assets').status_code == 401
    assert client.get('/api/health').status_code == 200
    print(f'PASS: 5958 activos campo a campo, {len(selected)} equipos en el estudio vigente, 6 hojas archivadas, validación e importación idempotente.')
