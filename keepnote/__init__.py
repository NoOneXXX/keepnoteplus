# Python imports
import json
import os
import shutil
import sys
import time
import re
import subprocess
import tempfile
import traceback
import uuid
import zipfile

from gi.overrides.Pango import Pango

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

# KeepNote imports
from keepnote import extension
from keepnote import mswin
from keepnote import orderdict
from keepnote import plist
from keepnote import safefile
from keepnote.listening import Listeners
from keepnote.notebook import NoteBookError, get_unique_filename_list
import keepnote.notebook as notebooklib
import keepnote.notebook.connection
import keepnote.notebook.connection.fs
import keepnote.notebook.connection.http
from keepnote.pref import Pref
import keepnote.timestamp
import keepnote.trans
from keepnote.trans import GETTEXT_DOMAIN
import keepnote.xdg
from gi.repository import Gtk
import base64
import html.entities
from keepnote import tarfile
import random
import sgmllib
import string

import xml.sax.saxutils
# from keepnote.py.gui.richtext.richtextbase_tags import RichTextTagTable
# Make pyflakes ignore these used modules
GETTEXT_DOMAIN
base64
get_unique_filename_list
htmlentitydefs = html.entities
random
sgmllib
string
tarfile
xml

# make sure py2exe finds win32com
try:
    import sys
    import modulefinder
    import win32com

    for p in win32com.__path__[1:]:
        modulefinder.AddPackagePath("win32com", p)
    for extra in ["win32com.shell"]:
        __import__(extra)
        m = sys.modules[extra]
        for p in m.__path__[1:]:
            modulefinder.AddPackagePath(extra, p)
except ImportError:
    # no build path setup, no worries.
    pass

# 移除对 screenshot 的引用
# try:
#     from . import screenshot  # type: ignore
# except ImportError:
#     pass

# Globals / Constants
PROGRAM_NAME = "KeepNote"
PROGRAM_VERSION_MAJOR = 0
PROGRAM_VERSION_MINOR = 7
PROGRAM_VERSION_RELEASE = 9
PROGRAM_VERSION = (PROGRAM_VERSION_MAJOR, PROGRAM_VERSION_MINOR, PROGRAM_VERSION_RELEASE)
PROGRAM_VERSION_TEXT = (
    f"{PROGRAM_VERSION_MAJOR}.{PROGRAM_VERSION_MINOR}.{PROGRAM_VERSION_RELEASE}"
    if PROGRAM_VERSION_RELEASE != 0
    else f"{PROGRAM_VERSION_MAJOR}.{PROGRAM_VERSION_MINOR}"
)

WEBSITE = "http://keepnote.org"
LICENSE_NAME = "GPL version 2"
COPYRIGHT = "Copyright Matt Rasmussen 2011."
TRANSLATOR_CREDITS = (
    "Chinese: hu dachuan <hdccn@sina.com>\n"
    "French: tb <thibaut.bethune@gmail.com>\n"
    "French: Sebastien KALT <skalt@throka.org>\n"
    "German: Jan Rimmek <jan.rimmek@mhinac.de>\n"
    "Japanese: Toshiharu Kudoh <toshi.kd2@gmail.com>\n"
    "Italian: Davide Melan <davide.melan@gmail.com>\n"
    "Polish: Bernard Baraniewski <raznaya2010(at)rambler(dot)ru>\n"
    "Russian: Hikiko Mori <hikikomori.dndz@gmail.com>\n"
    "Spanish: Klemens Hackel <click3d at linuxmail (dot) org>\n"
    "Slovak: Slavko <linux@slavino.sk>\n"
    "Swedish: Morgan Antonsson <morgan.antonsson@gmail.com>\n"
    "Turkish: Yuce Tekol <yucetekol@gmail.com>\n"
)

BASEDIR = os.path.dirname(os.path.abspath(__file__))
PLATFORM = None

USER_PREF_DIR = "keepnote"
USER_PREF_FILE = "keepnote.py.xml"
USER_LOCK_FILE = "lockfile"
USER_ERROR_LOG = "error-log.txt"
USER_EXTENSIONS_DIR = "extensions"
USER_EXTENSIONS_DATA_DIR = "extensions_data"
PORTABLE_FILE = "portable.txt"

# Default encoding setup
DEFAULT_ENCODING = sys.getdefaultencoding()
FS_ENCODING = sys.getfilesystemencoding()


# Application resources
def get_basedir():
    return os.path.dirname(os.path.abspath(__file__))


def set_basedir(basedir):
    global BASEDIR
    BASEDIR = basedir if basedir else get_basedir()
    keepnote.trans.set_local_dir(get_locale_dir())


# def get_resource(*path_list):
#     return os.path.join(BASEDIR, *path_list)


# Common functions
def get_platform():
    global PLATFORM
    if PLATFORM is None:
        p = sys.platform
        PLATFORM = 'darwin' if p == 'darwin' else 'windows' if p.startswith('win') else 'unix'
    return PLATFORM


