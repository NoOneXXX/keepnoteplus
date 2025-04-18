"""

    KeepNote
    Notebook data structure

"""

# python imports
import mimetypes
import os
import sys
import re
import urllib.parse
import urllib.request, urllib.error, urllib.parse
import uuid
import xml.etree.cElementTree as ET

# keepnote imports
from keepnote.listening import Listeners
from keepnote.timestamp import get_timestamp
from keepnote import trans
from keepnote.notebook.connection import fs as connection_fs
from keepnote.notebook import connection
from keepnote import safefile
from keepnote import orderdict
from keepnote import plist
from keepnote.pref import Pref
import keepnote

# currently imported for extensions that expect this here
from keepnote.notebook.connection.fs import get_valid_unique_filename
from keepnote.notebook.connection.fs import index as notebook_index
from keepnote.notebook import sync
import logging
logging.basicConfig(filename="keepnote_debug.log", level=logging.DEBUG)
# pyflakes import
get_valid_unique_filename

_ = trans.translate

#=============================================================================
# constants

# NOTE: the <?xml ?> header is left off to keep it compatiable with IE,
# for the time being.
# constants
NOTE_HEADER = """\
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" """ + """\
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml"><body>"""
NOTE_FOOTER = "</body></html>"
BLANK_NOTE = NOTE_HEADER + NOTE_FOOTER


NOTEBOOK_FORMAT_VERSION = 6
ELEMENT_NODE = 1
PAGE_DATA_FILE = "page.html"
PREF_FILE = "notebook.nbk"
NOTEBOOK_META_DIR = "__NOTEBOOK__"
NOTEBOOK_ICON_DIR = "icons"
TRASH_DIR = "__TRASH__"
TRASH_NAME = "Trash"
DEFAULT_PAGE_NAME = "New Page"
DEFAULT_DIR_NAME = "New Folder"

# content types
CONTENT_TYPE_PAGE = "text/xhtml+xml"
#CONTENT_TYPE_PLAIN_TEXT = "text/plain"
CONTENT_TYPE_TRASH = "application/x-notebook-trash"
CONTENT_TYPE_DIR = "application/x-notebook-dir"
CONTENT_TYPE_UNKNOWN = "application/x-notebook-unknown"

NULL = object()

# the node id of the implied root of all nodes everywhere
UNIVERSAL_ROOT = "b810760f-f246-4e42-aebb-50ce51c3d1ed"


#=============================================================================
# common filesystem functions

def get_unique_filename(path, filename, ext="", sep=" ", number=2,
                        return_number=False, use_number=False):
    """Returns a unique version of a filename for a given directory"""

    if path != "":
        assert os.path.exists(path), path

    # try the given filename
    if not use_number:
        newname = os.path.join(path, filename + ext)
        if not os.path.exists(newname):
            return (newname, None) if return_number else newname

    # try numbered suffixes
    i = number
    while True:
        newname = os.path.join(path, filename + sep + str(i) + ext)
        if not os.path.exists(newname):
            return (newname, i) if return_number else newname
        i += 1


def get_unique_filename_list(filenames, filename, ext="", sep=" ", number=2,
                             return_number=False, use_number=False):
    """Returns a unique filename for a given list of existing files"""
    filenames = set(filenames)

    # try the given filename
    if not use_number:
        newname = filename + ext
        if newname not in filenames:
            return (newname, None) if return_number else newname

    # try numbered suffixes
    i = number
    while True:
        newname = filename + sep + str(i) + ext
        if newname not in filenames:
            return (newname, i) if return_number else newname
        i += 1


def relpath(filename, start):
    """
    Returns the relative filename to start

    This is implemented to provide python2.5 support.
    """

    filename = os.path.normpath(filename)
    start = os.path.normpath(start)

    if filename.startswith(start):
        filename = filename[len(start):]
        while filename.startswith(os.path.sep):
            filename = filename[1:]
        return filename
    else:
        raise Exception("unhandled case")


#=============================================================================
# File naming scheme

def get_pref_file(nodepath):
    """Returns the filename of the notebook preference file"""
    return os.path.join(nodepath, PREF_FILE)


def normalize_notebook_dirname(filename, longpath=None):
    """
    Normalize a notebook filename

    If the filename contains 'path/to/the-notebook/notebook.nbk', then
    return 'path/to/the-notebook'.

    If the platform is windows (or longpath=True), then return the long
    file name prefix '\\\\?\\'.
    """
    filename = keepnote.ensure_unicode(filename, keepnote.FS_ENCODING)

    # allow long file paths in windows
    if (longpath is True or
            (longpath is None and keepnote.get_platform() == "windows")):
        filename = "\\\\?\\" + filename

    # ensure filename points to notebook directory
    if os.path.isdir(filename):
        return filename
    elif os.path.isfile(filename):
        # filename may be 'path/to/the-notebook/notebook.nbk'
        return os.path.dirname(filename)
    else:
        raise NoteBookError(_("Cannot find notebook '%s'" % filename))


#=============================================================================
# HTML functions

TAG_PATTERN = re.compile("<[^>]*>")


def strip_tags(line):
    return re.sub(TAG_PATTERN, "", line)


def read_data_as_plain_text(infile):
    """Read a Note data file as plain text"""

    # TODO: need to handle case when <body> and </body> are on same line

    for line in infile:
        # skip until body tag
        if "<body>" in line:
            pos = line.find("<body>")
            if pos != -1:
                yield strip_tags(line[pos+6:])
                break

    # yield until </body>
    for line in infile:
        pos = line.find("</body>")
        if pos != -1:
            yield strip_tags(line[:pos])
            break

        # strip tags
        yield strip_tags(line)


#=============================================================================
# functions

# TODO: Notebook version concept might need to be present in connection API

