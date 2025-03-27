"""
    KeepNote
    Graphical User Interface for KeepNote Application
"""

#
#  KeepNote
#  Copyright (c) 2008-2011 Matt Rasmussen
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

# Python imports
import os
import sys
import threading
import gi
gi.require_version('Gdk', '3.0')
gi.require_version('Gtk', '3.0')
gi.require_version('GLib', '2.0') # Specify GTK 3.0
from gi.repository import Gdk, Gtk, GLib
from gi.repository import GdkPixbuf

# KeepNote imports
import keepnote
from keepnote import log_error
from keepnote.gui.richtext import richtext_tags
from keepnote import get_resource
from keepnote import tasklib
from keepnote.notebook import NoteBookError
import keepnote.notebook as notebooklib
import keepnote.gui.dialog_app_options
import keepnote.gui.dialog_node_icon
import keepnote.gui.dialog_wait
from keepnote.gui.icons import DEFAULT_QUICK_PICK_ICONS, uncache_node_icon

_ = keepnote.translate

# Constants
MAX_RECENT_NOTEBOOKS = 20
ACCEL_FILE = "accel.txt"
IMAGE_DIR = "images"
CONTEXT_MENU_ACCEL_PATH = "<main>/context_menu"

DEFAULT_AUTOSAVE_TIME = 10 * 1000  # 10 sec (in msec)

# Font constants
DEFAULT_FONT_FAMILY = "Sans"
DEFAULT_FONT_SIZE = 10
DEFAULT_FONT = f"{DEFAULT_FONT_FAMILY} {DEFAULT_FONT_SIZE}"

if keepnote.get_platform() == "darwin":
    CLIPBOARD_NAME = Gdk.SELECTION_PRIMARY
else:
    CLIPBOARD_NAME = "CLIPBOARD"

DEFAULT_COLORS_FLOAT = [
    # lights
    (1, .6, .6),
    (1, .8, .6),
    (1, 1, .6),
    (.6, 1, .6),
    (.6, 1, 1),
    (.6, .6, 1),
    (1, .6, 1),

    # trues
    (1, 0, 0),
    (1, .64, 0),
    (1, 1, 0),
    (0, 1, 0),
    (0, 1, 1),
    (0, 0, 1),
    (1, 0, 1),

    # darks
    (.5, 0, 0),
    (.5, .32, 0),
    (.5, .5, 0),
    (0, .5, 0),
    (0, .5, .5),
    (0, 0, .5),
    (.5, 0, .5),

    # white, gray, black
    (1, 1, 1),
    (.9, .9, .9),
    (.75, .75, .75),
    (.5, .5, .5),
    (.25, .25, .25),
    (.1, .1, .1),
    (0, 0, 0),
]

def color_float_to_int8(color):
    return (int(255 * color[0]), int(255 * color[1]), int(255 * color[2]))

def color_int8_to_str(color):
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"

DEFAULT_COLORS = [color_int8_to_str(color_float_to_int8(color))
                  for color in DEFAULT_COLORS_FLOAT]

# Resources
class PixbufCache(object):
    """A cache for loading pixbufs from the filesystem"""

    def __init__(self):
        self._pixbufs = {}

    def get_pixbuf(self, filename, size=None, key=None):
        if key is None:
            key = (filename, size)

        if key in self._pixbufs:
            return self._pixbufs[key]
        else:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(filename)

            if size:
                if size != (pixbuf.get_width(), pixbuf.get_height()):
                    pixbuf = pixbuf.scale_simple(size[0], size[1],
                                                 GdkPixbuf.InterpType.BILINEAR)

            self._pixbufs[key] = pixbuf
            return pixbuf

    def cache_pixbuf(self, pixbuf, key):
        self._pixbufs[key] = pixbuf

    def is_pixbuf_cached(self, key):
        return key in self._pixbufs

# Singleton
pixbufs = PixbufCache()

get_pixbuf = pixbufs.get_pixbuf
cache_pixbuf = pixbufs.cache_pixbuf
is_pixbuf_cached = pixbufs.is_pixbuf_cached

def get_resource_image(*path_list):
    """Returns Gtk.Image from resource path"""
    filename = get_resource(IMAGE_DIR, *path_list)
    img = Gtk.Image.new_from_file(filename)
    return img

def get_resource_pixbuf(*path_list, **options):
    """Returns cached pixbuf from resource path"""
    return pixbufs.get_pixbuf(get_resource(IMAGE_DIR, *path_list), **options)

