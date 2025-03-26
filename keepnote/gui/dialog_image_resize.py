# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '3.0')  # Specify GTK 3.0
from gi.repository import Gtk

# KeepNote imports
import keepnote
from keepnote import get_resource

class ImageResizeDialog:
    """Image Resize dialog for KeepNote"""

    def __init__(self, main_window, app_pref):
        self.main_window = main_window
        self.app_pref = app_pref
        self.dialog = None
        self.image = None
        self.aspect = True
        self.owidth, self.oheight = None, None
        self.init_width, self.init_height = None, None
        self.ignore_width_changed = 0
        self.ignore_height_changed = 0
        self.snap_size = self.app_pref.get(
            "editors", "general", "image_size_snap_amount", default=50)
        self.snap_enabled = self.app_pref.get(
            "editors", "general", "image_size_snap", default=True)

        # Widgets
        self.size_width_scale = None
        self.size_height_scale = None
        self.width_entry = None
        self.height_entry = None
        self.aspect_check = None
        self.snap_check = None
        self.snap_entry = None
        self.xml = None

    def on_resize(self, image):
        """Launch resize dialog"""
        if not image.is_valid():
            self.main_window.error("Cannot resize image that is not properly loaded")
            return

        # Load the Glade file
        self.xml = Gtk.Builder()
        self.xml.add_from_file(get_resource("rc", "keepnote.glade"))
        self.xml.set_translation_domain(keepnote.GETTEXT_DOMAIN)
        self.dialog = self.xml.get_object("image_resize_dialog")
        self.dialog.set_transient_for(self.main_window)
        self.dialog.connect("response", self.on_response)

        # Show the dialog
        self.dialog.show()

        self.image = image
        self.aspect = True
        width, height = image.get_size(True)
        self.init_width, self.init_height = width, height
        self.owidth, self.oheight = image.get_original_size()

        # Get widgets
        self.width_entry = self.xml.get_object("width_entry")
        self.height_entry = self.xml.get_object("height_entry")
        self.size_width_scale = self.xml.get_object("size_width_scale")
        self.size_height_scale = self.xml.get_object("size_height_scale")
        self.aspect_check = self.xml.get_object("aspect_check")
        self.snap_check = self.xml.get_object("img_snap_check")
        self.snap_entry = self.xml.get_object("img_snap_amount_entry")

        # Populate info
        self.width_entry.set_text(str(width))
        self.height_entry.set_text(str(height))
        self.size_width_scale.set_value(width)
        self.size_height_scale.set_value(height)
        self.snap_check.set_active(self.snap_enabled)
        self.snap_entry.set_text(str(self.snap_size))

        # Connect signals
        self.xml.connect_signals({
            "on_width_entry_changed": lambda w: self.on_size_changed("width"),
            "on_height_entry_changed": lambda w: self.on_size_changed("height"),
            "on_aspect_check_toggled": self.on_aspect_check_toggled,
            "on_size_width_scale_value_changed": self.on_size_width_scale_value_changed,
            "on_size_height_scale_value_changed": self.on_size_height_scale_value_changed,
            "on_img_snap_check_toggled": self.on_img_snap_check_toggled,
            "on_img_snap_amount_entry_changed": self.on_img_snap_entry_changed
        })

    def get_size(self):
        """Returns the current size setting of the dialog"""
        wstr = self.width_entry.get_text()
        hstr = self.height_entry.get_text()

        try:
            width, height = int(wstr), int(hstr)

            if width <= 0:
                width = None
            if height <= 0:
                height = None

        except ValueError:
            width, height = None, None
        return width, height

    def on_response(self, dialog, response):
        """Callback for a response button in dialog"""
        if response == Gtk.ResponseType.OK:
            width, height = self.get_size()

            p = self.app_pref.get("editors", "general")
            p["image_size_snap"] = self.snap_enabled
            p["image_size_snap_amount"] = self.snap_size

            if width is not None:
                self.image.scale(width, height)
                self.dialog.destroy()
            else:
                self.main_window.error("Must specify positive integers for image size")

        elif response == Gtk.ResponseType.CANCEL:
            self.dialog.destroy()

        elif response == Gtk.ResponseType.APPLY:
            width, height = self.get_size()

            if width is not None:
                self.image.scale(width, height)

        elif response == Gtk.ResponseType.REJECT:
            # Restore default image size
            width, height = self.image.get_original_size()
            self.width_entry.set_text(str(width))
            self.height_entry.set_text(str(height))

    def set_size(self, dim, value):
        if dim == "width":
            if self.ignore_width_changed == 0:
                self.ignore_width_changed += 1
                self.width_entry.set_text(value)
                self.ignore_width_changed -= 1
        else:
            if self.ignore_height_changed == 0:
                self.ignore_height_changed += 1
                self.height_entry.set_text(value)
                self.ignore_height_changed -= 1

    def on_size_changed(self, dim):
        """Callback when a size changes"""
        if dim == "width":
            self.ignore_width_changed += 1
        else:
            self.ignore_height_changed += 1

        width, height = self.get_size()

        if self.aspect:
            if dim == "width" and width is not None:
                height = int(width / float(self.owidth) * self.oheight)
                self.size_width_scale.set_value(width)
                self.set_size("height", str(height))

            elif dim == "height" and height is not None:
                width = int(height / float(self.oheight) * self.owidth)
                self.size_height_scale.set_value(height)
                self.set_size("width", str(width))

        if width is not None and height is not None:
            self.init_width, self.init_height = width, height

        if dim == "width":
            self.ignore_width_changed -= 1
        else:
            self.ignore_height_changed -= 1

    def on_aspect_check_toggled(self, widget):
        """Callback when aspect checkbox is toggled"""
        self.aspect = self.aspect_check.get_active()

    def on_size_width_scale_value_changed(self, scale):
        """Callback for when scale value changes"""
        width = int(scale.get_value())

        if self.snap_enabled:
            snap = self.snap_size
            width = int((width + snap / 2.0) // snap * snap)
        self.set_size("width", str(width))

    def on_size_height_scale_value_changed(self, scale):
        """Callback for when scale value changes"""
        height = int(scale.get_value())

        if self.snap_enabled:
            snap = self.snap_size
            height = int((height + snap / 2.0) // snap * snap)
        self.set_size("height", str(height))

    def on_img_snap_check_toggled(self, check):
        """Callback when snap checkbox is toggled"""
        self.snap_enabled = self.snap_check.get_active()
        self.snap_entry.set_sensitive(self.snap_enabled)

    def on_img_snap_entry_changed(self, entry):
        """Callback when snap text entry changes"""
        try:
            self.snap_size = int(self.snap_entry.get_text())
        except ValueError:
            pass