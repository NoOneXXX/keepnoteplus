#!/usr/bin/env python3
import json
# Python imports
import sys
print("✅ PYTHONPATH = ", sys.path)

import sys
import os
from os.path import basename, dirname, realpath, join, isdir
import time
import optparse
import threading
import traceback
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, Gtk

# =============================================================================
# KeepNote import

"""
Three ways to run KeepNote

bin_path = os.path.dirname(sys.argv[0])

(1) directly from source dir

    pkgdir = bin_path + "../keepnote.py"
    basedir = pkgdir
    sys.path.append(pkgdir)

    src/bin/keepnote.py
    src/keepnote.py/__init__.py
    src/keepnote.py/images
    src/keepnote.py/rc

(2) from installation location by setup.py 

    pkgdir = keepnote.py.get_basedir()
    basedir = pkgdir

    prefix/bin/keepnote.py
    prefix/lib/python-XXX/site-packages/keepnote.py/__init__.py
    prefix/lib/python-XXX/site-packages/keepnote.py/images
    prefix/lib/python-XXX/site-packages/keepnote.py/rc

(3) windows py2exe dir

    pkgdir = bin_path
    basedir = bin_path

    dir/keepnote.py.exe
    dir/library.zip
    dir/images
    dir/rc
"""

# Try to infer keepnote.py lib path from program path
pkgdir = dirname(dirname(realpath(sys.argv[0])))
if os.path.exists(join(pkgdir, "keepnote.py", "__init__.py")):
    sys.path.insert(0, pkgdir)
    import keepnote
    print(keepnote.__file__)
    # If this works, we know we are running from src_path (1)
    basedir = keepnote.get_basedir()

else:
    # Try to import from python path
    import keepnote

    # Successful import, therefore we are running with (2) or (3)

    # Attempt to use basedir for (2)
    basedir = keepnote.get_basedir()

    if not isdir(join(basedir, "images")):
        # We must be running (3)
        basedir = dirname(realpath(sys.argv[0]))

keepnote.set_basedir(basedir)

# =============================================================================
# KeepNote imports
import keepnote
from keepnote.commands import get_command_executor, CommandExecutor
from keepnote.teefile import TeeFileStream
import keepnote.compat.pref

_ = keepnote.translate

# =============================================================================
# Command-line options

o = optparse.OptionParser(usage="%prog [options] [NOTEBOOK]")
o.set_defaults(default_notebook=True)
o.add_option("-c", "--cmd", dest="cmd",
             action="store_true",
             help="treat remaining arguments as a command")
o.add_option("-l", "--list-cmd", dest="list_cmd",
             action="store_true",
             help="list available commands")
o.add_option("-i", "--info", dest="info",
             action="store_true",
             help="show runtime information")
o.add_option("--no-gui", dest="no_gui",
             action="store_true",
             help="run in non-gui mode")
o.add_option("-t", "--continue", dest="cont",
             action="store_true",
             help="continue to run after command execution")
o.add_option("", "--show-errors", dest="show_errors",
             action="store_true",
             help="show errors on console")
o.add_option("--no-show-errors", dest="show_errors",
             action="store_false",
             help="do not show errors on console")
o.add_option("--no-default", dest="default_notebook",
             action="store_false",
             help="do not open default notebook")
o.add_option("", "--newproc", dest="newproc",
             action="store_true",
             help="start KeepNote in a new process")
o.add_option("-p", "--port", dest="port",
             default=None,
             type="int",
             help="use a specified port for listening to commands")

# =============================================================================

def start_error_log(show_errors):
    """Starts KeepNote error log"""
    print("Starting error log...")
    keepnote.init_error_log()

    stream_list = []
    stderr_test_str = "\n"
    stderr_except_msg = ""

    if show_errors:
        try:
            sys.stderr.write(stderr_test_str)
        except IOError:
            formatted_msg = traceback.format_exc().splitlines()
            stderr_except_msg = ''.join(
                ['** stderr - unavailable for messages - ',
                 formatted_msg[-1], "\n"])
        else:
            stream_list.append(sys.stderr)

    try:
        errorlog = open(keepnote.get_user_error_log(), "a")
    except IOError:
        sys.exit(traceback.print_exc())
    else:
        stream_list.append(errorlog)

    sys.stderr = TeeFileStream(stream_list, autoflush=True)

    keepnote.print_error_log_header()
    keepnote.log_message(stderr_except_msg)


def parse_argv(argv):
    """Parse arguments"""
    options = o.get_default_values()
    # Force show_errors=True to debug the issue
    options.show_errors = True

    options, args = o.parse_args(argv[1:], options)
    return options, args


def setup_threading():
    """Initialize threading environment"""
    print("Setting up threading...")
    try:
        from gi.repository import GLib
    except ImportError as e:
        print(f"Failed to import gi.repository: {e}")
        raise

    if keepnote.get_platform() == "windows":
        def sleeper():
            time.sleep(0.001)
            return True  # Repeat timer

        GLib.timeout_add(400, sleeper)


