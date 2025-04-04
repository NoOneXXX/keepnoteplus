"""
KeepNote
Insert date extension
"""

# Python imports
import gettext
import time
import os
import sys
_ = gettext.gettext

# KeepNote imports
import keepnote
from keepnote.gui import extension
from keepnote import safefile
from keepnote.gui.dialog_app_options import ApplicationOptionsDialog, Section

# PyGObject imports for GTK 4
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio

class Extension(extension.Extension):

    def __init__(self, app):
        """Initialize extension"""

        extension.Extension.__init__(self, app)

        self._widget_focus = {}
        self._set_focus_id = {}

        self.format = "%Y/%m/%d"

        self.enabled.add(self.on_enabled)

    def on_enabled(self, enabled):
        if enabled:
            self.load_config()

    def get_depends(self):
        return [("keepnote", ">=", (0, 7, 1))]

    #===============================
    # config handling

    def get_config_file(self):
        return self.get_data_file("config")

    def load_config(self):
        config = self.get_config_file()
        if not os.path.exists(config):
            self.format = "%Y-%m-%d"
            self.save_config()
        else:
            with open(config, "r", encoding="utf-8") as f:  # Use text mode with UTF-8
                self.format = f.readline().strip()

    def save_config(self):
        config = self.get_config_file()
        with safefile.safe_open(config, "w", codec="utf-8") as out:
            out.write(self.format)

    #================================
    # UI setup

    def on_add_ui(self, window):
        # listen to focus events from the window
        self._set_focus_id[window] = window.connect("notify::focus-widget", self._on_focus)

        # add menu options using actions
        action = Gio.SimpleAction.new("insert-date", None)
        action.connect("activate", lambda action, param: self.insert_date(window))
        window.add_action(action)

        # add menu items using GMenu
        app = window.get_application()
        menu = app.get_menubar()
        if not menu:
            menu = Gio.Menu()
            app.set_menubar(menu)

        edit_menu = None
        for i in range(menu.get_n_items()):
            if menu.get_item_attribute_value(i, "label").get_string() == "_Edit":
                edit_menu = menu.get_item_link(i, "submenu")
                break

        if not edit_menu:
            edit_menu = Gio.Menu()
            menu.append_submenu("_Edit", edit_menu)

        viewer_menu = None
        for i in range(edit_menu.get_n_items()):
            if edit_menu.get_item_attribute_value(i, "label") == "Viewer":
                viewer_menu = edit_menu.get_item_link(i, "submenu")
                break

        if not viewer_menu:
            viewer_menu = Gio.Menu()
            edit_menu.append_submenu("Viewer", viewer_menu)

        editor_menu = None
        for i in range(viewer_menu.get_n_items()):
            if viewer_menu.get_item_attribute_value(i, "label") == "Editor":
                editor_menu = viewer_menu.get_item_link(i, "submenu")
                break

        if not editor_menu:
            editor_menu = Gio.Menu()
            viewer_menu.append_submenu("Editor", editor_menu)

        extension_menu = None
        for i in range(editor_menu.get_n_items()):
            if editor_menu.get_item_attribute_value(i, "label") == "Extension":
                extension_menu = editor_menu.get_item_link(i, "submenu")
                break

        if not extension_menu:
            extension_menu = Gio.Menu()
            editor_menu.append_submenu("Extension", extension_menu)

        extension_menu.append("Insert _Date", "win.insert-date")

    def on_remove_ui(self, window):
        extension.Extension.on_remove_ui(self, window)

        # disconnect window callbacks
        window.disconnect(self._set_focus_id[window])
        del self._set_focus_id[window]

    #=================================
    # Options UI setup

    def on_add_options_ui(self, dialog):
        dialog.add_section(EditorInsertDateSection("editor_insert_date",
                                                   dialog, self._app,
                                                   self),
                           "extensions")

    def on_remove_options_ui(self, dialog):
        dialog.remove_section("editor_insert_date")

    #================================
    # actions

    def _on_focus(self, window, pspec):
        """Callback for focus change in window"""
        self._widget_focus[window] = window.get_focus()

    def insert_date(self, window):
        """Insert a date in the editor of a window"""
        widget = self._widget_focus.get(window, None)

        if isinstance(widget, Gtk.TextView):
            stamp = time.strftime(self.format, time.localtime())
            widget.get_buffer().insert_at_cursor(stamp)

class EditorInsertDateSection(Section):
    """A Section in the Options Dialog"""

    def __init__(self, key, dialog, app, ext,
                 label="Editor Insert Date",
                 icon=None):
        Section.__init__(self, key, dialog, app, label, icon)

        self.ext = ext

        w = self.get_default_widget()
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        w.append(v)

        table = Gtk.Grid()
        table.set_row_spacing(5)
        table.set_column_spacing(5)
        v.append(table)

        label = Gtk.Label(label="Date format:")
        table.attach(label, 0, 0, 1, 1)

        self.format = Gtk.Entry()
        table.attach(self.format, 1, 0, 1, 1)

        # Add a help button for date format examples
        help_button = Gtk.Button(label="Help with Date Formats")
        help_button.connect("clicked", self.on_help_clicked)
        table.attach(help_button, 1, 1, 1, 1)

    def on_help_clicked(self, button):
        """Show a dialog with date format examples"""
        dialog = Gtk.MessageDialog(
            transient_for=self.dialog,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Date Format Examples"
        )
        dialog.set_deletable(True)
        dialog.set_secondary_text(
            "Use the following codes in the date format:\n"
            "%Y - Year (e.g., 2025)\n"
            "%m - Month (01-12)\n"
            "%d - Day (01-31)\n"
            "%H - Hour (00-23)\n"
            "%M - Minute (00-59)\n"
            "%S - Second (00-59)\n\n"
            "Example formats:\n"
            "%Y/%m/%d - 2025/03/28\n"
            "%Y-%m-%d %H:%M:%S - 2025-03-28 14:30:00"
        )
        dialog.run()
        dialog.destroy()

    def load_options(self, app):
        """Load options from app to UI"""
        self.format.set_text(self.ext.format)

    def save_options(self, app):
        """Save options to the app"""
        self.ext.format = self.format.get_text()
        self.ext.save_config()