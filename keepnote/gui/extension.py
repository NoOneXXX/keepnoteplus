# Python 3 and PyGObject imports
import sys
import gi
gi.require_version('Gtk', '4.0')  # Specify GTK 4.0
from gi.repository import Gtk

# KeepNote imports
import keepnote
from keepnote import extension

class Extension(extension.Extension):
    """KeepNote Extension with GUI support"""

    def __init__(self, app):
        super().__init__(app)

        self.__windows = set()
        self.__uis = set()

        # UI interface
        self.__ui_ids = {}         # toolbar/menu ids (per window)
        self.__action_groups = {}  # ui actions (per window)

        self.enabled.add(self._on_enable_ui)

    #================================
    # Window interactions

    def _on_enable_ui(self, enabled):
        """Initialize UI during enable/disable"""
        if enabled:
            for window in self.__windows:
                if window not in self.__uis:
                    self.on_add_ui(window)
                    self.__uis.add(window)
        else:
            for window in list(self.__uis):
                self.on_remove_ui(window)
            self.__uis.clear()

    def on_new_window(self, window):
        """Initialize extension for a particular window"""
        if self._enabled:
            try:
                self.on_add_ui(window)
                self.__uis.add(window)
            except Exception as e:
                keepnote.log_error(e, sys.exc_info()[2])
        self.__windows.add(window)

    def on_close_window(self, window):
        """Callback for when window is closed"""
        if window in self.__windows:
            if window in self.__uis:
                try:
                    self.on_remove_ui(window)
                except Exception as e:
                    keepnote.log_error(e, sys.exc_info()[2])
                self.__uis.remove(window)
            self.__windows.remove(window)

    def get_windows(self):
        """Returns windows associated with extension"""
        return self.__windows

    #===============================
    # UI interaction

    def on_add_ui(self, window):
        """Callback to add UI elements for a window"""
        pass

    def on_remove_ui(self, window):
        """Callback to remove UI elements for a window"""
        self.remove_all_actions(window)
        self.remove_all_ui(window)

    def on_add_options_ui(self, dialog):
        """Callback to add options UI to a dialog"""
        pass

    def on_remove_options_ui(self, dialog):
        """Callback to remove options UI from a dialog"""
        pass

    #===============================
    # Helper functions

    def add_action(self, window, action_name, menu_text,
                   callback=lambda w: None,
                   stock_id=None, accel="", tooltip=None):
        """Add an action to the window's UI manager"""
        # Note: Gtk.ActionGroup is deprecated in GTK 4. This method needs to be reimplemented
        # using GAction and GMenu or manual widget creation.
        print(f"Warning: add_action needs to be reimplemented for GTK 4 (Gtk.ActionGroup is deprecated) - {action_name}")
        pass

    def remove_action(self, window, action_name):
        """Remove a specific action from the window's UI manager"""
        # Note: This method needs to be reimplemented for GTK 4.
        print(f"Warning: remove_action needs to be reimplemented for GTK 4 - {action_name}")
        pass

    def remove_all_actions(self, window):
        """Remove all actions for the window"""
        # Note: This method needs to be reimplemented for GTK 4.
        print("Warning: remove_all_actions needs to be reimplemented for GTK 4")
        if window in self.__action_groups:
            del self.__action_groups[window]

    def add_ui(self, window, uixml):
        """Add UI elements to the window's UI manager"""
        # Note: Gtk.UIManager is deprecated in GTK 4. This method needs to be reimplemented
        # using GMenu or manual widget creation.
        print("Warning: add_ui needs to be reimplemented for GTK 4 (Gtk.UIManager is deprecated)")
        return None

    def remove_ui(self, window, uid):
        """Remove a specific UI element from the window's UI manager"""
        # Note: This method needs to be reimplemented for GTK 4.
        print("Warning: remove_ui needs to be reimplemented for GTK 4")
        uids = self.__ui_ids.get(window)
        if uids is not None and uid in uids:
            uids.remove(uid)
            if len(uids) == 0:
                del self.__ui_ids[window]

    def remove_all_ui(self, window):
        """Remove all UI elements for the window"""
        # Note: This method needs to be reimplemented for GTK 4.
        print("Warning: remove_all_ui needs to be reimplemented for GTK 4")
        if window in self.__ui_ids:
            del self.__ui_ids[window]