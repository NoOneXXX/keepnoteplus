from gi import require_version
require_version('Gtk', '3.0')

from gi.repository import Gtk

window = Gtk.Window(title="你好窗口!!!")
window.connect("destroy", Gtk.main_quit)
window.show_all()
Gtk.main()
