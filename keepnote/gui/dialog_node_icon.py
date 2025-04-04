# Python 3 and PyGObject imports
import os
import gi
gi.require_version('Gtk', '4.0')  # Specify GTK 4.0
from gi.repository import Gtk, GdkPixbuf

# KeepNote imports
import keepnote
from keepnote import unicode_gtk
import keepnote.gui
from keepnote.gui.icons import (
    guess_open_icon_filename,
    lookup_icon_filename,
    builtin_icons,
    get_node_icon_filenames
)

_ = keepnote.translate

def browse_file(parent, title, filename=None):
    """Callback for selecting file browser"""
    dialog = Gtk.FileChooserDialog(
        title=title,
        transient_for=parent,
        modal=True
    )
    dialog.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
    dialog.add_button(_("_Open"), Gtk.ResponseType.OK)

    # Set the filename if it is fully specified
    if filename and os.path.isabs(filename):
        dialog.set_filename(filename)

    dialog.present()
    response = dialog.run()

    if response == Gtk.ResponseType.OK and dialog.get_filename():
        filename = unicode_gtk(dialog.get_filename())
    else:
        filename = None

    dialog.destroy()
    return filename

class NodeIconDialog:
    """Dialog for updating a notebook node's icon"""

    def __init__(self, app):
        self.app = app
        self.main_window = None
        self.node = None
        self.builder = None
        self.dialog = None
        self.icon_entry = None
        self.icon_open_entry = None
        self.icon_image = None
        self.icon_open_image = None
        self.standard_iconview = None
        self.notebook_iconview = None
        self.quick_iconview = None
        self.standard_iconlist = None
        self.notebook_iconlist = None
        self.quick_iconlist = None
        self.iconviews = []
        self.iconlists = []
        self.iconview_signals = {}

    def show(self, node=None, window=None):
        """Show the dialog"""
        self.main_window = window
        self.node = node

        # Load the UI file (replacing Glade with a GTK 4 UI file)
        self.builder = Gtk.Builder()
        self.builder.add_from_file(keepnote.gui.get_resource("rc", "keepnote.ui"))  # Update to .ui file
        self.builder.set_translation_domain(keepnote.GETTEXT_DOMAIN)
        self.dialog = self.builder.get_object("node_icon_dialog")
        self.dialog.set_transient_for(self.main_window)

        # Get widgets
        self.icon_entry = self.builder.get_object("icon_entry")
        self.icon_open_entry = self.builder.get_object("icon_open_entry")
        self.icon_image = self.builder.get_object("icon_image")
        self.icon_open_image = self.builder.get_object("icon_open_image")
        self.standard_iconview = self.builder.get_object("standard_iconview")
        self.notebook_iconview = self.builder.get_object("notebook_iconview")
        self.quick_iconview = self.builder.get_object("quick_pick_iconview")

        # Initialize icon lists
        self.standard_iconlist = Gtk.ListStore(GdkPixbuf.Pixbuf, str)
        self.notebook_iconlist = Gtk.ListStore(GdkPixbuf.Pixbuf, str)
        self.quick_iconlist = Gtk.ListStore(GdkPixbuf.Pixbuf, str)

        self.iconviews = [
            self.standard_iconview,
            self.notebook_iconview,
            self.quick_iconview
        ]
        self.iconlists = [
            self.standard_iconlist,
            self.notebook_iconlist,
            self.quick_iconlist
        ]

        # Connect signals for icon views
        for iconview in self.iconviews:
            self.iconview_signals[iconview] = iconview.connect(
                "selection-changed", self.on_iconview_selection_changed
            )
            iconview.connect("item-activated", lambda w, path: self.on_set_icon_button_clicked(w))

        # Connect dialog buttons
        self.builder.get_object("set_icon_button").connect("clicked", self.on_set_icon_button_clicked)
        self.builder.get_object("set_icon_open_button").connect("clicked", self.on_set_icon_open_button_clicked)
        self.builder.get_object("icon_set_button").connect("clicked", self.on_icon_set_button_clicked)
        self.builder.get_object("icon_open_set_button").connect("clicked", self.on_icon_open_set_button_clicked)
        self.builder.get_object("add_quick_pick_button").connect("clicked", self.on_add_quick_pick_button_clicked)
        self.builder.get_object("delete_icon_button").connect("clicked", self.on_delete_icon_button_clicked)

        # Set initial icon values
        if node:
            self.set_icon("icon", node.get_attr("icon", ""))
            self.set_icon("icon_open", node.get_attr("icon_open", ""))

        # Populate icon views
        self.populate_iconview()

        # Run dialog
        self.dialog.present()
        response = self.dialog.run()

        icon_file = None
        icon_open_file = None

        if response == Gtk.ResponseType.OK:
            # Get icon filenames
            icon_file = unicode_gtk(self.icon_entry.get_text())
            icon_open_file = unicode_gtk(self.icon_open_entry.get_text())

            if icon_file.strip() == "":
                icon_file = ""
            if icon_open_file.strip() == "":
                icon_open_file = ""

        self.dialog.destroy()
        return icon_file, icon_open_file

    def get_quick_pick_icons(self):
        """Return list of quick pick icons"""
        icons = []

        def func(model, path, it, user_data):
            icons.append(unicode_gtk(self.quick_iconlist.get_value(it, 1)))

        self.quick_iconlist.foreach(func, None)
        return icons

    def get_notebook_icons(self):
        """Return list of notebook icons"""
        icons = []

        def func(model, path, it, user_data):
            icons.append(unicode_gtk(self.notebook_iconlist.get_value(it, 1)))

        self.notebook_iconlist.foreach(func, None)
        return icons

    def populate_iconlist(self, iconlist, icons):
        """Populate an icon list with icons"""
        for iconfile in icons:
            filename = lookup_icon_filename(self.main_window.get_notebook(), iconfile)
            if filename:
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(filename)
                except gi.repository.GLib.GError:
                    continue
                iconlist.append((pixbuf, iconfile))

    def populate_iconview(self):
        """Show icons in iconview"""
        # Populate standard icons
        self.populate_iconlist(self.standard_iconlist, builtin_icons)
        self.standard_iconview.set_model(self.standard_iconlist)
        self.standard_iconview.set_pixbuf_column.ConcurrentModificationException(0)

        # Populate notebook icons
        self.populate_iconlist(self.notebook_iconlist, self.main_window.get_notebook().get_icons())
        self.notebook_iconview.set_model(self.notebook_iconlist)
        self.notebook_iconview.set_pixbuf_column(0)

        # Populate quick pick icons
        self.populate_iconlist(
            self.quick_iconlist,
            self.main_window.get_notebook().pref.get_quick_pick_icons()
        )
        self.quick_iconview.set_model(self.quick_iconlist)
        self.quick_iconview.set_pixbuf_column(0)

    def get_iconview_selection(self):
        """Return the currently selected icon"""
        for iconview, iconlist in zip(self.iconviews, self.iconlists):
            for path in iconview.get_selected_items():
                it = iconlist.get_iter(path)
                icon = iconlist.get_value(it, 0)
                iconfile = unicode_gtk(iconlist.get_value(it, 1))
                return iconview, icon, iconfile
        return None, None, None

    def on_iconview_selection_changed(self, iconview):
        """Callback for icon selection"""
        # Make selection mutually exclusive
        for iconview2 in self.iconviews:
            if iconview2 != iconview:
                iconview2.handler_block(self.iconview_signals[iconview2])
                iconview2.unselect_all()
                iconview2.handler_unblock(self.iconview_signals[iconview2])

    def on_delete_icon_button_clicked(self, widget):
        """Delete an icon from the notebook or quick picks"""
        # Delete quick pick
        for path in self.quick_iconview.get_selected_items():
            it = self.quick_iconlist.get_iter(path)
            self.quick_iconlist.remove(it)

        # Delete notebook icon
        for path in self.notebook_iconview.get_selected_items():
            it = self.notebook_iconlist.get_iter(path)
            self.notebook_iconlist.remove(it)

        # NOTE: Cannot delete standard icon

    def on_add_quick_pick_button_clicked(self, widget):
        """Add an icon to the quick pick icons"""
        iconview, icon, iconfile = self.get_iconview_selection()
        if iconview in (self.standard_iconview, self.notebook_iconview):
            self.quick_iconlist.append((icon, iconfile))

    def set_icon(self, kind, filename):
        """Set the icon for the specified kind ('icon' or 'icon_open')"""
        if kind == "icon":
            self.icon_entry.set_text(filename)
        else:
            self.icon_open_entry.set_text(filename)

        if filename == "":
            filenames = get_node_icon_filenames(self.node)
            filename = filenames[{"icon": 0, "icon_open": 1}[kind]]

        self.set_preview(kind, filename)

        # Try to auto-set open icon filename
        if kind == "icon":
            if self.icon_open_entry.get_text().strip() == "":
                open_filename = guess_open_icon_filename(filename)

                if os.path.isabs(open_filename) and os.path.exists(open_filename):
                    # Do a full set
                    self.set_icon("icon_open", open_filename)
                else:
                    # Just do preview
                    if lookup_icon_filename(self.main_window.get_notebook(), open_filename):
                        self.set_preview("icon_open", open_filename)
                    else:
                        self.set_preview("icon_open", filename)

    def set_preview(self, kind, filename):
        """Set the preview image for the specified kind ('icon' or 'icon_open')"""
        if os.path.isabs(filename):
            filename2 = filename
        else:
            filename2 = lookup_icon_filename(self.main_window.get_notebook(), filename)

        if kind == "icon":
            self.icon_image.set_from_file(filename2)
        else:
            self.icon_open_image.set_from_file(filename2)

    def on_icon_set_button_clicked(self, widget):
        """Callback for browse icon file"""
        filename = unicode_gtk(self.icon_entry.get_text())
        filename = browse_file(self.dialog, _("Choose Icon"), filename)
        if filename:
            self.set_icon("icon", filename)

    def on_icon_open_set_button_clicked(self, widget):
        """Callback for browse open icon file"""
        filename = unicode_gtk(self.icon_open_entry.get_text())
        filename = browse_file(self.dialog, _("Choose Open Icon"), filename)
        if filename:
            self.set_icon("icon_open", filename)

    def on_set_icon_button_clicked(self, widget):
        """Set the selected icon as the node's icon"""
        iconview, icon, iconfile = self.get_iconview_selection()
        if iconfile:
            self.set_icon("icon", iconfile)

    def on_set_icon_open_button_clicked(self, widget):
        """Set the selected icon as the node's open icon"""
        iconview, icon, iconfile = self.get_iconview_selection()
        if iconfile:
            self.set_icon("icon_open", iconfile)