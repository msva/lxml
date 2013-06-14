# XInclude processing

from .includes import xinclude
from .etree import LxmlError
from .xmlerror import _ErrorLog
from .apihelpers import _assertValidNode
from .parser import _GLOBAL_PARSER_CONTEXT

class XIncludeError(LxmlError):
    u"""Error during XInclude processing.
    """
    pass

class XInclude:
    u"""XInclude(self)
    XInclude processor.

    Create an instance and call it on an Element to run XInclude
    processing.
    """
    def __init__(self):
        self._error_log = _ErrorLog()

    @property
    def error_log(self):
        assert self._error_log is not None, "XInclude instance not initialised"
        return self._error_log.copy()

    def __call__(self, node):
        u"__call__(self, node)"
        # We cannot pass the XML_PARSE_NOXINCNODE option as this would free
        # the XInclude nodes - there may still be Python references to them!
        # Therefore, we allow XInclude nodes to be converted to
        # XML_XINCLUDE_START nodes.  XML_XINCLUDE_END nodes are added as
        # siblings.  Tree traversal will simply ignore them as they are not
        # typed as elements.  The included fragment is added between the two,
        # i.e. as a sibling, which does not conflict with traversal.
        _assertValidNode(node)
        assert self._error_log is not None, "XPath evaluator not initialised"
        self._error_log.connect()
        _GLOBAL_PARSER_CONTEXT.pushImpliedContextFromParser(
            node._doc._parser)
        if 1:
            if node._doc._parser is not None:
                result = xinclude.xmlXIncludeProcessTreeFlags(
                    node._c_node, node._doc._parser._parse_options)
            else:
                result = xinclude.xmlXIncludeProcessTree(node._c_node)
        _GLOBAL_PARSER_CONTEXT.popImpliedContext()
        self._error_log.disconnect()

        if result == -1:
            raise XIncludeError(
                self._error_log._buildExceptionMessage(
                    u"XInclude processing failed"),
                self._error_log)


