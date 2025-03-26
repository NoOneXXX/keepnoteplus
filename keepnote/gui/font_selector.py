# Python 3 and PyGObject imports
import gi
gi.require_version('Gtk', '3.0')  # Specify GTK 3.0
from gi.repository import Gtk, Pango

class FontSelector(Gtk.ComboBox):
    """ComboBox for selecting font families"""

    def __init__(self):
        super().__init__()

        # Create a ListStore to hold font family names (strings)
        self._list = Gtk.ListStore(str)
        self.set_model(self._list)

        # Get the list of font families from Pango context
        context = self.get_pango_context()
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

    def get_pango_context(self):
        """Get the Pango context for the widget"""
        # In GTK 3, we need to get the Pango context from the widget's style context
        # Since ComboBox doesn't directly provide a Pango context, we create a temporary one
        return self.get_pango_context() if hasattr(self, 'get_pango_context') else Pango.Context()