def gui_exec(function, *args, **kwargs):
    """Execute a function in the GUI thread"""
    print("Executing in GUI thread...")
    from gi.repository import GLib

    sem = threading.Semaphore()
    sem.acquire()

    def idle_func():
        try:
            function(*args, **kwargs)
            return False
        finally:
            sem.release()

    GLib.idle_add(idle_func)
    sem.acquire()


def start_gui(argv, options, args, cmd_exec):
    print("Starting GUI...")
    try:
        import keepnote.gui
        from gi.repository import Gtk, Gio
    except ImportError as e:
        print(f"Failed to import GUI modules: {e}")
        raise

    setup_threading()

    app = keepnote.gui.KeepNote(basedir)
    gtk_app = Gtk.Application(application_id="org.keepnote.py")
    cmd_exec.set_app(app)

    def on_activate(gtk_app):
        need_gui = execute_command(app, argv)
        if not need_gui:
            gtk_app.quit()

    gtk_app.connect("activate", on_activate)
    gtk_app.run()


def start_non_gui(argv, options, args, cmd_exec):
    print("Starting in non-GUI mode...")
    app = keepnote.KeepNote(basedir)
    app.init()
    cmd_exec.set_app(app)
    execute_command(app, argv)


def execute_command(app, argv):
    """
    Execute commands given on command line

    Returns True if GUI event loop should be started
    """
    print("DEBUG: Starting execute_command...")
    options, args = parse_argv(argv)
    print(f"DEBUG: Options: {options}, Args: {args}")

    if options.list_cmd:
        print("DEBUG: Listing commands...")
        list_commands(app)
        return False

    if options.info:
        print("DEBUG: Printing runtime info...")
        keepnote.print_runtime_info(sys.stdout)
        return False

    if options.cmd:
        if len(args) == 0:
            raise Exception(_("Expected command"))
        print(f"DEBUG: Executing command: {args[0]}")
        command = app.get_command(args[0])
        if command:
            command.func(app, args)
        else:
            raise Exception(_("Unknown command '%s'") % args[0])

        if not options.no_gui:
            if len(app.get_windows()) == 0:
                print("DEBUG: Creating new window for command...")
                app.new_window()
            return True
        return False

    if options.no_gui:
        print("DEBUG: Running in non-GUI mode...")
        return False

    if len(args) > 0:
        for arg in args:
            if keepnote.notebook.is_node_url(arg):
                print(f"DEBUG: Going to node ID: {arg}")
                host, nodeid = keepnote.notebook.parse_node_url(arg)
                app.goto_nodeid(nodeid)
            elif keepnote.extension.is_extension_install_file(arg):
                print(f"DEBUG: Installing extension: {arg}")
                if len(app.get_windows()) == 0:
                    print("DEBUG: Creating new window for extension...")
                    app.new_window()
                app.install_extension(arg)
            else:
                print(f"DEBUG: Opening notebook: {arg}")
                if len(app.get_windows()) == 0:
                    print("DEBUG: Creating new window for notebook...")
                    app.new_window()
                app.get_current_window().open_notebook(arg)
    else:
        print("DEBUG: Creating default window...")
        win = app.new_window()

        # if len(app.get_windows()) == 1 and options.default_notebook:
        #     default_notebooks = app.pref.get("default_notebooks", default=[])
        #     notebook_loaded = False
        #     for path in reversed(default_notebooks):
        #         if os.path.exists(path):
        #             print(f"DEBUG: Loading default notebook: {path}")
        #             if win.open_notebook(path, open_here=False):
        #                 notebook_loaded = True
        #                 break
        #         else:
        #             print(f"DEBUG: Skipping invalid default notebook path: {path}")
        #
        #     if not notebook_loaded:
        #         print("DEBUG: No valid default notebooks found to load.")

    print("DEBUG: execute_command returning True")
    return True


def list_commands(app):
    """List available commands"""
    commands = app.get_commands()
    commands.sort(key=lambda x: x.name)

    print()
    print("available commands:")
    for command in commands:
        print(" " + command.name, end="")
        if command.metavar:
            print(" " + command.metavar, end="")
        if command.help:
            print(" -- " + command.help, end="")
        print()


# Setup sys.path to include KeepNote source if needed
BIN_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.abspath(os.path.join(BIN_DIR, "..", "keepnote.py"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import keepnote

def main(argv):
    # 修改：添加异常捕获和调试日志，确保程序退出原因被记录
    # 原因：原始 main 未捕获异常，可能导致窗口一闪即逝后无声退出
    print("DEBUG: Entering main...")
    try:
        app = keepnote.KeepNoteApplication()
        print("DEBUG: Running application...")
        exit_status = app.run(argv)
        print(f"DEBUG: Application exited with status: {exit_status}")
        sys.exit(exit_status)
    except Exception as e:
        print(f"ERROR: Exception in main: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main(sys.argv)

    def get_node(self, path):
        if hasattr(self, 'notebook'):
            return self.notebook.get_node_by_path(path)
        else:
            raise NotImplementedError("Notebook 尚未初始化，无法获取节点")