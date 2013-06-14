import threading
import re
import cffi

from .etree import __MAX_LOG_SIZE
from .apihelpers import _decodeFilename, _isFilePath
from .includes import xmlerror
from . import python

# module level API functions

def clear_error_log():
    u"""clear_error_log()

    Clear the global error log.  Note that this log is already bound to a
    fixed size.

    Note: since lxml 2.2, the global error log is local to a thread
    and this function will only clear the global error log of the
    current thread.
    """
    _getGlobalErrorLog().clear()

# Another ffi to deal with variadic callbacks
ffi = cffi.FFI()
ffi.include(xmlerror.ffi)
ffi.cdef("""
void nullGenericErrorFunc(void* ctxt, char* msg, ...);
void pyXsltGenericErrorFunc(void* ctxt, char* msg, ...);
typedef void (*PyXsltErrorFunc)(void *ctxt, xmlError *error);
void setPyXsltErrorFunc(PyXsltErrorFunc func);
""")
helpers = ffi.verify("""
#include "libxml/xmlerror.h"
#include <string.h>
#include <stdio.h>

void nullGenericErrorFunc(void* ctxt, char* msg, ...)
{
}
typedef void (*PyXsltErrorFunc)(void *ctxt, xmlError *error);
static PyXsltErrorFunc _pyXsltErrorFunc;
void setPyXsltErrorFunc(PyXsltErrorFunc func)
{
    _pyXsltErrorFunc = func;
}
void pyXsltGenericErrorFunc(void* ctxt, char* msg, ...)
{
    xmlError c_error;
    va_list args;
    char* c_text;
    char* c_message;
    char* c_element;
    int i, text_size, element_size;
    if (!msg || msg[0] == '\\n' || msg[0] == '\\0')
        return;

    va_start(args, msg);
    if (msg[0] == '%' && msg[1] == 's')
        c_text = va_arg(args, char*);
    else
        c_text = NULL;
    if (strstr(msg, "file %s")) {
        c_error.file = va_arg(args, char*);
        if (c_error.file &&
            strncmp(c_error.file,
                    "string://__STRING__XSLT", 23) == 0)
            c_error.file = "<xslt>";
    }
    else {
        c_error.file = NULL;
    }
    if (strstr(msg, "line %d"))
        c_error.line = va_arg(args, int);
    else
        c_error.line = 0;
    if (strstr(msg, "element %s"))
        c_element = va_arg(args, char*);
    else
        c_element = NULL;
    va_end(args);

    c_message = NULL;
    if (!c_text) {
        if (c_element && strchr(msg, '%') == strrchr(msg, '%')) {
            /* special case: a single occurrence of 'element %s' */
            text_size    = strlen(msg);
            element_size = strlen(c_element);
            c_message = malloc(
                (text_size + element_size + 1) * sizeof(char));
            sprintf(c_message, msg, c_element);
            c_error.message = c_message;
        }
        else
            c_error.message = "";
    }
    else if (!c_element) {
        c_error.message = c_text;
    }
    else {
        text_size    = strlen(c_text);
        element_size = strlen(c_element);
        c_message = malloc(
            (text_size + 12 + element_size + 1) * sizeof(char));
        sprintf(c_message, "%s, element '%s'", c_text, c_element);
        c_error.message = c_message;
    }

    c_error.domain = XML_FROM_XSLT;
    c_error.code   = XML_ERR_OK;  /* what else? */
    c_error.level  = XML_ERR_ERROR;  /* what else? */
    c_error.int2   = 0;

    _pyXsltErrorFunc(ctxt, &c_error);

    if (c_message)
        free(c_message);
}
""",
include_dirs=['/usr/include/libxml2'],
libraries=['xml2'])

pyXsltGenericErrorFunc = helpers.pyXsltGenericErrorFunc

# setup for global log:

def _initThreadLogging():
    # disable generic error lines from libxml2
    xmlerror.xmlSetGenericErrorFunc(
        xmlerror.ffi.NULL, helpers.nullGenericErrorFunc)

    # divert error messages to the global error log
    connectErrorLog(None)

def connectErrorLog(log):
    from .includes import xslt
    helpers.setPyXsltErrorFunc(_receiveError)
    if log is None:
        handle = xmlerror.ffi.NULL
    else:
        handle = log.get_handle()
    xslt.xsltSetGenericErrorFunc(handle, pyXsltGenericErrorFunc)

# Logging classes

