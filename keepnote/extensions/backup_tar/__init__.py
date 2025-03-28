"""
    KeepNote Extension 
    backup_tar

    Tar file notebook backup
"""

import gettext
import os
import re
import shutil
import sys
import time

import keepnote
from keepnote import unicode_gtk
from keepnote.notebook import NoteBookError, get_unique_filename
from keepnote import notebook as notebooklib
from keepnote import tasklib
from keepnote import tarfile
from keepnote.gui import extension

# GTK3 imports
from gi import require_version
require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject, Gdk

class Extension(extension.Extension):

    def __init__(self, app):
        """Initialize extension"""
        extension.Extension.__init__(self, app)
        self.app = app

    def get_depends(self):
        return [("keepnote", ">=", (0, 7, 1))]

    def on_add_ui(self, window):
        """Initialize extension for a particular window"""
        self.add_action(window, "Backup Notebook", "_Backup Notebook...",
                        lambda w: self.on_archive_notebook(window, window.get_notebook()))
        self.add_action(window, "Restore Notebook", "R_estore Notebook...",
                        lambda w: self.on_restore_notebook(window))

        # Access the menu bar by traversing the window's children
        menu_bar = None
        for child in window.get_children():
            if isinstance(child, Gtk.MenuBar):
                menu_bar = child
                break

        if menu_bar:
            file_menu = None
            for item in menu_bar.get_children():
                if item.get_label() == "_File":
                    file_menu = item
                    break

            if file_menu:
                extensions_menu = None
                for item in file_menu.get_submenu().get_children():
                    if item.get_label() == "Extensions":
                        extensions_menu = item.get_submenu()
                        break
                if not extensions_menu:
                    extensions_menu = Gtk.Menu()
                    extensions_item = Gtk.MenuItem(label="Extensions")
                    extensions_item.set_submenu(extensions_menu)
                    file_menu.get_submenu().append(extensions_item)

                backup_item = Gtk.MenuItem(label="_Backup Notebook...")
                backup_item.connect("activate", lambda w: self.on_archive_notebook(window, window.get_notebook()))
                restore_item = Gtk.MenuItem(label="R_estore Notebook...")
                restore_item.connect("activate", lambda w: self.on_restore_notebook(window))
                extensions_menu.append(backup_item)
                extensions_menu.append(restore_item)
                extensions_menu.show_all()

    def on_archive_notebook(self, window, notebook):
        """Callback for archiving a notebook"""
        if notebook is None:
            return

        dialog = Gtk.FileChooserDialog(
            title="Backup Notebook",
            parent=window,
            action=Gtk.FileChooserAction.SAVE,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                     "Backup", Gtk.ResponseType.OK)
        )
        dialog.set_transient_for(window)
        path = self.app.get_default_path("archive_notebook_path")
        if os.path.exists(path):
            filename = notebooklib.get_unique_filename(
                path,
                os.path.basename(notebook.get_path()) + time.strftime("-%Y-%m-%d"), ".tar.gz", "."
            )
        else:
            filename = os.path.basename(notebook.get_path()) + time.strftime("-%Y-%m-%d") + ".tar.gz"

        dialog.set_current_name(os.path.basename(filename))

        file_filter = Gtk.FileFilter()
        file_filter.add_pattern("*.tar.gz")
        file_filter.set_name("Archives (*.tar.gz)")
        dialog.add_filter(file_filter)

        file_filter = Gtk.FileFilter()
        file_filter.add_pattern("*")
        file_filter.set_name("All files (*.*)")
        dialog.add_filter(file_filter)

        response = dialog.run()

        if response == Gtk.ResponseType.OK and dialog.get_filename():
            filename = unicode_gtk(dialog.get_filename())
            dialog.destroy()

            if "." not in filename:
                filename += ".tar.gz"

            window.set_status("Archiving...")
            return self.archive_notebook(notebook, filename, window)
        elif response == Gtk.ResponseType.CANCEL:
            dialog.destroy()
            return False

    def on_restore_notebook(self, window):
        """Callback for restoring a notebook from an archive"""
        dialog = Gtk.FileChooserDialog(
            title="Choose Archive To Restore",
            parent=window,
            action=Gtk.FileChooserAction.OPEN,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                     "Restore", Gtk.ResponseType.OK)
        )
        dialog.set_transient_for(window)

        file_filter = Gtk.FileFilter()
        file_filter.add_pattern("*.tar.gz")
        file_filter.set_name("Archive (*.tar.gz)")
        dialog.add_filter(file_filter)

        file_filter = Gtk.FileFilter()
        file_filter.add_pattern("*")
        file_filter.set_name("All files (*.*)")
        dialog.add_filter(file_filter)

        response = dialog.run()

        if response == Gtk.ResponseType.OK and dialog.get_filename():
            archive_filename = unicode_gtk(dialog.get_filename())
            dialog.destroy()
        elif response == Gtk.ResponseType.CANCEL:
            dialog.destroy()
            return

        # Choose new notebook name
        dialog = Gtk.FileChooserDialog(
            title="Choose New Notebook Name",
            parent=window,
            action=Gtk.FileChooserAction.SAVE,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                     "New", Gtk.ResponseType.OK)
        )
        dialog.set_transient_for(window)

        file_filter = Gtk.FileFilter()
        file_filter.add_pattern("*.nbk")
        file_filter.set_name("Notebook (*.nbk)")
        dialog.add_filter(file_filter)

        file_filter = Gtk.FileFilter()
        file_filter.add_pattern("*.tar.gz")
        file_filter.set_name("Archives (*.tar.gz)")
        dialog.add_filter(file_filter)

        file_filter = Gtk.FileFilter()
        file_filter.add_pattern("*")
        file_filter.set_name("All files (*.*)")
        dialog.add_filter(file_filter)

        response = dialog.run()

        if response == Gtk.ResponseType.OK and dialog.get_filename():
            notebook_filename = unicode_gtk(dialog.get_filename())
            dialog.destroy()

            window.set_status("Restoring...")
            self.restore_notebook(archive_filename, notebook_filename, window)
        elif response == Gtk.ResponseType.CANCEL:
            dialog.destroy()

    def archive_notebook(self, notebook, filename, window=None):
        """Archive a notebook"""
        if notebook is None:
            return

        task = tasklib.Task(lambda task: archive_notebook(notebook, filename, task))

        if window:
            window.wait_dialog("Creating archive '%s'..." % os.path.basename(filename),
                               "Beginning archive...", task)

            try:
                ty, error, tracebk = task.exc_info()
                if error:
                    raise error
                window.set_status("Notebook archived")
                return True
            except NoteBookError as e:
                window.set_status("")
                window.error("Error while archiving notebook:\n%s" % e.msg, e, tracebk)
                return False
            except Exception as e:
                window.set_status("")
                window.error("unknown error", e, tracebk)
                return False
        else:
            archive_notebook(notebook, filename, None)

    def restore_notebook(self, archive_filename, notebook_filename, window=None):
        """Restore notebook"""
        if window:
            window.close_notebook()
            task = tasklib.Task(lambda task: restore_notebook(archive_filename, notebook_filename, True, task))

            window.wait_dialog("Restoring notebook from '%s'..." % os.path.basename(archive_filename),
                               "Opening archive...", task)

            try:
                ty, error, tracebk = task.exc_info()
                if error:
                    raise error
                window.set_status("Notebook restored")
            except NoteBookError as e:
                window.set_status("")
                window.error("Error restoring notebook:\n%s" % e.msg, e, tracebk)
                return
            except Exception as e:
                window.set_status("")
                window.error("unknown error", e, tracebk)
                return

            window.open_notebook(notebook_filename)
        else:
            restore_notebook(archive_filename, notebook_filename, True, None)

