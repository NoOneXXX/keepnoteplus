# Python 3 and PyGObject imports
import mimetypes
import os
import gi
gi.require_version('Gtk', '3.0')  # Specify GTK 3.0
from gi.repository import Gtk, GdkPixbuf

# KeepNote imports
import keepnote
from keepnote import unicode_gtk
import keepnote.gui
from keepnote import get_resource
import keepnote.notebook as notebooklib

# Globals/constants
NODE_ICON_DIR = os.path.join("images", "node_icons")

_g_default_node_icon_filenames = {
    notebooklib.CONTENT_TYPE_TRASH: ("trash.png", "trash.png"),
    notebooklib.CONTENT_TYPE_DIR: ("folder.png", "folder-open.png"),
    notebooklib.CONTENT_TYPE_PAGE: ("note.png", "note.png")
}
_g_unknown_icons = ("note-unknown.png", "note-unknown.png")

_colors = ["", "-red", "-orange", "-yellow",
           "-green", "-blue", "-violet", "-grey"]

builtin_icons = ["folder" + c + ".png" for c in _colors] + \
                ["folder" + c + "-open.png" for c in _colors] + \
                ["note" + c + ".png" for c in _colors] + \
                ["star.png",
                 "heart.png",
                 "check.png",
                 "x.png",
                 "important.png",
                 "question.png",
                 "web.png",
                 "note-unknown.png"]

DEFAULT_QUICK_PICK_ICONS = ["folder" + c + ".png" for c in _colors] + \
                           ["note" + c + ".png" for c in _colors] + \
                           ["star.png",
                            "heart.png",
                            "check.png",
                            "x.png",
                            "important.png",
                            "question.png",
                            "web.png",
                            "note-unknown.png"]

# Node icons
class MimeIcons:
    def __init__(self):
        self.theme = Gtk.IconTheme.get_default()
        if self.theme is None:
            icons = []
        else:
            icons = self.theme.list_icons()
        self._icons = set(icons)
        self._cache = {}

    def get_icon(self, filename, default=None):
        """Try to find icon for filename"""
        mime_type = mimetypes.guess_type(filename)[0]
        if mime_type:
            mime_type = mime_type.replace("/", "-")
        else:
            mime_type = "unknown"
        return self.get_icon_mimetype(mime_type, default)

    def get_icon_mimetype(self, mime_type, default=None):
        """Try to find icon for mime type"""
        if mime_type in self._cache:
            return self._cache[mime_type]

        items = mime_type.split('/')
        # Try gnome mime
        for i in range(len(items), 0, -1):
            icon_name = "gnome-mime-" + '-'.join(items[:i])
            if icon_name in self._icons:
                self._cache[mime_type] = icon_name
                return str(icon_name)

        # Try simple mime
        for i in range(len(items), 0, -1):
            icon_name = '-'.join(items[:i])
            if icon_name in self._icons:
                self._cache[mime_type] = icon_name
                return icon_name

        # Fallback to default
        self._cache[mime_type] = default
        return default

    def get_icon_filename(self, name, default=None):
        """Get the filename of an icon from the icon theme"""
        if name is None or self.theme is None:
            return default

        size = 16
        info = self.theme.lookup_icon(name, size, 0)
        if info:
            return info.get_filename()
        return default

# Singleton
_g_mime_icons = MimeIcons()

def get_icon_filename(icon_name, default=None):
    return _g_mime_icons.get_icon_filename(icon_name, default)

# Cache for icon filenames
_icon_basename_cache = {}

def lookup_icon_filename(notebook, basename):
    """
    Lookup full filename of an icon from a notebook and builtins
    Returns None if not found
    notebook can be None
    """
    if (notebook, basename) in _icon_basename_cache:
        return _icon_basename_cache[(notebook, basename)]

    # Lookup in notebook icon store
    if notebook is not None:
        filename = notebook.get_icon_file(basename)
        if filename:
            _icon_basename_cache[(notebook, basename)] = filename
            return filename

    # Lookup in builtins
    filename = get_resource(NODE_ICON_DIR, basename)
    if os.path.isfile(filename):
        _icon_basename_cache[(notebook, basename)] = filename
        return filename

    # Lookup mime types
    filename = _g_mime_icons.get_icon_filename(basename)
    _icon_basename_cache[(notebook, basename)] = filename
    return filename

