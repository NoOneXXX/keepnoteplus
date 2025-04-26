# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '3.0')  # Specify GTK 3.0
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
        self.find_xml = None
        self.find_last_pos = -1

    def on_find(self, replace=False, forward=None):
        if self.find_dialog is not None:
            self.find_dialog.present()

            # Update UI for replace mode
            self.find_xml.get_object("replace_checkbutton").set_active(replace)
            self.find_xml.get_object("replace_entry").set_sensitive(replace)
            self.find_xml.get_object("replace_button").set_sensitive(replace)
            self.find_xml.get_object("replace_all_button").set_sensitive(replace)

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

        # Load the Glade file
        self.find_xml = Gtk.Builder()
        self.find_xml.add_from_file(get_resource("rc", "keepnote.glade"))
        self.find_xml.set_translation_domain(keepnote.GETTEXT_DOMAIN)
        self.find_dialog = self.find_xml.get_object("find_dialog")
        print("[DEBUG] find_dialog content_area children:", self.find_dialog.get_children())
        self.find_dialog.connect("delete-event", lambda w, e: self.on_find_response("close"))

        # Connect signals
        self.find_xml.connect_signals({
            "on_find_dialog_key_release_event": self.on_find_key_released,
            "on_close_button_clicked": lambda w: self.on_find_response("close"),
            "on_find_button_clicked": lambda w: self.on_find_response("find"),
            "on_replace_button_clicked": lambda w: self.on_find_response("replace"),
            "on_replace_all_button_clicked": lambda w: self.on_find_response("replace_all"),
            "on_replace_checkbutton_toggled": lambda w: self.on_find_replace_toggled()
        })

        # Set initial values
        if self.find_text is not None:
            self.find_xml.get_object("text_entry").set_text(self.find_text)

        if self.replace_text is not None:
            self.find_xml.get_object("replace_entry").set_text(self.replace_text)

        self.find_xml.get_object("replace_checkbutton").set_active(replace)
        self.find_xml.get_object("replace_entry").set_sensitive(replace)
        self.find_xml.get_object("replace_button").set_sensitive(replace)
        self.find_xml.get_object("replace_all_button").set_sensitive(replace)

        self.find_dialog.show()
        print("[DEBUG] find_dialog shown, children after show:", self.find_dialog.get_children())
        # Position the dialog relative to the editor's top-level window
        parent_pos = self.editor.get_toplevel().get_position()
        self.find_dialog.move(parent_pos[0], parent_pos[1])

    def on_find_key_released(self, widget, event):
        # Check for Ctrl+G (find next) or Ctrl+Shift+G (find previous)
        if (event.keyval == Gdk.KEY_G and
                (event.state & Gdk.ModifierType.SHIFT_MASK) and
                (event.state & Gdk.ModifierType.CONTROL_MASK)):
            self.on_find_response("find_prev")
            widget.stop_emission_by_name("key-release-event")

        elif (event.keyval == Gdk.KEY_g and
              (event.state & Gdk.ModifierType.CONTROL_MASK)):
            self.on_find_response("find_next")
            widget.stop_emission_by_name("key-release-event")

    def on_find_response(self, response):
        # Get find options
        find_text = unicode_gtk(self.find_xml.get_object("text_entry").get_text())
        replace_text = unicode_gtk(self.find_xml.get_object("replace_entry").get_text())
        case_sensitive = self.find_xml.get_object("case_sensitive_button").get_active()
        search_forward = self.find_xml.get_object("forward_button").get_active()

        self.find_text = find_text
        self.replace_text = replace_text
        next_search = (self.find_last_pos != -1)

        if response == "close":
            self.find_dialog.destroy()
            self.find_dialog = None
            self.find_xml = None

        elif response == "find":
            self.find_last_pos = self.editor.get_textview().find(
                find_text, case_sensitive, search_forward, next_search)

        elif response == "find_next":
            self.find_xml.get_object("forward_button").set_active(True)
            self.find_last_pos = self.editor.get_textview().find(
                find_text, case_sensitive, True)

        elif response == "find_prev":
            self.find_xml.get_object("backward_button").set_active(True)
            self.find_last_pos = self.editor.get_textview().find(
                find_text, case_sensitive, False)

        elif response == "replace":
            self.find_last_pos = self.editor.get_textview().replace(
                find_text, replace_text, case_sensitive, search_forward)

        elif response == "replace_all":
            self.editor.get_textview().replace_all(
                find_text, replace_text, case_sensitive, search_forward)

    def on_find_replace_toggled(self):
        replace_active = self.find_xml.get_object("replace_checkbutton").get_active()
        self.find_xml.get_object("replace_entry").set_sensitive(replace_active)
        self.find_xml.get_object("replace_button").set_sensitive(replace_active)
        self.find_xml.get_object("replace_all_button").set_sensitive(replace_active)