# The remaining functions (truncate_filename, archive_notebook, restore_notebook, archive_notebook_zip)
# remain largely unchanged as they don’t directly interact with GTK.
# They are included here for completeness:

def truncate_filename(filename, maxsize=100):
    if len(filename) > maxsize:
        filename = "..." + filename[-(maxsize-3):]
    return filename

def archive_notebook(notebook, filename, task=None):
    if task is None:
        task = tasklib.Task()

    if os.path.exists(filename):
        raise NoteBookError("File '%s' already exists" % filename)

    try:
        notebook.save()
    except Exception as e:
        raise NoteBookError("Could not save notebook before archiving", e)

    archive = tarfile.open(filename, "w:gz", format=tarfile.PAX_FORMAT)
    path = notebook.get_path()

    nfiles = 0
    for root, dirs, files in os.walk(path):
        nfiles += len(files)

    task.set_message(("text", "Archiving %d files..." % nfiles))

    nfiles2 = [0]
    def walk(path, arcname):
        archive.add(path, arcname, False)
        if os.path.isfile(path):
            nfiles2[0] += 1
            if task:
                task.set_message(("detail", truncate_filename(path)))
                task.set_percent(nfiles2[0] / float(nfiles))

        if os.path.isdir(path):
            for f in os.listdir(path):
                if task.aborted():
                    archive.close()
                    os.remove(filename)
                    raise NoteBookError("Backup canceled")
                if not os.path.islink(f):
                    walk(os.path.join(path, f), os.path.join(arcname, f))

    walk(path, os.path.basename(path))
    task.set_message(("text", "Closing archive..."))
    task.set_message(("detail", ""))
    archive.close()
    if task:
        task.finish()

