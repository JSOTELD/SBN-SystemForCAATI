import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
VENV_PYTHON = BACKEND_DIR / ".venv-local" / "Scripts" / "python.exe"
REQUIRED_MODULES = ("flask", "flask_cors", "flask_jwt_extended", "flask_sqlalchemy", "pymysql")


def ensure_virtual_environment():
    missing = []
    for module in REQUIRED_MODULES:
        try:
            __import__(module)
        except ModuleNotFoundError:
            missing.append(module)
    if not missing:
        return
    if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise SystemExit(
        "Faltan dependencias de Python. Ejecute PREPARAR_PROYECTO.cmd una vez "
        "o instale backend/requirements.txt dentro de backend/.venv."
    )


ensure_virtual_environment()

from app import create_app

app = create_app()

if __name__ == "__main__":
    from waitress import serve
    serve(app, host=os.getenv('HOST', '127.0.0.1'), port=app.config['PORT'])
