from .cffi_base import ffi

ffi.cdef("""
    typedef struct _xmlURI xmlURI;
    typedef xmlURI *xmlURIPtr;
    xmlURIPtr 	xmlParseURI		(const char *str);
    void 	xmlFreeURI		(xmlURIPtr uri);

""")