def is_url(text):
    return re.match(r"^[^:]+://", text) is not None


def ensure_unicode(text, encoding="utf-8"):
    if text is None:
        return None
    return text if isinstance(text, str) else str(text, encoding)





def print_error_log_header(out=None):
    out = out or sys.stderr
    out.write(
        "==============================================\n"
        f"{PROGRAM_NAME} {PROGRAM_VERSION_TEXT}: {time.asctime()}\n"
    )


def print_runtime_info(out=None):
    out = out or sys.stderr
    from keepnote.notebook.connection.fs.index import sqlite

    out.write(
        "Python runtime\n"
        "--------------\n"
        f"sys.version={sys.version}\n"
        f"sys.getdefaultencoding()={DEFAULT_ENCODING}\n"
        f"sys.getfilesystemencoding()={FS_ENCODING}\n"
        "PYTHONPATH=\n  " + "\n  ".join(sys.path) + "\n\n"
                                                    "Imported libs\n"
                                                    "-------------\n"
                                                    f"keepnote.py: {keepnote.__file__}\n"
    )
    try:
        from gi.repository import Gtk
        out.write(f"gtk: {Gtk.__file__}\n")
        out.write(f"gtk.gtk_version: {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}\n")
    except ImportError:
        out.write("gtk: NOT PRESENT\n")

    out.write(
        f"sqlite: {sqlite.__file__}\n"
        f"sqlite.version: {sqlite.version}\n"
        f"sqlite.sqlite_version: {sqlite.sqlite_version}\n"
        f"sqlite.fts3: {test_fts3()}\n"
    )
    try:
        import gtkspellcheck
        out.write(f"gtkspell: {gtkspellcheck.__file__}\n")
    except ImportError:
        out.write("gtkspell: NOT PRESENT\n")
    out.write("\n")


def test_fts3():
    from keepnote.notebook.connection.fs.index import sqlite
    con = sqlite.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE fts3test USING fts3(col TEXT);")
        return True
    except:
        return False
    finally:
        con.close()


# Locale functions
def translate(message):
    return keepnote.trans.translate(message)


def get_locale_dir():
    return get_resource("rc", "locale")

def get_resource(*path_list):
    return os.path.join(BASEDIR, *path_list)

_ = translate


# Preference filenaming scheme
def get_home():
    home = ensure_unicode(os.getenv("HOME"), FS_ENCODING)
    if home is None:
        raise EnvError("HOME environment variable must be specified")
    return home





def get_user_pref_dir(home=None):
    p = get_platform()
    if p in ("unix", "darwin"):
        if home is None:
            home = get_home()
        return keepnote.xdg.get_config_file(USER_PREF_DIR, default=True)

    elif p == "windows":
        if os.path.exists(os.path.join(BASEDIR, PORTABLE_FILE)):
            path = os.path.join(BASEDIR, USER_PREF_DIR)
        else:
            appdata = get_win_env("APPDATA")
            if appdata is None:
                raise EnvError("APPDATA environment variable must be specified")
            path = os.path.join(appdata, USER_PREF_DIR)

        # ✅ 如果目录不存在，自动创建（避免 NoteBookError）
        os.makedirs(path, exist_ok=True)
        return path

    raise Exception(f"unknown platform '{p}'")


def get_user_extensions_dir(pref_dir=None, home=None):
    if pref_dir is None:
        pref_dir = get_user_pref_dir(home)
    return os.path.join(pref_dir, USER_EXTENSIONS_DIR)


def get_user_extensions_data_dir(pref_dir=None, home=None):
    if pref_dir is None:
        pref_dir = get_user_pref_dir(home)
    return os.path.join(pref_dir, USER_EXTENSIONS_DATA_DIR)


def get_system_extensions_dir():
    return os.path.join(BASEDIR, "extensions")


def get_user_documents():
    """Returns the path to the user's documents folder"""
    if get_platform() == "windows":
        return mswin.get_my_documents()
    else:
        return os.path.expanduser("~/Documents")


def get_user_pref_file(pref_dir=None, home=None):
    if pref_dir is None:
        pref_dir = get_user_pref_dir(home)
    return os.path.join(pref_dir, USER_PREF_FILE)


def get_user_lock_file(pref_dir=None, home=None):
    if pref_dir is None:
        pref_dir = get_user_pref_dir(home)
    return os.path.join(pref_dir, USER_LOCK_FILE)


def get_user_error_log(pref_dir=None, home=None):
    if pref_dir is None:
        pref_dir = get_user_pref_dir(home)
    return os.path.join(pref_dir, USER_ERROR_LOG)


def get_win_env(key):
    try:
        return ensure_unicode(os.getenv(key), DEFAULT_ENCODING)
    except UnicodeDecodeError:
        return ensure_unicode(os.getenv(key), FS_ENCODING)


