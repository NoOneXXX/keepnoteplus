"""
    KeepNote
    Backward compatibility for configuration information
"""

#
#  KeepNote
#  Copyright (c) 2008-2009 Matt Rasmussen
#  Author: Matt Rasmussen <rasmus@alum.mit.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.
#

import os
import shutil
from xml.etree import ElementTree

import keepnote
from keepnote import FS_ENCODING
from keepnote import xdg
import keepnote.timestamp
import keepnote.compat.xmlobject_v3 as xmlo
from keepnote.util import compose
from keepnote import orderdict

OLD_USER_PREF_DIR = "takenote"
OLD_USER_PREF_FILE = "takenote.xml"
OLD_XDG_USER_EXTENSIONS_DIR = "takenote/extensions"
OLD_XDG_USER_EXTENSIONS_DATA_DIR = "takenote/extensions_data"

USER_PREF_DIR = "keepnote"
USER_PREF_FILE = "keepnote.xml"
USER_EXTENSIONS_DIR = "extensions"
USER_EXTENSIONS_DATA_DIR = "extensions_data"

XDG_USER_EXTENSIONS_DIR = "keepnote/extensions"
XDG_USER_EXTENSIONS_DATA_DIR = "keepnote/extensions_data"


# =============================================================================
# Preference directory compatibility

def get_old_pref_dir1(home):
    """
    Returns old preference directory (type 1)
    $HOME/.takenote
    """
    return os.path.join(home, "." + OLD_USER_PREF_DIR)


def get_old_pref_dir2(home):
    """
    Returns old preference directory (type 2)
    $HOME/.config/takenote
    """
    return os.path.join(home, ".config", OLD_USER_PREF_DIR)


def get_new_pref_dir(home):
    """
    Returns new preference directory
    $HOME/.config/keepnote
    """
    return os.path.join(home, ".config", USER_PREF_DIR)


def get_home():
    """Return HOME directory"""
    home = keepnote.ensure_unicode(os.getenv("HOME"), FS_ENCODING)
    if home is None:
        raise keepnote.EnvError("HOME environment variable must be specified")
    return home


def get_old_user_pref_dir(home=None):
    """Returns the directory of the old application preference file"""

    p = keepnote.get_platform()
    if p in ("unix", "darwin"):
        if home is None:
            home = get_home()
        old_dir = get_old_pref_dir1(home)

        if os.path.exists(old_dir):
            return old_dir
        else:
            return xdg.get_config_file(OLD_USER_PREF_DIR, default=True)

    elif p == "windows":
        appdata = keepnote.get_win_env("APPDATA")
        if appdata is None:
            raise keepnote.EnvError("APPDATA environment variable must be specified")
        return os.path.join(appdata, OLD_USER_PREF_DIR)

    else:
        raise Exception(f"unknown platform '{p}'")


def get_new_user_pref_dir(home=None):
    """Returns the directory of the new application preference file"""

    p = keepnote.get_platform()
    if p in ("unix", "darwin"):
        if home is None:
            home = get_home()
        return xdg.get_config_file(USER_PREF_DIR, default=True)

    elif p == "windows":
        appdata = keepnote.get_win_env("APPDATA")
        if appdata is None:
            raise keepnote.EnvError("APPDATA environment variable must be specified")
        return os.path.join(appdata, USER_PREF_DIR)

    else:
        raise Exception(f"unknown platform '{p}'")


