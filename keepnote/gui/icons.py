# icons.py (GTK4-Compatible Full Rewrite)

# Python 3 and PyGObject imports
import mimetypes
import os
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk

# KeepNote imports
import keepnote
from keepnote import unicode_gtk
import keepnote.gui
from keepnote import get_resource
import keepnote.notebook as notebooklib

# Constants and globals
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
                ["star.png", "heart.png", "check.png", "x.png",
                 "important.png", "question.png", "web.png", "note-unknown.png"]

DEFAULT_QUICK_PICK_ICONS = ["folder" + c + ".png" for c in _colors] + \
                           ["note" + c + ".png" for c in _colors] + \
                           ["star.png", "heart.png", "check.png", "x.png",
                            "important.png", "question.png", "web.png", "note-unknown.png"]

# GTK4 Compatible MimeIcons class
class MimeIcons:
    def __init__(self):
        display = Gdk.Display.get_default()  # GTK4 change
        self.theme = Gtk.IconTheme.get_for_display(display)
        self._icons = set(self.theme.get_icon_names()) if self.theme else set()
        self._cache = {}

    def get_icon(self, filename, default=None):
        mime_type = mimetypes.guess_type(filename)[0]
        if mime_type:
            mime_type = mime_type.replace("/", "-")
        else:
            mime_type = "unknown"
        return self.get_icon_mimetype(mime_type, default)

    def get_icon_mimetype(self, mime_type, default=None):
        if mime_type in self._cache:
            return self._cache[mime_type]

        parts = mime_type.split('/')
        for i in range(len(parts), 0, -1):
            icon_name = "gnome-mime-" + '-'.join(parts[:i])
            if icon_name in self._icons:
                self._cache[mime_type] = icon_name
                return icon_name

        for i in range(len(parts), 0, -1):
            icon_name = '-'.join(parts[:i])
            if icon_name in self._icons:
                self._cache[mime_type] = icon_name
                return icon_name

        self._cache[mime_type] = default
        return default

    def get_icon_filename(self, name, default=None):
        if name is None or self.theme is None:
            return default
        size = 16
        info = self.theme.lookup_icon(name, [], size, 0)
        return info.get_filename() if info else default

_g_mime_icons = MimeIcons()

def get_icon_filename(icon_name, default=None):
    return _g_mime_icons.get_icon_filename(icon_name, default)

_icon_basename_cache = {}

def lookup_icon_filename(notebook, basename):
    if (notebook, basename) in _icon_basename_cache:
        return _icon_basename_cache[(notebook, basename)]

    if notebook:
        filename = notebook.get_icon_file(basename)
        if filename:
            _icon_basename_cache[(notebook, basename)] = filename
            return filename

    filename = get_resource(NODE_ICON_DIR, basename)
    if os.path.isfile(filename):
        _icon_basename_cache[(notebook, basename)] = filename
        return filename

    filename = _g_mime_icons.get_icon_filename(basename)
    _icon_basename_cache[(notebook, basename)] = filename
    return filename

def get_default_icon_basenames(node):
    content_type = node.get_attr("content_type")
    default = _g_mime_icons.get_icon_mimetype(content_type, "note-unknown.png")
    return _g_default_node_icon_filenames.get(content_type, (default, default))

def get_default_icon_filenames(node):
    basenames = get_default_icon_basenames(node)
    return [lookup_icon_filename(node.get_notebook(), basenames[0]),
            lookup_icon_filename(node.get_notebook(), basenames[1])]

def get_all_icon_basenames(notebook):
    return builtin_icons + notebook.get_icons()

def guess_open_icon_filename(icon_file):
    path, ext = os.path.splitext(icon_file)
    return path + "-open" + ext

def get_node_icon_filenames_basenames(node):
    notebook = node.get_notebook()
    basenames = list(get_default_icon_basenames(node))
    filenames = get_default_icon_filenames(node)

    if node.has_attr("icon"):
        basename = node.get_attr("icon")
        filename = lookup_icon_filename(notebook, basename)
        if filename:
            filenames[0] = filename
            basenames[0] = basename

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
            return self._resolve_icon(icon_cache, icon_size, fade)
        elif expand and icon_open_cache:
            return self._resolve_icon(icon_open_cache, icon_size, fade)
        else:
            filenames = get_node_icon_filenames(node)
            self._node_icon_cache[node] = filenames
            return self._resolve_icon(filenames[int(expand)], icon_size, fade)

    def _resolve_icon(self, filename, size, fade):
        if not fade:
            return self.pixbufs.get_pixbuf(filename, size)
        return self.get_node_icon_fade(filename, size)

    def get_node_icon_fade(self, filename, size, fade_alpha=128):
        key = (filename, size, "fade")
        cached = self.pixbufs.is_pixbuf_cached(key)
        pixbuf = self.pixbufs.get_pixbuf(filename, size, key)
        if cached:
            return pixbuf
        pixbuf = keepnote.gui.fade_pixbuf(pixbuf, fade_alpha)
        self.pixbufs.cache_pixbuf(pixbuf, key)
        return pixbuf

    def uncache_node_icon(self, node):
        self._node_icon_cache.pop(node, None)

notebook_icon_manager = NoteBookIconManager()

def get_node_icon(node, expand=False, fade=False):
    effects = {e for e, b in [("expand", expand), ("fade", fade)] if b}
    return notebook_icon_manager.get_node_icon(node, effects)

def uncache_node_icon(node):
    notebook_icon_manager.uncache_node_icon(node)
