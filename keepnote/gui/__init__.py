"""
    KeepNote
    Graphical User Interface for KeepNote Application
"""

# Python imports
import os
import sys
import threading



from keepnote.sqlitedict import logger
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gdk, GdkPixbuf
from gi.repository import Gio
# KeepNote imports
import keepnote

from keepnote.gui.richtext import richtext_tags
from keepnote.util.platform import get_resource
from keepnote import tasklib
from keepnote.notebook import NoteBookError
import keepnote.notebook as notebooklib
import keepnote.gui.dialog_app_options
import keepnote.gui.dialog_node_icon
import keepnote.gui.dialog_wait
from keepnote.gui.icons import DEFAULT_QUICK_PICK_ICONS, uncache_node_icon

# 修改为从 util.perform 直接导入
from keepnote.util.platform import translate
_ = translate

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

from keepnote.util.platform import get_platform
if get_platform() == "darwin":
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
            if not isinstance(filename, str):
                # 不接受 Gtk.Image 或 Paintable，返回默认或跳过
                return None

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
    return Gtk.Image.new_from_file(filename)

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
        Gtk.accelerator_parse_from_file(accel_file)  # GTK 4 doesn't have AccelMap
    else:
        pass  # No direct equivalent in GTK 4 for saving accel map

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
    display = Gdk.Display.get_default()
    Gtk.StyleContext.add_provider_for_display(
        display,
        css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

def update_file_preview(file_chooser, preview):
    """Preview widget for file choosers"""
    filename = file_chooser.get_filename()
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(filename, 128, 128)
        preview.set_pixbuf(pixbuf)
        file_chooser.set_preview_widget_active(True)
    except GLib.GError:
        file_chooser.set_preview_widget_active(False)

class FileChooserDialog(Gtk.FileChooserDialog):
    def __init__(self, title, parent, action, buttons, app=None, persistent_path=None):
        super().__init__(
            title=title,
            transient_for=parent,
            action=action
        )
        for label, response in buttons:
            self.add_button(label, response)

        self._app = app
        self._persistent_path = persistent_path

    def run(self):
        response = self.show()
        return response

    def get_filename(self):
        return super().get_filename()

# Menu actions (GTK 4 uses Gio.SimpleAction instead of Gtk.Action)
class UIManager:
    """Custom UIManager replacement for GTK 4"""
    def __init__(self, force_stock=False):
        self.action_groups = []
        self.force_stock = force_stock

    def insert_action_group(self, action_group, pos=-1):
        if action_group.get_name() not in [ag.get_name() for ag in self.action_groups]:
            if pos == -1:
                self.action_groups.append(action_group)
            else:
                self.action_groups.insert(pos, action_group)

    def set_force_stock(self, force):
        self.force_stock = force

    def get_action_groups(self):
        return self.action_groups

class Action(Gio.SimpleAction):
    def __init__(self, name, stockid=None, label=None,
                 accel="", tooltip="", func=None, icon=None):
        super().__init__(name=name)
        self.func = func
        self.accel = accel
        self.icon = icon
        self.label = label
        self.tooltip = tooltip
        if func:
            self.connect("activate", lambda action, param: func(action))

class ToggleAction(Gio.SimpleAction):
    def __init__(self, name, stockid=None, label=None,
                 accel="", tooltip="", func=None, icon=None):
        super().__init__(name=name, state=GLib.Variant.new_boolean(False))
        self.func = func
        self.accel = accel
        self.icon = icon
        self.label = label
        self.tooltip = tooltip
        if func:
            self.connect("activate", lambda action, param: func(action))

def add_actions(actiongroup, actions):
    for action in actions:
        actiongroup.add_action(action)

# Application for GUI
class KeepNote(keepnote.KeepNote):

    def get_node(self, node_id):
        print(">>> get_node() called")
        notebook = self.get_notebook()
        if notebook:
            return notebook.get_node_by_id(node_id)
        return None

    """GUI version of the KeepNote application instance"""
    def __init__(self, basedir=None):
        super().__init__(basedir)
        self._current_window = None
        self._windows = []
        self._tag_table = richtext_tags.RichTextTagTable()
        self.init_dialogs()
        self._auto_saving = False
        self._auto_save_registered = False
        self._auto_save_pause = 0

    def init(self):
        super().init()

    def init_dialogs(self):
        self.app_options_dialog = keepnote.gui.dialog_app_options.ApplicationOptionsDialog(self)
        self.node_icon_dialog = keepnote.gui.dialog_node_icon.NodeIconDialog(self)

    def set_lang(self):
        super().set_lang()

    def parse_window_size(self, size_str):
        try:
            if not isinstance(size_str, str):
                return (1024, 600)
            size_str = size_str.strip("()")
            width, height = map(int, size_str.split(","))
            return (width, height)
        except (ValueError, AttributeError):
            print("Failed to parse window_size, using default (1024, 600)")
            return (1024, 600)

    def load_preferences(self):
        super().load_preferences()
        p = self.pref
        p.get("autosave_time", default=DEFAULT_AUTOSAVE_TIME)
        set_gtk_style(font_size=p.get("look_and_feel", "app_font_size", default=10))
        for window in self._windows:
            window.load_preferences()
        for notebook in self._notebooks.values():
            notebook.enable_fulltext_search(p.get("use_fulltext_search", default=True))
        self.begin_auto_save()

    def save_preferences(self):
        for window in self._windows:
            window.save_preferences()
        super().save_preferences()

    def get_richtext_tag_table(self):
        return self._tag_table

    def new_window(self):
        import keepnote.gui.main_window
        window = keepnote.gui.main_window.KeepNoteWindow(self)
        window.connect("close-request", self._on_window_close)
        window.connect("focus-in-event", self._on_window_focus)
        self._windows.append(window)
        self.init_extensions_windows([window])
        window.show()
        if self._current_window is None:
            self._current_window = window
        return window

    def get_current_window(self):
        return self._current_window

    def get_windows(self):
        return self._windows

    def open_notebook(self, filename, window=None, task=None):
        from keepnote.gui import dialog_update_notebook
        if isinstance(self._conns.get(filename), keepnote.notebook.connection.fs.NoteBookConnectionFS):
            try:
                version = notebooklib.get_notebook_version(filename)
            except Exception as e:
                self.error(f"Could not load notebook test '{filename}'.", e, sys.exc_info()[2])
                return None
            if version < notebooklib.NOTEBOOK_FORMAT_VERSION:
                dialog = dialog_update_notebook.UpdateNoteBookDialog(self, window)
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
            self.error(f"Could not load notebook first'{filename}'.", e, task.exc_info()[2])
            return None
        except Exception as e:
            logger.error(f"没有发现这个文件的名字{filename}")
            return None
        self._init_notebook(notebook)
        return notebook

    def _init_notebook(self, notebook):
        write_needed = False
        if len(notebook.pref.get_quick_pick_icons()) == 0:
            notebook.pref.set_quick_pick_icons(list(DEFAULT_QUICK_PICK_ICONS))
            notebook.set_preferences_dirty()
            write_needed = True
        if len(notebook.pref.get("colors", default=())) == 0:
            notebook.pref.set("colors", DEFAULT_COLORS)
            notebook.set_preferences_dirty()
            write_needed = True
        notebook.enable_fulltext_search(self.pref.get("use_fulltext_search", default=True))
        if write_needed:
            notebook.write_preferences()

    def save_notebooks(self, silent=False):
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
        from keepnote import log_error
        super()._on_closing_notebook(notebook, save)
        try:
            if save:
                self.save()
        except Exception as e:
            log_error("Error while closing notebook", e)
        for window in self._windows:
            window.close_notebook(notebook)

    def goto_nodeid(self, nodeid):
        for window in self.get_windows():
            notebook = window.get_notebook()
            if not notebook:
                continue
            node = notebook.get_node_by_id(nodeid)
            if node:
                window.get_viewer().goto_node(node)
                break

    def begin_auto_save(self):
        if self.pref.get("autosave"):
            self._auto_saving = True
            if not self._auto_save_registered:
                self._auto_save_registered = True
                autosave_time = int(self.pref.get("autosave_time", default=DEFAULT_AUTOSAVE_TIME))
                GLib.timeout_add(autosave_time, self.auto_save)
        else:
            self._auto_saving = False

    def end_auto_save(self):
        self._auto_saving = False

    def auto_save(self):
        self._auto_saving = self.pref.get("autosave")
        if not self._auto_saving:
            self._auto_save_registered = False
            return False
        if self._auto_save_pause > 0:
            return True
        self.save(True)
        return True

    def pause_auto_save(self, pause):
        self._auto_save_pause += 1 if pause else -1

    def on_set_icon(self, icon_file, icon_open_file, nodes):
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
        if notebook is None:
            return
        node = nodes[0]
        icon_file, icon_open_file = self.node_icon_dialog.show(node, window=window)
        newly_installed = set()
        if icon_file and os.path.isabs(icon_file) and icon_open_file and os.path.isabs(icon_open_file):
            icon_file, icon_open_file = notebook.install_icons(icon_file, icon_open_file)
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
            notebook.pref.set_quick_pick_icons(self.node_icon_dialog.get_quick_pick_icons())
            notebook_icons = notebook.get_icons()
            keep_set = (set(self.node_icon_dialog.get_notebook_icons()) | newly_installed)
            for icon in notebook_icons:
                if icon not in keep_set:
                    notebook.uninstall_icon(icon)
            notebook.set_preferences_dirty()
            notebook.write_preferences()
        self.on_set_icon(icon_file, icon_open_file, nodes)

    def on_attach_file(self, node=None, parent_window=None):
        dialog = FileChooserDialog(
            title=_("Attach File..."),
            parent=parent_window,
            action=Gtk.FileChooserAction.OPEN,
            buttons=[
                (_("Cancel"), Gtk.ResponseType.CANCEL),
                (_("Attach"), Gtk.ResponseType.OK)
            ],
            app=self,
            persistent_path="attach_file_path"
        )
        dialog.set_select_multiple(True)
        preview = Gtk.Image()
        dialog.set_preview_widget(preview)
        dialog.connect("update-preview", update_file_preview, preview)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filenames = list(dialog.get_filenames())
            self.attach_files(filenames, node, parent_window=parent_window)
        dialog.destroy()

    def attach_file(self, filename, parent, index=None, parent_window=None):
        self.attach_files([filename], parent, index, parent_window)

    def attach_files(self, filenames, parent, index=None, parent_window=None):
        if parent_window is None:
            parent_window = self.get_current_window()
        try:
            for filename in filenames:
                notebooklib.attach_file(filename, parent, index)
        except Exception as e:
            if len(filenames) > 1:
                self.error(f"Error while attaching files {', '.join([f'{f}' for f in filenames])}.", e, sys.exc_info()[2])
            else:
                self.error(f"Error while attaching file '{filenames[0]}'.", e, sys.exc_info()[2])

    def focus_windows(self):
        for window in self._windows:
            window.present()

    def error(self, text, error=None, tracebk=None, parent=None):
        from keepnote import log_error
        if parent is None:
            parent = self.get_current_window()
        dialog = Gtk.MessageDialog(
            transient_for=parent,
            modal=True,
            destroy_with_parent=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=text
        )
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.set_title(_("Error"))
        dialog.show()
        if error is not None:
            log_error(error, tracebk)

    def message(self, text, title="KeepNote", parent=None):
        if parent is None:
            parent = self.get_current_window()
        dialog = Gtk.MessageDialog(
            transient_for=parent,
            modal=True,
            destroy_with_parent=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=text
        )
        dialog.set_title(title)
        dialog.run()
        dialog.destroy()

    def ask_yes_no(self, text, title="KeepNote", parent=None):
        if parent is None:
            parent = self.get_current_window()
        dialog = Gtk.MessageDialog(
            transient_for=parent,
            modal=True,
            destroy_with_parent=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=text
        )
        dialog.set_title(title)
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.YES

    def quit(self):
        super().quit()
        Gtk.main_quit()

    def _on_window_close(self, window):
        from keepnote import log_error
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
        return False

    def _on_window_focus(self, window, event):
        self._current_window = window

    def init_extensions_windows(self, windows=None, exts=None):
        from keepnote import log_error
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
                    log_error(f"看看这里弹出的是啥'.", e, sys.exc_info()[2])

    def install_extension(self, filename):
        if self.ask_yes_no(f"Do you want to install the extension \"{filename}\"?", "Extension Install"):
            new_exts = super().install_extension(filename)
            self.init_extensions_windows(exts=new_exts)
            if len(new_exts) > 0:
                self.message(f"Extension \"{filename}\" is now installed.", _("Install Successful"))
                return True
        return False

    def uninstall_extension(self, ext_key):
        if self.ask_yes_no(f"Do you want to uninstall the extension \"{ext_key}\"?", _("Extension Uninstall")):
            if super().uninstall_extension(ext_key):
                self.message(f"Extension \"{ext_key}\" is now uninstalled.", _("Uninstall Successful"))
                return True
        return False