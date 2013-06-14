# iterparse -- event-driven parsing
from .parser import _BaseParser, _ParserContext, _GLOBAL_PARSER_CONTEXT
from .parser import _XML_DEFAULT_PARSE_OPTIONS
from .parser import _raiseParseError, _fixHtmlDictNodeNames
from .apihelpers import _encodeFilename, _getFilenameForFile, funicode
from .apihelpers import _rootNodeOrRaise, _findChildForwards
from .includes import xmlparser, xmlerror, tree, htmlparser
from . import python
from .etree import _documentFactory

_ITERPARSE_CHUNK_SIZE = 32768

ITERPARSE_FILTER_START     =  1
ITERPARSE_FILTER_END       =  2
ITERPARSE_FILTER_START_NS  =  4
ITERPARSE_FILTER_END_NS    =  8
ITERPARSE_FILTER_COMMENT   = 16
ITERPARSE_FILTER_PI        = 32

def _buildIterparseEventFilter(events):
    event_filter = 0
    for event in events:
        if event == u'start':
            event_filter |= ITERPARSE_FILTER_START
        elif event == u'end':
            event_filter |= ITERPARSE_FILTER_END
        elif event == u'start-ns':
            event_filter |= ITERPARSE_FILTER_START_NS
        elif event == u'end-ns':
            event_filter |= ITERPARSE_FILTER_END_NS
        elif event == u'comment':
            event_filter |= ITERPARSE_FILTER_COMMENT
        elif event == u'pi':
            event_filter |= ITERPARSE_FILTER_PI
        else:
            raise ValueError, u"invalid event name '%s'" % event
    return event_filter

def _appendStartNsEvents(c_node, event_list):
    count = 0
    c_ns = c_node.nsDef
    while c_ns:
        ns_tuple = (funicode(c_ns.prefix) if c_ns.prefix else '',
                    funicode(c_ns.href))
        event_list.append( (u"start-ns", ns_tuple) )
        count += 1
        c_ns = c_ns.next
    return count

class _IterparseContext(_ParserContext):
    _root = None
    _doc = None

    def __init__(self):
        _ParserContext.__init__(self)
        self._ns_stack = []
        self._node_stack = []
        self._events = []
        self._event_index = 0

    def _initParserContext(self, c_ctxt):
        u"""wrap original SAX2 callbacks"""
        _ParserContext._initParserContext(self, c_ctxt)
        sax = c_ctxt.sax
        self._origSaxStartDocument = sax.startDocument
        sax.startDocument = _iterparseSaxStartDocument
        self._origSaxStart = sax.startElementNs
        self._origSaxStartNoNs = sax.startElement
        # only override start event handler if needed
        if self._event_filter == 0 or \
               self._event_filter & (ITERPARSE_FILTER_START |
                                     ITERPARSE_FILTER_START_NS |
                                     ITERPARSE_FILTER_END_NS):
            sax.startElementNs = _iterparseSaxStart
            sax.startElement = _iterparseSaxStartNoNs

        self._origSaxEnd = sax.endElementNs
        self._origSaxEndNoNs = sax.endElement
        # only override end event handler if needed
        if self._event_filter == 0 or \
               self._event_filter & (ITERPARSE_FILTER_END |
                                     ITERPARSE_FILTER_END_NS):
            sax.endElementNs = _iterparseSaxEnd
            sax.endElement = _iterparseSaxEndNoNs

        self._origSaxComment = sax.comment
        if self._event_filter & ITERPARSE_FILTER_COMMENT:
            sax.comment = _iterparseSaxComment

        self._origSaxPI = sax.processingInstruction
        if self._event_filter & ITERPARSE_FILTER_PI:
            sax.processingInstruction = _iterparseSaxPI

    def _setEventFilter(self, events, tag):
        from .etree import _MultiTagMatcher
        self._event_filter = _buildIterparseEventFilter(events)
        if tag is None or tag == '*':
            self._matcher = None
        else:
            self._matcher = _MultiTagMatcher(tag)

    def startDocument(self, c_doc):
        self._doc = _documentFactory(c_doc, None)
        if self._matcher is not None:
            self._matcher.cacheTags(self._doc, True) # force entry in libxml2 dict
        return 0

    def startNode(self, c_node):
        from .etree import _elementFactory
        ns_count = 0
        if self._event_filter & ITERPARSE_FILTER_START_NS:
            ns_count = _appendStartNsEvents(c_node, self._events)
        elif self._event_filter & ITERPARSE_FILTER_END_NS:
            ns_count = _countNsDefs(c_node)
        if self._event_filter & ITERPARSE_FILTER_END_NS:
            self._ns_stack.append(ns_count)
        if self._root is None:
            self._root = self._doc.getroot()
        if self._matcher is None or self._matcher.matches(c_node):
            node = _elementFactory(self._doc, c_node)
            if self._event_filter & ITERPARSE_FILTER_END:
                self._node_stack.append(node)
            if self._event_filter & ITERPARSE_FILTER_START:
                self._events.append( (u"start", node) )
        return 0

    def endNode(self, c_node):
        from .etree import _elementFactory
        if self._event_filter & ITERPARSE_FILTER_END:
            if self._matcher is None or self._matcher.matches(c_node):
                if self._event_filter & (ITERPARSE_FILTER_START |
                                         ITERPARSE_FILTER_START_NS |
                                         ITERPARSE_FILTER_END_NS):
                    node = self._node_stack.pop()
                else:
                    if self._root is None:
                        self._root = self._doc.getroot()
                    node = _elementFactory(self._doc, c_node)
                self._events.append( (u"end", node) )

        if self._event_filter & ITERPARSE_FILTER_END_NS:
            ns_count = self._ns_stack.pop()
            if ns_count > 0:
                event = (u"end-ns", None)
                for i in xrange(ns_count):
                    self._events.append(event)
        return 0

    def pushEvent(self, event, c_node) :
        from .etree import _elementFactory
        if self._root is None:
            root = self._doc.getroot()
            if root is not None and root._c_node.type == tree.XML_ELEMENT_NODE:
                self._root = root
        node = _elementFactory(self._doc, c_node)
        self._events.append( (event, node) )
        return 0

    def _assureDocGetsFreed(self):
        if self._c_ctxt.myDoc and self._doc is None:
            tree.xmlFreeDoc(self._c_ctxt.myDoc)
            self._c_ctxt.myDoc = tree.ffi.NULL