def fade_pixbuf(pixbuf, alpha=128):
    """Returns a new faded pixbuf"""
    width, height = pixbuf.get_width(), pixbuf.get_height()
    pixbuf2 = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, width, height)
    pixbuf2.fill(0xffffff00)  # Fill with transparent
    pixbuf.composite(pixbuf2, 0, 0, width, height,
                     0, 0, 1.0, 1.0, GdkPixbuf.InterpType.NEAREST, alpha)
    return pixbuf2

# Misc GUI functions
def get_accel_file():
    """Returns gtk accel file"""
    return os.path.join(keepnote.get_user_pref_dir(), ACCEL_FILE)

def init_key_shortcuts():
    """Setup key shortcuts for the window"""
    accel_file = get_accel_file()
    if os.path.exists(accel_file):
        Gtk.AccelMap.load(accel_file)
    else:
        Gtk.AccelMap.save(accel_file)

def set_gtk_style(font_size=10, vsep=0):
    """Set basic GTK style settings using CSS"""
    css_provider = Gtk.CssProvider()
    css = f"""
    * {{
        font-family: {DEFAULT_FONT_FAMILY};
        font-size: {font_size}px;
    }}
    """
    css_provider.load_from_data(css.encode('utf-8'))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

def update_file_preview(file_chooser, preview):
    """Preview widget for file choosers"""
    filename = file_chooser.get_preview_filename()
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(filename, 128, 128)
        preview.set_from_pixbuf(pixbuf)
        have_preview = True
    except GLib.GError:
        have_preview = False
    file_chooser.set_preview_widget_active(have_preview)

class FileChooserDialog(Gtk.FileChooserDialog):
    """File Chooser Dialog with a persistent path"""

    def __init__(self, title=None, parent=None,
                 action=Gtk.FileChooserAction.OPEN,
                 buttons=None, backend=None,
                 app=None,
                 persistent_path=None):
        super().__init__(title=title, parent=parent,
                         action=action)

        # Add buttons manually since buttons parameter is deprecated
        if buttons:
            for label, response in buttons:
                self.add_button(label, response)

        self._app = app
        self._persistent_path = persistent_path

        if self._app and self._persistent_path:
            path = self._app.get_default_path(self._persistent_path)
            if path and os.path.exists(path):
                self.set_current_folder(path)

    def run(self):
        response = super().run()

        if (response == Gtk.ResponseType.OK and
                self._app and self._persistent_path):
            self._app.set_default_path(
                self._persistent_path, self.get_current_folder())

        return response

# Menu actions
class UIManager(Gtk.UIManager):
    """Specialization of UIManager for use in KeepNote"""

    def __init__(self, force_stock=False):
        super().__init__()
        self.connect("connect-proxy", self._on_connect_proxy)
        self.connect("disconnect-proxy", self._on_disconnect_proxy)

        self.force_stock = force_stock

    def _on_connect_proxy(self, uimanager, action, widget):
        """Callback for a widget entering management"""
        if isinstance(action, (Action, ToggleAction)) and action.icon:
            self.set_icon(widget, action)

    def _on_disconnect_proxy(self, uimanager, action, widget):
        """Callback for a widget leaving management"""
        pass

    def set_force_stock(self, force):
        """Sets the 'force stock icon' option"""
        self.force_stock = force

        for ag in self.get_action_groups():
            for action in ag.list_actions():
                for widget in action.get_proxies():
                    self.set_icon(widget, action)

    def set_icon(self, widget, action):
        """Sets the icon for a managed widget"""
        if not isinstance(action, (Action, ToggleAction)):
            return

        if isinstance(widget, Gtk.MenuItem):
            if self.force_stock and action.get_property("stock-id"):
                img = Gtk.Image.new_from_icon_name(action.get_property("stock-id"),
                                                   Gtk.IconSize.MENU)
                widget.set_image(img)
            elif action.icon:
                img = Gtk.Image.new_from_pixbuf(get_resource_pixbuf(action.icon))
                widget.set_image(img)

        elif isinstance(widget, Gtk.ToolButton):
            if self.force_stock and action.get_property("stock-id"):
                widget.set_icon_name(action.get_property("stock-id"))
            elif action.icon:
                img = Gtk.Image.new_from_pixbuf(get_resource_pixbuf(action.icon))
                widget.set_icon_widget(img)

class Action(Gtk.Action):
    def __init__(self, name, stockid=None, label=None,
                 accel="", tooltip="", func=None,
                 icon=None):
        super().__init__(name=name, label=label, tooltip=tooltip, stock_id=stockid)
        self.func = func
        self.accel = accel
        self.icon = icon
        self.signal = None

        if func:
            self.signal = self.connect("activate", func)