def restore_notebook(filename, path, rename, task=None):
    if task is None:
        task = tasklib.Task()

    if path == "":
        raise NoteBookError("Must specify a path for restoring notebook")

    path = re.sub("/+$", "", path)
    tar = tarfile.open(filename, "r:gz", format=tarfile.PAX_FORMAT)

    if rename:
        if not os.path.exists(path):
            tmppath = get_unique_filename(os.path.dirname(path), os.path.basename(path + "-tmp"))
        else:
            raise NoteBookError("Notebook path already exists")

        try:
            members = list(tar.getmembers())
            if task:
                task.set_message(("text", "Restoring %d files..." % len(members)))

            for i, member in enumerate(members):
                if 'path' in member.pax_headers:
                    member.name = member.pax_headers['path']
                if task:
                    if task.aborted():
                        raise NoteBookError("Restore canceled")
                    task.set_message(("detail", truncate_filename(member.name)))
                    task.set_percent(i / float(len(members)))
                tar.extract(member, tmppath)

            files = os.listdir(tmppath)
            extracted_path = os.path.join(tmppath, files[0])
            if task:
                task.set_message(("text", "Finishing restore..."))
                shutil.move(extracted_path, path)
                os.rmdir(tmppath)

        except NoteBookError as e:
            raise e
        except Exception as e:
            raise NoteBookError("File writing error while extracting notebook", e)
    else:
        try:
            if task:
                task.set_message(("text", "Restoring archive..."))
            tar.extractall(path)
        except Exception as e:
            raise NoteBookError("File writing error while extracting notebook", e)

    task.finish()

# Note: archive_notebook_zip is omitted here as it’s not used in the main flow, but it would require
# similar logic updates if adapted for GTK3 usage.
def on_archive_notebook(self, window, notebook):
    """Callback for archiving a notebook"""
    if notebook is None:
        return

    dialog = Gtk.FileChooserDialog(
        title="Backup Notebook",
        parent=window,
        action=Gtk.FileChooserAction.SAVE,
        buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                 "Backup", Gtk.ResponseType.OK)
    )
    dialog.set_transient_for(window)
    path = self.app.get_default_path("archive_notebook_path")
    if os.path.exists(path):
        filename = notebooklib.get_unique_filename(
            path,
            os.path.basename(notebook.get_path()) + time.strftime("-%Y-%m-%d"), ".zip", "."
        )
    else:
        filename = os.path.basename(notebook.get_path()) + time.strftime("-%Y-%m-%d") + ".zip"

    dialog.set_current_name(os.path.basename(filename))

    # Add filters for both tar.gz and zip
    tar_filter = Gtk.FileFilter()
    tar_filter.add_pattern("*.tar.gz")
    tar_filter.set_name("Tar Archives (*.tar.gz)")
    dialog.add_filter(tar_filter)

    zip_filter = Gtk.FileFilter()
    zip_filter.add_pattern("*.zip")
    zip_filter.set_name("ZIP Archives (*.zip)")
    dialog.add_filter(zip_filter)
    dialog.set_filter(zip_filter)  # Default to ZIP

    all_filter = Gtk.FileFilter()
    all_filter.add_pattern("*")
    all_filter.set_name("All files (*.*)")
    dialog.add_filter(all_filter)

    response = dialog.run()

    if response == Gtk.ResponseType.OK and dialog.get_filename():
        filename = unicode_gtk(dialog.get_filename())
        dialog.destroy()

        # Determine archive type based on extension
        if filename.endswith(".tar.gz"):
            if "." not in filename[-7:]:
                filename += ".tar.gz"
            window.set_status("Archiving to tar.gz...")
            return self.archive_notebook(notebook, filename, window)
        elif filename.endswith(".zip"):
            if "." not in filename[-4:]:
                filename += ".zip"
            window.set_status("Archiving to ZIP...")
            return self.archive_notebook_zip(notebook, filename, window)
        else:
            window.set_status("")
            window.error("Please select a valid archive format (.tar.gz or .zip)")
            return False
    elif response == Gtk.ResponseType.CANCEL:
        dialog.destroy()
        return False


def archive_notebook_zip(self, notebook, filename, window=None):
    """Wrapper for archive_notebook_zip function"""
    if notebook is None:
        return

    task = tasklib.Task(lambda task: archive_notebook_zip(notebook, filename, task))

    if window:
        window.wait_dialog("Creating ZIP archive '%s'..." % os.path.basename(filename),
                           "Beginning archive...", task)

        try:
            ty, error, tracebk = task.exc_info()
            if error:
                raise error
            window.set_status("Notebook archived as ZIP")
            return True
        except NoteBookError as e:
            window.set_status("")
            window.error("Error while archiving notebook:\n%s" % e.msg, e, tracebk)
            return False
        except Exception as e:
            window.set_status("")
            window.error("Unknown error", e, tracebk)
            return False
    else:
        archive_notebook_zip(notebook, filename, None)