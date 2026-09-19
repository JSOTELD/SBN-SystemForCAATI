from flask import request

from ..extensions import db
from ..models import AuditLog


def audit(user_id, action, entity_type, entity_id=None, details=None):
    db.session.add(AuditLog(user_id=user_id, action=action, entity_type=entity_type,
                            entity_id=entity_id, details=details, ip_address=request.remote_addr))

