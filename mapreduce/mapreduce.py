#!/usr/bin/env python3
"""
Driver MapReduce (simulado con multiprocessing) para las metricas de la red
social estudiantil de PowerESFOT.

Flujo:
  1. Lee las lineas de entrada desde un archivo de texto plano (datos.txt) o,
     opcionalmente, desde el endpoint /datos via el balanceador Nginx (--url).
  2. Divide las lineas en N splits (equivalente a los InputSplits de Hadoop) y
     escribe cada split en carpeta_splits/split_N.txt.
  3. Fase MAP: cada split se procesa en un proceso worker independiente
     (map.py) y su salida intermedia (pares clave/valor) se escribe en
     carpeta_splits/split_N.out.
  4. Fase SHUFFLE + REDUCE: se agrupan y suman los pares emitidos (reduce.py).
  5. Calcula las 6 metricas pedidas y escribe el resultado final agregado
     en un .txt.
"""

import argparse
import sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

import requests

from map import crear_splits, map_split, parsear_linea
from reduce import shuffle, reducer, calcular_metricas, generar_reporte

DIR_SCRIPT = Path(__file__).resolve().parent


def resolver_ruta_datos(nombre="datos.txt"):
    """Busca el archivo de datos en el directorio actual, junto al script,
    o en el directorio del proyecto (un nivel arriba de mapreduce/)."""
    candidatos = [Path(nombre), DIR_SCRIPT / nombre, DIR_SCRIPT.parent / nombre]
    for candidato in candidatos:
        if candidato.exists():
            return candidato
    return Path(nombre)


def leer_lineas_de_archivo(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


def probar_balanceo(url, intentos=6):
    print(f"\n=== Prueba de balanceo de carga ({intentos} requests a {url}) ===")
    servidores = []
    for i in range(1, intentos + 1):
        resp = requests.get(url, timeout=10)
        servido_por = resp.headers.get("X-Served-By", "desconocido")
        servidores.append(servido_por)
        print(f"  request {i}: X-Served-By = {servido_por}")
    distintos = set(servidores)
    print(f"Servidores que respondieron: {sorted(distintos)}")
    return servidores


def descargar_lineas(url):
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return [l for l in resp.text.splitlines() if l.strip()]


def procesar_split(tarea):
    """Se ejecuta en un proceso worker: materializa el split de entrada como
    split_N.txt y su salida Map (pares clave/valor) como split_N.out."""
    indice, lineas, carpeta_splits = tarea

    ruta_split = carpeta_splits / f"split_{indice}.txt"
    ruta_split.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    pares = map_split(lineas)

    ruta_out = carpeta_splits / f"split_{indice}.out"
    contenido_out = "\n".join(f"{clave}\t{valor}" for clave, valor in pares)
    ruta_out.write_text(contenido_out + "\n" if contenido_out else "", encoding="utf-8")

    return pares


def ejecutar_mapreduce(splits, carpeta_splits, workers=4):
    carpeta_splits.mkdir(parents=True, exist_ok=True)
    tareas = [(indice, lineas, carpeta_splits) for indice, lineas in enumerate(splits)]

    with Pool(processes=workers) as pool:
        resultados_map = pool.map(procesar_split, tareas)

    agrupado = shuffle(resultados_map)

    with Pool(processes=workers) as pool:
        resultados_reduce = pool.map(reducer, agrupado)

    conteos = defaultdict(int)
    for clave, total in resultados_reduce:
        conteos[clave] = total

    return conteos


def guardar_reporte(texto, ruta):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto + "\n", encoding="utf-8")
    return ruta


def main():
    parser = argparse.ArgumentParser(description="MapReduce de metricas de red social estudiantil")
    parser.add_argument("--file", default=None,
                         help="Archivo de texto plano con los datos (por defecto: datos.txt)")
    parser.add_argument("--url", default=None,
                         help="URL del endpoint /datos (alternativa a --file, via el balanceador Nginx)")
    parser.add_argument("--splits", type=int, default=4,
                         help="Cantidad de splits en los que se divide la entrada (default: 4)")
    parser.add_argument("--splits-dir", default="splits",
                         help="Carpeta donde se escriben split_N.txt (entrada) y split_N.out (salida Map)")
    parser.add_argument("--workers", type=int, default=4, help="Numero de procesos worker")
    parser.add_argument("--output", default="resultados_mapreduce.txt",
                         help="Archivo .txt donde se guarda el resultado final")
    parser.add_argument("--skip-balance-test", action="store_true",
                         help="Omitir la prueba previa de balanceo de carga (solo aplica con --url)")
    args = parser.parse_args()

    if args.url:
        if not args.skip_balance_test:
            try:
                probar_balanceo(args.url, intentos=6)
            except requests.RequestException as e:
                print(f"Aviso: no se pudo probar el balanceo ({e}). Continuando con el MapReduce...")
        print(f"\nDescargando datos desde {args.url} ...")
        try:
            lineas = descargar_lineas(args.url)
        except requests.RequestException as e:
            print(f"ERROR: no se pudo obtener /datos: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        ruta = Path(args.file) if args.file else resolver_ruta_datos()
        print(f"\nLeyendo datos desde {ruta} ...")
        if not ruta.exists():
            print(f"ERROR: no se encontro el archivo {ruta}", file=sys.stderr)
            sys.exit(1)
        lineas = leer_lineas_de_archivo(ruta)

    registros_validos = sum(1 for l in lineas if parsear_linea(l) is not None)
    print(f"Lineas leidas: {len(lineas)} (registros validos: {registros_validos})")

    splits = crear_splits(lineas, args.splits)
    carpeta_splits = Path(args.splits_dir)
    print(f"Entrada dividida en {len(splits)} splits "
          f"(tamanos: {[len(s) for s in splits]})")
    print(f"Escribiendo splits en: {carpeta_splits.resolve()} "
          f"(split_N.txt = entrada, split_N.out = salida de la fase Map)")

    conteos = ejecutar_mapreduce(splits, carpeta_splits, workers=args.workers)
    metricas = calcular_metricas(conteos)
    reporte = generar_reporte(metricas)

    print("\n" + reporte)

    ruta_salida = guardar_reporte(reporte, args.output)
    print(f"\nResultado final guardado en: {ruta_salida.resolve()}")


if __name__ == "__main__":
    main()
