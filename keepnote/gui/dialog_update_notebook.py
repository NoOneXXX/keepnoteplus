# Python 3 and PyGObject imports
import sys
import shutil
import gi
gi.require_version('Gtk', '3.0')  # Specify GTK 3.0
from gi.repository import Gtk

# KeepNote imports
import keepnote
from keepnote import unicode_gtk
from keepnote.gui import dialog_wait
from keepnote import tasklib
from keepnote.notebook import update
from keepnote import notebook as notebooklib
from keepnote.gui import get_resource, FileChooserDialog

_ = keepnote.translate

MESSAGE_TEXT = _("This notebook has format version %d and must be updated to "
                 "version %d before opening.")

class UpdateNoteBookDialog:
    """Dialog for updating a notebook to a newer format version"""

    def __init__(self, app, main_window):
        self.main_window = main_window
        self.app = app
        self.xml = None
        self.dialog = None
        self.text = None
        self.saved = None

    def show(self, notebook_filename, version=None, task=None):
        """Show the dialog to update the notebook"""
        # Load the Glade file
        self.xml = Gtk.Builder()
        self.xml.add_from_file(get_resource("rc", "keepnote.glade"))
        self.xml.set_translation_domain(keepnote.GETTEXT_DOMAIN)
        self.dialog = self.xml.get_object("update_notebook_dialog")
        self.dialog.connect("response", lambda d, r: self.dialog.response(r))
        self.dialog.set_transient_for(self.main_window)

        # Get widgets
        self.text = self.xml.get_object("update_message_label")
        self.saved = self.xml.get_object("save_backup_check")

        # Connect signals
        self.xml.connect_signals(self)

        # Determine the notebook version
        if version is None:
            version = notebooklib.get_notebook_version(notebook_filename)

        # Set the message text
        self.text.set_text(MESSAGE_TEXT % (version, notebooklib.NOTEBOOK_FORMAT_VERSION))

        # Run the dialog
        ret = False
        response = self.dialog.run()

        if response == Gtk.ResponseType.OK:
            # Do backup if selected
            if self.saved.get_active():
                if not self.backup(notebook_filename):
                    self.dialog.destroy()
                    return False

            self.dialog.destroy()

            # Perform the update
            def func(task):
                update.update_notebook(notebook_filename, notebooklib.NOTEBOOK_FORMAT_VERSION)

            # Create a new task if none provided
            task = tasklib.Task(func)
            dialog2 = dialog_wait.WaitDialog(self.main_window)
            dialog2.show(_("Updating Notebook"), _("Updating notebook..."), task, cancel=False)

            # Check the result of the update
            ret = not task.aborted()
            ty, err, tb = task.exc_info()
            if err:
                self.main_window.error(_("Error while updating."), err, tb)
                ret = False
        else:
            self.dialog.destroy()

        # Show success message if update was successful
        if ret:
            self.app.message(
                _("Notebook updated successfully"),
                _("Notebook Update Complete"),
                self.main_window
            )

        return ret

    def backup(self, notebook_filename):
        """Backup the notebook before updating"""
        dialog = FileChooserDialog(
            _("Choose Backup Notebook Name"),
            self.main_window,
            action=Gtk.FileChooserAction.SAVE,
            buttons=(
                _("Cancel"), Gtk.ResponseType.CANCEL,
                _("Backup"), Gtk.ResponseType.OK
            ),
            app=self.app,
            persistent_path="new_notebook_path"
        )

        response = dialog.run()
        new_filename = dialog.get_filename()
        dialog.destroy()

        if response == Gtk.ResponseType.OK and new_filename:
            new_filename = unicode_gtk(new_filename)

            def func(task):
                try:
                    shutil.copytree(notebook_filename, new_filename)
                except Exception as e:
                    print(e, file=sys.stderr)
                    print(f"'{notebook_filename}' '{new_filename}'", file=sys.stderr)
                    raise

            task = tasklib.Task(func)
            dialog2 = dialog_wait.WaitDialog(self.dialog)
            dialog2.show(
                _("Backing Up Notebook"),
                _("Backing up old notebook..."),
                task,
                cancel=False
            )

            # Handle errors
            if task.aborted():
                ty, err, tb = task.exc_info()
                if err:
                    self.main_window.error(_("Error occurred during backup."), err, tb)
                else:
                    self.main_window.error(_("Backup canceled."))
                return False

        return True