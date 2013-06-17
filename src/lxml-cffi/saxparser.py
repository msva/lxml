# SAX-like interfaces

from .parser import _ParserContext
from inspect import getargspec as inspect_getargspec
from .includes import xmlparser, xmlerror
from .apihelpers import _namespacedNameFromNsName, _makeElement, _makeSubElement
from .apihelpers import funicode, funicodeOrNone, funicodeOrEmpty, _appendChild
from .etree import EMPTY_READ_ONLY_DICT
from . import python
from .includes import tree


SAX_EVENT_START   =  1
SAX_EVENT_END     =  2
SAX_EVENT_DATA    =  4
SAX_EVENT_DOCTYPE =  8
SAX_EVENT_PI      = 16
SAX_EVENT_COMMENT = 32

class _SaxParserTarget:
    def __init__(self):
        self._sax_event_filter = 0
        self._sax_event_propagate = 0

    def _handleSaxStart(self, tag, attrib, nsmap):
        return None
    def _handleSaxEnd(self, tag):
        return None
    def _handleSaxData(self, data):
        return 0
    def _handleSaxDoctype(self, root_tag, public_id, system_id):
        return 0
    def _handleSaxPi(self, target, data):
        return None
    def _handleSaxComment(self, comment):
        return None

class _SaxParserContext(_ParserContext):
    u"""This class maps SAX2 events to method calls.
    """
    _origSaxCData = None

    def _setSaxParserTarget(self, target):
        self._target = target

    def _initParserContext(self, c_ctxt):
        u"wrap original SAX2 callbacks"
        _ParserContext._initParserContext(self, c_ctxt)
        sax = c_ctxt.sax
        if self._target._sax_event_propagate & SAX_EVENT_START:
            # propagate => keep orig callback
            self._origSaxStart = sax.startElementNs
            self._origSaxStartNoNs = sax.startElement
        else:
            # otherwise: never call orig callback
            self._origSaxStart = sax.startElementNs = xmlparser.ffi.NULL
            self._origSaxStartNoNs = sax.startElement = xmlparser.ffi.NULL
        if self._target._sax_event_filter & SAX_EVENT_START:
            # intercept => overwrite orig callback
            if sax.initialized == xmlparser.XML_SAX2_MAGIC:
                sax.startElementNs = _handleSaxStart
            sax.startElement = _handleSaxStartNoNs

        if self._target._sax_event_propagate & SAX_EVENT_END:
            self._origSaxEnd = sax.endElementNs
            self._origSaxEndNoNs = sax.endElement
        else:
            self._origSaxEnd = sax.endElementNs = xmlparser.ffi.NULL
            self._origSaxEndNoNs = sax.endElement = xmlparser.ffi.NULL
        if self._target._sax_event_filter & SAX_EVENT_END:
            if sax.initialized == xmlparser.XML_SAX2_MAGIC:
                sax.endElementNs = _handleSaxEnd
            sax.endElement = _handleSaxEndNoNs

        if self._target._sax_event_propagate & SAX_EVENT_DATA:
            self._origSaxData = sax.characters
            self._origSaxCData = sax.cdataBlock
        else:
            self._origSaxData = sax.characters = sax.cdataBlock = xmlparser.ffi.NULL
        if self._target._sax_event_filter & SAX_EVENT_DATA:
            sax.characters = _handleSaxData
            sax.cdataBlock = _handleSaxCData

        # doctype propagation is always required for entity replacement
        self._origSaxDoctype = sax.internalSubset
        if self._target._sax_event_filter & SAX_EVENT_DOCTYPE:
            sax.internalSubset = _handleSaxDoctype

        if self._target._sax_event_propagate & SAX_EVENT_PI:
            self._origSaxPi = sax.processingInstruction
        else:
            self._origSaxPi = sax.processingInstruction = xmlparser.ffi.NULL
        if self._target._sax_event_filter & SAX_EVENT_PI:
            sax.processingInstruction = _handleSaxPI

        if self._target._sax_event_propagate & SAX_EVENT_COMMENT:
            self._origSaxComment = sax.comment
        else:
            self._origSaxComment = sax.comment = xmlparser.ffi.NULL
        if self._target._sax_event_filter & SAX_EVENT_COMMENT:
            sax.comment = _handleSaxComment

        # enforce entity replacement
        sax.reference = xmlparser.ffi.NULL
        c_ctxt.replaceEntities = 1

    def _handleSaxException(self, c_ctxt):
        if c_ctxt.errNo == xmlerror.XML_ERR_OK:
            c_ctxt.errNo = xmlerror.XML_ERR_INTERNAL_ERROR
        # stop parsing immediately
        c_ctxt.wellFormed = 0
        c_ctxt.disableSAX = 1
        self._store_raised()

