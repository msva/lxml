import cffi

from . import tree
from . import xmlerror

ffi = cffi.FFI()
ffi.include(tree.ffi)
ffi.include(xmlerror.ffi)
ffi.cdef("""
    typedef struct _xmlRelaxNG xmlRelaxNG;
    typedef xmlRelaxNG *xmlRelaxNGPtr;

    typedef struct _xmlRelaxNGParserCtxt xmlRelaxNGParserCtxt;
    typedef xmlRelaxNGParserCtxt *xmlRelaxNGParserCtxtPtr;

    typedef struct _xmlRelaxNGValidCtxt xmlRelaxNGValidCtxt;
    typedef xmlRelaxNGValidCtxt *xmlRelaxNGValidCtxtPtr;

    xmlRelaxNGParserCtxtPtr xmlRelaxNGNewDocParserCtxt	(xmlDocPtr doc);
    void 	    xmlRelaxNGFreeParserCtxt	(xmlRelaxNGParserCtxtPtr ctxt);
    void 	    xmlRelaxNGSetParserStructuredErrors(
					 xmlRelaxNGParserCtxtPtr ctxt,
					 xmlStructuredErrorFunc serror,
					 void *ctx);

    xmlRelaxNGPtr   xmlRelaxNGParse		(xmlRelaxNGParserCtxtPtr ctxt);
    void 	    xmlRelaxNGFree		(xmlRelaxNGPtr schema);

    xmlRelaxNGValidCtxtPtr xmlRelaxNGNewValidCtxt	(xmlRelaxNGPtr schema);
    void 		xmlRelaxNGSetValidStructuredErrors(xmlRelaxNGValidCtxtPtr ctxt,
					  xmlStructuredErrorFunc serror, void *ctx);
    int 	    xmlRelaxNGValidateDoc	(xmlRelaxNGValidCtxtPtr ctxt,
						 xmlDocPtr doc);
    void 	    xmlRelaxNGFreeValidCtxt	(xmlRelaxNGValidCtxtPtr ctxt);

""")

libxml = ffi.verify("""
    #include "libxml/relaxng.h"
""",
include_dirs=['/usr/include/libxml2'],
libraries=['xml2'])

for name in dir(libxml):
    if name.startswith('xml'):
        globals()[name] = getattr(libxml, name)