def get_notebook_version(filename):
    """Read the version of a notebook from its preference file"""
    if os.path.isdir(filename):
        filename = get_pref_file(filename)

    # Check if the file exists before attempting to read it
    if not os.path.exists(filename):
        keepnote.log_message(f"Notebook preference file '{filename}' not found. Assuming default version {NOTEBOOK_FORMAT_VERSION}.\n")
        return NOTEBOOK_FORMAT_VERSION

    try:
        tree = ET.ElementTree(file=filename)
    except IOError as e:
        raise NoteBookError(_("Cannot read notebook preferences"), e)
    except Exception as e:
        raise NoteBookError(_("Notebook preference data is corrupt"), e)

    return get_notebook_version_etree(tree)


def get_notebook_version_etree(tree):
    """Read the version of a notebook from an ElementTree"""

    root = tree.getroot()
    if root.tag == "notebook":
        p = root.find("version")
        if p is None:
            # assume latest version
            return NOTEBOOK_FORMAT_VERSION

        if not p.text.isdigit():
            raise NoteBookError(_("Unknown version string"))

        return int(p.text)
    else:
        raise NoteBookError(_("Notebook preference data is corrupt"))


def new_nodeid():
    """Generate a new node id"""
    return str(uuid.uuid4())


def get_node_url(nodeid, host=""):
    """Get URL for a nodeid"""
    return "nbk://%s/%s" % (host, nodeid)


def is_node_url(url):
    """Returns True if URL is a node"""
    return re.match("nbk://[^/]*/.*", url) is not None


def parse_node_url(url):
    """
    Parses a node URL into a tuple (host, nodeid)

    nbk:///abcd              => ("", "abcd")
    nbk://example.com/abcd   => ("example.com", "abcd")
    """
    match = re.match("nbk://([^/]*)/(.*)", url)
    if match:
        return match.groups()
    else:
        raise Exception("bad node URL")


def guess_file_mimetype(filename, default="application/octet-stream"):
    """Guess the mimetype of a file by its filename"""
    content_type = mimetypes.guess_type(filename)[0]
    if content_type is None:
        return default
    else:
        return content_type


def write_empty_page(node, page_file=PAGE_DATA_FILE):
    """Initializes an empty page file for a node"""
    out = node.open_file(page_file, "w", "utf-8")
    out.write(BLANK_NOTE)
    out.close()


#=============================================================================
# adding content to a notebook/nodes


def new_page(parent, title=None, index=None):
    """Add a new page to a node in a notebook"""

    if title is None:
        title = DEFAULT_PAGE_NAME

    child = parent.new_child(CONTENT_TYPE_PAGE, title, index)
    write_empty_page(child)
    return child


def attach_file(filename, node, index=None):
    """Attach a file to a node in a notebook"""

    # cannot attach directories (yet)
    if os.path.isdir(filename):
        return None

    # determine content-type
    content_type = guess_file_mimetype(filename)
    new_filename = os.path.basename(filename)

    try:
        child = node.new_child(content_type, new_filename, index)
        child.set_payload(filename, new_filename)
        child.save(True)
        return child

    except Exception as e:
        # remove child
        keepnote.log_error(e)
        if child:
            child.delete()
        raise e


#=============================================================================
# errors

class NoteBookError (Exception):
    """Exception that occurs when manipulating NoteBook's"""

    def __init__(self, msg, error=None):
        Exception.__init__(self)
        self.msg = msg
        self.error = error

    def __str__(self):
        if self.error is not None:
            return repr(self.error) + "\n" + self.msg
        else:
            return self.msg


class NoteBookVersionError (NoteBookError):
    """Exception for version errors while reading notebooks"""

    def __init__(self, notebook_version, readable_version,  error=None):
        NoteBookError.__init__(
            self,
            "Notebook version '%d' is higher than what is readable '%d'" %
            (notebook_version,
             readable_version),
            error)
        self.notebook_version = notebook_version
        self.readable_version = readable_version


#=============================================================================
# notebook attributes

_datatype_defaults = {
    "string": "",
    "integer": 0,
    "float": 0.0,
    "bool": False}


class AttrDef (object):
    """
    An AttrDef defines the type of an notebook attr
    """

    def __init__(self, key, datatype, name, default=None):
        self.key = key
        self.datatype = datatype
        self.name = name

        # default value
        if default is None:
            self.default = _datatype_defaults.get(datatype, None)
        else:
            self.default = default

    def format(self):
        """
        Returns dict representation
        """
        return {"key": self.key,
                "datatype": self.datatype,
                "name": self.name,
                "default": self.default}


class AttrDefs (object):
    """
    A collection of AttrDef's
    """

    def __init__(self):
        self._attr_defs = {}

    def add(self, attr_def):
        self._attr_defs[attr_def.key] = attr_def

    def remove(self, key):
        if key in self._attr_defs:
            del self._attr_defs[key]

    def clear(self):
        self._attr_defs.clear()

    def get(self, key):
        return self._attr_defs.get(key, None)

    def parse(self, lst):
        for item in lst:
            self.add(parse_attr_def(item))

    def format(self):
        return [attr_def.format()
                for attr_def in self._attr_defs.values()]


def format_attr_def(attr_def):
    return attr_def.format()


def parse_attr_def(attr_def_dict):
    return AttrDef(attr_def_dict["key"],
                   attr_def_dict["datatype"],
                   attr_def_dict.get("name", attr_def_dict["key"]),
                   default=attr_def_dict.get("default", None))


def iter_attr_defs(lst):
    for item in lst:
        yield parse_attr_def(item)


# typedef timestamp integer

