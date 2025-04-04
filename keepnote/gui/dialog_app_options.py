# Python 3 and PyGObject imports
import os
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GdkPixbuf
import keepnote
from keepnote import unicode_gtk
from keepnote import get_resource
from keepnote.gui.font_selector import FontSelector
import keepnote.gui
from keepnote.gui.icons import get_icon_filename
import keepnote.trans
import keepnote.gui.extension

_ = keepnote.translate

def on_browse(parent, title, filename, entry, action=Gtk.FileChooserAction.OPEN):
    dialog = Gtk.FileChooserDialog(
        title=title,
        parent=parent,
        action=action,
    )
    dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
    dialog.add_button(_("Open"), Gtk.ResponseType.OK)
    dialog.set_transient_for(parent)
    dialog.set_modal(True)

    if filename == "":
        filename = entry.get_text()
    if os.path.isabs(filename):
        dialog.set_filename(filename)

    if dialog.run() == Gtk.ResponseType.OK and dialog.get_filename():
        entry.set_text(dialog.get_filename())

    dialog.destroy()

class Section:
    def __init__(self, key, dialog, app, label="", icon=None):
        self.key = key
        self.dialog = dialog
        self.label = label
        self.icon = icon

        self.frame = Gtk.Frame(label=f"<b>{label}</b>")
        self.frame.get_label_widget().set_use_markup(True)

        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._box.set_margin_start(10)
        self._box.set_margin_end(10)
        self._box.set_margin_top(10)
        self.frame.set_child(self._box)

    def get_default_widget(self):
        return self._box

    def load_options(self, app):
        pass

    def save_options(self, app):
        pass

class GeneralSection(Section):
    def __init__(self, key, dialog, app, label="", icon="keepnote-16x16.png"):
        super().__init__(key, dialog, app, label, icon)
        self.notebook = None

        self.xml = Gtk.Builder()
        self.xml.add_from_file(get_resource("rc", "keepnote.glade"))
        self.xml.set_translation_domain(keepnote.GETTEXT_DOMAIN)
        self.frame = self.xml.get_object("general_frame")

        default_notebook_button = self.xml.get_object("default_notebook_button")
        default_notebook_button.connect("clicked", self.on_default_notebook_button_clicked)

        systray_check = self.xml.get_object("systray_check")
        systray_check.connect("toggled", self.on_systray_check_toggled)

        default_radio = self.xml.get_object("default_notebook_radio")
        default_radio.connect("toggled", self.on_default_notebook_radio_changed)

    def on_default_notebook_radio_changed(self, radio):
        default = self.xml.get_object("default_notebook_radio")
        default_tab = self.xml.get_object("default_notebook_table")
        default_tab.set_sensitive(default.get_active())

    def on_autosave_check_toggled(self, widget):
        self.xml.get_object("autosave_entry").set_sensitive(widget.get_active())
        self.xml.get_object("autosave_label").set_sensitive(widget.get_active())

    def on_default_notebook_button_clicked(self, widget):
        on_browse(self.dialog, _("Choose Default Notebook"), "", self.xml.get_object("default_notebook_entry"))

    def on_systray_check_toggled(self, widget):
        self.xml.get_object("skip_taskbar_check").set_sensitive(widget.get_active())
        self.xml.get_object("minimize_on_start_check").set_sensitive(widget.get_active())

    def load_options(self, app):
        win = app.get_current_window()
        if win:
            self.notebook = win.get_notebook()

        if app.pref.get("use_last_notebook", default=True):
            self.xml.get_object("last_notebook_radio").set_active(True)
        elif app.pref.get("default_notebooks", default=[]) == []:
            self.xml.get_object("no_default_notebook_radio").set_active(True)
        else:
            self.xml.get_object("default_notebook_radio").set_active(True)
            self.xml.get_object("default_notebook_entry").set_text(
                (app.pref.get("default_notebooks", default=[]) + [""])[0])

        self.xml.get_object("autosave_check").set_active(app.pref.get("autosave"))
        self.xml.get_object("autosave_entry").set_text(str(int(app.pref.get("autosave_time") / 1000)))
        self.xml.get_object("autosave_entry").set_sensitive(app.pref.get("autosave"))
        self.xml.get_object("autosave_label").set_sensitive(app.pref.get("autosave"))

        self.xml.get_object("systray_check").set_active(app.pref.get("window", "use_systray"))
        self.xml.get_object("skip_taskbar_check").set_active(app.pref.get("window", "skip_taskbar"))
        self.xml.get_object("skip_taskbar_check").set_sensitive(app.pref.get("window", "use_systray"))
        self.xml.get_object("minimize_on_start_check").set_active(app.pref.get("window", "minimize_on_start"))
        self.xml.get_object("minimize_on_start_check").set_sensitive(app.pref.get("window", "use_systray"))
        self.xml.get_object("window_keep_above_check").set_active(app.pref.get("window", "keep_above"))
        self.xml.get_object("window_stick_check").set_active(app.pref.get("window", "stick"))
        self.xml.get_object("use_fulltext_check").set_active(app.pref.get("use_fulltext_search", default=True))

    def save_options(self, app):
        if self.xml.get_object("last_notebook_radio").get_active():
            app.pref.set("use_last_notebook", True)
        elif self.xml.get_object("default_notebook_radio").get_active():
            app.pref.set("use_last_notebook", False)
            app.pref.set("default_notebooks", [unicode_gtk(self.xml.get_object("default_notebook_entry").get_text())])
        else:
            app.pref.set("use_last_notebook", False)
            app.pref.set("default_notebooks", [])

        app.pref.set("autosave", self.xml.get_object("autosave_check").get_active())
        try:
            app.pref.set("autosave_time", int(self.xml.get_object("autosave_entry").get_text()) * 1000)
        except:
            pass

        app.pref.set("window", "use_systray", self.xml.get_object("systray_check").get_active())
        app.pref.set("window", "skip_taskbar", self.xml.get_object("skip_taskbar_check").get_active())
        app.pref.set("window", "minimize_on_start", self.xml.get_object("minimize_on_start_check").get_active())
        app.pref.set("window", "keep_above", self.xml.get_object("window_keep_above_check").get_active())
        app.pref.set("window", "stick", self.xml.get_object("window_stick_check").get_active())
        app.pref.set("use_fulltext_search", self.xml.get_object("use_fulltext_check").get_active())

