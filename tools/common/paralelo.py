"""The converter's pure and expensive work, spread across processes.

The converter is a single Python process and the machine has several cores:
what is pure —the same result for the same argument, without touching
anything outside— and costly is spread with `en_paralelo`. The processes are
**forked**, so they are born with all of the converter's state already built;
the only things that travel between processes are the arguments and the
results.
"""

import os


def en_paralelo(funcion, argumentos):
    """`[funcion(a) for a in argumentos]`, in forked processes.

    Because it forks, the function can be a lambda or a closure: it does not
    travel, each process inherits it. The results come back in the order of
    the arguments. An exception comes back as a value and is re-raised here:
    a `SystemExit` that escapes from a pool process kills it silently, and
    the converter has to stop with the same message it stopped with serially.

    With a single argument or a single core, serially and in this process.
    And also if this process already has other threads —a pytest worker with
    a libretro core loaded, for example—: forking a process with threads can
    leave the child stuck on a lock another thread was holding, and Python
    warns about it. The converter runs in a process of its own with a single
    thread.
    """
    argumentos = list(argumentos)
    procesos = min(len(argumentos), os.cpu_count() or 1)
    if procesos < 2 or not _un_solo_hilo():
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
    except BaseException as e:      # noqa: B036 — see `en_paralelo`
        return None, e


def _un_solo_hilo():
    """Whether this process has a single thread, counting the ones that are
    not Python's: it is the same thing Python looks at to warn."""
    try:
        return len(os.listdir("/proc/self/task")) == 1
    except OSError:
        import threading
        return threading.active_count() == 1
