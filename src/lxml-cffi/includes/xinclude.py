from .cffi_base import ffi

ffi.cdef("""
    int 	xmlXIncludeProcessTreeFlags(xmlNodePtr tree,
					 int flags);
    int		xmlXIncludeProcessTreeFlagsData(xmlNodePtr tree,
					 int flags,
					 void *data);
""")