def upgrade_user_pref_dir(old_user_pref_dir, new_user_pref_dir):
    """Moves preference data from old location to new one"""
    # Move user preference directory
    shutil.copytree(old_user_pref_dir, new_user_pref_dir)

    # Rename takenote.xml to keepnote.xml
    oldfile = os.path.join(new_user_pref_dir, OLD_USER_PREF_FILE)
    newfile = os.path.join(new_user_pref_dir, USER_PREF_FILE)

    if os.path.exists(oldfile):
        os.rename(oldfile, newfile)

        # Rename root XML tag
        tree = ElementTree.ElementTree(file=newfile)
        elm = tree.getroot()
        elm.tag = "keepnote"
        tree.write(newfile, encoding="UTF-8")

    # Move over data files from .local/share/takenote
    if keepnote.get_platform() in ("unix", "darwin"):
        datadir = os.path.join(get_home(), ".local", "share", "takenote")

        old_ext_dir = os.path.join(datadir, "extensions")
        new_ext_dir = os.path.join(new_user_pref_dir, "extensions")
        if not os.path.exists(new_ext_dir) and os.path.exists(old_ext_dir):
            shutil.copytree(old_ext_dir, new_ext_dir)

        old_ext_dir = os.path.join(datadir, "extensions_data")
        new_ext_dir = os.path.join(new_user_pref_dir, "extensions_data")
        if not os.path.exists(new_ext_dir) and os.path.exists(old_ext_dir):
            shutil.copytree(old_ext_dir, new_ext_dir)


def check_old_user_pref_dir(home=None):
    """Upgrades user preference directory if it exists in an old format"""
    old_pref_dir = get_old_user_pref_dir(home)
    new_pref_dir = get_new_user_pref_dir(home)
    if not os.path.exists(new_pref_dir) and os.path.exists(old_pref_dir):
        upgrade_user_pref_dir(old_pref_dir, new_pref_dir)


# =============================================================================
# XML config compatibility

DEFAULT_WINDOW_SIZE = (1024, 600)
DEFAULT_WINDOW_POS = (-1, -1)
DEFAULT_VSASH_POS = 200
DEFAULT_HSASH_POS = 200
DEFAULT_VIEW_MODE = "vertical"
DEFAULT_AUTOSAVE_TIME = 10 * 1000  # 10 sec (in msec)


class ExternalApp:
    """Class represents the information needed for calling an external application"""

    def __init__(self, key, title, prog, args=None):
        self.key = key
        self.title = title
        self.prog = prog
        self.args = args if args is not None else []