# Preference/extension initialization
def init_user_pref_dir(pref_dir=None, home=None):
    if pref_dir is None:
        pref_dir = get_user_pref_dir(home)
    print(f"Initializing pref_dir: {pref_dir}")
    if not os.path.exists(pref_dir):
        os.makedirs(pref_dir, mode=0o700)
        print(f"Created directory: {pref_dir}")
    pref_file = get_user_pref_file(pref_dir)
    # Write default content if file doesn't exist OR is empty
    if not os.path.exists(pref_file) or os.path.getsize(pref_file) == 0:
        try:
            with open(pref_file, "w", encoding="utf-8") as out:
                out.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<keepnote.py>\n</keepnote.py>\n")
            print(f"Created or updated pref_file: {pref_file}, size: {os.path.getsize(pref_file)} bytes")
            if os.path.getsize(pref_file) == 0:
                raise IOError("Failed to write content to preferences file")
        except Exception as e:
            print(f"Failed to create/update pref_file: {e}")
            raise
    init_error_log(pref_dir)
    extension.init_user_extensions(pref_dir)


def init_error_log(pref_dir=None, home=None):
    if pref_dir is None:
        pref_dir = get_user_pref_dir(home)
    error_log = get_user_error_log(pref_dir)
    if not os.path.exists(error_log):
        error_dir = os.path.dirname(error_log)
        if not os.path.exists(error_dir):
            os.makedirs(error_dir)
        open(error_log, "a").close()


def log_error(error=None, tracebk=None, out=None):
    out = out or sys.stderr
    if error is None:
        ty, error, tracebk = sys.exc_info()
    try:
        out.write("\n")
        if tracebk:
            traceback.print_exception(type(error), error, tracebk, file=out)
        else:
            out.write(str(error))  # Handle string error
        out.flush()
    except UnicodeEncodeError:
        out.write(str(error).encode("ascii", "replace"))



def log_message(message, out=None):
    out = out or sys.stderr
    try:
        out.write(message)
    except UnicodeEncodeError:
        out.write(message.encode("ascii", "replace"))
    out.flush()


# Exceptions
class EnvError(Exception):
    def __init__(self, msg, error=None):
        super().__init__(msg)
        self.msg = msg
        self.error = error

    def __str__(self):
        return f"{self.error}\n{self.msg}" if self.error else self.msg


class KeepNoteError(Exception):
    def __init__(self, msg, error=None):
        super().__init__(msg)
        self.msg = msg
        self.error = error

    def __repr__(self):
        return f"{self.error}\n{self.msg}" if self.error else self.msg

    def __str__(self):
        return self.msg


class KeepNotePreferenceError(Exception):
    def __init__(self, msg, error=None):
        super().__init__(msg)
        self.msg = msg
        self.error = error

    def __str__(self):
        return f"{self.error}\n{self.msg}" if self.error else self.msg


# Preference data structures
class ExternalApp:
    def __init__(self, key, title, prog, args=None):
        self.key = key
        self.title = title
        self.prog = prog
        self.args = args or []


DEFAULT_EXTERNAL_APPS = [
    ExternalApp("file_launcher", "File Launcher", ""),
    ExternalApp("web_browser", "Web Browser", ""),
    ExternalApp("file_explorer", "File Explorer", ""),
    ExternalApp("text_editor", "Text Editor", ""),
    ExternalApp("image_editor", "Image Editor", ""),
    ExternalApp("image_viewer", "Image Viewer", ""),
    ExternalApp("screen_shot", "Screen Shot", ""),
]


def get_external_app_defaults():
    if get_platform() == "windows":
        files = ensure_unicode(os.environ.get("PROGRAMFILES", "C:\\Program Files"), FS_ENCODING)
        return [
            ExternalApp("file_launcher", "File Launcher", "explorer.exe"),
            ExternalApp("web_browser", "Web Browser", f"{files}\\Internet Explorer\\iexplore.exe"),
            ExternalApp("file_explorer", "File Explorer", "explorer.exe"),
            ExternalApp("text_editor", "Text Editor", f"{files}\\Windows NT\\Accessories\\wordpad.exe"),
            ExternalApp("image_editor", "Image Editor", "mspaint.exe"),
            ExternalApp("image_viewer", "Image Viewer", f"{files}\\Internet Explorer\\iexplore.exe"),
            ExternalApp("screen_shot", "Screen Shot", ""),
        ]
    elif get_platform() == "unix":
        return [
            ExternalApp("file_launcher", "File Launcher", "xdg-open"),
            ExternalApp("web_browser", "Web Browser", ""),
            ExternalApp("file_explorer", "File Explorer", ""),
            ExternalApp("text_editor", "Text Editor", ""),
            ExternalApp("image_editor", "Image Editor", ""),
            ExternalApp("image_viewer", "Image Viewer", "display"),
            ExternalApp("screen_shot", "Screen Shot", "import"),
        ]
    return DEFAULT_EXTERNAL_APPS


