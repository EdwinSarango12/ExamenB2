"""
Fase MAP: parsea cada linea de texto plano (usuario, accion, fecha, hora, video)
y emite pares (clave, valor) para cada metrica que luego se agrupa en la fase
de Shuffle y se agrega en la fase Reduce (ver reduce.py).
"""

SEP = "::"

ACCION_A_CATEGORIA = {
    "view": "VIEWS",
    "like": "LIKES",
    "comment": "COMMENTS",
    "shared": "SHARES",
}


def parsear_linea(linea):
    partes = [p.strip() for p in linea.split(",")]
    if len(partes) != 5:
        return None
    usuario, accion, fecha, hora, video = partes
    return usuario, accion, fecha, hora, video


def mapper(linea):
    registro = parsear_linea(linea)
    if registro is None:
        return []
    usuario, accion, fecha, hora, video = registro

    emitidos = []
    categoria = ACCION_A_CATEGORIA.get(accion)
    if categoria:
        emitidos.append((f"{categoria}{SEP}{video}", 1))

    emitidos.append((f"USER{SEP}{usuario}", 1))

    hora_num = hora.split(":")[0].zfill(2)
    emitidos.append((f"HOUR{SEP}{hora_num}", 1))

    return emitidos


def crear_splits(lineas, n_splits):
    """Divide las lineas de entrada en n_splits bloques (equivalente a los
    InputSplits de Hadoop): cada split se asigna a una tarea Map independiente."""
    n_splits = max(1, min(n_splits, len(lineas)) or 1)
    tam = -(-len(lineas) // n_splits)  # techo de la division
    return [lineas[i:i + tam] for i in range(0, len(lineas), tam)]


def map_split(split):
    """Tarea Map: aplica el mapper a todas las lineas de un split y concatena
    los pares (clave, valor) emitidos."""
    resultados = []
    for linea in split:
        resultados.extend(mapper(linea))
    return resultados