class _LogEntry(object):
    """A log message entry from an error log.

    Attributes:

    - message: the message text
    - domain: the domain ID (see lxml.etree.ErrorDomains)
    - type: the message type ID (see lxml.etree.ErrorTypes)
    - level: the log level ID (see lxml.etree.ErrorLevels)
    - line: the line at which the message originated (if applicable)
    - column: the character column at which the message originated (if applicable)
    - filename: the name of the file in which the message originated (if applicable)
    """

    def _setError(self, error):
        self.domain   = error.domain
        self.type     = error.code
        self.level    = error.level
        self.line     = error.line
        self.column   = error.int2
        if not error.message:
            self.message = "unknown error"
        else:
            message = xmlerror.ffi.string(error.message)
            message = message.rstrip('\n')
            try:
                self.message = message.decode('utf8')
            except:
                try:
                    self.message = message.decode('ascii', 'backslashreplace')
                except:
                    self.message = '<undecodable error message>'
        if not error.file:
            self.filename = u'<string>'
        else:
            self.filename = _decodeFilename(xmlerror.ffi.string(error.file))

    def _setGeneric(self, domain, type, level, line, message, filename):
        self.domain  = domain
        self.type    = type
        self.level   = level
        self.line    = line
        self.column  = 0
        self.message = message
        self.filename = filename

    def __repr__(self):
        return u"%s:%d:%d:%s:%s:%s: %s" % (
            self.filename, self.line, self.column, self.level_name,
            self.domain_name, self.type_name, self.message)

    @property
    def domain_name(self):
        """The name of the error domain.  See lxml.etree.ErrorDomains
        """
        return ErrorDomains._getName(self.domain, u"unknown")

    @property
    def type_name(self):
        """The name of the error type.  See lxml.etree.ErrorTypes
        """
        if self.domain == ErrorDomains.RELAXNGV:
            getName = RelaxNGErrorTypes._getName
        else:
            getName = ErrorTypes._getName
        return getName(self.type, u"unknown")

    @property
    def level_name(self):
        """The name of the error level.  See lxml.etree.ErrorLevels
        """
        return ErrorLevels._getName(self.level, u"unknown")

class _BaseErrorLog:
    _handle = None

    def __init__(self, first_error, last_error):
        self._first_error = first_error
        self.last_error = last_error

    def get_handle(self):
        if self._handle is None:
            self._handle = xmlerror.ffi.new_handle(self)
        return self._handle

    def receive(self, entry):
        pass

    def _receive(self, error):
        entry = _LogEntry.__new__(_LogEntry)
        entry._setError(error)
        is_error = (error.level in (xmlerror.XML_ERR_ERROR, xmlerror.XML_ERR_FATAL))
        global_log = _getGlobalErrorLog()
        if global_log is not self:
            global_log.receive(entry)
            if is_error:
                global_log.last_error = entry
        self.receive(entry)
        if is_error:
            self.last_error = entry

    def _receiveGeneric(self, domain, type, level, line, message, filename):
        entry = _LogEntry.__new__(_LogEntry)
        entry._setGeneric(domain, type, level, line, message, filename)
        is_error = level == xmlerror.XML_ERR_ERROR or \
                   level == xmlerror.XML_ERR_FATAL
        global_log = _getGlobalErrorLog()
        if global_log is not self:
            global_log.receive(entry)
            if is_error:
                global_log.last_error = entry
        self.receive(entry)
        if is_error:
            self.last_error = entry

    def _buildParseException(self, exctype, default_message):
        code = xmlerror.XML_ERR_INTERNAL_ERROR
        if self._first_error is None:
            return exctype(default_message, code, 0, 0)
        message = self._first_error.message
        if message:
            code = self._first_error.type
        else:
            message = default_message
        line = self._first_error.line
        column = self._first_error.column
        if line > 0:
            if column > 0:
                message = u"%s, line %d, column %d" % (message, line, column)
            else:
                message = u"%s, line %d" % (message, line)
        return exctype(message, code, line, column)

    def _buildExceptionMessage(self, default_message):
        if self._first_error is None:
            return default_message
        if self._first_error.message:
            message = self._first_error.message
        elif default_message is None:
            return None
        else:
            message = default_message
        if self._first_error.line > 0:
            if self._first_error.column > 0:
                message = u"%s, line %d, column %d" % (
                    message, self._first_error.line, self._first_error.column)
            else:
                message = u"%s, line %d" % (message, self._first_error.line)
        return message

class _ListErrorLog(_BaseErrorLog):
    u"Immutable base version of a list based error log."
    def __init__(self, entries, first_error, last_error):
        if entries:
            if first_error is None:
                first_error = entries[0]
            if last_error is None:
                last_error = entries[-1]
        _BaseErrorLog.__init__(self, first_error, last_error)
        self._entries = entries

    def copy(self):
        u"""Creates a shallow copy of this error log.  Reuses the list of
        entries.
        """
        return _ListErrorLog(self._entries, self._first_error, self.last_error)

    def __iter__(self):
        return iter(self._entries)

    def __repr__(self):
        l = []
        for entry in self._entries:
            l.append(repr(entry))
        return u'\n'.join(l)

    def __getitem__(self, index):
        return self._entries[index]

    def __len__(self):
        return len(self._entries)

    def __contains__(self, error_type):
        for entry in self._entries:
            if entry.type == error_type:
                return True
        return False

    def __nonzero__(self):
        return bool(self._entries)

    def filter_types(self, types):
        u"""filter_types(self, types)

        Filter the errors by the given types and return a new error
        log containing the matches.
        """
        filtered = []
        if not python.PySequence_Check(types):
            types = (types,)
        for entry in self._entries:
            if entry.type in types:
                filtered.append(entry)
        return _ListErrorLog(filtered, None, None)

    def filter_from_level(self, level):
        u"""filter_from_level(self, level)

        Return a log with all messages of the requested level of worse.
        """
        filtered = []
        for entry in self._entries:
            if entry.level >= level:
                filtered.append(entry)
        return _ListErrorLog(filtered, None, None)

    def filter_from_fatals(self):
        u"""filter_from_fatals(self)

        Convenience method to get all fatal error messages.
        """
        return self.filter_from_level(ErrorLevels.FATAL)

    def filter_from_errors(self):
        u"""filter_from_errors(self)

        Convenience method to get all error messages or worse.
        """
        return self.filter_from_level(ErrorLevels.ERROR)

    def filter_from_warnings(self):
        u"""filter_from_warnings(self)

        Convenience method to get all warnings or worse.
        """
        return self.filter_from_level(ErrorLevels.WARNING)

