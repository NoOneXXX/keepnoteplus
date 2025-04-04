# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '4.0')  # Specify GTK 4.0
from gi.repository import Gtk, Gdk

# KeepNote imports
import keepnote
from keepnote import get_resource, unicode_gtk

class KeepNoteFindDialog:
    """Find dialog for KeepNote editor"""

    def __init__(self, editor):
        self.editor = editor
        self.find_dialog = None
        self.find_text = None
        self.replace_text = None
        self.find_builder = None
        self.find_last_pos = -1

    def on_find(self, replace=False, forward=None):
        if self.find_dialog is not None:
            self.find_dialog.present()

            # Update UI for replace mode
            self.find_builder.get_object("replace_checkbutton").set_active(replace)
            self.find_builder.get_object("replace_entry").set_sensitive(replace)
            self.find_builder.get_object("replace_button").set_sensitive(replace)
            self.find_builder.get_object("replace_all_button").set_sensitive(replace)

            if not replace:
                if forward is None:
                    self.on_find_response("find")
                elif forward:
                    self.on_find_response("find_next")
                else:
                    self.on_find_response("find_prev")
            else:
                self.on_find_response("replace")

            return

        # Load the UI file (replacing Glade with a GTK 4 UI file)
        self.find_builder = Gtk.Builder()
        self.find_builder.add_from_file(get_resource("rc", "keepnote.ui"))  # Update to .ui file
        self.find_builder.set_translation_domain(keepnote.GETTEXT_DOMAIN)
        self.find_dialog = self.find_builder.get_object("find_dialog")
        self.find_dialog.connect("close-request", lambda w: self.on_find_response("close"))

        # Connect signals
        self.find_builder.get_object("close_button").connect("clicked", lambda w: self.on_find_response("close"))
        self.find_builder.get_object("find_button").connect("clicked", lambda w: self.on_find_response("find"))
        self.find_builder.get_object("replace_button").connect("clicked", lambda w: self.on_find_response("replace"))
        self.find_builder.get_object("replace_all_button").connect("clicked", lambda w: self.on_find_response("replace_all"))
        self.find_builder.get_object("replace_checkbutton").connect("toggled", lambda w: self.on_find_replace_toggled())

        # Add key controller for Ctrl+G and Ctrl+Shift+G
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-released", self.on_find_key_released)
        self.find_dialog.add_controller(key_controller)

        # Set initial values
        if self.find_text is not None:
            self.find_builder.get_object("text_entry").set_text(self.find_text)

        if self.replace_text is not None:
            self.find_builder.get_object("replace_entry").set_text(self.replace_text)

        self.find_builder.get_object("replace_checkbutton").set_active(replace)
        self.find_builder.get_object("replace_entry").set_sensitive(replace)
        self.find_builder.get_object("replace_button").set_sensitive(replace)
        self.find_builder.get_object("replace_all_button").set_sensitive(replace)

        self.find_dialog.present()
        # Position the dialog relative to the editor's top-level window
        parent_pos = self.editor.get_toplevel().get_position()
        self.find_dialog.set_position(parent_pos[0], parent_pos[1])

    def on_find_key_released(self, controller, keyval, keycode, state):
        # Check for Ctrl+G (find next) or Ctrl+Shift+G (find previous)
        if (keyval == Gdk.KEY_G and
                (state & Gdk.ModifierType.SHIFT_MASK) and
                (state & Gdk.ModifierType.CONTROL_MASK)):
            self.on_find_response("find_prev")
            return True

        elif (keyval == Gdk.KEY_g and
              (state & Gdk.ModifierType.CONTROL_MASK)):
            self.on_find_response("find_next")
            return True

        return False

    def on_find_response(self, response):
        # Get find options
        find_text = unicode_gtk(self.find_builder.get_object("text_entry").get_text())
        replace_text = unicode_gtk(self.find_builder.get_object("replace_entry").get_text())
        case_sensitive = self.find_builder.get_object("case_sensitive_button").get_active()
        search_forward = self.find_builder.get_object("forward_button").get_active()

        self.find_text = find_text
        self.replace_text = replace_text
        next_search = (self.find_last_pos != -1)

        if response == "close":
            self.find_dialog.destroy()
            self.find_dialog = None
            self.find_builder = None

        elif response == "find":
            self.find_last_pos = self.editor.get_textview().find(
                find_text, case_sensitive, search_forward, next_search)

        elif response == "find_next":
            self.find_builder.get_object("forward_button").set_active(True)
            self.find_last_pos = self.editor.get_textview().find(
                find_text, case_sensitive, True)

        elif response == "find_prev":
            self.find_builder.get_object("backward_button").set_active(True)
            self.find_last_pos = self.editor.get_textview().find(
                find_text, case_sensitive, False)

        elif response == "replace":
            self.find_last_pos = self.editor.get_textview().replace(
                find_text, replace_text, case_sensitive, search_forward)

        elif response == "replace_all":
            self.editor.get_textview().replace_all(
                find_text, replace_text, case_sensitive, search_forward)

    def on_find_replace_toggled(self):
        replace_active = self.find_builder.get_object("replace_checkbutton").get_active()
        self.find_builder.get_object("replace_entry").set_sensitive(replace_active)
        self.find_builder.get_object("replace_button").set_sensitive(replace_active)
        self.find_builder.get_object("replace_all_button").set_sensitive(replace_active)