class LookAndFeelSection(Section):
    def __init__(self, key, dialog, app, label="", icon="lookandfeel.png"):
        super().__init__(key, dialog, app, label, icon)
        w = self.get_default_widget()
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

        def add_check(label):
            c = Gtk.CheckButton(label=label)
            v.append(c)
            return c

        self.treeview_lines_check = add_check(_("show lines in treeview"))
        self.listview_rules_check = add_check(_("use ruler hints in listview"))
        self.use_stock_icons_check = add_check(_("use GTK stock icons in toolbar"))
        self.use_minitoolbar = add_check(_("use minimal toolbar"))

        font_size = 10
        h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        l = Gtk.Label(label=_("Application Font Size:"))
        h.append(l)
        self.app_font_size = Gtk.SpinButton.new_with_range(2, 500, 1)
        self.app_font_size.set_value(font_size)
        h.append(self.app_font_size)
        v.append(h)

        h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        l = Gtk.Label(label=_("Listview Layout:"))
        h.append(l)
        c = Gtk.DropDown.new_from_strings(["Vertical", "Horizontal"])
        h.append(c)
        v.append(h)
        self.listview_layout = c

        w.append(v)

    def load_options(self, app):
        l = app.pref.get("look_and_feel")
        self.treeview_lines_check.set_active(l.get("treeview_lines"))
        self.listview_rules_check.set_active(l.get("listview_rules"))
        self.use_stock_icons_check.set_active(l.get("use_stock_icons"))
        self.use_minitoolbar.set_active(l.get("use_minitoolbar"))
        self.app_font_size.set_value(l.get("app_font_size"))

        if app.pref.get("viewers", "three_pane_viewer", "view_mode", default="") == "horizontal":
            self.listview_layout.set_selected(1)
        else:
            self.listview_layout.set_selected(0)

    def save_options(self, app):
        l = app.pref.get("look_and_feel")
        l["treeview_lines"] = self.treeview_lines_check.get_active()
        l["listview_rules"] = self.listview_rules_check.get_active()
        l["use_stock_icons"] = self.use_stock_icons_check.get_active()
        l["use_minitoolbar"] = self.use_minitoolbar.get_active()
        l["app_font_size"] = self.app_font_size.get_value()

        app.pref.set("viewers", "three_pane_viewer", "view_mode",
                     ["vertical", "horizontal"][self.listview_layout.get_selected()])