class KeepNotePreferences:
    """Preference data structure for the KeepNote application"""

    def __init__(self):
        # External apps
        self.external_apps = []
        self._external_apps = []
        self._external_apps_lookup = {}

        self.id = ""

        # Extensions
        self.disabled_extensions = []

        # Window presentation options
        self.window_size = DEFAULT_WINDOW_SIZE
        self.window_maximized = True
        self.vsash_pos = DEFAULT_VSASH_POS
        self.hsash_pos = DEFAULT_HSASH_POS
        self.view_mode = DEFAULT_VIEW_MODE

        # Look and feel
        self.treeview_lines = True
        self.listview_rules = True
        self.use_stock_icons = False
        self.use_minitoolbar = False

        # Autosave
        self.autosave = True
        self.autosave_time = DEFAULT_AUTOSAVE_TIME

        self.default_notebook = ""
        self.use_last_notebook = True
        self.timestamp_formats = dict(keepnote.timestamp.DEFAULT_TIMESTAMP_FORMATS)
        self.spell_check = True
        self.image_size_snap = True
        self.image_size_snap_amount = 50
        self.use_systray = True
        self.skip_taskbar = False
        self.recent_notebooks = []

        self.language = ""

        # Dialog chooser paths
        docs = ""
        self.new_notebook_path = docs
        self.archive_notebook_path = docs
        self.insert_image_path = docs
        self.save_image_path = docs
        self.attach_file_path = docs

        # Temp variables for parsing
        self._last_timestamp_name = ""
        self._last_timestamp_format = ""

    def _get_data(self, data=None):
        if data is None:
            data = orderdict.OrderDict()

        data["id"] = self.id

        # Language
        data["language"] = self.language

        # Window presentation options
        data["window"] = {
            "window_size": self.window_size,
            "window_maximized": self.window_maximized,
            "use_systray": self.use_systray,
            "skip_taskbar": self.skip_taskbar
        }

        # Autosave
        data["autosave"] = self.autosave
        data["autosave_time"] = self.autosave_time

        data["default_notebook"] = self.default_notebook
        data["use_last_notebook"] = self.use_last_notebook
        data["recent_notebooks"] = self.recent_notebooks
        data["timestamp_formats"] = self.timestamp_formats

        # Editor
        data["editors"] = {
            "general": {
                "spell_check": self.spell_check,
                "image_size_snap": self.image_size_snap,
                "image_size_snap_amount": self.image_size_snap_amount
            }
        }

        # Viewer
        data["viewers"] = {
            "three_pane_viewer": {
                "vsash_pos": self.vsash_pos,
                "hsash_pos": self.hsash_pos,
                "view_mode": self.view_mode
            }
        }

        # Look and feel
        data["look_and_feel"] = {
            "treeview_lines": self.treeview_lines,
            "listview_rules": self.listview_rules,
            "use_stock_icons": self.use_stock_icons,
            "use_minitoolbar": self.use_minitoolbar
        }

        # Dialog chooser paths
        data["default_paths"] = {
            "new_notebook_path": self.new_notebook_path,
            "archive_notebook_path": self.archive_notebook_path,
            "insert_image_path": self.insert_image_path,
            "save_image_path": self.save_image_path,
            "attach_file_path": self.attach_file_path
        }

        # External apps
        data["external_apps"] = [
            {
                "key": app.key,
                "title": app.title,
                "prog": app.prog,
                "args": app.args
            }
            for app in self.external_apps
        ]

        # Extensions
        data["extension_info"] = {
            "disabled": self.disabled_extensions
        }
        data["extensions"] = {}

        return data

    def read(self, filename):
        """Read preferences from file"""
        # Clear external apps vars
        self.external_apps = []
        self._external_apps_lookup = {}

        # Read XML preference file
        with open(filename, "rb") as infile:
            g_keepnote_pref_parser.read(self, infile)


