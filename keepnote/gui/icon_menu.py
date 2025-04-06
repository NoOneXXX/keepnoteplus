# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '4.0')  # Specify GTK 4.0
from gi.repository import Gtk, GObject

# KeepNote imports
import keepnote.gui.icons
from keepnote.gui.icons import lookup_icon_filename

# Default menu icons (excluding "-open" variants, limited to 20)
default_menu_icons = [x for x in keepnote.gui.icons.builtin_icons
                      if "-open." not in x][:20]

class IconMenu(Gtk.Popover):
    """Icon picker menu"""

    def __init__(self):
        super().__init__()

        self._notebook = None
        self.width = 4  # Number of icons per row
        self.grid = Gtk.Grid()  # Use a grid for icon layout
        self.grid.set_column_spacing(5)
        self.grid.set_row_spacing(5)

        # Set the grid as the popover's child
        self.set_child(self.grid)

        # Setup menu initially
        self.setup_menu()

    def clear(self):
        """Clear the menu"""
        child = self.grid.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.grid.remove(child)
            child = next_child

    def set_notebook(self, notebook):
        """Set notebook for menu"""
        if self._notebook is not None:
            # Disconnect from old notebook
            self._notebook.pref.quick_pick_icons_changed.remove(self.setup_menu)

        self._notebook = notebook

        if self._notebook is not None:
            # Listen to new notebook
            self._notebook.pref.quick_pick_icons_changed.add(self.setup_menu)

        self.setup_menu()

    def setup_menu(self):
        """Update menu to reflect notebook"""
        self.clear()

        # Add icons
        if self._notebook is None:
            icons = default_menu_icons
        else:
            icons = self._notebook.pref.get_quick_pick_icons()

        for i, iconfile in enumerate(icons):
            self.add_icon(iconfile, i)

        # Add separator (using a horizontal separator widget)
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.grid.attach(separator, 0, len(icons) // self.width + 1, self.width, 1)

        # Default icon button
        default_button = Gtk.Button(label="_Default Icon")
        default_button.connect("clicked", lambda w: self.emit("set-icon", ""))
        self.grid.attach(default_button, 0, len(icons) // self.width + 2, self.width, 1)

        # New icon button
        self.new_icon = Gtk.Button(label="_More Icons...")
        self.new_icon.connect("clicked", lambda w: self.emit("new-icon-activated"))  # Custom signal for new icon
        self.grid.attach(self.new_icon, 0, len(icons) // self.width + 3, self.width, 1)

    def add_icon(self, iconfile, index):
        """Add an icon to the menu"""
        button = Gtk.Button()
        iconfile2 = lookup_icon_filename(self._notebook, iconfile)

        if isinstance(iconfile2, Gtk.Widget):  # Paintable
            img = iconfile2
        else:  # string path fallback
            img = Gtk.Image.new_from_file(iconfile2)

        button.set_child(img)
        button.connect("clicked", lambda w: self.emit("set-icon", iconfile))

        # Calculate grid position
        row = index // self.width
        col = index % self.width
        self.grid.attach(button, col, row, 1, 1)


# Register the custom signals for IconMenu
GObject.type_register(IconMenu)
GObject.signal_new("set-icon", IconMenu, GObject.SignalFlags.RUN_LAST, None, (str,))
GObject.signal_new("new-icon-activated", IconMenu, GObject.SignalFlags.RUN_LAST, None, ())