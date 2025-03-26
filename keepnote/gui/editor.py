# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '3.0')  # Specify GTK 3.0
from gi.repository import Gtk, GObject

# KeepNote imports
import keepnote

_ = keepnote.translate

class KeepNoteEditor(Gtk.Box):
    """
    Base class for all KeepNoteEditors
    """

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._app = app
        self._notebook = None
        self._textview = None
        self.show_all()

    def set_notebook(self, notebook):
        """Set notebook for editor"""
        pass

    def get_textview(self):
        """Return the textview widget"""
        return self._textview

    def is_focus(self):
        """Return True if text editor has focus"""
        return False

    def grab_focus(self):
        """Pass focus to textview"""
        pass

    def clear_view(self):
        """Clear editor view"""
        pass

    def view_nodes(self, nodes):
        """View a node(s) in the editor"""
        pass

    def save(self):
        """Save the loaded page"""
        pass

    def save_needed(self):
        """Returns True if textview is modified"""
        return False

    def load_preferences(self, app_pref, first_open=False):
        """Load application preferences"""
        pass

    def save_preferences(self, app_pref):
        """Save application preferences"""
        pass

    def add_ui(self, window):
        """Add UI elements to the window"""
        pass

    def remove_ui(self, window):
        """Remove UI elements from the window"""
        pass

    def undo(self):
        """Undo the last action"""
        pass

    def redo(self):
        """Redo the last undone action"""
        pass

# Add new signals to KeepNoteEditor
GObject.type_register(KeepNoteEditor)
GObject.signal_new("view-node", KeepNoteEditor, GObject.SignalFlags.RUN_LAST,
                   None, (object,))
GObject.signal_new("visit-node", KeepNoteEditor, GObject.SignalFlags.RUN_LAST,
                   None, (object,))
GObject.signal_new("modified", KeepNoteEditor, GObject.SignalFlags.RUN_LAST,
                   None, (object, bool))
GObject.signal_new("font-change", KeepNoteEditor, GObject.SignalFlags.RUN_LAST,
                   None, (object,))
GObject.signal_new("error", KeepNoteEditor, GObject.SignalFlags.RUN_LAST,
                   None, (str, object))
GObject.signal_new("child-activated", KeepNoteEditor, GObject.SignalFlags.RUN_LAST,
                   None, (object, object))
GObject.signal_new("window-request", KeepNoteEditor, GObject.SignalFlags.RUN_LAST,
                   None, (str,))
GObject.signal_new("make-link", KeepNoteEditor, GObject.SignalFlags.RUN_LAST,
                   None, ())