def _pushSaxStartDocument(context, c_doc):
    try:
        context.startDocument(c_doc)
    except:
        if context._c_ctxt.errNo == xmlerror.XML_ERR_OK:
            context._c_ctxt.errNo = xmlerror.XML_ERR_INTERNAL_ERROR
        context._c_ctxt.disableSAX = 1
        context._store_raised()

def _pushSaxStartEvent(context, c_node):
    try:
        if context._c_ctxt.html:
            _fixHtmlDictNodeNames(context._c_ctxt.dict, c_node)
        context.startNode(c_node)
    except:
        if context._c_ctxt.errNo == xmlerror.XML_ERR_OK:
            context._c_ctxt.errNo = xmlerror.XML_ERR_INTERNAL_ERROR
        context._c_ctxt.disableSAX = 1
        context._store_raised()

def _pushSaxEndEvent(context, c_node):
    try:
        context.endNode(c_node)
    except:
        if context._c_ctxt.errNo == xmlerror.XML_ERR_OK:
            context._c_ctxt.errNo = xmlerror.XML_ERR_INTERNAL_ERROR
        context._c_ctxt.disableSAX = 1
        context._store_raised()

def _pushSaxEvent(context, event, c_node):
    try:
        context.pushEvent(event, c_node)
    except:
        if context._c_ctxt.errNo == xmlerror.XML_ERR_OK:
            context._c_ctxt.errNo = xmlerror.XML_ERR_INTERNAL_ERROR
        context._c_ctxt.disableSAX = 1
        context._store_raised()

@xmlparser.ffi.callback("startDocumentSAXFunc")
def _iterparseSaxStartDocument(ctxt):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    context._origSaxStartDocument(ctxt)
    if c_ctxt.myDoc and c_ctxt.dict and not c_ctxt.myDoc.dict:
        # I have no idea why libxml2 disables this - we need it
        c_ctxt.dictNames = 1
        c_ctxt.myDoc.dict = c_ctxt.dict
    _pushSaxStartDocument(context, c_ctxt.myDoc)

