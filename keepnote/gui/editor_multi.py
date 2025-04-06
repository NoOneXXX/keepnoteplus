# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '4.0')  # Specify GTK 4.0
from gi.repository import Gtk

# KeepNote imports
import keepnote
from keepnote.gui.editor import KeepNoteEditor

_ = keepnote.translate

class MultiEditor(KeepNoteEditor):
    """
    Manager for switching between multiple editors
    """

    def __init__(self, app):
        super().__init__(app)

        self._notebook = None
        self._nodes = []
        self._editor = None
        self._window = None

        self._signals = [
            "view-node",
            "visit-node",
            "modified",
            "font-change",
            "error",
            "child-activated",
            "window-request",
            "make-link"
        ]
        self._signal_ids = []

    def set_editor(self, editor):
        """Set the current child editor"""
        # Do nothing if editor is already set
        if editor == self._editor:
            return

        # Tear down old editor, if it exists
        if self._editor:
            self._editor.view_nodes([])
            self._editor.save_preferences(self._app.pref)
            self._disconnect_signals(self._editor)
            if self._window:
                self._editor.remove_ui(self._window)
            self._editor.set_notebook(None)
            self.remove(self._editor)

        self._editor = editor

        # Start up new editor, if it exists
        if self._editor:
            self.append(self._editor)  # Changed from pack_start to append
            self._editor.set_notebook(self._notebook)
            if self._window:
                self._editor.add_ui(self._window)
            self._editor.load_preferences(self._app.pref)
            self._editor.view_nodes(self._nodes)
            self._connect_signals(self._editor)

    def get_editor(self):
        """Get the current child editor"""
        return self._editor

    def _connect_signals(self, editor):
        """Connect all signals for child editor"""
        def make_callback(sig):
            return lambda *args: self.emit(sig, *args[1:])

        for sig in self._signals:
            self._signal_ids.append(
                editor.connect(sig, make_callback(sig))
            )

    def _disconnect_signals(self, editor):
        """Disconnect all signals for child editor"""
        for sigid in self._signal_ids:
            editor.disconnect(sigid)
        self._signal_ids = []

    #========================================
    # Editor Interface

    def set_notebook(self, notebook):
        """Set notebook for editor"""
        self._notebook = notebook
        if self._editor:
            self._editor.set_notebook(notebook)

    def get_textview(self):
        """Return the textview"""
        if self._editor:
            return self._editor.get_textview()
        return None

    def is_focus(self):
        """Return True if text editor has focus"""
        if self._editor:
            return self._editor.is_focus()
        return False

    def grab_focus(self):
        """Pass focus to textview"""
        if self._editor:
            return self._editor.grab_focus()

    def clear_view(self):
        """Clear editor view"""
        if self._editor:
            return self._editor.clear_view()

    def view_nodes(self, nodes):
        """View a page in the editor"""
        self._nodes = nodes[:]
        if self._editor:
            return self._editor.view_nodes(nodes)

    def save(self):
        """Save the loaded node"""
        if self._editor:
            return self._editor.save()

    def save_needed(self):
        """Returns True if textview is modified"""
        if self._editor:
            return self._editor.save_needed()
        return False

    def load_preferences(self, app_pref, first_open=False):
        """Load application preferences"""
        if self._editor:
            return self._editor.load_preferences(app_pref, first_open)

    def save_preferences(self, app_pref):
        """Save application preferences"""
        if self._editor:
            return self._editor.save_preferences(app_pref)

    def add_ui(self, window):
        """Add editor UI to window"""
        self._window = window
        if self._editor:
            return self._editor.add_ui(window)

    def remove_ui(self, window):
        """Remove editor from UI"""
        self._window = None
        if self._editor:
            return self._editor.remove_ui(window)

    def undo(self):
        """Undo last editor action"""
        if self._editor:
            return self._editor.undo()

    def redo(self):
        """Redo last editor action"""
        if self._editor:
            return self._editor.redo()


class ContentEditor(MultiEditor):
    """
    Register multiple editors depending on the content type
    """

    def __init__(self, app):
        super().__init__(app)

        self._editors = {}
        self._default_editor = None

    def add_editor(self, content_type, editor):
        """Add an editor for a content-type"""
        self._editors[content_type] = editor

    def remove_editor(self, content_type):
        """Remove editor for a content-type"""
        if content_type in self._editors:
            del self._editors[content_type]

    def get_editor_content(self, content_type):
        """Get editor associated with content-type"""
        return self._editors.get(content_type)

    def set_default_editor(self, editor):
        """Set the default editor"""
        self._default_editor = editor

    # 在 ContentEditor 类中加上这个方法
    def get_widget(self):
        return self._textview  # 或者返回 Gtk.Box、Gtk.Widget 等视图控件

    #=============================
    # Editor Interface

    def view_nodes(self, nodes):
        """View nodes and select the appropriate editor based on content type"""
        if len(nodes) != 1:
            super().view_nodes([])
        else:
            content_type = nodes[0].get_attr("content_type", "").split("/")

            for i in range(len(content_type), 0, -1):
                editor = self._editors.get("/".join(content_type[:i]), None)
                if editor:
                    self.set_editor(editor)
                    break
            else:
                self.set_editor(self._default_editor)

            super().view_nodes(nodes)