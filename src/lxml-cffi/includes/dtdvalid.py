import cffi
from . import tree

ffi = cffi.FFI()
ffi.include(tree.ffi)

ffi.cdef("""
    typedef struct _xmlValidCtxt xmlValidCtxt;
    typedef xmlValidCtxt *xmlValidCtxtPtr;

    xmlValidCtxtPtr xmlNewValidCtxt(void);
    void xmlFreeValidCtxt(xmlValidCtxtPtr);
    int 	xmlValidateDtd		(xmlValidCtxtPtr ctxt,
					 xmlDocPtr doc,
					 xmlDtdPtr dtd);
    xmlElementPtr	xmlGetDtdElementDesc	(xmlDtdPtr dtd, 
					 const xmlChar * name);
""")

libxml = ffi.verify("""
    #include "libxml/parser.h"
    #include "libxml/valid.h"
""",
include_dirs=['/usr/include/libxml2'],
libraries=['xml2'])

for name in dir(libxml):
    if name.startswith('xml'):
        globals()[name] = getattr(libxml, name)