class LanguageSection(Section):
    def __init__(self, key, dialog, app, label="", icon=None):
        super().__init__(key, dialog, app, label, icon)
        w = self.get_default_widget()
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

        h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        l = Gtk.Label(label=_("Language:"))
        h.append(l)
        c = Gtk.DropDown.new_from_strings(["default"] + keepnote.trans.get_langs())
        h.append(c)
        v.append(h)
        self.language_box = c

        w.append(v)

    def load_options(self, app):
        lang = app.pref.get("language", default="")
        if lang == "":
            self.language_box.set_selected(0)
        else:
            for i, l in enumerate(["default"] + keepnote.trans.get_langs()):
                if lang == l:
                    self.language_box.set_selected(i)
                    break

    def save_options(self, app):
        if self.language_box.get_selected() > 0:
            app.pref.set("language", self.language_box.get_model().get_string(self.language_box.get_selected()))
        else:
            app.pref.set("language", "")

class HelperAppsSection(Section):
    def __init__(self, key, dialog, app, label="", icon=None):
        super().__init__(key, dialog, app, label, icon)
        self.entries = {}
        w = self.get_default_widget()
        self.table = Gtk.Grid()
        w.append(self.table)

        try:
            self.icon = keepnote.gui.get_pixbuf(get_icon_filename("system-run"), size=(15, 15))
        except:
            pass

    def load_options(self, app):
        for child in self.table.get_children():
            self.table.remove(child)
        apps = list(app.iter_external_apps())
        self.table.set_row_spacing(2)
        self.table.set_column_spacing(2)

        for i, app in enumerate(apps):
            key = app.key
            app_title = app.title
            prog = app.prog

            label = Gtk.Label(label=f"{app_title}:")
            label.set_halign(Gtk.Align.END)
            self.table.attach(label, 0, i, 1, 1)

            entry = Gtk.Entry()
            entry.set_text(prog)
            entry.set_width_chars(30)
            self.entries[key] = entry
            self.table.attach(entry, 1, i, 1, 1)

            button = Gtk.Button(label=_("Browse..."))
            button.set_icon_name("document-open")
            button.connect("clicked", lambda w, k=key, t=app_title: on_browse(self.dialog, _("Choose %s") % t, "", self.entries[k]))
            self.table.attach(button, 2, i, 1, 1)

    def save_options(self, app):
        apps = app.pref.get("external_apps", default=[])
        for app in apps:
            key = app.get("key", None)
            if key and key in self.entries:
                app["prog"] = unicode_gtk(self.entries[key].get_text())

class DatesSection(Section):
    def __init__(self, key, dialog, app, label="", icon=None):
        super().__init__(key, dialog, app, label, icon)
        self.xml = Gtk.Builder()
        try:
            glade_file = get_resource("rc", "keepnote.glade")
            print(f"Loading GLADE file for DatesSection: {glade_file}")
            self.xml.add_from_file(glade_file)
        except Exception as e:
            print(f"Failed to load GLADE file for DatesSection: {e}")
            self.frame = Gtk.Frame(label=f"<b>{label}</b>")
            self.frame.get_label_widget().set_use_markup(True)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            box.set_margin_start(10)
            box.set_margin_end(10)
            box.set_margin_top(10)
            box.append(Gtk.Label(label="DatesSection Placeholder"))
            self.frame.set_child(box)

        self.frame = self.xml.get_object("dates_frame") or self.frame

    def load_options(self, app):
        for name in ["same_day", "same_month", "same_year", "diff_year"]:
            self.xml.get_object(f"date_{name}_entry").set_text(app.pref.get("timestamp_formats", name))

    def save_options(self, app):
        for name in ["same_day", "same_month", "same_year", "diff_year"]:
            app.pref.set("timestamp_formats", name, unicode_gtk(self.xml.get_object(f"date_{name}_entry").get_text()))