g_keepnote_pref_parser = xmlo.XmlObject(
    xmlo.Tag("keepnote", tags=[
        xmlo.Tag("id", attr=("id", None, None)),
        xmlo.Tag("language", attr=("language", None, None)),

        xmlo.Tag("default_notebook",
                 attr=("default_notebook", None, None)),
        xmlo.Tag("use_last_notebook",
                 attr=("use_last_notebook", xmlo.str2bool, xmlo.bool2str)),

        # Window presentation options
        xmlo.Tag("view_mode",
                 attr=("view_mode", None, None)),
        xmlo.Tag("window_size",
                 attr=("window_size",
                       lambda x: tuple(map(int, x.split(","))),
                       lambda x: "%d,%d" % x)),
        xmlo.Tag("window_maximized",
                 attr=("window_maximized", xmlo.str2bool, xmlo.bool2str)),
        xmlo.Tag("vsash_pos",
                 attr=("vsash_pos", int, compose(str, int))),
        xmlo.Tag("hsash_pos",
                 attr=("hsash_pos", int, compose(str, int))),

        xmlo.Tag("treeview_lines",
                 attr=("treeview_lines", xmlo.str2bool, xmlo.bool2str)),
        xmlo.Tag("listview_rules",
                 attr=("listview_rules", xmlo.str2bool, xmlo.bool2str)),
        xmlo.Tag("use_stock_icons",
                 attr=("use_stock_icons", xmlo.str2bool, xmlo.bool2str)),
        xmlo.Tag("use_minitoolbar",
                 attr=("use_minitoolbar", xmlo.str2bool, xmlo.bool2str)),

        # Image resize
        xmlo.Tag("image_size_snap",
                 attr=("image_size_snap", xmlo.str2bool, xmlo.bool2str)),
        xmlo.Tag("image_size_snap_amount",
                 attr=("image_size_snap_amount", int, compose(str, int))),

        xmlo.Tag("use_systray",
                 attr=("use_systray", xmlo.str2bool, xmlo.bool2str)),
        xmlo.Tag("skip_taskbar",
                 attr=("skip_taskbar", xmlo.str2bool, xmlo.bool2str)),

        # Misc options
        xmlo.Tag("spell_check",
                 attr=("spell_check", xmlo.str2bool, xmlo.bool2str)),

        xmlo.Tag("autosave",
                 attr=("autosave", xmlo.str2bool, xmlo.bool2str)),
        xmlo.Tag("autosave_time",
                 attr=("autosave_time", int, compose(str, int))),

        # Default paths
        xmlo.Tag("new_notebook_path",
                 attr=("new_notebook_path", None, None)),
        xmlo.Tag("archive_notebook_path",
                 attr=("archive_notebook_path", None, None)),
        xmlo.Tag("insert_image_path",
                 attr=("insert_image_path", None, None)),
        xmlo.Tag("save_image_path",
                 attr=("save_image_path", None, None)),
        xmlo.Tag("attach_file_path",
                 attr=("attach_file_path", None, None)),

        # Recent notebooks
        xmlo.Tag("recent_notebooks", tags=[
            xmlo.TagMany("notebook",
                         iterfunc=lambda s: list(range(len(s.recent_notebooks))),
                         get=lambda s_i, x: s_i[0].recent_notebooks.append(x),
                         set=lambda s_i: s_i[0].recent_notebooks[s_i[1]])
        ]),

        # Disabled extensions
        xmlo.Tag("extensions", tags=[
            xmlo.Tag("disabled", tags=[
                xmlo.TagMany("extension",
                             iterfunc=lambda s: list(range(len(s.disabled_extensions))),
                             get=lambda s_i, x: s_i[0].disabled_extensions.append(x),
                             set=lambda s_i: s_i[0].disabled_extensions[s_i[1]])
            ]),
        ]),

        xmlo.Tag("external_apps", tags=[
            xmlo.TagMany("app",
                         iterfunc=lambda s: list(range(len(s.external_apps))),
                         before=lambda s_i: s_i[0].external_apps.append(xmlo.ExternalApp("", "", "")),
                         tags=[
                             xmlo.Tag("title",
                                      get=lambda s_i, x: setattr(s_i[0].external_apps[s_i[1]], "title", x),
                                      set=lambda s_i: s_i[0].external_apps[s_i[1]].title),
                             xmlo.Tag("name",
                                      get=lambda s_i, x: setattr(s_i[0].external_apps[s_i[1]], "key", x),
                                      set=lambda s_i: s_i[0].external_apps[s_i[1]].key),
                             xmlo.Tag("program",
                                      get=lambda s_i, x: setattr(s_i[0].external_apps[s_i[1]], "prog", x),
                                      set=lambda s_i: s_i[0].external_apps[s_i[1]].prog)]
                         )]),

        xmlo.Tag("timestamp_formats", tags=[
            xmlo.TagMany("timestamp_format",
                         iterfunc=lambda s: list(range(len(s.timestamp_formats))),
                         before=lambda s_i: (setattr(s_i[0], "_last_timestamp_name", ""),
                                             setattr(s_i[0], "_last_timestamp_format", "")),
                         after=lambda s_i: s_i[0].timestamp_formats.__setitem__(
                             s_i[0]._last_timestamp_name,
                             s_i[0]._last_timestamp_format),
                         tags=[
                             xmlo.Tag("name",
                                      get=lambda s_i, x: setattr(s_i[0], "_last_timestamp_name", x),
                                      set=lambda s_i: list(s_i[0].timestamp_formats.keys())[s_i[1]]),
                             xmlo.Tag("format",
                                      get=lambda s_i, x: setattr(s_i[0], "_last_timestamp_format", x),
                                      set=lambda s_i: list(s_i[0].timestamp_formats.values())[s_i[1]])
                         ]
                         )])
    ]))