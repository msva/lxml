# A pure-python version of includes/etreepublic.pxd

from .apihelpers import (
    _hasChild as hasChild,
    _attributeValueFromNsName as attributeValueFromNsName,
    _namespacedName as namespacedName,
    _namespacedNameFromNsName as namespacedNameFromNsName,
    _getNsTag as getNsTag,
    _getNsTagWithEmptyNs as getNsTagWithEmptyNs,
    _nextElement as nextElement,
    _previousElement as previousElement,
    _makeElement as makeElement,
    _setAttributeValue as setAttributeValue,
    _delAttributeFromNsName as delAttributeFromNsName,
    _setNodeText as setNodeText,
    _setTailText as setTailText,
    _appendChild as appendChild,
    _rootNodeOrRaise as rootNodeOrRaise,
    _hasText as hasText,
    _utf8 as utf8,
    _findChildBackwards as findChildBackwards,
    )
from .etree import (
    _elementFactory as elementFactory,
    )

from .apihelpers import _collectText, _isElement, _getNs
from .etree import _elementFactory, _attributeIteratorFactory
from .parser import _copyNodeToDoc

def deepcopyNodeToDocument(doc, c_root):
    u"Recursively copy the element into the document. doc is not modified."
    c_node = _copyNodeToDoc(c_root, doc._c_doc)
    return _elementFactory(doc, c_node)

def textOf(c_node):
    if not c_node:
        return None
    return _collectText(c_node.children)

def tailOf(c_node):
    if not c_node:
        return None
    return _collectText(c_node.next)

def findOrBuildNodeNsPrefix(doc, c_node, href, prefix):
    if doc is None:
        raise TypeError
    return doc._findOrBuildNodeNs(c_node, href, prefix, 0)

def iterattributes(element, keysvalues):
    return _attributeIteratorFactory(element, keysvalues)

