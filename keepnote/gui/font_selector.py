# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '4.0')  # Specify GTK 4.0
from gi.repository import Gtk, Pango

class FontSelector(Gtk.ComboBox):
    """ComboBox for selecting font families"""

    def __init__(self):
        super().__init__()
        # Create a ListStore to hold font family names (strings)
        self._list = Gtk.ListStore.new([str])
        self.set_model(self._list)

        # Get the list of font families from Pango context
        context = self.get_pango_context_fixed()
        self._families = sorted(f.get_name() for f in context.list_families())
        self._lookup = [x.lower() for x in self._families]

        # Populate the ListStore with font family names
        for f in self._families:
            self._list.append([f])

        # Set up a cell renderer to display the font names
        cell = Gtk.CellRendererText()
        self.pack_start(cell, True)
        self.add_attribute(cell, 'text', 0)

        # Set the default font family to the system's default
        fam = context.get_font_description().get_family()
        self.set_family(fam)

    def set_family(self, family):
        """Set the active font family in the ComboBox"""
        try:
            index = self._lookup.index(family.lower())
            self.set_active(index)
        except ValueError:
            pass

    def get_family(self):
        """Get the currently selected font family"""
        active = self.get_active()
        if active != -1:  # Check if a valid item is selected
            return self._families[active]
        return None

    def get_pango_context_fixed(self):
        # Directly call Gtk.Widget's get_pango_context or create a new Pango.Context
        return super().get_pango_context()  # Call parent method

    # Original method retained but not used, to avoid conflicts
    def get_pango_context(self):
        return self.get_pango_context_fixed()  # Redirect to new method