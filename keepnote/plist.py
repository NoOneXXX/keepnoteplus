"""
    KeepNote
    extended plist module

    Apple's property list xml serialization

    - added null type
"""


# python imports
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.elementtree.ElementTree as ET
from io import StringIO
import base64
import datetime
import re
import sys
from xml.sax.saxutils import escape

try:
    from .orderdict import OrderDict
except (ImportError, ValueError):
    OrderDict = dict


class Data (object):
    def __init__(self, text):
        self.text = text


# date format:
# ISO 8601 (in particular, YYYY '-' MM '-' DD 'T' HH ':' MM ':' SS 'Z'.
# Smaller units may be omitted with a loss of precision


_unmarshallers = {
    # collections
    "array": lambda x: [v.text for v in x],
    "dict": lambda x: OrderDict(
        (x[i].text, x[i+1].text) for i in range(0, len(x), 2)),
    "key": lambda x: x.text or "",

    # simple types
    "string": lambda x: x.text or "",
    "data": lambda x: Data(base64.decodestring(x.text or "")),
    "date": lambda x: datetime.datetime(*list(map(int, re.findall("\\d+", x.text)))),
    "true": lambda x: True,
    "false": lambda x: False,
    "real": lambda x: float(x.text),
    "integer": lambda x: int(x.text),
    "null": lambda x: None

}


def load(infile=sys.stdin):
    parser = ET.iterparse(infile)

    for action, elem in parser:
        unmarshal = _unmarshallers.get(elem.tag)
        if unmarshal:
            data = unmarshal(elem)
            elem.clear()
            elem.text = data
        elif elem.tag != "plist":
            raise IOError("unknown plist type: %r" % elem.tag)

    return parser.root.text


def loads(string):
    return load(StringIO(string))


def load_etree(elm):
    for child in elm:
        load_etree(child)

    unmarshal = _unmarshallers.get(elm.tag)
    if unmarshal:
        data = unmarshal(elm)
        elm.clear()
        elm.text = data
    elif elm.tag != "plist":
        raise IOError("unknown plist type: %r" % elm.tag)

    return elm.text


def dump(elm, out=sys.stdout, indent=0, depth=0, suppress=False):

    if indent and not suppress:
        out.write(" " * depth)

    if isinstance(elm, dict):
        out.write("<dict>")
        if indent:
            out.write("\n")
        for key, val in elm.items():
            if indent:
                out.write(" " * (depth + indent))
            out.write("<key>%s</key>" % key)
            dump(val, out, indent, depth+indent, suppress=True)
        if indent:
            out.write(" " * depth)
        out.write("</dict>")

    elif isinstance(elm, (list, tuple)):
        out.write("<array>")
        if indent:
            out.write("\n")
        for item in elm:
            dump(item, out, indent, depth+indent)
        if indent:
            out.write(" " * depth)
        out.write("</array>")

    elif isinstance(elm, str):
        out.write("<string>%s</string>" % escape(elm))

    elif isinstance(elm, bool):
        if elm:
            out.write("<true/>")
        else:
            out.write("<false/>")

    elif isinstance(elm, int):
        out.write("<integer>%d</integer>" % elm)

    elif isinstance(elm, float):
        out.write("<real>%f</real>" % elm)

    elif elm is None:
        out.write("<null/>")

    elif isinstance(elm, Data):
        out.write("<data>")
        base64.encode(StringIO(elm), out)
        out.write("</data>")

    elif isinstance(elm, datetime.datetime):
        raise Exception("not implemented")

    else:
        raise Exception("unknown data type '%s' for value '%s'" %
                        (str(type(elm)), str(elm)))

    if indent:
        out.write("\n")


def dumps(elm, indent=0):
    s = StringIO()
    dump(elm, s, indent)
    return s.getvalue()


# In keepnote.plist
def dump_etree(data, element=None):
    if element is None:
        element = ET.Element("dict")
    # Serialize data into element
    for key, value in data.items():
        key_elem = ET.SubElement(element, "key")
        key_elem.text = key
        if isinstance(value, dict):
            value_elem = ET.SubElement(element, "dict")
            dump_etree(value, value_elem)
        elif isinstance(value, list):
            value_elem = ET.SubElement(element, "array")
            for item in value:
                if isinstance(item, dict):
                    item_elem = ET.SubElement(value_elem, "dict")
                    dump_etree(item, item_elem)
                else:
                    item_elem = ET.SubElement(value_elem, "string")
                    item_elem.text = str(item)
        else:
            value_elem = ET.SubElement(element, "string")
            value_elem.text = str(value)
    return element