class EditorSection(Section):
    def __init__(self, key, dialog, app, label="", icon=None):
        super().__init__(key, dialog, app, label, icon)
        w = self.get_default_widget()
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

        h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        l = Gtk.Label(label=_("Quote format:"))
        h.append(l)
        e = Gtk.Entry()
        e.set_width_chars(40)
        h.append(e)
        v.append(h)
        self.quote_format = e

        w.append(v)

    def load_options(self, app):
        try:
            quote_format = app.pref.get("editors", "general", "quote_format")
            self.quote_format.set_text(quote_format)
        except:
            pass

    def save_options(self, app):
        quote_format = self.quote_format.get_text()
        if quote_format:
            app.pref.set("editors", "general", "quote_format", quote_format)

class AllNoteBooksSection(Section):
    def __init__(self, key, dialog, app, label="", icon="folder.png"):
        super().__init__(key, dialog, app, label, icon)
        w = self.get_default_widget()
        l = Gtk.Label(label=_("This section contains options that are saved on a per notebook basis (e.g. notebook-specific font). A subsection will appear for each notebook that is currently opened."))
        l.set_wrap(True)
        w.append(l)

class NoteBookSection(Section):
    def __init__(self, key, dialog, app, notebook, label="", icon="folder.png"):
        super().__init__(key, dialog, app, label, icon)
        self.notebook = notebook

        self.notebook_xml = Gtk.Builder()
        self.notebook_xml.add_from_file(get_resource("rc", "keepnote.glade"))
        self.notebook_xml.set_translation_domain(keepnote.GETTEXT_DOMAIN)
        self.frame = self.notebook_xml.get_object("notebook_frame")

        notebook_font_spot = self.notebook_xml.get_object("notebook_font_spot")
        self.notebook_font_family = FontSelector()
        notebook_font_spot.append(self.notebook_font_family)

        self.notebook_font_size = self.notebook_xml.get_object("notebook_font_size")
        self.notebook_font_size.set_value(10)
        self.notebook_index_dir = self.notebook_xml.get_object("index_dir_entry")
        self.notebook_xml.get_object("index_dir_browse").connect("clicked",
            lambda w: on_browse(self.dialog, _("Choose alternative notebook index directory"), "", self.notebook_index_dir, action=Gtk.FileChooserAction.SELECT_FOLDER))

    def load_options(self, app):
        if self.notebook:
            font = self.notebook.pref.get("default_font", default=keepnote.gui.DEFAULT_FONT)
            family, mods, size = keepnote.gui.richtext.parse_font(font)
            self.notebook_font_family.set_family(family)
            self.notebook_font_size.set_value(size)
            self.notebook_index_dir.set_text(self.notebook.pref.get("index_dir", default="", type=str))

    def save_options(self, app):
        if self.notebook:
            pref = self.notebook.pref
            pref.set("default_font", f"{self.notebook_font_family.get_family()} {int(self.notebook_font_size.get_value())}")
            pref.set("index_dir", self.notebook_index_dir.get_text())