@xmlparser.ffi.callback("startElementNsSAX2Func")
def _iterparseSaxStart(ctxt, localname, prefix,
                       URI, nb_namespaces, namespaces,
                       nb_attributes, nb_defaulted,
                       attributes):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    context._origSaxStart(
        ctxt, localname, prefix, URI,
        nb_namespaces, namespaces,
        nb_attributes, nb_defaulted, attributes)
    _pushSaxStartEvent(context, c_ctxt.node)

@xmlparser.ffi.callback("endElementNsSAX2Func")
def _iterparseSaxEnd(ctxt, localname, prefix, URI):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    _pushSaxEndEvent(context, c_ctxt.node)
    context._origSaxEnd(ctxt, localname, prefix, URI)

@xmlparser.ffi.callback("startElementSAXFunc")
def _iterparseSaxStartNoNs(ctxt, name, attributes):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    context._origSaxStartNoNs(ctxt, name, attributes)
    _pushSaxStartEvent(context, c_ctxt.node)

@xmlparser.ffi.callback("endElementSAXFunc")
def _iterparseSaxEndNoNs(ctxt, name):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    _pushSaxEndEvent(context, c_ctxt.node)
    context._origSaxEndNoNs(ctxt, name)

@xmlparser.ffi.callback("commentSAXFunc")
def _iterparseSaxComment(ctxt, text):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    context._origSaxComment(ctxt, text)
    c_node = _iterparseFindLastNode(c_ctxt)
    if c_node:
        _pushSaxEvent(context, u"comment", c_node)

@xmlparser.ffi.callback("processingInstructionSAXFunc")
def _iterparseSaxPI(ctxt, target, data):
    c_ctxt = xmlparser.ffi.cast("xmlParserCtxtPtr", ctxt)
    context = xmlparser.ffi.from_handle(c_ctxt._private)
    context._origSaxPI(ctxt, target, data)
    c_node = _iterparseFindLastNode(c_ctxt)
    if c_node:
        _pushSaxEvent(context, u"pi", c_node)

def _iterparseFindLastNode(c_ctxt):
    # this mimics what libxml2 creates for comments/PIs
    if c_ctxt.inSubset == 1:
        return c_ctxt.myDoc.intSubset.last
    elif c_ctxt.inSubset == 2:
        return c_ctxt.myDoc.extSubset.last
    elif not c_ctxt.node:
        return c_ctxt.myDoc.last
    elif c_ctxt.node.type == tree.XML_ELEMENT_NODE:
        return c_ctxt.node.last
    else:
        return c_ctxt.node.next