g_default_attr_defs = [
    AttrDef("nodeid", "string", "Node ID"),
    AttrDef(
        "content_type", "string", "Content type", default=CONTENT_TYPE_DIR),
    AttrDef("title", "string", "Title"),
    AttrDef("order", "integer", "Order", default=sys.maxsize),
    AttrDef("created_time", "timestamp", "Created time"),
    AttrDef("modified_time", "timestamp", "Modified time"),
    AttrDef("expanded", "bool", "Expaned", default=True),
    AttrDef("expanded2", "bool", "Expanded2", default=True),
    AttrDef("info_sort", "string", "Folder sort", default="order"),
    AttrDef("info_sort_dir", "integer", "Folder sort direction", default=1),
    AttrDef("icon", "string", "Icon"),
    AttrDef("icon_open", "string", "Icon open"),
    AttrDef("payload_filename", "string", "Filename"),
    AttrDef("duplicate_of", "string", "Duplicate of"),
    AttrDef("title_bgcolor", "string", "Title Background Color")
]


class AttrTable (object):
    def __init__(self, key, name, attrs=[]):
        self.key = key
        self.name = name
        self.attrs = list(attrs)

    def format(self):
        return {"key": self.key,
                "name": self.name,
                "attrs": list(self.attrs)}


class AttrTables (object):
    """
    A collection of AttrTable's
    """

    def __init__(self):
        self._attr_tables = {}

    def add(self, attr_table):
        self._attr_tables[attr_table.key] = attr_table

    def remove(self, key):
        if key in self._attr_tables:
            del self._attr_tables[key]

    def clear(self):
        self._attr_tables.clear()

    def get(self, key):
        return self._attr_tables.get(key, None)

    def parse(self, lst):
        for item in lst:
            self.add(parse_attr_table(item))

    def format(self):
        return [attr_table.format()
                for attr_table in self._attr_tables.values()]


g_default_attr_tables = [
    AttrTable(
        "default", "Default Table",
        attrs=["title", "created_time", "modified_time"])]


def format_attr_table(attr_table):
    return attr_table.format()


def parse_attr_table(dct):
    return AttrTable(dct["key"], dct["name"], dct["attrs"])


def iter_attr_tables(lst):
    for item in lst:
        yield parse_attr_table(item)


#=============================================================================
# Notebook nodes

BUILTIN_ATTR = ("nodeid", "parentids", "childrenids", "order")