class ToggleAction(Gtk.ToggleAction):
    def __init__(self, name, stockid, label=None,
                 accel="", tooltip="", func=None, icon=None):
        super().__init__(name=name, label=label, tooltip=tooltip, stock_id=stockid)
        self.func = func
        self.accel = accel
        self.icon = icon
        self.signal = None

        if func:
            self.signal = self.connect("toggled", func)

def add_actions(actiongroup, actions):
    """Add a list of Action's to an gtk.ActionGroup"""
    for action in actions:
        actiongroup.add_action_with_accel(action, action.accel)

# Application for GUI
class KeepNote(keepnote.KeepNote):
    """GUI version of the KeepNote application instance"""

    def __init__(self, basedir=None):
        super().__init__(basedir)

        # Window management
        self._current_window = None
        self._windows = []

        # Shared GUI resources
        self._tag_table = richtext_tags.RichTextTagTable()
        self.init_dialogs()

        # Auto save
        self._auto_saving = False
        self._auto_save_registered = False
        self._auto_save_pause = 0

    def init(self):
        """Initialize application from disk"""
        super().init()

    def init_dialogs(self):
        self.app_options_dialog = (
            keepnote.gui.dialog_app_options.ApplicationOptionsDialog(self))
        self.node_icon_dialog = (
            keepnote.gui.dialog_node_icon.NodeIconDialog(self))

    def set_lang(self):
        """Set language for application"""
        super().set_lang()

    def load_preferences(self):
        """Load information from preferences"""
        super().load_preferences()

        p = self.pref
        p.get("autosave_time", default=DEFAULT_AUTOSAVE_TIME)

        set_gtk_style(font_size=p.get("look_and_feel", "app_font_size",
                                      default=10))

        for window in self._windows:
            window.load_preferences()

        for notebook in self._notebooks.values():
            notebook.enable_fulltext_search(p.get("use_fulltext_search",
                                                  default=True))

        self.begin_auto_save()

    def save_preferences(self):
        """Save information into preferences"""
        for window in self._windows:
            window.save_preferences()

        super().save_preferences()

    def get_richtext_tag_table(self):
        """Returns the application-wide richtext tag table"""
        return self._tag_table

    def new_window(self):
        """Create a new main window"""
        import keepnote.gui.main_window

        window = keepnote.gui.main_window.KeepNoteWindow(self)
        window.connect("delete-event", self._on_window_close)
        window.connect("focus-in-event", self._on_window_focus)
        self._windows.append(window)

        self.init_extensions_windows([window])
        window.show_all()

        if self._current_window is None:
            self._current_window = window

        return window

    def get_current_window(self):
        """Returns the currently active window"""
        return self._current_window

    def get_windows(self):
        """Returns a list of open windows"""
        return self._windows

    def open_notebook(self, filename, window=None, task=None):
        """Open notebook"""
        from keepnote.gui import dialog_update_notebook

        if isinstance(self._conns.get(filename),
                      keepnote.notebook.connection.fs.NoteBookConnectionFS):

            try:
                version = notebooklib.get_notebook_version(filename)
            except Exception as e:
                self.error(f"Could not load notebook '{filename}'.", e, sys.exc_info()[2])
                return None

            if version < notebooklib.NOTEBOOK_FORMAT_VERSION:
                dialog = dialog_update_notebook.UpdateNoteBookDialog(
                    self, window)
                if not dialog.show(filename, version=version, task=task):
                    self.error("Cannot open notebook (version too old)")
                    return None

        def update(task):
            sem = threading.Semaphore()
            sem.acquire()

            def func():
                try:
                    conn = self._conns.get(filename)
                    notebook = notebooklib.NoteBook()
                    notebook.load(filename, conn)
                    task.set_result(notebook)
                except Exception as e:
                    task.set_exc_info(sys.exc_info())
                    task.stop()
                finally:
                    sem.release()
                return False

            GLib.idle_add(func)
            sem.acquire()

        task = tasklib.Task(update)
        dialog = keepnote.gui.dialog_wait.WaitDialog(window)
        dialog.show(_("Opening notebook"), _("Loading..."), task, cancel=False)

        try:
            if task.aborted():
                raise task.exc_info()[1]
            else:
                notebook = task.get_result()
                if notebook is None:
                    return None

        except notebooklib.NoteBookVersionError as e:
            self.error(f"This version of {keepnote.PROGRAM_NAME} cannot read this notebook.\n"
                       f"The notebook has version {e.notebook_version}.  {keepnote.PROGRAM_NAME} can only read {e.readable_version}.",
                       e, task.exc_info()[2])
            return None

        except NoteBookError as e:
            self.error(f"Could not load notebook '{filename}'.", e, task.exc_info()[2])
            return None

        except Exception as e:
            self.error(f"Could not load notebook '{filename}'.", e, task.exc_info()[2])
            return None

        self._init_notebook(notebook)
        return notebook

    def _init_notebook(self, notebook):
        write_needed = False

        if len(notebook.pref.get_quick_pick_icons()) == 0:
            notebook.pref.set_quick_pick_icons(
                list(DEFAULT_QUICK_PICK_ICONS))
            notebook.set_preferences_dirty()
            write_needed = True

        if len(notebook.pref.get("colors", default=())) == 0:
            notebook.pref.set("colors", DEFAULT_COLORS)
            notebook.set_preferences_dirty()
            write_needed = True

        notebook.enable_fulltext_search(self.pref.get("use_fulltext_search",
                                                      default=True))

        if write_needed:
            notebook.write_preferences()

    def save_notebooks(self, silent=False):
        """Save all opened notebooks"""
        for notebook in self._notebooks.values():
            notebook.pref.clear("windows", "ids")
            notebook.pref.clear("viewers", "ids")

        for window in self._windows:
            window.save_notebook(silent=silent)

        for notebook in self._notebooks.values():
            notebook.save()

        for window in self._windows:
            window.update_title()

    def _on_closing_notebook(self, notebook, save):
        """Callback for when notebook is about to close"""
        super()._on_closing_notebook(notebook, save)

        try:
            if save:
                self.save()
        except Exception as e:
            log_error("Error while closing notebook", e)

        for window in self._windows:
            window.close_notebook(notebook)

    def goto_nodeid(self, nodeid):
        """Open a node by nodeid"""
        for window in self.get_windows():
            notebook = window.get_notebook()
            if not notebook:
                continue
            node = notebook.get_node_by_id(nodeid)
            if node:
                window.get_viewer().goto_node(node)
                break

    # Auto-save
    def begin_auto_save(self):
        """Begin autosave callbacks"""
        if self.pref.get("autosave"):
            self._auto_saving = True

            if not self._auto_save_registered:
                self._auto_save_registered = True
                GLib.timeout_add(self.pref.get("autosave_time"),
                                 self.auto_save)
        else:
            self._auto_saving = False

    def end_auto_save(self):
        """Stop autosave"""
        self._auto_saving = False

    def auto_save(self):
        """Callback for autosaving"""
        self._auto_saving = self.pref.get("autosave")

        if not self._auto_saving:
            self._auto_save_registered = False
            return False

        if self._auto_save_pause > 0:
            return True

        self.save(True)
        return True

    def pause_auto_save(self, pause):
        """Pauses autosaving"""
        self._auto_save_pause += 1 if pause else -1

    # Node icons
    def on_set_icon(self, icon_file, icon_open_file, nodes):
        """Change the icon for a node"""
        for node in nodes:
            if icon_file == "":
                node.del_attr("icon")
            elif icon_file is not None:
                node.set_attr("icon", icon_file)

            if icon_open_file == "":
                node.del_attr("icon_open")
            elif icon_open_file is not None:
                node.set_attr("icon_open", icon_open_file)

            uncache_node_icon(node)

    def on_new_icon(self, nodes, notebook, window=None):
        """Change the icon for a node"""
        if notebook is None:
            return

        node = nodes[0]

        icon_file, icon_open_file = self.node_icon_dialog.show(node,
                                                               window=window)

        newly_installed = set()

        if icon_file and os.path.isabs(icon_file) and \
           icon_open_file and os.path.isabs(icon_open_file):
            icon_file, icon_open_file = notebook.install_icons(
                icon_file, icon_open_file)
            newly_installed.add(os.path.basename(icon_file))
            newly_installed.add(os.path.basename(icon_open_file))

        else:
            if icon_file and os.path.isabs(icon_file):
                icon_file = notebook.install_icon(icon_file)
                newly_installed.add(os.path.basename(icon_file))

            if icon_open_file and os.path.isabs(icon_open_file):
                icon_open_file = notebook.install_icon(icon_open_file)
                newly_installed.add(os.path.basename(icon_open_file))

        if icon_file is not None:
            notebook.pref.set_quick_pick_icons(
                self.node_icon_dialog.get_quick_pick_icons())

            notebook_icons = notebook.get_icons()
            keep_set = (set(self.node_icon_dialog.get_notebook_icons()) |
                        newly_installed)
            for icon in notebook_icons:
                if icon not in keep_set:
                    notebook.uninstall_icon(icon)

            notebook.set_preferences_dirty()
            notebook.write_preferences()

        self.on_set_icon(icon_file, icon_open_file, nodes)

    # File attachment
    def on_attach_file(self, node=None, parent_window=None):
        dialog = FileChooserDialog(
            title=_("Attach File..."), parent=parent_window,
            action=Gtk.FileChooserAction.OPEN,
            buttons=(_("Cancel"), Gtk.ResponseType.CANCEL,
                     _("Attach"), Gtk.ResponseType.OK),
            app=self,
            persistent_path="attach_file_path")
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_select_multiple(True)

        preview = Gtk.Image()
        dialog.set_preview_widget(preview)
        dialog.connect("update-preview", update_file_preview, preview)

        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            filenames = list(dialog.get_filenames())
            self.attach_files(filenames, node,
                              parent_window=parent_window)

        dialog.destroy()

    def attach_file(self, filename, parent, index=None,
                    parent_window=None):
        self.attach_files([filename], parent, index, parent_window)

    def attach_files(self, filenames, parent, index=None,
                     parent_window=None):
        if parent_window is None:
            parent_window = self.get_current_window()

        try:
            for filename in filenames:
                notebooklib.attach_file(filename, parent, index)

        except Exception as e:
            if len(filenames) > 1:
                self.error(f"Error while attaching files {', '.join([f'\"{f}\"' for f in filenames])}.",
                           e, sys.exc_info()[2])
            else:
                self.error(f"Error while attaching file '{filenames[0]}'.",
                           e, sys.exc_info()[2])

    # Misc GUI
    def focus_windows(self):
        """Focus all open windows on desktop"""
        for window in self._windows:
            window.present()

    def error(self, text, error=None, tracebk=None, parent=None):
        """Display an error message"""
        if parent is None:
            parent = self.get_current_window()

        dialog = Gtk.MessageDialog(
            parent=parent,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=text)
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.set_title(_("Error"))
        dialog.show()

        if error is not None:
            log_error(error, tracebk)

    def message(self, text, title="KeepNote", parent=None):
        """Display a message window"""
        if parent is None:
            parent = self.get_current_window()

        dialog = Gtk.MessageDialog(
            parent=parent,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=text)
        dialog.set_title(title)
        dialog.run()
        dialog.destroy()

    def ask_yes_no(self, text, title="KeepNote", parent=None):
        """Display a yes/no window"""
        if parent is None:
            parent = self.get_current_window()

        dialog = Gtk.MessageDialog(
            parent=parent,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=text)

        dialog.set_title(title)
        response = dialog.run()
        dialog.destroy()

        return response == Gtk.ResponseType.YES

    def quit(self):
        """Quit the gtk event loop"""
        super().quit()
        Gtk.AccelMap.save(get_accel_file())
        Gtk.main_quit()

    # Callbacks
    def _on_window_close(self, window, event):
        """Callback for window close event"""
        if window in self._windows:
            for ext in self.get_enabled_extensions():
                try:
                    if isinstance(ext, keepnote.gui.extension.Extension):
                        ext.on_close_window(window)
                except Exception as e:
                    log_error(e, sys.exc_info()[2])

            self._windows.remove(window)

            if window == self._current_window:
                self._current_window = None

        if len(self._windows) == 0:
            self.quit()

    def _on_window_focus(self, window, event):
        """Callback for when a window gains focus"""
        self._current_window = window

    # Extension methods
    def init_extensions_windows(self, windows=None, exts=None):
        """Initialize all extensions for a window"""
        if exts is None:
            exts = self.get_enabled_extensions()

        if windows is None:
            windows = self.get_windows()

        for window in windows:
            for ext in exts:
                try:
                    if isinstance(ext, keepnote.gui.extension.Extension):
                        ext.on_new_window(window)
                except Exception as e:
                    log_error(e, sys.exc_info()[2])

    def install_extension(self, filename):
        """Install a new extension"""
        if self.ask_yes_no(f"Do you want to install the extension \"{filename}\"?", "Extension Install"):
            new_exts = super().install_extension(filename)
            self.init_extensions_windows(exts=new_exts)

            if len(new_exts) > 0:
                self.message(f"Extension \"{filename}\" is now installed.", _("Install Successful"))
                return True
        return False

    def uninstall_extension(self, ext_key):
        """Install a new extension"""
        if self.ask_yes_no(f"Do you want to uninstall the extension \"{ext_key}\"?", _("Extension Uninstall")):
            if super().uninstall_extension(ext_key):
                self.message(f"Extension \"{ext_key}\" is now uninstalled.",
                             _("Uninstall Successful"))
                return True
        return False