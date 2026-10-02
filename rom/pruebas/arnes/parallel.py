"""The converter's pure and expensive work, spread across processes.

The converter is a single Python process and the machine has several cores:
what is pure —the same result for the same argument, without touching
anything outside— and costly is spread with `in_parallel`. The processes are
**forked**, so they are born with all of the converter's state already built;
the only things that travel between processes are the arguments and the
results.
"""

import os


def in_parallel(function, arguments):
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
    arguments = list(arguments)
    processes = min(len(arguments), os.cpu_count() or 1)
    if processes < 2 or not _single_thread():
        return [function(a) for a in arguments]
    import multiprocessing
    global _function
    _function = function
    try:
        with multiprocessing.get_context("fork").Pool(processes) as pool:
            results = pool.map(_one, arguments, chunksize=1)
    finally:
        _function = None
    for _result, error in results:
        if error is not None:
            raise error
    return [result for result, _error in results]


_function = None


def _one(argument):
    try:
        return _function(argument), None
    except BaseException as e:      # noqa: B036 — see `in_parallel`
        return None, e


def _single_thread():
    """Whether this process has a single thread, counting the ones that are
    not Python's: it is the same thing Python looks at to warn."""
    try:
        return len(os.listdir("/proc/self/task")) == 1
    except OSError:
        import threading
        return threading.active_count() == 1
