# Python 3 and PyGObject imports
import sys
import gi
gi.require_version('Gtk', '3.0')  # Specify GTK 3.0
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
        # Initialize action group if not present
        if window not in self.__action_groups:
            group = Gtk.ActionGroup(name="MainWindow")
            self.__action_groups[window] = group
            window.get_uimanager().insert_action_group(group, 0)

        # Add action
        self.__action_groups[window].add_actions([
            (action_name, stock_id, menu_text, accel, tooltip, callback)])

    def remove_action(self, window, action_name):
        """Remove a specific action from the window's UI manager"""
        group = self.__action_groups.get(window)
        if group is not None:
            action = group.get_action(action_name)
            if action:
                group.remove_action(action)

    def remove_all_actions(self, window):
        """Remove all actions for the window"""
        group = self.__action_groups.get(window)
        if group is not None:
            window.get_uimanager().remove_action_group(group)
            del self.__action_groups[window]

    def add_ui(self, window, uixml):
        """Add UI elements to the window's UI manager"""
        # Initialize list of UI IDs if not present
        uids = self.__ui_ids.get(window)
        if uids is None:
            uids = self.__ui_ids[window] = []

        # Add UI and record ID
        uid = window.get_uimanager().add_ui_from_string(uixml)
        uids.append(uid)

        # Return ID
        return uid

    def remove_ui(self, window, uid):
        """Remove a specific UI element from the window's UI manager"""
        uids = self.__ui_ids.get(window)
        if uids is not None and uid in uids:
            window.get_uimanager().remove_ui(uid)
            uids.remove(uid)

            # Remove UID list if last UID removed
            if len(uids) == 0:
                del self.__ui_ids[window]

    def remove_all_ui(self, window):
        """Remove all UI elements for the window"""
        uids = self.__ui_ids.get(window)
        if uids is not None:
            for uid in uids:
                window.get_uimanager().remove_ui(uid)
            del self.__ui_ids[window]