# Icon management functions
def get_default_icon_basenames(node):
    """Returns basenames for default icons for a node"""
    content_type = node.get_attr("content_type")
    default = _g_mime_icons.get_icon_mimetype(content_type, "note-unknown.png")
    basenames = _g_default_node_icon_filenames.get(content_type, (default, default))
    return basenames

def get_default_icon_filenames(node):
    """Returns NoteBookNode icon filenames from resource path"""
    filenames = get_default_icon_basenames(node)
    return [lookup_icon_filename(node.get_notebook(), filenames[0]),
            lookup_icon_filename(node.get_notebook(), filenames[1])]

def get_all_icon_basenames(notebook):
    """Return a list of all builtin icons and notebook-specific icons"""
    return builtin_icons + notebook.get_icons()

def guess_open_icon_filename(icon_file):
    """Guess an 'open' version of an icon from its closed version"""
    path, ext = os.path.splitext(icon_file)
    return path + "-open" + ext

def get_node_icon_filenames_basenames(node):
    notebook = node.get_notebook()
    basenames = list(get_default_icon_basenames(node))
    filenames = get_default_icon_filenames(node)

    # Load icon
    if node.has_attr("icon"):
        basename = node.get_attr("icon")
        filename = lookup_icon_filename(notebook, basename)
        if filename:
            filenames[0] = filename
            basenames[0] = basename

    # Load icon with open state
    if node.has_attr("icon_open"):
        basename = node.get_attr("icon_open")
        filename = lookup_icon_filename(notebook, basename)
        if filename:
            filenames[1] = filename
            basenames[1] = basename
    else:
        if node.has_attr("icon"):
            basename = guess_open_icon_filename(node.get_attr("icon"))
            filename = lookup_icon_filename(notebook, basename)
            if filename:
                filenames[1] = filename
                basenames[1] = basename
            else:
                basename = node.get_attr("icon")
                filename = lookup_icon_filename(notebook, basename)
                if filename:
                    filenames[1] = filename
                    basenames[1] = basename

    return basenames, filenames

def get_node_icon_basenames(node):
    return get_node_icon_filenames_basenames(node)[0]

def get_node_icon_filenames(node):
    """Loads the icons for a node"""
    return get_node_icon_filenames_basenames(node)[1]

class NoteBookIconManager:
    def __init__(self):
        self.pixbufs = None
        self._node_icon_cache = {}

    def get_node_icon(self, node, effects=None):
        if effects is None:
            effects = set()
        if self.pixbufs is None:
            self.pixbufs = keepnote.gui.pixbufs

        expand = "expand" in effects
        fade = "fade" in effects
        icon_size = (15, 15)

        icon_cache, icon_open_cache = self._node_icon_cache.get(node, (None, None))

        if not expand and icon_cache:
            if not fade:
                return self.pixbufs.get_pixbuf(icon_cache, icon_size)
            else:
                return self.get_node_icon_fade(icon_cache, icon_size)

        elif expand and icon_open_cache:
            if not fade:
                return self.pixbufs.get_pixbuf(icon_open_cache, icon_size)
            else:
                return self.get_node_icon_fade(icon_open_cache, icon_size)

        else:
            filenames = get_node_icon_filenames(node)
            self._node_icon_cache[node] = filenames
            if not fade:
                return self.pixbufs.get_pixbuf(filenames[int(expand)], icon_size)
            else:
                return self.get_node_icon_fade(filenames[int(expand)], icon_size)

    def get_node_icon_fade(self, filename, icon_size, fade_alpha=128):
        key = (filename, icon_size, "fade")
        cached = self.pixbufs.is_pixbuf_cached(key)
        pixbuf = self.pixbufs.get_pixbuf(filename, icon_size, key)
        if cached:
            return pixbuf
        else:
            pixbuf = keepnote.gui.fade_pixbuf(pixbuf, fade_alpha)
            self.pixbufs.cache_pixbuf(pixbuf, key)
            return pixbuf

    def uncache_node_icon(self, node):
        if node in self._node_icon_cache:
            del self._node_icon_cache[node]

# Singleton
notebook_icon_manager = NoteBookIconManager()

def get_node_icon(node, expand=False, fade=False):
    """Returns pixbuf of NoteBookNode icon from resource path"""
    effects = set()
    if expand:
        effects.add("expand")
    if fade:
        effects.add("fade")
    return notebook_icon_manager.get_node_icon(node, effects)

def uncache_node_icon(node):
    notebook_icon_manager.uncache_node_icon(node)