class _ErrorLogContext(object):
    """
    Error log context for the 'with' statement.
    Stores a reference to the current callbacks to allow for
    recursively stacked log contexts.
    """

class _ErrorLog(_ListErrorLog):
    def __init__(self):
        self._logContexts = []
        _ListErrorLog.__init__(self, [], None, None)

    def __enter__(self):
        return self.connect()

    def __exit__(self, *args):
        self.disconnect()

    def connect(self):
        self._first_error = None
        del self._entries[:]
        connectErrorLog(self)

        context = _ErrorLogContext.__new__(_ErrorLogContext)
        context.old_error_func = xmlerror.get_xmlStructuredError()
        context.old_error_context = xmlerror.get_xmlStructuredErrorContext()
        self._logContexts.append(context)
        xmlerror.xmlSetStructuredErrorFunc(self.get_handle(), _receiveError)

    def disconnect(self):
        context = self._logContexts.pop()
        xmlerror.xmlSetStructuredErrorFunc(
            context.old_error_context, context.old_error_func)

    def clear(self):
        self._first_error = None
        del self._entries[:]

    def copy(self):
        u"""Creates a shallow copy of this error log and the list of entries.
        """
        return _ListErrorLog(self._entries[:], self._first_error,
                             self.last_error)

    def __iter__(self):
        return iter(self._entries[:])

    def receive(self, entry):
        if self._first_error is None:
            self._first_error = entry
        self._entries.append(entry)

class _RotatingErrorLog(_ErrorLog):
    def __init__(self, max_len):
        _ErrorLog.__init__(self)
        self._max_len = max_len

    def receive(self, entry):
        if len(self._entries) > self._max_len:
            del self._entries[0]
        self._entries.append(entry)

# thread-local, global list log to collect error output messages from
# libxml2/libxslt

__ERROR_LOG = threading.local()

def _getGlobalErrorLog():
    u"""Retrieve the global error log of this thread."""
    try:
        return __ERROR_LOG.log
    except AttributeError:
        log = _RotatingErrorLog(__MAX_LOG_SIZE)
        __ERROR_LOG.log = log
        return log

def _copyGlobalErrorLog():
    u"Helper function for properties in exceptions."
    return _getGlobalErrorLog().copy()

# local log functions: forward error to logger object
def _forwardError(c_log_handler, error):
    log_handler = xmlerror.ffi.from_handle(c_log_handler)
    log_handler._receive(error)

@xmlerror.ffi.callback("xmlStructuredErrorFunc")
def _receiveError(c_log_handler, error):
    # no Python objects here, may be called without thread context !
    _forwardError(c_log_handler, error)

################################################################################
## CONSTANTS FROM "xmlerror.h" (or rather libxml-xmlerror.html)
################################################################################

class MetaErrorEnum(type):
    def __new__(meta, name, bases, dict):
        cls = type.__new__(meta, name, bases, dict)
        if not hasattr(cls, 'elements'):
            return cls
        for value, name in cls.elements.items():
            setattr(cls, name, value)

        return cls

class BaseErrorEnum(object):
    __metaclass__ = MetaErrorEnum
    @classmethod
    def _getName(cls, value, default=None):
        return cls.elements.get(value, default)

class ErrorLevels(BaseErrorEnum):
    u"Libxml2 error levels"
    elements = dict(
        (value, name[8:])  # Strip "XML_ERR_" prefix
        for (value, name) in xmlerror.ffi.typeof("xmlErrorLevel").elements.items())

class ErrorDomains(BaseErrorEnum):
    u"Libxml2 error domains"
    elements = dict(
        (value, name[9:])  # Strip "XML_FROM_" prefix
        for (value, name) in xmlerror.ffi.typeof("xmlErrorDomain").elements.items())

class ErrorTypes(BaseErrorEnum):
    u"Libxml2 error types"
    elements = dict(
        (value, name[4:])  # Strip "XML_" prefix
        for (value, name) in xmlerror.ffi.typeof("xmlParserErrors").elements.items())

class RelaxNGErrorTypes(BaseErrorEnum):
    u"Libxml2 RelaxNG error types"
    elements = dict(
        (value, name[4:])  # Strip "XML_" prefix
        for (value, name) in xmlerror.ffi.typeof("xmlRelaxNGValidErr").elements.items())