@xmlparser.ffi.callback("startElementNsSAX2Func")
def _handleSaxStart(ctxt, c_localname, c_prefix,
                    c_namespace, c_nb_namespaces,
                    c_namespaces,
                    c_nb_attributes, c_nb_defaulted,
                    c_attributes):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private:
        return
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    if context._origSaxStart:
        context._origSaxStart(c_ctxt, c_localname, c_prefix, c_namespace,
                              c_nb_namespaces, c_namespaces, c_nb_attributes,
                              c_nb_defaulted, c_attributes)
    try:
        tag = _namespacedNameFromNsName(c_namespace, c_localname)
        if c_nb_defaulted > 0:
            # only add default attributes if we asked for them
            if c_ctxt.loadsubset & xmlparser.XML_COMPLETE_ATTRS == 0:
                c_nb_attributes = c_nb_attributes - c_nb_defaulted
        if c_nb_attributes == 0:
            attrib = EMPTY_READ_ONLY_DICT
        else:
            attrib = {}
            for i in xrange(c_nb_attributes):
                name = _namespacedNameFromNsName(
                    c_attributes[2], c_attributes[0])
                if not c_attributes[3]:
                    if python.IS_PYTHON3:
                        value = u''
                    else:
                        value = ''
                else:
                    value = xmlparser.ffi.buffer(
                        c_attributes[3],
                        c_attributes[4] - c_attributes[3])[:]
                    value = value.decode('utf8')
                attrib[name] = value
                c_attributes += 5
        if c_nb_namespaces == 0:
            nsmap = EMPTY_READ_ONLY_DICT
        else:
            nsmap = {}
            for i in xrange(c_nb_namespaces):
                if c_namespaces[0] is NULL:
                    prefix = None
                else:
                    prefix = funicode(c_namespaces[0])
                nsmap[prefix] = funicode(c_namespaces[1])
                c_namespaces += 2
        element = context._target._handleSaxStart(tag, attrib, nsmap)
        if element is not None and c_ctxt.input:
            if c_ctxt.input.line < 65535:
                element._c_node.line = c_ctxt.input.line
            else:
                element._c_node.line = 65535
    except:
        context._handleSaxException(c_ctxt)

@xmlparser.ffi.callback("startElementSAXFunc")
def _handleSaxStartNoNs(ctxt, c_name, c_attributes):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private:
        return
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    if context._origSaxStartNoNs:
        context._origSaxStartNoNs(c_ctxt, c_name, c_attributes)
    try:
        tag = funicode(c_name)
        if not c_attributes:
            attrib = EMPTY_READ_ONLY_DICT
        else:
            attrib = {}
            while c_attributes[0] is not NULL:
                name = funicode(c_attributes[0])
                if c_attributes[1] is NULL:
                    if python.IS_PYTHON3:
                        value = u''
                    else:
                        value = ''
                else:
                    value = funicode(c_attributes[1])
                c_attributes = c_attributes + 2
                attrib[name] = value
        element = context._target._handleSaxStart(
            tag, attrib, EMPTY_READ_ONLY_DICT)
        if element is not None and c_ctxt.input is not NULL:
            if c_ctxt.input.line < 65535:
                element._c_node.line = c_ctxt.input.line
            else:
                element._c_node.line = 65535
    except:
        context._handleSaxException(c_ctxt)

@xmlparser.ffi.callback("endElementNsSAX2Func")
def _handleSaxEnd(ctxt, c_localname, c_prefix, c_namespace):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private:
        return
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    if context._origSaxEnd:
        context._origSaxEnd(c_ctxt, c_localname, c_prefix, c_namespace)
    try:
        tag = _namespacedNameFromNsName(c_namespace, c_localname)
        context._target._handleSaxEnd(tag)
    except:
        context._handleSaxException(c_ctxt)

@xmlparser.ffi.callback("endElementSAXFunc")
def _handleSaxEndNoNs(ctxt, c_name):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private:
        return
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    if context._origSaxEndNoNs:
        context._origSaxEndNoNs(c_ctxt, c_name)
    try:
        context._target._handleSaxEnd(funicode(c_name))
    except:
        context._handleSaxException(c_ctxt)

@xmlparser.ffi.callback("charactersSAXFunc")
def _handleSaxData(ctxt, c_data, data_len):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    if context._origSaxData:
        context._origSaxData(c_ctxt, c_data, data_len)
    try:
        data = xmlparser.ffi.buffer(c_data, data_len)[:]
        data = data.decode('utf8')
        context._target._handleSaxData(data)
    except:
        context._handleSaxException(c_ctxt)

@xmlparser.ffi.callback("cdataBlockSAXFunc")
def _handleSaxCData(ctxt, c_data, data_len):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    if context._origSaxCData:
        context._origSaxCData(c_ctxt, c_data, data_len)
    try:
        data = xmlparser.ffi.buffer(c_data, data_len)[:]
        context._target._handleSaxData(data.decode('utf8'))
    except:
        context._handleSaxException(c_ctxt)

