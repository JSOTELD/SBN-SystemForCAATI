import csv
import hashlib
import io
import random


def allocate_proportional(target_size, counts):
    entries = [(key, value) for key, value in counts.items() if value > 0]
    population = sum(value for _, value in entries)
    if not isinstance(target_size, int) or target_size < 1:
        raise ValueError("El tamaño de muestra debe ser un entero positivo.")
    if target_size > population:
        raise ValueError(f"No hay suficientes activos elegibles: {population} disponibles para una muestra de {target_size}.")
    rows = []
    for stratum, count in entries:
        exact = target_size * count / population
        rows.append({"stratum": stratum, "count": count, "assigned": int(exact), "remainder": exact - int(exact)})
    pending = target_size - sum(row["assigned"] for row in rows)
    rows.sort(key=lambda row: (-row["remainder"], -row["count"], row["stratum"]))
    for row in rows:
        if pending and row["assigned"] < row["count"]:
            row["assigned"] += 1
            pending -= 1
    return {row["stratum"]: row["assigned"] for row in rows}


def select_stratified(candidates, target_size, seed):
    # Fuente metodológica de la entrega: Excel, 00_Definicion y 01_Resumen.
    # Ordenar por identificador patrimonial estable evita que los UUID creados
    # en otra importación cambien el resultado para la misma población/semilla.
    # Esta selección del sistema no reproduce el algoritmo desconocido del Excel;
    # la muestra referencial del libro se importa directamente desde su hoja 03.
    grouped = {}
    for candidate in candidates:
        grouped.setdefault(candidate.asset_type, []).append(candidate)
    allocation = allocate_proportional(target_size, {key: len(value) for key, value in grouped.items()})
    selected = []
    for stratum, rows in grouped.items():
        digest = hashlib.sha256(f"{seed}:{stratum}".encode()).digest()
        generator = random.Random(int.from_bytes(digest[:8], "big"))
        shuffled = sorted(rows, key=lambda row: row.sbn)
        generator.shuffle(shuffled)
        selected.extend(shuffled[:allocation.get(stratum, 0)])
    return sorted(selected, key=lambda row: (row.asset_type, row.sbn))


def csv_response(headers, rows):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    safe_rows = [[f"'{cell}" if str(cell or "").startswith(("=", "+", "-", "@")) else cell for cell in row] for row in rows]
    writer.writerow(headers)
    writer.writerows(safe_rows)
    return output.getvalue()


def is_strong_password(value):
    return (12 <= len(value) <= 128 and any(c.islower() for c in value) and any(c.isupper() for c in value)
            and any(c.isdigit() for c in value) and any(not c.isalnum() for c in value))
