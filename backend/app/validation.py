import re
from flask import jsonify


class ValidationFailure(Exception):
    pass


def data():
    from flask import request
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ValidationFailure("Se esperaba un objeto JSON.")
    return value


def required(value, name, minimum=1, maximum=None):
    result = str(value or "").strip()
    if len(result) < minimum or (maximum and len(result) > maximum):
        raise ValidationFailure(f"El campo {name} no es válido.")
    return result


def sbn(value):
    # Fuente: 02_Base Consolidada contiene códigos como 74089950A001.
    # Se conserva el identificador documental; no se certifica su validez SBN.
    result = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{12}", result):
        raise ValidationFailure("El código patrimonial debe contener 12 letras mayúsculas o dígitos.")
    return result


def register_validation(app):
    @app.errorhandler(ValidationFailure)
    def handle(error):
        return jsonify(message="Los datos enviados no son válidos.", issues=[{"message": str(error)}]), 400
