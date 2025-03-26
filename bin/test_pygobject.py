import os
print("Current PATH:", os.environ["PATH"])  # Debug PATH
import gi
gi.require_version('Gtk', '3.0')
try:
    from gi.repository import Gtk
    print("PyGObject and GTK are working!")
except ImportError as e:
    print(f"ImportError: {e}")
    raise