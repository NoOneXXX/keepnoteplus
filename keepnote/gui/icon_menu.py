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

        # Default icon menu item
        self.default_icon = Gtk.MenuItem.new_with_label("_Default Icon")
        self.default_icon.connect("activate", lambda w: self.emit("set-icon", ""))

        # New icon menu item
        self.new_icon = Gtk.MenuItem.new_with_label("_More Icons...")

        self.width = 4
        self.posi = 0
        self.posj = 0

        self.setup_menu()

    def clear(self):
        """Clear the menu"""
        for item in self.get_children():
            self.remove(item)
        self.posi = 0
        self.posj = 0

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

        if self._notebook is None:
            for iconfile in default_menu_icons:
                self.add_icon(iconfile)
        else:
            for iconfile in self._notebook.pref.get_quick_pick_icons():
                self.add_icon(iconfile)

        # Separator
        item = Gtk.SeparatorMenuItem()
        self.append(item)

        # Default icon
        self.append(self.default_icon)

        # New icon
        self.append(self.new_icon)

    def append_grid(self, item):
        """Attach item in a grid layout"""
        # Note: attach() is not available in GTK 4 for Gtk.Menu.
        # We will simulate the grid layout by using a different approach if needed.
        # For now, we will append items directly and note the limitation.
        print("Warning: append_grid is not fully supported in GTK 4 (Gtk.Menu.attach is deprecated)")
        self.append(item)

    def append(self, item):
        """Append item to menu, resetting grid position if needed"""
        if self.posj > 0:
            self.posi += 1
            self.posj = 0
        super().append(item)

    def add_icon(self, iconfile):
        """Add an icon to the menu"""
        child = Gtk.MenuItem()
        # Remove default label if it exists
        default_child = child.get_child()
        if default_child is not None:
            child.remove(default_child)
        img = Gtk.Image()
        iconfile2 = lookup_icon_filename(self._notebook, iconfile)
        img.set_from_file(iconfile2)
        child.set_child(img)  # Changed from add to set_child
        child.connect("activate", lambda w: self.emit("set-icon", iconfile))
        self.append_grid(child)

# Note: GObject.signal_new is not needed in GTK 4 for custom signals.
# We assume the signal "set-icon" is handled by KeepNote's custom signal system.
# If needed, this can be reimplemented using a custom GObject subclass with a signal.

# Register the custom signal for IconMenu
GObject.type_register(IconMenu)
GObject.signal_new("set-icon", IconMenu, GObject.SignalFlags.RUN_LAST,
                   None, (str,))