@xmlparser.ffi.callback("internalSubsetSAXFunc")
def _handleSaxDoctype(ctxt, c_name, c_public, c_system):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    if context._origSaxDoctype:
        context._origSaxDoctype(c_ctxt, c_name, c_public, c_system)
    try:
        context._target._handleSaxDoctype(
            funicodeOrNone(c_name),
            funicodeOrNone(c_public),
            funicodeOrNone(c_system))
    except:
        context._handleSaxException(c_ctxt)

@xmlparser.ffi.callback("processingInstructionSAXFunc")
def _handleSaxPI(ctxt, c_target, c_data):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    if context._origSaxPi:
        context._origSaxPi(c_ctxt, c_target, c_data)
    try:
        context._target._handleSaxPi(
            funicodeOrNone(c_target),
            funicodeOrEmpty(c_data))
    except:
        context._handleSaxException(c_ctxt)

@xmlparser.ffi.callback("commentSAXFunc")
def _handleSaxComment(ctxt, c_data):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    if context._origSaxComment:
        context._origSaxComment(c_ctxt, c_data)
    try:
        context._target._handleSaxComment(funicodeOrEmpty(c_data))
    except:
        context._handleSaxException(c_ctxt)


############################################################
## ET compatible XML tree builder
############################################################

class TreeBuilder(_SaxParserTarget):
    u"""TreeBuilder(self, element_factory=None, parser=None)
    Parser target that builds a tree.

    The final tree is returned by the ``close()`` method.
    """
    def __init__(self, element_factory=None, parser=None):
        self._sax_event_filter = \
            SAX_EVENT_START | SAX_EVENT_END | SAX_EVENT_DATA | \
            SAX_EVENT_PI | SAX_EVENT_COMMENT
        self._data = [] # data collector
        self._element_stack = [] # element stack
        self._element_stack_pop = self._element_stack.pop
        self._last = None # last element
        self._in_tail = 0 # true if we're after an end tag
        self._factory = element_factory
        self._parser = parser

    def _flush(self):
        if len(self._data) > 0:
            if self._last is not None:
                text = u"".join(self._data)
                if self._in_tail:
                    assert self._last.tail is None, u"internal error (tail)"
                    self._last.tail = text
                else:
                    assert self._last.text is None, u"internal error (text)"
                    self._last.text = text
            del self._data[:]
        return 0

    # Python level event handlers

    def close(self):
        u"""close(self)

        Flushes the builder buffers, and returns the toplevel document
        element.
        """
        assert len(self._element_stack) == 0, u"missing end tags"
        assert self._last is not None, u"missing toplevel element"
        return self._last

    def data(self, data):
        u"""data(self, data)

        Adds text to the current element.  The value should be either an
        8-bit string containing ASCII text, or a Unicode string.
        """
        self._handleSaxData(data)

    def start(self, tag, attrs, nsmap=None):
        u"""start(self, tag, attrs, nsmap=None)

        Opens a new element.
        """
        if nsmap is None:
            nsmap = EMPTY_READ_ONLY_DICT
        return self._handleSaxStart(tag, attrs, nsmap)

    def end(self, tag):
        u"""end(self, tag)

        Closes the current element.
        """
        element = self._handleSaxEnd(tag)
        assert self._last.tag == tag,\
               u"end tag mismatch (expected %s, got %s)" % (
                   self._last.tag, tag)
        return element

    def pi(self, target, data):
        u"""pi(self, target, data)
        """
        return self._handleSaxPi(target, data)

    def comment(self, comment):
        u"""comment(self, comment)
        """
        return self._handleSaxComment(comment)

    # internal SAX event handlers

    def _handleSaxStart(self, tag, attrib, nsmap):
        self._flush()
        if self._factory is not None:
            self._last = self._factory(tag, attrib)
            if len(self._element_stack):
                _appendChild(self._element_stack[-1], self._last)
        elif len(self._element_stack):
            self._last = _makeSubElement(
                self._element_stack[-1], tag, None, None, attrib, nsmap, None)
        else:
            self._last = _makeElement(
                tag, tree.ffi.NULL, None, self._parser, None, None,
                attrib, nsmap, None)
        self._element_stack.append(self._last)
        self._in_tail = 0
        return self._last

    def _handleSaxEnd(self, tag):
        self._flush()
        self._last = self._element_stack_pop()
        self._in_tail = 1
        return self._last

    def _handleSaxData(self, data):
        self._data.append(data)

    def _handleSaxPi(self, target, data):
        from .etree import ProcessingInstruction
        self._flush()
        self._last = ProcessingInstruction(target, data)
        if self._element_stack:
            _appendChild(self._element_stack[-1], self._last)
        self._in_tail = 1
        return self._last

    def _handleSaxComment(self, comment):
        from .etree import Comment
        self._flush()
        self._last = Comment(comment)
        if self._element_stack:
            _appendChild(self._element_stack[-1], self._last)
        self._in_tail = 1
        return self._last
