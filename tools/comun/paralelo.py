"""Lo puro y caro del conversor, repartido en procesos.

El conversor es un solo proceso de Python y la máquina tiene varios núcleos:
lo que es puro —el mismo resultado para el mismo argumento, sin tocar nada
de afuera— y cuesta, se reparte con `en_paralelo`. Los procesos se
**bifurcan**, así que nacen con todo el estado del conversor ya armado; lo
único que viaja entre procesos son los argumentos y los resultados.
"""

import os


def en_paralelo(funcion, argumentos):
    """`[funcion(a) for a in argumentos]`, en procesos bifurcados.

    Por bifurcar, la función puede ser una lambda o un cierre: no viaja, la
    hereda cada proceso. Los resultados vuelven en el orden de los
    argumentos. Una excepción vuelve como valor y se relanza acá: un
    `SystemExit` que se escapa de un proceso del pool lo mata sin avisar, y
    el conversor tiene que cortar con el mismo mensaje que cortaba en serie.

    Con un solo argumento o un solo núcleo, en serie y en este proceso.
    """
    argumentos = list(argumentos)
    procesos = min(len(argumentos), os.cpu_count() or 1)
    if procesos < 2:
        return [funcion(a) for a in argumentos]
    import multiprocessing
    global _funcion
    _funcion = funcion
    try:
        with multiprocessing.get_context("fork").Pool(procesos) as pool:
            hechos = pool.map(_uno, argumentos, chunksize=1)
    finally:
        _funcion = None
    for _hecho, error in hechos:
        if error is not None:
            raise error
    return [hecho for hecho, _error in hechos]


_funcion = None


def _uno(argumento):
    try:
        return _funcion(argumento), None
    except BaseException as e:      # noqa: B036 — ver `en_paralelo`
        return None, e