class NoteBookNode (object):
    """A general base class for all nodes in a NoteBook"""

    def __init__(self, title="", parent=None, notebook=None,
                 content_type=CONTENT_TYPE_DIR, conn=None,
                 attr=None):
        self._notebook = notebook
        self._conn = conn if conn else self._notebook._conn
        self._parent = parent
        self._children = None
        self._has_children = None
        self._valid = True

        self._attr = {"version": NOTEBOOK_FORMAT_VERSION,
                      "title": title,
                      "content_type": content_type}
        if attr:
            self._attr.update(attr)

    def is_valid(self):
        """Returns True if node is valid (not deleted)"""
        return self._valid

    def get_notebook(self):
        """Returns the notebook that owns this node"""
        return self._notebook

    #==============================================
    # filesystem-specific methods (may not always be available)

    def get_path(self):
        """Returns the directory path of the node"""
        return self._conn.get_node_path(self._attr["nodeid"])

    def get_basename(self):
        """Returns the basename of the node"""
        return self._conn.get_node_basename(self._attr["nodeid"])

    #================================
    # URL methods

    def get_url(self, host=""):
        """Returns URL for node"""
        return get_node_url(self._attr["nodeid"], host)

    #=======================================
    # attr methods

    def clear_attr(self, title="", content_type=CONTENT_TYPE_DIR):
        """Clear attributes (set them to defaults)"""
        for key in list(self._attr.keys()):
            if key not in BUILTIN_ATTR:
                del self._attr[key]

        # set title and content_type
        self._attr["title"] = title
        self._attr["content_type"] = content_type

    def get_attr(self, name, default=None):
        """Get the value of an attribute"""
        return self._attr.get(name, default)

    def set_attr(self, name, value):
        """Set the value of an attribute"""
        oldvalue = self._attr.get(name, NULL)
        self._attr[name] = value
        if value != oldvalue:
            self._set_dirty(True)

    def has_attr(self, name):
        """Returns True if node has the attribute"""
        return name in self._attr

    def del_attr(self, name):
        """Delete an attribute from the node"""

        # TODO: check against un-deletable attributes
        if name in self._attr:
            del self._attr[name]
        self._set_dirty(True)

    def iter_attr(self):
        """Iterate through attributes of the node"""
        return iter(self._attr.items())

    def _init_attr(self):
        """Initialize attributes from a dict"""
        t = get_timestamp()
        self._attr.setdefault("created_time", t)
        self._attr.setdefault("modified_time", t)
        self._attr.setdefault("childrenids", [])
        self._attr.setdefault("parentids", [])

    #========================================
    # special attr methods

    def get_parent(self):
        """Returns the parent of the node"""
        return self._parent

    def get_title(self):
        """Returns the display title of a node"""
        return self._attr.get("title", "")

    def set_attr_timestamp(self, name, timestamp=None):
        """Set a timestamp attribute"""
        if timestamp is None:
            timestamp = get_timestamp()
        self._attr[name] = timestamp
        self._set_dirty(True)

    def set_payload(self, filename, new_filename=None):
        """Copy file into NoteBook directory"""
        logging.debug(f"Loading notebook at: {path}")
        # determine new file name
        if new_filename is None:
            new_filename = os.path.basename(filename)
        new_filename = connection_fs.new_filename(
            self._conn, self._attr["nodeid"], new_filename, None)
        logging.debug("Finished loading notebook")
        try:
            # attempt url parse
            parts = urllib.parse.urlparse(filename)

            if os.path.exists(filename) or parts[0] == "":
                # perform local copy
                self._conn.copy_file(None, filename,
                                     self._attr["nodeid"], new_filename)
            else:
                # perform download
                out = self.open_file(new_filename, "w")
                infile = urllib.request.urlopen(filename)
                while True:
                    data = infile.read(1024*4)
                    if data == "":
                        break
                    out.write(data)
                infile.close()
                out.close()
        except Exception as e:
            raise NoteBookError(_("Cannot copy file '%s'" % filename), e)

        # set attr
        self._attr["payload_filename"] = new_filename

    #=============================================
    # node structure methods

    def create(self):
        """Initializes the node on disk (create required files/directories)"""

        if "nodeid" not in self._attr:
            self._attr["nodeid"] = new_nodeid()
        self._attr["parentids"] = [self._parent._attr["nodeid"]]
        self._attr["childrenids"] = []
        self._attr.setdefault("order", sys.maxsize)

        self._init_attr()

        self._conn.create_node(self._attr["nodeid"], self._attr)
        self._set_dirty(False)

    def delete(self):
        """Deletes this node from the notebook"""

        # when deleting multiple nodes, some nodes (children) might already
        # be invalid.  Therefore, ignore them.
        if not self._valid:
            return

        # check whether this is allowed
        allowed, error = self._notebook.delete_allowed(self)
        if not allowed:
            raise error

        # perform delete on disk
        def walk(node):
            for child in node.get_children():
                walk(child)
            self._conn.delete_node(node._attr["nodeid"])
        walk(self)

        # update data structure
        self._parent._remove_child(self)
        self._parent._set_child_order()
        self._set_dirty(False)

        # TODO: this will change with multiple parents.  Need GC of some sort
        # make sure to recursively invalidate
        def walk(node):
            node._valid = False
            if node._children is not None:
                for child in node._children:
                    walk(child)
        walk(self)

        # parent node notifies listeners of change
        self._notebook.node_changed.notify(
            [("removed", self._parent, self._attr["order"])])

    def trash(self):
        """Places node in the notebook's trash folder"""
        if self._notebook is None:
            raise NoteBookError(_("This node is not part of any notebook"))

        if self.in_trash():
            # delete if in trash folder already
            self.delete()
        else:
            # move to trash
            self.move(self._notebook._trash)

    def in_trash(self):
        """Determines if node is inside Trash folder"""

        # TODO: become more complicated with general graph structure
        # trace up through parents

        if self == self._notebook._trash:
            return True

        ptr = self._parent
        while ptr is not None:
            if ptr == self._notebook._trash:
                return True
            ptr = ptr._parent
        return False

    def move(self, parent, index=None):
        """Move this node to be the child of another node 'parent'"""

        # TODO: if parent is in another notebook, accessory data like icons
        # might need to be transferred.
        #  Maybe I won't support that.

        # TODO: with multiple parents, we need to specify here which
        # parent relationship we are breaking.

        assert self != parent
        old_parent = self._parent
        #old_index = self._attr["order"]

        # check whether move is allowed
        allowed, error = self._notebook.move_allowed(self, parent, index)
        if not allowed:
            raise error

        # check to see if move is across notebooks
        if self._notebook != parent._notebook:
            return self._move_notebooks(parent, index)

        # make sure new parents children are loaded
        parent.get_children()

        # perform actual move if new parent
        if old_parent != parent:
            try:
                self._attr["parentids"] = [parent._attr["nodeid"]]
                self.save(True)
            except:
                self._attr["parentids"] = [old_parent._attr["nodeid"]]
                raise

        # perform move in NoteBook data structure
        self._parent._remove_child(self)
        if self._parent != parent:
            self._parent._set_child_order()
            self._parent = parent
            self._parent._add_child(self, index)
        else:
            if self._attr["order"] < index:
                index -= 1
            self._parent._add_child(self, index)
        self.save(True)

        # notify listeners
        if parent != old_parent:
            self.notify_changes([old_parent, parent], True)
        else:
            old_parent.notify_change(True)

        # TODO: I would like to do this, but it is complicated when
        # the 'added' event changes path of 'remove' location
        #self._notebook.node_changed.notify([
        #        ("removed", old_parent, old_index), ("added", self)])

    def _move_notebooks(self, parent, index=None):
        """Move node to a different notebook"""

        # TODO: does conflict detection go inside the connection?

        conn1 = self._conn
        conn2 = parent._conn

        # perform sync subtree between connections
        try:
            # change parent pointer
            self._attr["parentids"] = [parent._attr["nodeid"]]

            def walk(node):
                sync.sync_node(node._attr["nodeid"], conn1, conn2,
                               attr=node._attr)
                for child in node.get_children():
                    walk(child)
            walk(self)
        except:
            keepnote.log_error()
            raise

        # delete self from this notebook
        self.delete()

        # reread node from other connection
        try:
            new_child = parent._notebook._read_node(
                self._attr["nodeid"], parent)
            parent.add_child(new_child, index=index)
        except:
            keepnote.log_error()
            pass

    def rename(self, title):
        """Renames the title of the node"""

        # TODO: keep attach file names in sync

        self.set_attr("title", title)
        self.save()

        # TODO: generalize notify for all attrs that might appear in listview
        # or other GUI widgets
        self.notify_change(False)

    def new_child(self, content_type, title, index=None):
        """Add a new node under this node"""
        self.get_children()
        node = self._notebook.new_node(content_type, self, {"title": title})
        self._add_child(node, index)
        node.save(True)
        #self.notify_change(True)
        self._notebook.node_changed.notify([("added", node)])
        return node

    def _new_child(self, content_type, title, index=None):
        """
        Add a new node under this node
        Private method.  Does not notify listeners.
        """
        self.get_children()
        node = self._notebook.new_node(content_type, self, {"title": title})
        self._add_child(node, index)
        node.save(True)
        return node

    def duplicate(self, parent, index=None, recurse=False, notify=True,
                  skip=None):
        """Duplicate a node to a new parent"""

        # NOTE: we must be able to handle the case where the root node is
        # duplicated.

        # initialize skip set to prevent double copying
        if skip is None:
            skip = set()

        # create new node
        node = parent._new_child(self.get_attr("content_type"),
                                 self.get_attr("title", ""),
                                 index=index)
        skip.add(node)

        # copy attributes
        for key, value in self.iter_attr():
            if key not in ("nodeid", "order", "parentids", "childrenids"):
                node._attr[key] = value

        # record the nodeid of the original node
        node._attr["duplicate_of"] = self.get_attr("nodeid")

        #node._conn.update_node(node._attr["nodeid"], node._attr)
        node._write_attr(node._attr)

        # copy files
        try:
            sync.sync_files(self._conn, self._attr["nodeid"],
                            node._conn, node._attr["nodeid"])
        except:
            keepnote.log_error()
            # TODO: handle errors
            pass

        # TODO: prevent loops, copy paste within same tree.
        if recurse:
            for child in self.get_children():
                if child not in skip:
                    child.duplicate(node, recurse=True, notify=False,
                                    skip=skip)

        if notify:
            parent.notify_change(True)

        return node

    def _write_attr(self, attr):
        #self._notebook._mask_attr.set_dict(attr)
        #self._conn.update_node(attr["nodeid"], self._notebook._mask_attr)
        self._conn.update_node(attr["nodeid"], attr)

    #==================================
    # child node management

    def get_children(self):
        """Returns all children of this node"""
        if self._children is None:
            self._get_children()
        return self._children

    def has_children(self):
        """Return True if node has children"""
        if self._children is None:
            if self._has_children is None:
                self._has_children = (len(self._attr["childrenids"]) > 0)
            return self._has_children
        else:
            return len(self._children) > 0

    def add_child(self, child, index=None):
        """Add node as a child"""
        self._add_child(child, index)
        self._notebook.node_changed.notify([("added", child)])
        #self.notify_change(True)

    def allows_children(self):
        """Returns True if this node allows children"""
        return True

    def _get_children(self):
        """Load children list from filesystem"""
        self._children = list(self._iter_children())

        # assign orders
        self._children.sort(key=lambda x: x._attr.get("order", sys.maxsize))
        self._set_child_order()

    def _iter_children(self):
        """Iterate through children
           Returns temporary node objects
        """
        for childid in self._attr["childrenids"]:
            try:
                yield self._notebook._read_node(childid, parent=self)
            except:
                keepnote.log_error()
                continue

    def _set_child_order(self):
        """Ensures that child know their order in the children list"""
        for i, child in enumerate(self._children):
            if child._attr.get("order") != i:
                child._attr["order"] = i
                child._set_dirty(True)

    def _add_child(self, child, index=None):
        """Add a node as a child"""

        # propogate notebook
        child._notebook = self._notebook
        child._conn = self._conn

        # determine insert location
        if self._children is None:
            self._get_children()

        if index is not None:
            # insert child at index
            self._children.insert(index, child)
            self._set_child_order()
        elif (self._notebook and len(self._children) > 0 and
              self._children[-1] == self._notebook.get_trash()):
            # append child before trash
            self._children.insert(len(self._children)-1, child)
            self._set_child_order()
        else:
            # append child at end of list
            child._attr["order"] = len(self._children)
            self._children.append(child)

        child._set_dirty(True)

    def _remove_child(self, child):
        """Remove a child node"""
        if self._children is None:
            self._get_children()
        self._children.remove(child)

    #==============================================
    # input/output

    def save(self, force=False):
        """Save node if modified (dirty)"""
        if (force or self._is_dirty()) and self._valid:
            self._write_attr(self._attr)
            #self._conn.update_node(self._attr["nodeid"], self._attr)
            self._set_dirty(False)

    #=============================================
    # node file methods

    def open_file(self, filename, mode="r", codec=None):
        return self._conn.open_file(
            self._attr["nodeid"], filename, mode, codec=codec)

    def delete_file(self, filename):
        return self._conn.delete_file(self._attr["nodeid"], filename)

    def new_filename(self, new_filename, ext="", sep=" ", number=2,
                     return_number=False, use_number=False, ensure_valid=True):
        return connection_fs.new_filename(
            self._conn,
            self._attr["nodeid"], new_filename, ext, sep, number,
            return_number=return_number, use_number=use_number,
            ensure_valid=ensure_valid)

    def list_dir(self, filename="/"):
        return self._conn.list_dir(self._attr["nodeid"], filename)

    def create_dir(self, filename):
        self._conn.create_dir(self._attr["nodeid"], filename)

    def get_page_file(self):
        """Returns filename of data/text/html/etc"""
        # TODO: think about generalizing this to payload concept
        return PAGE_DATA_FILE

    def get_file(self, filename):
        return self._conn.get_file(self._attr["nodeid"], filename)

    def get_data_file(self):
        """
        Returns filename of data/text/html/etc

        (deprecated can't always assume data file has local path)
        """
        return self._conn.get_file(self._attr["nodeid"], PAGE_DATA_FILE)

    #=============================================
    # marking for save needed

    def _set_dirty(self, dirty):
        """Sets the dirty bit to indicates whether node needs saving"""
        self._notebook._set_dirty_node(self, dirty)

    def _is_dirty(self):
        """Returns True if node needs saving"""
        return self._notebook._is_dirty_node(self)

    def mark_modified(self):
        """Marks a node as modified or dirty"""
        self._notebook._set_dirty_node(self, True)

    #===============================================
    # listeners

    def notify_change(self, recurse):
        """Notify listeners that node has changed"""
        if self._notebook:
            if recurse:
                self._notebook.node_changed.notify([("changed-recurse", self)])
            else:
                self._notebook.node_changed.notify([("changed", self)])

    def notify_changes(self, nodes, recurse):
        """Notify listeners that several nodes have changed"""
        if self._notebook:
            if recurse:
                self._notebook.node_changed.notify(
                    [("changed-recurse", n) for n in nodes])
            else:
                self._notebook.node_changed.notify(
                    [("changed", n) for n in nodes])

    '''
    def suppress_change(self, listener=None):
        """Suppress notification of listeners for node changes"""
        if self._notebook:
            self._notebook.node_changed.suppress(listener)

    def resume_change(self, listener=None):
        """Resume notification of listeners for node changes"""
        if self._notebook:
            self._notebook.node_changed.resume(listener)
    '''


