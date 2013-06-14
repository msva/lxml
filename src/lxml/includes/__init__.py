try:
    import __pypy__
except ImportError:
    pass
else:
    # PyPy prefers the cffi port
    import os
    __path__.append(os.path.join(__path__[0], "../../lxml-cffi/includes"))

