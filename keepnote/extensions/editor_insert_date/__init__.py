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

# PyGObject imports for GTK 3
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject

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
        self._set_focus_id[window] = window.connect("set-focus", self._on_focus)

        # add menu options
        self.add_action(window, "InsertDate", "Insert _Date",
                        lambda w: self.insert_date(window))

        self.add_ui(window,
                """
                <ui>
                <menubar name="main_menu_bar">
                   <menu action="Edit">
                      <placeholder name="Viewer">
                         <placeholder name="Editor">
                           <placeholder name="Extension">
                             <menuitem action="InsertDate"/>
                           </placeholder>
                         </placeholder>
                      </placeholder>
                   </menu>
                </menubar>
                </ui>
                """)

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

    def _on_focus(self, window, widget):
        """Callback for focus change in window"""
        self._widget_focus[window] = widget

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
        v = Gtk.VBox(spacing=5)
        w.add(v)

        table = Gtk.Grid()
        table.set_row_spacing(5)
        table.set_column_spacing(5)
        v.pack_start(table, False, True, 0)

        label = Gtk.Label(label="Date format:")
        table.attach(label, 0, 0, 1, 1)

        self.format = Gtk.Entry()
        table.attach(self.format, 1, 0, 1, 1)

        # Add a help button for date format examples
        help_button = Gtk.Button(label="Help with Date Formats")
        help_button.connect("clicked", self.on_help_clicked)
        table.attach(help_button, 1, 1, 1, 1)

        w.show_all()

    def on_help_clicked(self, button):
        """Show a dialog with date format examples"""
        dialog = Gtk.MessageDialog(
            transient_for=self.dialog,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Date Format Examples"
        )
        dialog.format_secondary_text(
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