class KeepNotePreferences(Pref):
    def __init__(self, pref_dir=None, home=None):
        super().__init__()
        self._pref_dir = pref_dir or get_user_pref_dir(home)
        self._tree = ET.ElementTree(ET.Element("keepnote.py"))  # Always start with valid tree
        self.changed = Listeners()

    def get_pref_dir(self):
        return self._pref_dir

    def read(self):
        pref_file = get_user_pref_file(self._pref_dir)
        print(f"Reading from: {pref_file}")
        if not os.path.exists(pref_file) or os.path.getsize(pref_file) == 0:
            print(
                f"File missing or empty (exists: {os.path.exists(pref_file)}, size: {os.path.getsize(pref_file)} bytes)")
            try:
                init_user_pref_dir(self._pref_dir)
                print(
                    f"After init_user_pref_dir, file exists: {os.path.exists(pref_file)}, size: {os.path.getsize(pref_file)} bytes")
                with open(pref_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    print(f"File content after init: {repr(content)}")
            except Exception as e:
                raise KeepNotePreferenceError("Cannot initialize preferences", e)
        else:
            print(f"File exists, size: {os.path.getsize(pref_file)} bytes")
            with open(pref_file, "r", encoding="utf-8") as f:
                content = f.read()
                print(f"File content before parsing: {repr(content)}")
        try:
            tree = ET.ElementTree(file=pref_file)
            root = tree.getroot()
            print(f"Parsed root tag: {root.tag}")
            if root.tag != "keepnote.py":
                raise KeepNotePreferenceError("Invalid root tag in preferences file", None)
            p = root.find("pref")
            if p is None:
                import keepnote.compat.pref as old
                old_pref = old.KeepNotePreferences()
                old_pref.read(pref_file)
                data = old_pref._get_data()
            else:
                d = p.find("dict")
                data = plist.load_etree(d) if d is not None else orderdict.OrderDict()
            self._data.clear()
            self._data.update(data)
        except Exception as e:
            raise KeepNotePreferenceError("Cannot read preferences", e)
        self.changed.notify()

    def write(self):
        pref_file = get_user_pref_file(self._pref_dir)
        if self._tree is None or self._tree.getroot() is None:
            self._tree = ET.ElementTree(ET.Element("keepnote.py"))
        # Add current preferences to the tree before writing
        root = self._tree.getroot()
        pref_elem = ET.SubElement(root, "pref")
        dict_elem = ET.SubElement(pref_elem, "dict")
        plist.dump_etree(self._data, dict_elem)
        with open(pref_file, "w", encoding="utf-8") as out:
            self._tree.write(out, encoding="unicode", xml_declaration=True)


# Application class
class ExtensionEntry:
    def __init__(self, filename, ext_type, ext):
        self.filename = filename
        self.ext_type = ext_type
        self.ext = ext

    def get_key(self):
        return os.path.basename(self.filename)


class AppCommand:
    def __init__(self, name, func=lambda app, args: None, metavar="", help=""):
        self.name = name
        self.func = func
        self.metavar = metavar
        self.help = help


class KeepNote:
    def __init__(self, basedir=None, pref_dir=None):
        if basedir is not None:
            set_basedir(basedir)
        self._basedir = BASEDIR
        self.pref = KeepNotePreferences(pref_dir)
        self.pref.changed.add(self._on_pref_changed)
        self.id = None
        self._commands = {}
        self._notebooks = {}
        self._notebook_count = {}
        self._conns = keepnote.notebook.connection.NoteBookConnections()
        self._conns.add("file", keepnote.notebook.connection.fs.NoteBookConnectionFS)
        self._conns.add("http", keepnote.notebook.connection.http.NoteBookConnectionHttp)
        self._external_apps = []
        self._external_apps_lookup = {}
        self._extension_paths = []
        self._extensions = {}
        self._disabled_extensions = []
        self._listeners = {}
        # Initialization code for KeepNote
        self.pref_dir = pref_dir
        self._richtext_tag_table = self.create_richtext_tag_table()  # Initialize the tag table

    def get_richtext_tag_table(self):
        # Ensure that this method returns the richtext tag table.
        if not hasattr(self, "_richtext_tag_table"):
            self._richtext_tag_table = self.create_richtext_tag_table()  # Create if it doesn't exist
        return self._richtext_tag_table

    def create_richtext_tag_table(self):
        # Create a new GtkTextTagTable and populate it with tags
        tag_table = Gtk.TextTagTable()

        # Example: Add tags to the table (this depends on the actual dictionary structure)
        tag = Gtk.TextTag.new("example-tag")
        tag_table.add(tag)

        # You should create and add tags based on the dictionary
        # For example, assuming the dictionary is {'tag_name': tag_properties}
        tag_properties = {'tag_name': 'bold', 'weight': Pango.Weight.BOLD}
        tag = Gtk.TextTag.new(tag_properties['tag_name'])
        tag.set_property("weight", tag_properties['weight'])
        tag_table.add(tag)

        return tag_table

    def init(self):
        import threading
        if threading.current_thread() is not threading.main_thread():
            print("Error: GTK must run in the main thread")
            sys.exit(1)
        # super().init()

    def load_preferences(self):
        self.language = self.pref.get("language", default="")
        self.set_lang()
        self.id = self.pref.get("id", default="")
        if not self.id:
            self.id = str(uuid.uuid4())
            self.pref.set("id", self.id)
        self.pref.get("timestamp_formats", default=dict(keepnote.timestamp.DEFAULT_TIMESTAMP_FORMATS))
        self._load_external_app_preferences()
        self._disabled_extensions = self.pref.get("extension_info", "disabled", default=[])
        self.pref.get("extensions", define=True)

    def save_preferences(self):
        self.pref.set("language", self.language)
        self.pref.set("external_apps", [
            {"key": app.key, "title": app.title, "prog": app.prog, "args": app.args}
            for app in self._external_apps
        ])
        self.pref.set("extension_info", {"disabled": self._disabled_extensions[:]})
        self.pref.write()

    def _on_pref_changed(self):
        self.load_preferences()

    def set_lang(self):
        keepnote.trans.set_lang(self.language)

    def error(self, text, error=None, tracebk=None):
        keepnote.log_message(text)
        if error is not None:
            keepnote.log_error(error, tracebk)

    def quit(self):
        if self.pref.get("use_last_notebook", default=False):
            self.pref.set("default_notebooks", [n.get_path() for n in self.iter_notebooks()])
        self.save_preferences()

    def get_default_path(self, name):
        return self.pref.get("default_paths", name, default=get_user_documents())

    def set_default_path(self, name, path):
        self.pref.set("default_paths", name, path)

    def get_pref_dir(self):
        return self.pref.get_pref_dir()

    # Notebooks
    def open_notebook(self, filename, window=None, task=None):
        try:
            conn = self._conns.get(filename)
            notebook = notebooklib.NoteBook()
            notebook.load(filename, conn)
            return notebook
        except Exception:
            return None

    def close_notebook(self, notebook):
        if self.has_ref_notebook(notebook):
            self.unref_notebook(notebook)

    def close_all_notebook(self, notebook, save=True):
        try:
            notebook.close(save)
        except:
            keepnote.log_error()
        notebook.closing_event.remove(self._on_closing_notebook)
        del self._notebook_count[notebook]
        for key, val in list(self._notebooks.items()):
            if val == notebook:
                del self._notebooks[key]
                break

    def _on_closing_notebook(self, notebook, save):
        pass

    def get_notebook(self, filename, window=None, task=None):
        try:
            filename = notebooklib.normalize_notebook_dirname(filename, longpath=False)
            filename = os.path.realpath(filename)
        except:
            pass
        if filename not in self._notebooks:
            notebook = self.open_notebook(filename, window, task=task)
            if notebook is None:
                return None
            self._notebooks[filename] = notebook
            notebook.closing_event.add(self._on_closing_notebook)
            self.ref_notebook(notebook)
        else:
            notebook = self._notebooks[filename]
            self.ref_notebook(notebook)
        return notebook

    def ref_notebook(self, notebook):
        self._notebook_count[notebook] = self._notebook_count.get(notebook, 0) + 1

    def unref_notebook(self, notebook):
        self._notebook_count[notebook] -= 1
        if self._notebook_count[notebook] == 0:
            self.close_all_notebook(notebook)

    def has_ref_notebook(self, notebook):
        return notebook in self._notebook_count

    def iter_notebooks(self):
        return iter(self._notebooks.values())

    def save_notebooks(self, silent=False):
        for notebook in self._notebooks.values():
            notebook.save()



    def get_node(self, nodeid):
        for notebook in self._notebooks.values():
            node = notebook.get_node_by_id(nodeid)
            if node is not None:
                return node
        return None

    def save(self, silent=False):
        self.save_notebooks()
        self.save_preferences()

    # Listeners
    def get_listeners(self, key):
        if key not in self._listeners:
            self._listeners[key] = Listeners()
        return self._listeners[key]

    # External apps
    def _load_external_app_preferences(self):
        self._external_apps = []
        for app in self.pref.get("external_apps", default=[]):
            if "key" not in app:
                continue
            app2 = ExternalApp(app["key"], app.get("title", ""), app.get("prog", ""), app.get("args", ""))
            self._external_apps.append(app2)
        self._external_apps_lookup = {app.key: app for app in self._external_apps}
        for defapp in get_external_app_defaults():
            if defapp.key not in self._external_apps_lookup:
                self._external_apps.append(defapp)
                self._external_apps_lookup[defapp.key] = defapp
        lookup = {x.key: i for i, x in enumerate(DEFAULT_EXTERNAL_APPS)}
        top = len(DEFAULT_EXTERNAL_APPS)
        self._external_apps.sort(key=lambda x: (lookup.get(x.key, top), x.key))

    def get_external_app(self, key):
        app = self._external_apps_lookup.get(key)
        return None if app == "" else app

    def iter_external_apps(self):
        return iter(self._external_apps)

    def run_external_app(self, app_key, filename, wait=False):
        app = self.get_external_app(app_key)
        if not app or not app.prog:
            title = app.title if app else app_key
            raise KeepNoteError(f"Must specify '{title}' program in Helper Applications")
        cmd = [app.prog] + app.args
        if "%f" not in cmd:
            cmd.append(filename)
        else:
            cmd = [filename if x == "%f" else x for x in cmd]
        cmd = [str(x) for x in cmd]
        if get_platform() == "windows":
            cmd = [x.encode('mbcs') for x in cmd]
        else:
            cmd = [x.encode(FS_ENCODING) for x in cmd]
        try:
            proc = subprocess.Popen(cmd)
            return proc.wait() if wait else None
        except OSError as e:
            raise KeepNoteError(
                f"Error occurred while opening file with {app.title}.\n\n"
                f"program: '{app.prog}'\n\nfile: '{filename}'\n\nerror: {e}", e
            )

    def run_external_app_node(self, app_key, node, kind, wait=False):
        if kind == "dir":
            filename = node.get_path()
        else:
            content_type = node.get_attr("content_type")
            if content_type == notebooklib.CONTENT_TYPE_PAGE:
                filename = node.get_data_file()
            elif content_type == notebooklib.CONTENT_TYPE_DIR:
                filename = node.get_path()
            elif node.has_attr("payload_filename"):
                filename = node.get_file(node.get_attr("payload_filename"))
            else:
                raise KeepNoteError("Unable to determine note type.")
        self.run_external_app(app_key, filename, wait=wait)

    def open_webpage(self, url):
        if url:
            self.run_external_app("web_browser", url)

    def take_screenshot(self, filename):
        filename = ensure_unicode(filename, "utf-8")
        if get_platform() == "windows":
            # 禁用 Windows 上的截图功能
            raise NotImplementedError("Screenshot functionality is not supported on Windows without pywin32.")
        else:
            screenshot = self.get_external_app("screen_shot")
            if not screenshot or not screenshot.prog:
                raise Exception("You must specify a Screen Shot program in Application Options")
            f, imgfile = tempfile.mkstemp(".png", prefix=os.path.basename(filename))
            os.close(f)
            proc = subprocess.Popen([screenshot.prog, imgfile])
            if proc.wait() != 0:
                raise OSError("Exited with error")
        if not os.path.exists(imgfile):
            raise Exception(f"The screenshot program did not create the necessary image file '{imgfile}'")
        return imgfile

    # Commands
    def get_command(self, command_name):
        return self._commands.get(command_name)

    def get_commands(self):
        return list(self._commands.values())

    def add_command(self, command):
        if command.name in self._commands:
            raise Exception(f"command '{command.name}' already exists")
        self._commands[command.name] = command

    def remove_command(self, command_name):
        self._commands.pop(command_name, None)

    # Extensions
    def init_extensions(self):
        self._clear_extensions()
        self._scan_extension_paths()
        self._import_all_extensions()
        for ext in self.get_imported_extensions():
            try:
                if ext.key not in self._disabled_extensions:
                    log_message(f"enabling extension '{ext.key}'\n")
                    ext.enable(True)
            except extension.DependencyError as e:
                log_message(f"  skipping extension '{ext.key}':\n")
                for dep in ext.get_depends():
                    if not self.dependency_satisfied(dep):
                        log_message(f"    failed dependency: {dep}\n")
            except Exception as e:
                log_error(e, sys.exc_info()[2])

    def _clear_extensions(self):
        for ext in list(self.get_enabled_extensions()):
            ext.disable()
        self._extensions = {"keepnote.py": ExtensionEntry("", "system", KeepNoteExtension(self))}

    def _scan_extension_paths(self):
        for path, ext_type in self._extension_paths:
            self._scan_extension_path(path, ext_type)

    def _scan_extension_path(self, extensions_path, ext_type):
        for filename in extension.scan_extensions_dir(extensions_path):
            self.add_extension(filename, ext_type)

    def add_extension(self, filename, ext_type):
        entry = ExtensionEntry(filename, ext_type, None)
        self._extensions[entry.get_key()] = entry
        return entry

    def remove_extension(self, ext_key):
        entry = self._extensions.get(ext_key)
        if entry:
            if entry.ext:
                entry.ext.enable(False)
            del self._extensions[ext_key]

    def get_extension(self, name):
        if name not in self._extensions:
            return None
        entry = self._extensions[name]
        if entry.ext is None:
            self._import_extension(entry)
        return entry.ext

    def get_installed_extensions(self):
        return iter(self._extensions.keys())

    def get_imported_extensions(self):
        return (entry.ext for entry in self._extensions.values() if entry.ext is not None)

    def get_enabled_extensions(self):
        return (ext for ext in self.get_imported_extensions() if ext.is_enabled())

    def _import_extension(self, entry):
        try:
            entry.ext = extension.import_extension(self, entry.get_key(), entry.filename)
            # Check if the extension was successfully loaded
            if entry.ext is None:
                log_message(f"Extension '{entry.get_key()}' was not loaded (skipped or failed)\n")
                return None  # Skip further processing for this extension
            entry.ext.type = entry.ext_type
            entry.ext.enabled.add(lambda e: self.on_extension_enabled(entry.ext, e))
            return entry.ext
        except KeepNotePreferenceError as e:
            log_error(e, sys.exc_info()[2])
            return None

    def _import_all_extensions(self):
        for entry in list(self._extensions.values()):
            if entry.ext is None:
                log_message(f"Importing extension: {entry.get_key()} (filename: {entry.filename})\n")
                self._import_extension(entry)

    def dependency_satisfied(self, dep):
        ext = self.get_extension(dep[0])
        return extension.dependency_satisfied(ext, dep)

    def dependencies_satisfied(self, depends):
        return all(self.dependency_satisfied(dep) for dep in depends)

    def on_extension_enabled(self, ext, enabled):
        if enabled and ext.key in self._disabled_extensions:
            self._disabled_extensions.remove(ext.key)
        elif not enabled and ext.key not in self._disabled_extensions:
            self._disabled_extensions.append(ext.key)

    def install_extension(self, filename):
        log_message(f"Installing extension '{filename}'\n")
        userdir = get_user_extensions_dir(self.get_pref_dir())
        newfiles = []
        try:
            for fn in unzip(filename, userdir):
                newfiles.append(fn)
            exts = set(self._extensions.keys())
            self._scan_extension_path(userdir, "user")
            new_names = set(self._extensions.keys()) - exts
            new_exts = [self.get_extension(name) for name in new_names]
        except Exception as e:
            self.error(f"Unable to install extension '{filename}'", e, sys.exc_info()[2])
            for newfile in newfiles:
                try:
                    log_message(f"Removing file '{newfile}'\n")
                    os.remove(newfile)
                except:
                    pass
            return []
        log_message("Enabling new extensions:\n")
        for ext in new_exts:
            log_message(f"enabling extension '{ext.key}'\n")
            ext.enable(True)
        return new_exts

    def uninstall_extension(self, ext_key):
        entry = self._extensions.get(ext_key)
        if not entry:
            self.error(f"Unable to uninstall unknown extension '{ext_key}'.")
            return False
        if entry.ext_type != "user":
            self.error("KeepNote can only uninstall user extensions")
            return False
        self.remove_extension(ext_key)
        try:
            shutil.rmtree(entry.filename)
        except OSError:
            self.error("Unable to uninstall extension. Do not have permission.")
            return False
        return True

    def can_uninstall(self, ext):
        return ext.type != "system"

    def get_extension_base_dir(self, extkey):
        return self._extensions[extkey].filename

    def get_extension_data_dir(self, extkey):
        return os.path.join(get_user_extensions_data_dir(self.get_pref_dir()), extkey)


def unzip(filename, outdir):
    with zipfile.ZipFile(filename) as extzip:
        for fn in extzip.namelist():
            if fn.endswith(("/", "\\")):
                continue
            if fn.startswith("../") or "/../" in fn:
                raise Exception(f"bad file paths in zipfile '{fn}'")
            newfilename = os.path.join(outdir, fn)
            dirname = os.path.dirname(newfilename)
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            elif not os.path.isdir(dirname) or os.path.exists(newfilename):
                raise Exception("Cannot unzip. Other files are in the way")
            with open(newfilename, "wb") as out:
                out.write(extzip.read(fn))
            yield newfilename


class KeepNoteExtension(extension.Extension):
    version = PROGRAM_VERSION
    key = "keepnote.py"
    name = "KeepNote"
    description = "The KeepNote application"
    visible = False

    def __init__(self, app):
        super().__init__(app)

    def enable(self, enable):
        super().enable(True)
        return True

    def get_richtext_tag_table(self):
        """
        返回富文本编辑器用的标签表（Gtk.TextTagTable）
        这通常是用于高亮、粗体、颜色等文本标记。
        """
        if not hasattr(self, "_richtext_tag_table"):
            self._richtext_tag_table = Gtk.TextTagTable()
        return self._richtext_tag_table


def get_depends(self):
    return []

class Listener:
    def __init__(self):
        self._callbacks = []

    def add(self, callback):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def remove(self, callback):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def fire(self, *args, **kwargs):
        for callback in self._callbacks:
            callback(*args, **kwargs)

class KeepNoteApplication(Gtk.Application):
    # def get_richtext_tag_table(self):
    #     # TODO: Return a tag table for rich text editing
    #     from gi.repository import Gtk
    #     return Gtk.TextTagTable()
    def __init__(self):
        Gtk.Application.__init__(self, application_id="org.keepnote.py.KeepNote")
        self._tag_table = None
        self.pref = self.load_preferences()
        self.connect("activate", self.do_activate)
        self._notebooks = []
        self._windows = []
        self._window = None
        self._activated = False  # 初始化 _activated 属性
        self._app = None  # 初始化 _app 属性
        # Ensure _app is initialized properly here
        self._app = KeepNote(pref_dir=self.get_pref_dir())
        print("✅ Application finished without exception.")

    def get_pref_dir(self):
        # Make sure this method returns the preferences directory
        return get_user_pref_dir(home=None)  # Calls the previously defined get_user_pref_dir function

    def set_app(self, app):
        self._app = app

    def load_preferences(self):
        """
        加载用户偏好设置，可以是 JSON 或其他格式
        """
        config_path = os.path.join(keepnote.get_user_pref_dir(), "settings.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print("Error loading preferences:", e)
        return {}

    def get_listeners(self, key):
        if not hasattr(self, "_listeners"):
            self._listeners = {}
        if key not in self._listeners:
            self._listeners[key] = Listener()
        return self._listeners[key]

    def ref_notebook(self, notebook):
        """注册一个 notebook 引用，避免重复添加"""
        if notebook not in self._notebooks:
            self._notebooks.append(notebook)

    def unref_notebook(self, notebook):
        """注销 notebook 引用"""
        if notebook in self._notebooks:
            self._notebooks.remove(notebook)

    def get_notebooks(self):
        """获取当前引用的所有 notebooks"""
        return list(self._notebooks)


    def get_richtext_tag_table(self):
        if self._tag_table is None:
            from keepnote.gui.richtext.richtextbase_tags import RichTextTagTable
            self._tag_table = RichTextTagTable()
        return self._tag_table

    # 在 keepnote.py/__init__.py 的 KeepNoteApplication 类中
    def do_activate(self, *args):
        # Delay the import of `keepnote.gui` until it's needed
        print("✅ Entering do_activate with args:")
        try:
            import keepnote.gui
            from keepnote.gui.main_window import KeepNoteWindow  # Ensure the class is imported correctly
        except ImportError as e:
            print(f"ERROR: Failed to import keepnote.gui: {e}")
            raise
        log_message(f"✅ Entering do_activate with args: {args}\n")
        try:
            # 防止重复激活
            if self._activated:
                print("⚠️ Application already activated, presenting existing window")
                if self._windows:
                    self._windows[0].present()
                    log_message(f"ℹ️ Window presented (id: {self._windows[0]})\n")
                return

            self._activated = True
            print("✅ Marked as activated")
            # 创建新窗口
            print("🧱 Constructing KeepNoteWindow...")
            window = KeepNoteWindow(self._app)
            print("✅ KeepNoteWindow created")
            self.add_window(window)  # ✅ 保证 Gtk.Application 不会退出
            self._windows.append(window)
            window.set_application(self)
            window.present()
            # 加载菜单
            builder = Gtk.Builder()
            menu_ui_path = os.path.join(keepnote.get_basedir(), "rc", "menu.ui")
            if os.path.exists(menu_ui_path):
                builder.add_from_file(menu_ui_path)
                menu = builder.get_object("app_menu")
                if menu:
                    popover = Gtk.PopoverMenu()
                    popover.set_menu_model(menu)
                    # 假设 menu_button 在 KeepNoteWindow 中
                    menu_button = window.get_widget("menu_button") if hasattr(window, 'get_widget') else None
                    if menu_button:
                        menu_button.set_popover(popover)
                        print("✅ Menu loaded and attached to menu_button")
                        log_message("✅ Menu loaded and set to menu_button\n")
                    else:
                        log_message("⚠️ menu_button not found in UI\n")
                else:
                    log_message("⚠️ app_menu not found in menu.ui\n")
            else:
                log_message(f"⚠️ menu.ui not found at: {menu_ui_path}\n")

            # 呈现窗口
            window.present()
            log_message(f"✅ New window created (id: {window._winid}) and presented\n")


            # 执行命令
            # need_gui = self._app.execute_command(sys.argv)
            need_gui = True  # Always launch GUI
            log_message(f"ℹ️ Window presented (id: {self._windows[0]})")
            print("✅ do_activate() 完成，主窗口应该已展示")

        except Exception as e:
            exc_type, exc_value, tracebk = sys.exc_info()
            log_error(exc_value, tracebk)
            # 保持主循环运行
            return

    def get_node(self, uid):
        # 兼容接口，用于提供 get_node 方法
        if hasattr(self, "notebook") and self.notebook:
            return self.notebook.get_node(uid)
        return None

    def error(self, text, error=None, tracebk=None):
        from keepnote import log_message, log_error
        """
        用于统一打印错误信息（主窗口或后台异常）。
        """
        log_message(text + "\n")
        if error is not None:
            log_error(error, tracebk)

    def do_startup(self):
        Gtk.Application.do_startup(self)


    def get_windows(self):
        return self._windows

    def new_window(self):
        window = keepnote.gui.KeepNoteWindow(self._app)
        self.add_window(window)  # 告诉 Gtk.Application 它需要保持这个窗口存在
        self._windows.append(window)
        window.set_application(self)
        window.present()
        return window

    def get_current_window(self):
        return self._windows[0] if self._windows else None