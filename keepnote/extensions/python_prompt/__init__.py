"""
    KeepNote
    Python prompt extension
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
from keepnote.gui import dialog_app_options

# PyGObject imports for GTK 4
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio

# Add the current directory to sys.path to import dialog_python
sys.path.append(os.path.dirname(__file__))
from . import dialog_python


class Extension(extension.Extension):

    def __init__(self, app):
        """Initialize extension"""
        extension.Extension.__init__(self, app)

    def get_depends(self):
        return [("keepnote.py", ">=", (0, 7, 1))]

    #================================
    # UI setup

    def on_add_ui(self, window):
        # Add "Python Prompt" action
        action = Gio.SimpleAction.new("python-prompt", None)
        action.connect("activate", lambda action, param: self.on_python_prompt(window))
        window.add_action(action)

        # Add menu items using GMenu
        app = window.get_application()
        menu = app.get_menubar()
        if not menu:
            menu = Gio.Menu()
            app.set_menubar(menu)

        tools_menu = None
        for i in range(menu.get_n_items()):
            if menu.get_item_attribute_value(i, "label").get_string() == "_Tools":
                tools_menu = menu.get_item_link(i, "submenu")
                break

        if not tools_menu:
            tools_menu = Gio.Menu()
            menu.append_submenu("_Tools", tools_menu)

        extensions_menu = None
        for i in range(tools_menu.get_n_items()):
            if tools_menu.get_item_attribute_value(i, "label") == "Extensions":
                extensions_menu = tools_menu.get_item_link(i, "submenu")
                break

        if not extensions_menu:
            extensions_menu = Gio.Menu()
            tools_menu.append_submenu("Extensions", extensions_menu)

        extensions_menu.append("Python Prompt...", "win.python-prompt")

    #================================
    # actions

    def on_python_prompt(self, window):
        dialog = dialog_python.PythonDialog(window)
        dialog.show()