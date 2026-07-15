"""
Fase SHUFFLE + REDUCE: agrupa por clave los pares emitidos por los mappers
(map.py), suma los valores de cada clave (patron word-count) y calcula las
6 metricas finales pedidas a partir de los conteos reducidos.
"""

from collections import defaultdict

from map import SEP


def shuffle(resultados_map):
    agrupado = defaultdict(list)
    for pares in resultados_map:
        for clave, valor in pares:
            agrupado[clave].append(valor)
    return list(agrupado.items())


def reducer(item):
    clave, valores = item
    return clave, sum(valores)


def top(conteos, prefijo, n=5):
    filtrados = {
        clave.split(SEP, 1)[1]: total
        for clave, total in conteos.items()
        if clave.startswith(prefijo + SEP)
    }
    ranking = sorted(filtrados.items(), key=lambda kv: kv[1], reverse=True)
    return ranking[:n], filtrados


def calcular_metricas(conteos):
    ranking_views, views = top(conteos, "VIEWS")
    ranking_likes, likes = top(conteos, "LIKES")
    ranking_comments, comments = top(conteos, "COMMENTS")
    ranking_shares, shares = top(conteos, "SHARES")
    ranking_users, _ = top(conteos, "USER")
    ranking_hours, _ = top(conteos, "HOUR", n=24)

    videos = set(views) | set(likes) | set(comments) | set(shares)
    ratios = {}
    for video in videos:
        v = views.get(video, 0)
        if v > 0:
            ratios[video] = (likes.get(video, 0) + comments.get(video, 0) + shares.get(video, 0)) / v
    ranking_ratio = sorted(ratios.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return {
        "video_mas_visto": ranking_views,
        "video_mas_likes": ranking_likes,
        "video_mas_comentado": ranking_comments,
        "usuario_mas_recurrente": ranking_users,
        "hora_mas_interaccion": ranking_hours,
        "video_mayor_ratio": ranking_ratio,
    }


def generar_reporte(metricas):
    """Arma el reporte final de las 6 metricas como texto plano,
    listo tanto para imprimir en consola como para guardar en un .txt."""
    lineas = []

    def agregar_ranking(titulo, ranking, unidad):
        lineas.append(f"\n--- {titulo} ---")
        if not ranking:
            lineas.append("  (sin datos)")
            return
        ganador, valor = ranking[0]
        lineas.append(f"  GANADOR: {ganador}  ->  {valor} {unidad}")
        lineas.append("  Top 5:")
        for pos, (clave, valor) in enumerate(ranking, start=1):
            lineas.append(f"    {pos}. {clave}: {valor}")

    lineas.append("================= RESULTADOS MAPREDUCE =================")
    agregar_ranking("1) Video mas visto", metricas["video_mas_visto"], "views")
    agregar_ranking("2) Video con mas likes", metricas["video_mas_likes"], "likes")
    agregar_ranking("3) Video mas comentado", metricas["video_mas_comentado"], "comments")
    agregar_ranking("4) Usuario mas recurrente", metricas["usuario_mas_recurrente"], "interacciones")
    agregar_ranking("5) Hora con mas interaccion", metricas["hora_mas_interaccion"], "interacciones")

    lineas.append("\n--- 6) Video con mayor Ratio de Interaccion ---")
    lineas.append("  Ratio = (likes + comments + shares) / views")
    ranking_ratio = metricas["video_mayor_ratio"]
    if ranking_ratio:
        ganador, valor = ranking_ratio[0]
        lineas.append(f"  GANADOR: {ganador}  ->  ratio {valor:.3f}")
        lineas.append("  Top 5:")
        for pos, (clave, valor) in enumerate(ranking_ratio, start=1):
            lineas.append(f"    {pos}. {clave}: {valor:.3f}")
    lineas.append("==========================================================")

    return "\n".join(lineas)