class ExtensionsSection(Section):
    def __init__(self, key, dialog, app, label="", icon=None):
        super().__init__(key, dialog, app, label, icon)
        self.app = app
        self.entries = {}
        self.frame = Gtk.Frame(label="<b>Extensions</b>")
        self.frame.get_label_widget().set_use_markup(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        self.frame.set_child(box)

        self.sw = Gtk.ScrolledWindow()
        self.sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        box.append(self.sw)

        self.extlist = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.sw.set_child(self.extlist)

        h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.install_button = Gtk.Button(label="Install new extension")
        self.install_button.connect("clicked", self._on_install)
        h.append(self.install_button)
        box.append(h)

        try:
            self.icon = keepnote.gui.get_pixbuf(get_icon_filename("list-add"), size=(15, 15))
        except:
            pass

    def load_options(self, app):
        for child in self.extlist.get_children():
            self.extlist.remove(child)

        def callback(ext):
            return lambda w: self._on_uninstall(ext.key)

        exts = list(app.get_imported_extensions())
        d = {"user": 0, "system": 1}
        exts.sort(key=lambda e: (d.get(e.type, 10), e.name))
        for ext in exts:
            if ext.visible:
                p = ExtensionWidget(app, ext)
                p.uninstall_button.connect("clicked", callback(ext))
                self.extlist.append(p)

        maxheight = 270
        w, h = self.extlist.get_preferred_size()
        self.sw.set_size_request(400, min(maxheight, h.height + 10))

    def save_options(self, app):
        app.pref.set("extension_info", "disabled", [widget.ext.key for widget in self.extlist.get_children() if not widget.enabled])
        for widget in self.extlist.get_children():
            if widget.enabled != widget.ext.is_enabled():
                try:
                    widget.ext.enable(widget.enabled)
                except:
                    keepnote.log_error()

    def _on_uninstall(self, ext):
        if self.app.uninstall_extension(ext):
            self.load_options(self.app)

    def _on_install(self, widget):
        dialog = Gtk.FileChooserDialog(
            title=_("Install New Extension"),
            parent=self.dialog,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("Open"), Gtk.ResponseType.OK)
        dialog.set_transient_for(self.dialog)
        dialog.set_modal(True)

        file_filter = Gtk.FileFilter()
        file_filter.add_pattern("*.kne")
        file_filter.set_name(_("KeepNote Extension (*.kne)"))
        dialog.add_filter(file_filter)

        file_filter = Gtk.FileFilter()
        file_filter.add_pattern("*")
        file_filter.set_name(_("All files (*.*)"))
        dialog.add_filter(file_filter)

        if dialog.run() == Gtk.ResponseType.OK and dialog.get_filename():
            self.app.install_extension(dialog.get_filename())
            self.load_options(self.app)

        dialog.destroy()

class ExtensionWidget(Gtk.Box):
    def __init__(self, app, ext):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.app = app
        self.enabled = ext.is_enabled()
        self.ext = ext

        frame = Gtk.Frame(label=f"<b>{ext.name}</b> ({ext.type}/{ext.key})")
        frame.get_label_widget().set_use_markup(True)
        self.append(frame)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        frame.set_child(box)

        l = Gtk.Label(label=ext.description)
        l.set_halign(Gtk.Align.START)
        l.set_wrap(True)
        box.append(l)

        h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.enable_check = Gtk.CheckButton(label=_("Enabled"))
        self.enable_check.set_active(self.enabled)
        self.enable_check.connect("toggled", lambda w: self._on_enabled(ext))
        h.append(self.enable_check)

        l = Gtk.Label(label="|")
        h.append(l)

        self.uninstall_button = Gtk.Button(label=_("Uninstall"))
        self.uninstall_button.set_sensitive(app.can_uninstall(ext))
        h.append(self.uninstall_button)

        box.append(h)

    def update(self):
        self.enable_check.set_active(self.ext.is_enabled())

    def _on_enabled(self, ext):
        self.enabled = self.enable_check.get_active()

class ApplicationOptionsDialog:
    def __init__(self, app):
        self.app = app
        self.parent = None
        self._sections = []

        self.xml = Gtk.Builder()
        glade_file = get_resource("rc", "keepnote.glade")
        print(f"Loading GLADE file: {glade_file}")
        try:
            self.xml.add_from_file(glade_file)
        except Exception as e:
            raise Exception(f"Failed to load keepnote.glade: {str(e)}")
        self.xml.set_translation_domain(keepnote.GETTEXT_DOMAIN)

        self.dialog = self.xml.get_object("app_options_dialog")
        if self.dialog is None:
            raise ValueError("Could not find 'app_options_dialog' in keepnote.glade")
        self.dialog.connect("close-request", self._on_close_request)

        self.tabs = self.xml.get_object("app_options_tabs")
        if self.tabs is None:
            raise ValueError("Could not find 'app_options_tabs' in keepnote.glade")

        cancel_button = self.xml.get_object("cancel_button")
        if cancel_button:
            cancel_button.connect("clicked", self.on_cancel_button_clicked)

        ok_button = self.xml.get_object("ok_button")
        if ok_button:
            ok_button.connect("clicked", self.on_ok_button_clicked)

        apply_button = self.xml.get_object("apply_button")
        if apply_button:
            apply_button.connect("clicked", self.on_apply_button_clicked)

        self.overview = self.xml.get_object("app_config_treeview")
        if self.overview is None:
            raise ValueError("Could not find 'app_config_treeview' in keepnote.glade")
        self.overview_store = Gtk.TreeStore(str, object, GdkPixbuf.Pixbuf)
        self.overview.set_model(self.overview_store)
        self.overview.connect("row-activated", self.on_overview_select)

        column = Gtk.TreeViewColumn()
        self.overview.append_column(column)
        cell_icon = Gtk.CellRendererPixbuf()
        cell_text = Gtk.CellRendererText()
        column.pack_start(cell_icon, True)
        column.add_attribute(cell_icon, "pixbuf", 2)
        column.pack_start(cell_text, True)
        column.add_attribute(cell_text, "text", 0)

        self.add_default_sections()

    def add_section(self, section, parent=None):
        if section.frame is None:
            print(f"Warning: Section '{section.key}' has no frame; skipping")
            return None

        size = (15, 15)
        if parent:
            path = self.get_section_path(parent)
            it = self.overview_store.get_iter(path)
        else:
            it = None

        self._sections.append(section)
        self.tabs.append_page(section.frame)
        section.frame.show()

        icon = section.icon
        if icon is None:
            icon = "note.png"
        pixbuf = keepnote.gui.get_resource_pixbuf(icon, size=size) if isinstance(icon, str) else icon

        it = self.overview_store.append(it, [section.label, section, pixbuf])
        path = self.overview_store.get_path(it)
        self.overview.expand_to_path(path)

        return section

    def add_default_sections(self):
        self.add_section(GeneralSection("general", self.dialog, self.app, keepnote.PROGRAM_NAME))
        self.add_section(LookAndFeelSection("look_and_feel", self.dialog, self.app, _("Look and Feel")), "general")
        self.add_section(LanguageSection("language", self.dialog, self.app, _("Language")), "general")
        self.add_section(DatesSection("date_and_time", self.dialog, self.app, _("Date and Time")), "general")
        self.add_section(EditorSection("editor", self.dialog, self.app, _("Editor")), "general")
        self.add_section(HelperAppsSection("helper_apps", self.dialog, self.app, _("Helper Applications")), "general")
        self.add_section(AllNoteBooksSection("notebooks", self.dialog, self.app, _("Notebook Options"), "folder.png"))
        self.add_section(ExtensionsSection("extensions", self.dialog, self.app, _("Extensions")))

    def load_options(self, app):
        for section in self._sections:
            section.load_options(app)

    def save_options(self, app):
        app.save_preferences()
        for section in self._sections:
            section.save_options(app)
        self.app.pref.changed.notify()
        for notebook in self.app.iter_notebooks():
            notebook.notify_change(False)
        app.save()

    def remove_section(self, key):
        section = self.get_section(key)
        if section:
            self.tabs.remove_page(self._sections.index(section))
            self._sections.remove(section)
        path = self.get_section_path(key)
        if path:
            self.overview_store.remove(self.overview_store.get_iter(path))

    def get_section(self, key):
        for section in self._sections:
            if section.key == key:
                return section
        return None

    def get_section_path(self, key):
        def walk(node):
            child = self.overview_store.iter_children(node)
            while child:
                row = self.overview_store[child]
                if row[1].key == key:
                    return row.path
                ret = walk(child)
                if ret:
                    return ret
                child = self.overview_store.iter_next(child)
            return None
        return walk(None)

    def on_overview_select(self, overview, path, column):
        if path:
            section = self.overview_store[path][1]
            self.tabs.set_current_page(self._sections.index(section))

    def on_cancel_button_clicked(self, widget):
        self.dialog.hide()

    def on_ok_button_clicked(self, widget):
        self.save_options(self.app)
        self.dialog.hide()

    def on_apply_button_clicked(self, widget):
        self.save_options(self.app)

    def _on_close_request(self, widget):
        self.dialog.hide()
        return True

    def show(self, parent):
        self.parent = parent
        self.dialog.set_transient_for(parent)
        self.load_options(self.app)
        self.dialog.show()

if __name__ == "__main__":
    class MockApp:
        def __init__(self):
            self.pref = keepnote.pref.AppPreferences()
        def get_current_window(self): return None
        def iter_notebooks(self): return []
        def save_preferences(self): pass
        def save(self): pass
        def iter_external_apps(self): return []
        def get_imported_extensions(self): return []
        def get_enabled_extensions(self): return []

    app = MockApp()
    dialog = ApplicationOptionsDialog(app)
    dialog.show(None)
    Gtk.main()