class iterparse(_BaseParser):
    u"""iterparse(self, source, events=("end",), tag=None, attribute_defaults=False, dtd_validation=False, load_dtd=False, no_network=True, remove_blank_text=False, remove_comments=False, remove_pis=False, encoding=None, html=False, huge_tree=False, schema=None)

    Incremental parser.

    Parses XML into a tree and generates tuples (event, element) in a
    SAX-like fashion. ``event`` is any of 'start', 'end', 'start-ns',
    'end-ns'.

    For 'start' and 'end', ``element`` is the Element that the parser just
    found opening or closing.  For 'start-ns', it is a tuple (prefix, URI) of
    a new namespace declaration.  For 'end-ns', it is simply None.  Note that
    all start and end events are guaranteed to be properly nested.

    The keyword argument ``events`` specifies a sequence of event type names
    that should be generated.  By default, only 'end' events will be
    generated.

    The additional ``tag`` argument restricts the 'start' and 'end' events to
    those elements that match the given tag.  By default, events are generated
    for all elements.  Note that the 'start-ns' and 'end-ns' events are not
    impacted by this restriction.

    The other keyword arguments in the constructor are mainly based on the
    libxml2 parser configuration.  A DTD will also be loaded if validation or
    attribute default values are requested.

    Available boolean keyword arguments:
     - attribute_defaults: read default attributes from DTD
     - dtd_validation: validate (if DTD is available)
     - load_dtd: use DTD for parsing
     - no_network: prevent network access for related files
     - remove_blank_text: discard blank text nodes
     - remove_comments: discard comments
     - remove_pis: discard processing instructions
     - strip_cdata: replace CDATA sections by normal text content (default: True)
     - compact: safe memory for short text content (default: True)
     - resolve_entities: replace entities by their text value (default: True)
     - huge_tree: disable security restrictions and support very deep trees
                  and very long text content (only affects libxml2 2.7+)

    Other keyword arguments:
     - encoding: override the document encoding
     - schema: an XMLSchema to validate against
    """
    _buffer = None
    root = None

    def __init__(self, source, events=(u"end",), tag=None,
                 attribute_defaults=False, dtd_validation=False,
                 load_dtd=False, no_network=True, remove_blank_text=False,
                 compact=True, resolve_entities=True, remove_comments=False,
                 remove_pis=False, strip_cdata=True, encoding=None,
                 html=False, huge_tree=False, schema=None):
        if not hasattr(source, 'read'):
            filename = _encodeFilename(source)
            if not python.IS_PYTHON3:
                source = filename
            source = open(source, 'rb')
            self._close_source_after_read = True
        else:
            filename = _encodeFilename(_getFilenameForFile(source))
            self._close_source_after_read = False

        self._source = source
        if html:
            # make sure we're not looking for namespaces
            events = tuple([ event for event in events
                             if event != u'start-ns' and event != u'end-ns' ])

        self._events = events
        self._tag = tag

        parse_options = _XML_DEFAULT_PARSE_OPTIONS
        if load_dtd:
            parse_options = parse_options | xmlparser.XML_PARSE_DTDLOAD
        if dtd_validation:
            parse_options = parse_options | (xmlparser.XML_PARSE_DTDVALID |
                                             xmlparser.XML_PARSE_DTDLOAD)
        if attribute_defaults:
            parse_options = parse_options | (xmlparser.XML_PARSE_DTDATTR |
                                             xmlparser.XML_PARSE_DTDLOAD)
        if remove_blank_text:
            parse_options = parse_options | xmlparser.XML_PARSE_NOBLANKS
        if huge_tree:
            parse_options = parse_options | xmlparser.XML_PARSE_HUGE
        if not no_network:
            parse_options = parse_options ^ xmlparser.XML_PARSE_NONET
        if not compact:
            parse_options = parse_options ^ xmlparser.XML_PARSE_COMPACT
        if not resolve_entities:
            parse_options = parse_options ^ xmlparser.XML_PARSE_NOENT
        if not strip_cdata:
            parse_options = parse_options ^ xmlparser.XML_PARSE_NOCDATA

        _BaseParser.__init__(self, parse_options, html, schema,
                             remove_comments, remove_pis, strip_cdata,
                             None, filename, encoding)

        if self._for_html:
            self._parse_chunk = htmlparser.htmlParseChunk
        else:
            self._parse_chunk = xmlparser.xmlParseChunk

        context = self._getPushParserContext()
        _GLOBAL_PARSER_CONTEXT.initParserDict(context._c_ctxt)

        if self._default_encoding is not None:
            if self._for_html:
                error = _htmlCtxtResetPush(
                    context._c_ctxt, xmlparser.ffi.NULL, 0,
                    self._default_encoding, self._parse_options)
            else:
                xmlparser.xmlCtxtUseOptions(
                    context._c_ctxt, self._parse_options)
                error = xmlparser.xmlCtxtResetPush(
                    context._c_ctxt, xmlparser.ffi.NULL, 0, xmlparser.ffi.NULL,
                    self._default_encoding)

        context.prepare()
        # parser will not be unlocked - no other methods supported

    def _createContext(self, target):
        context = _IterparseContext()
        context._setEventFilter(self._events, self._tag)
        return context

    def _close_source(self):
        if self._source is None or not self._close_source_after_read:
            return
        try:
            close = self._source.close
        except AttributeError:
            close = None
        finally:
            self._source = None
        if close is not None:
            close()

    def copy(self):
        raise TypeError, u"iterparse parsers cannot be copied"

    def __iter__(self):
        return self

    def __next__(self):
        if self._source is None:
            raise StopIteration

        context = self._push_parser_context
        events = context._events
        if len(events) <= context._event_index:
            del events[:]
            context._event_index = 0
            if self._source is not None:
                self._read_more_events(context)
            if not events:
                self.root = context._root
                raise StopIteration
        item = events[context._event_index]
        context._event_index += 1
        return item
    next = __next__

    def _read_more_events(self, context):
        pctxt = context._c_ctxt
        error = 0
        done = 0

        events = context._events
        del events[:]
        context._event_index = 0
        if hasattr(self._source, "readinto"):
            c_stream = self._source
        else:
            c_stream = None
        while not events:
            if not c_stream:
                data = self._source.read(_ITERPARSE_CHUNK_SIZE)
                if not isinstance(data, bytes):
                    self._close_source()
                    raise TypeError("reading file objects must return bytes objects")
                c_data_len = python.PyBytes_GET_SIZE(data)
                c_data = data
                done = (c_data_len == 0)
                error = self._parse_chunk(pctxt, c_data, c_data_len, done)
            else:
                if self._buffer is None:
                    self._buffer = xmlparser.ffi.new(
                        "char[]", _ITERPARSE_CHUNK_SIZE)
                c_data = self._buffer
                c_data_len = c_stream.readinto(xmlparser.ffi.buffer(c_data))
                done = (c_data_len == 0)
                error = self._parse_chunk(
                    pctxt, c_data, c_data_len, done)
            if error or done:
                self._close_source()
                self._buffer = None
                break

        # XXX AFA Added by me
        if context._has_raised():
            context._handleParseResult(self, context._doc._c_doc, None)

        if not error and context._validator is not None:
            error = not context._validator.isvalid()
        if error:
            del events[:]
            context._assureDocGetsFreed()
            _raiseParseError(pctxt, self._filename, context._error_log)


