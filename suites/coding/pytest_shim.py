"""Mini-helper per i test (evita la dipendenza da pytest)."""
import math


def raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    except BaseException as e:  # noqa: BLE001
        raise AssertionError(f"{fn.__name__}{args!r}: atteso {exc_type.__name__}, sollevato {type(e).__name__}: {e}")
    raise AssertionError(f"{fn.__name__}{args!r}: atteso {exc_type.__name__}, nessuna eccezione")


def approx(a, b, tol=1e-9):
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


def source():
    with open("solution.py", encoding="utf-8") as f:
        return f.read()
