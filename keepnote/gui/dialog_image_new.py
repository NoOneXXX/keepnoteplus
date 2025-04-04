# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '4.0')  # Specify GTK 4.0
from gi.repository import Gtk

# KeepNote imports
import keepnote

_ = keepnote.translate

class NewImageDialog:
    """New Image dialog for KeepNote"""

    def __init__(self, main_window, app):
        self.main_window = main_window
        self.app = app
        self.width_entry = None
        self.height_entry = None
        self.format_entry = None

    def show(self):
        dialog = Gtk.Dialog(
            title=_("New Image"),
            transient_for=self.main_window,
            modal=True
        )

        # Add buttons using the new GTK 4 API
        dialog.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("_OK"), Gtk.ResponseType.OK)

        # Create a grid
        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_column_spacing(6)
        dialog.get_content_area().append(grid)

        # Format label and entry
        label = Gtk.Label(label=_("format:"))
        grid.attach(label, 0, 0, 1, 1)

        self.format_entry = Gtk.Entry()
        grid.attach(self.format_entry, 1, 0, 1, 1)

        # Width label and entry
        label = Gtk.Label(label=_("width:"))
        grid.attach(label, 0, 1, 1, 1)

        self.width_entry = Gtk.Entry()
        grid.attach(self.width_entry, 1, 1, 1, 1)

        # Height label and entry
        label = Gtk.Label(label=_("height:"))
        grid.attach(label, 0, 2, 1, 1)

        self.height_entry = Gtk.Entry()
        grid.attach(self.height_entry, 1, 2, 1, 1)

        # Run the dialog and get the response
        dialog.present()
        response = dialog.run()

        # Retrieve the values if needed
        if response == Gtk.ResponseType.OK:
            format_value = self.format_entry.get_text()
            width_value = self.width_entry.get_text()
            height_value = self.height_entry.get_text()
            # Do something with the values if needed
            print(f"Format: {format_value}, Width: {width_value}, Height: {height_value}")

        dialog.destroy()
        return response