class iterwalk:
    u"""iterwalk(self, element_or_tree, events=("end",), tag=None)

    A tree walker that generates events from an existing tree as if it
    was parsing XML data with ``iterparse()``.
    """
    _tag_tuple = None

    def __init__(self, element_or_tree, events=(u"end",), tag=None):
        from .etree import _MultiTagMatcher
        root = _rootNodeOrRaise(element_or_tree)
        self._event_filter = _buildIterparseEventFilter(events)
        if tag is None or tag == '*':
            self._matcher = None
        else:
            self._matcher = _MultiTagMatcher(tag)
        self._node_stack  = []
        self._events = []
        self._pop_event = self._events.pop

        if self._event_filter:
            self._index = 0
            ns_count = self._start_node(root)
            self._node_stack.append( (root, ns_count) )
        else:
            self._index = -1

    def __iter__(self):
        return self

    def __next__(self):
        from .etree import _elementFactory
        ns_count = 0
        if self._events:
            return self._pop_event(0)
        if self._matcher is not None and self._index >= 0:
            node = self._node_stack[self._index][0]
            self._matcher.cacheTags(node._doc)

        # find next node
        while self._index >= 0:
            node = self._node_stack[self._index][0]

            c_child = _findChildForwards(node._c_node, 0)
            if c_child:
                # try children
                next_node = _elementFactory(node._doc, c_child)
            else:
                # back off
                next_node = None
                while next_node is None:
                    # back off through parents
                    self._index -= 1
                    node = self._end_node()
                    if self._index < 0:
                        break
                    next_node = node.getnext()
            if next_node is not None:
                if self._event_filter & (ITERPARSE_FILTER_START |
                                         ITERPARSE_FILTER_START_NS):
                    ns_count = self._start_node(next_node)
                elif self._event_filter & ITERPARSE_FILTER_END_NS:
                    ns_count = _countNsDefs(next_node._c_node)
                self._node_stack.append( (next_node, ns_count) )
                self._index += 1
            if self._events:
                return self._pop_event(0)
        raise StopIteration
    next = __next__

    def _start_node(self, node):
        if self._event_filter & ITERPARSE_FILTER_START_NS:
            ns_count = _appendStartNsEvents(node._c_node, self._events)
        elif self._event_filter & ITERPARSE_FILTER_END_NS:
            ns_count = _countNsDefs(node._c_node)
        else:
            ns_count = 0
        if self._event_filter & ITERPARSE_FILTER_START:
            if self._matcher is None or self._matcher.matches(node._c_node):
                self._events.append( (u"start", node) )
        return ns_count

    def _end_node(self):
        node, ns_count = self._node_stack.pop()
        if self._event_filter & ITERPARSE_FILTER_END:
            if self._matcher is None or self._matcher.matches(node._c_node):
                self._events.append( (u"end", node) )
        if self._event_filter & ITERPARSE_FILTER_END_NS:
            event = (u"end-ns", None)
            for i in xrange(ns_count):
                self._events.append(event)
        return node