class NodeAction (object):
    pass


#=============================================================================
# Notebook preferences


class NoteBookPreferences (Pref):
    """Preference data structure for a NoteBook"""
    def __init__(self):
        keepnote.Pref.__init__(self)

        self.quick_pick_icons_changed = Listeners()
        self.init()

    def set_data(self, data):
        self.init()
        self._data.update(data)

    def get_data(self):
        return self._data

    def init(self):
        self._data["version"] = NOTEBOOK_FORMAT_VERSION
        self._data["quick_pick_icons"] = []

        self.quick_pick_icons_changed.notify()

    def get_quick_pick_icons(self):
        return self._data.get("quick_pick_icons", [])

    def set_quick_pick_icons(self, icons):
        self._data["quick_pick_icons"] = list(icons)
        self.quick_pick_icons_changed.notify()


#=============================================================================
# NoteBook type


class NoteBook (NoteBookNode):
    """Class represents a NoteBook"""

    def __init__(self):

        self._conn = None  # Note: this comes first in order satify base class
        NoteBookNode.__init__(self, notebook=self,
                              content_type=CONTENT_TYPE_DIR)

        self.pref = NoteBookPreferences()
        self._filename = None
        self._dirty = set()
        self._trash = None
        self.attr_defs = AttrDefs()
        self.attr_tables = AttrTables()
        self._necessary_attrs = []

        # init notebook attributes
        self._init_default_attr()

        self._attr["order"] = 0

        # listeners
        self.listeners = {}
        self.node_changed = Listeners()  # signature = (node, recurse)
        self.closing_event = Listeners()
        self.close_event = Listeners()

    def get_listeners(self, key):
        """Get custom listener"""
        listeners = self.listeners.get(key, None)
        if listeners is None:
            listeners = Listeners()
            self.listeners[key] = listeners
        return listeners

    #=====================================
    # attrs

    def _init_default_attr(self):
        """Initialize default notebook attributes"""

        # TODO: not being used right now
        self._necessary_attrs = ["nodeid", "created_time", "modified_time",
                                 "order"]

        # init attr defs
        self.attr_defs.clear()
        for attr_def in g_default_attr_defs:
            self.attr_defs.add(attr_def)

        # init attr tables
        self.attr_tables.clear()
        for attr_table in g_default_attr_tables:
            self.attr_tables.add(attr_table)

    def add_attr_def(self, attr_def):
        """Adds a new attribute definition to the notebook"""
        self.attr_defs.add(attr_def)

    def clear_attr_defs(self):
        """Clears all attribute definitions from the notebook"""
        self.attr_defs.clear()

    def get_necessary_attrs(self):
        """Returns necessary attributes"""
        return self._necessary_attrs

    def _read_attr_defs(self):
        self._init_default_attr()

        self.attr_defs.parse(self._attr.get("attr_defs", ()))
        self.attr_tables.parse(self._attr.get("attr_tables", ()))

    def _write_attr_defs(self):
        self._attr["attr_defs"] = self.attr_defs.format()
        self._attr["attr_tables"] = self.attr_tables.format()

    #===================================================
    # input/output

    def create(self, filename, conn=None):
        """Initialize NoteBook at location 'filename'"""
        self._conn = conn if conn else connection_fs.NoteBookConnectionFS()
        self._filename = filename

        self._attr["nodeid"] = new_nodeid()
        self._init_attr()

        self._conn.connect(filename)
        self._conn.create_node(self._attr["nodeid"],  self._attr)

        self._init_index()

        self.write_preferences()

        self._set_dirty(False)

        self._init_trash()

    def load(self, filename, conn=None):
        """Load the NoteBook from filename"""
        self._conn = conn if conn else connection_fs.NoteBookConnectionFS()

        if isinstance(self._conn, connection_fs.NoteBookConnectionFS):
            # ensure filename points to notebook directory
            filename = normalize_notebook_dirname(filename, longpath=False)

            # TODO: generalize. this is currently fs-specific
            # cheat by reading preferences first so that we can set index_dir
            # if needed.  Ideally this should be set in the app pref, but in a
            # notebook-specific way
            pref_file = os.path.join(filename, PREF_FILE)
            if os.path.exists(pref_file):
                try:
                    self.read_preferences(
                        safefile.open(pref_file, codec="utf-8"))

                    # TODO: temp solution. remove soon.
                    index_dir = self.pref.get("index_dir", default="")
                    if index_dir and os.path.exists(index_dir):
                        self._conn._set_index_file(
                            os.path.join(index_dir, notebook_index.INDEX_FILE))
                except:
                    pass

            # check version
            version = get_notebook_version(filename)
            if version > NOTEBOOK_FORMAT_VERSION:
                raise NoteBookVersionError(version, NOTEBOOK_FORMAT_VERSION)

        # read basic info
        self._filename = filename
        self._conn.connect(filename)
        self._init_index()

        attr = self._conn.read_node(self._conn.get_rootid())
        self._attr.update(attr)
        self._init_attr()

        self._init_trash()

        self._read_attr_defs()

        self.read_preferences()

        self.notify_change(True)

    def save(self, force=False):
        """Recursively save any loaded nodes"""

        # TODO: keepnote copy of old pref.  only save pref if its changed.

        if force or self in self._dirty:
            self._write_attr_defs()
            self._write_attr(self._attr)
            #self._conn.update_node(self._attr["nodeid"], self._attr)
            self.write_preferences()
        self._set_dirty(False)

        if force:
            for node in self.get_children():
                node.save(force=force)
        else:
            for node in list(self._dirty):
                node.save()
        self._conn.save()

        self._dirty.clear()

    def close(self, save=True):
        """Close notebook"""
        self.closing_event.notify(self, save)
        if save:
            self.save()
        self._conn.close()
        self.close_event.notify(self)

    def get_connection(self):
        """Returns the notebook connection"""
        return self._conn

    def get_filename(self):
        return self._filename

    def _init_index(self):
        """Initialize the index"""

        # TODO: ideally I would like to do index_attr()'s before
        # conn.init_index(), so that the initial indexing properly
        # catches all the desired attr's
        self._conn.index_attr("icon", "TEXT")
        self._conn.index_attr("title", "TEXT", index_value=True)

    #--------------------------------------
    # input/output

    def save_needed(self):
        """Returns True if save is needed"""
        return len(self._dirty) > 0

    def new_node(self, content_type, parent, attr):
        """Create a new NodeBookNode"""

        node = NoteBookNode(attr.get("title", DEFAULT_PAGE_NAME),
                            parent=parent, notebook=self,
                            content_type=content_type,
                            attr=attr)
        node.create()
        return node

    def move_allowed(self, node, parent, index=None):
        """Returns True if this node move is allowed"""

        if node.get_attr("content_type") == CONTENT_TYPE_TRASH:
            if parent != self:
                # trash node must be child of root
                return False, NoteBookError(
                    _("The Trash folder must be a top-level folder."))

        # move is allowed
        return True, None

    def delete_allowed(self, node):
        """Returns True if this node can be deleted"""

        if node.get_attr("content_type") == CONTENT_TYPE_TRASH:
            # cannot delete trash
            return False, NoteBookError(
                _("The Trash folder cannot be deleted."))

        return True, None

    def _set_dirty_node(self, node, dirty):
        """Mark a node to be dirty (needs saving) in NoteBook"""

        if dirty:
            self._dirty.add(node)
        else:
            if node in self._dirty:
                self._dirty.remove(node)

    def _is_dirty_node(self, node):
        """Returns True if node is dirty (needs saving)"""
        return node in self._dirty

    def _read_node(self, nodeid, parent=None,
                   default_content_type=CONTENT_TYPE_DIR):
        attr = self._conn.read_node(nodeid)
        node = NoteBookNode(
            attr.get("title", DEFAULT_PAGE_NAME),
            parent=parent, notebook=self,
            content_type=attr.get("content_type", default_content_type),
            attr=attr)
        node._init_attr()

        return node

    #=====================================
    # trash functions

    def get_trash(self):
        """Returns the Trash Folder for the NoteBook"""
        return self._trash

    def _init_trash(self):
        """Ensures Trash directory exists in a notebook"""

        # ensure trash directory exists
        self._trash = None
        for child in self.get_children():
            if self.is_trash_dir(child):
                self._trash = child
                break

        # if no trash folder, create it
        if self._trash is None:
            try:
                self._trash = self.new_node(CONTENT_TYPE_TRASH, self,
                                            {"title": TRASH_NAME})
                self._add_child(self._trash)

            except NoteBookError as e:
                raise NoteBookError(_("Cannot create Trash folder"), e)

    def is_trash_dir(self, node):
        """Returns True if node is a Trash Folder"""
        return node.get_attr("content_type") == CONTENT_TYPE_TRASH

    def empty_trash(self):
        """Deletes all nodes under Trash Folder"""

        for child in reversed(list(self._trash.get_children())):
            child.delete()

    #==============================================
    # icons

    # TODO: think about how to replace icon interface with connection.
    # this may not be necessary

    # TODO: maybe I can move this interface outside of the notebook object

    def get_icon_file(self, basename):
        """Lookup icon filename in notebook icon store"""

        # TODO: is there a better way to access icons?
        # directly by stream?
        filename = connection.path_join(
            NOTEBOOK_META_DIR, NOTEBOOK_ICON_DIR, basename)
        if self._conn.has_file(self._attr["nodeid"], filename):
            return self._conn.get_file(self._attr["nodeid"], filename)
        else:
            return None

    def get_icons(self):
        """Returns list of icons in notebook icon store"""
        filename = connection.path_join(
            NOTEBOOK_META_DIR, NOTEBOOK_ICON_DIR) + '/'
        filenames = list(self._conn.list_dir(self._attr["nodeid"], filename))
        filenames.sort()
        return filenames

    def install_icon(self, filename):
        """Installs an icon into the notebook icon store"""

        # TODO: test this function

        basename = os.path.basename(filename)
        basename, ext = os.path.splitext(basename)
        newfilename = connection.path_join(
            NOTEBOOK_META_DIR, NOTEBOOK_ICON_DIR, basename)

        newfilename = connection_fs.new_filename(
            self._conn, self._attr["nodeid"], newfilename, ext, "-",
            ensure_valid=False)

        self._conn.copy_file(None, filename,
                             self._attr["nodeid"], newfilename)
        return connection.path_basename(newfilename)

    def install_icons(self, filename, filename_open):
        """Installs an icon into the notebook icon store"""

        # TODO: test this function

        basename = os.path.basename(filename)
        basename, ext = os.path.splitext(basename)
        startname = connection.path_join(NOTEBOOK_META_DIR, NOTEBOOK_ICON_DIR,
                                         basename)

        number = 2
        use_number = False
        while True:
            newfilename, number = connection_fs.new_filename(
                self._conn, self._attr["nodeid"], startname, ext, "-",
                number=number, return_number=True, use_number=use_number,
                ensure_valid=False)

            # determine open icon filename
            newfilename_open = startname
            if number:
                newfilename_open += "-" + str(number)
            else:
                number = 2
            newfilename_open += "-open" + ext

            # see if it already exists
            if self._conn.has_file(self._attr["nodeid"], newfilename_open):
                number += 1
                use_number = True
            else:
                # we are done searching for names
                break

        self._conn.copy_file(None, filename,
                             self._attr["nodeid"], newfilename)
        self._conn.copy_file(None, filename_open,
                             self._attr["nodeid"], newfilename_open)

        return (connection.path_basename(newfilename),
                connection.path_basename(newfilename_open))

    def uninstall_icon(self, basename):
        """Removes an icon from the notebook icon store"""
        if len(basename) == 0:
            return
        filename = connection.path_join(
            NOTEBOOK_META_DIR, NOTEBOOK_ICON_DIR, basename)
        self._conn.delete_file(self._attr["nodeid"], filename)

    #================================================
    # search

    def get_node_by_id(self, nodeid):
        """Lookup node by nodeid"""

        # TODO: could make this more efficient by not loading all uncles
        path = self._conn.get_node_path_by_id(nodeid)
        if path is None:
            keepnote.log_message("node %s not found\n" % nodeid)
            return None

        def walk(node, path, i):
            if i >= len(path):
                return node

            # search children
            nodeid2 = path[i]
            for child in node.get_children():
                if child.get_attr("nodeid") == nodeid2:
                    return walk(child, path, i+1)

            # node not found
            keepnote.log_message("node %s not found\n" % str(path))
            return None
        return walk(self._notebook, path[1:], 0)

    def get_node_path_by_id(self, nodeid):
        """Lookup node path by nodeid"""
        return self._conn.get_node_path_by_id(nodeid)

    def search_node_titles(self, text):
        """Search nodes by title"""
        return self._conn.search_node_titles(text)

    def search_node_contents(self, text):
        """Search nodes by content"""
        return self._conn.search_node_contents(text)

    def has_fulltext_search(self):
        """Returns True if full text indexed search is availble"""
        return self._conn.index(["has_fulltext"])

    def enable_fulltext_search(self, enabled):
        """Returns True if full text indexed search is availble"""
        return self._conn.index(["enable_fulltext", enabled])

    def get_attr_by_id(self, nodeid, key):
        """Returns attr value for a node with id 'nodeid'"""
        return self._conn.get_attr_by_id(nodeid, key)

    def index(self, query):
        return self._conn.index(query)

    #----------------------------------------
    # index interface (temparary until fully transparent)

    def index_needed(self):
        return self._conn.index_needed()

    def clear_index(self):
        return self._conn.clear_index()

    def index_all(self):
        for node in self._conn.index_all():
            yield node

    #===============================================
    # preferences

    def get_pref_file(self):
        """Gets the NoteBook's preference file"""
        return self._conn.get_file(self._attr["nodeid"], PREF_FILE)

    def get_pref_dir(self):
        """
        Gets the NoteBook's preference directory
        (deprecated, only used by index module)
        """
        return self._conn.get_file(self._attr["nodeid"], NOTEBOOK_META_DIR)

    def get_icon_dir(self):
        """Gets the NoteBook's icon directory"""
        return self._conn.get_file(
            self._attr["nodeid"],
            connection.path_join(NOTEBOOK_META_DIR, NOTEBOOK_ICON_DIR))

    def set_preferences_dirty(self):
        """Notifies notebook that preferences need saving"""
        self._set_dirty(True)

    def write_preferences(self):
        """Writes the NoteBooks preferences"""
        try:
            # ensure preference directory exists
            self._conn.create_dir(
                self._attr["nodeid"], NOTEBOOK_META_DIR + "/")

            # ensure icon directory exists
            self._conn.create_dir(
                self._attr["nodeid"],
                NOTEBOOK_META_DIR + "/" + NOTEBOOK_ICON_DIR + "/")

            data = self.pref.get_data()

            out = self.open_file(PREF_FILE, "w", codec="utf-8")
            out.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                      '<notebook>\n'
                      '<version>%d</version>\n'
                      '<pref>\n' % data["version"])
            plist.dump(data, out, indent=4, depth=4)
            out.write('</pref>\n'
                      '</notebook>\n')
            out.close()

        except (IOError, OSError) as e:
            raise NoteBookError(_("Cannot save notebook preferences"), e)
        except Exception as e:
            raise NoteBookError(_("File format error"), e)

    def read_preferences(self, infile=None):
        """Reads the NoteBook's preferneces"""
        try:
            if infile is None:
                infile = self.open_file(PREF_FILE, "r", codec="utf-8")
            root = ET.fromstring(infile.read())
            tree = ET.ElementTree(root)
        except IOError as e:
            raise NoteBookError(_("Cannot read notebook preferences %s") %
                                self.get_file(PREF_FILE), e)
        except Exception as e:
            keepnote.log_error(e)
            #if recover:
            #    if infile:
            #        infile.close()
            #        infile = None
            #    self._recover_preferences()
            #    return self.read_preferences(recover=False)
            raise NoteBookError(_("Notebook preference data is corrupt"), e)
        finally:
            if infile:
                infile.close()

        # check version
        version = get_notebook_version_etree(tree)
        if version > NOTEBOOK_FORMAT_VERSION:
            raise NoteBookVersionError(version, NOTEBOOK_FORMAT_VERSION)

        if root.tag == "notebook":
            p = root.find("pref")
            if p is not None:
                d = p.find("dict")
                if d is not None:
                    data = plist.load_etree(d)
                else:
                    data = orderdict.OrderDict()
            else:
                data = orderdict.OrderDict()
        else:
            raise NoteBookError(_("Cannot read notebook preferences %s") %
                                self.get_file(PREF_FILE), e)

        data["version"] = version
        self.pref.set_data(data)

    def _recover_preferences(self):
        out = self.open_file(PREF_FILE, "w", "utf-8")
        out.write("<notebook></notebook>")
        out.close()
