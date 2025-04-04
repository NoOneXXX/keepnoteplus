"""
    KeepNote
    Extension system
"""



# import imp
import importlib.util
import sys
import os
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.elementtree.ElementTree as ET

import keepnote
from keepnote.listening import Listeners
from keepnote import plist


# globals
EXTENSION_EXT = ".kne"  # filename extension for KeepNote Extensions
INFO_FILE = "info.xml"


class DependencyError (Exception):
    """Exception for dependency error"""
    def __init__(self, ext, dep):
        self.ext = ext
        self.dep = dep

    def __str__(self):
        return "Extension '%s' has failed dependency %s" % \
            (self.ext.key, self.dep)


#=============================================================================
# extension functions


def init_user_extensions(pref_dir=None, home=None):
    """
    Ensure users extensions are initialized
    Install defaults if needed
    """
    if pref_dir is None:
        pref_dir = keepnote.get_user_pref_dir(home)

    extensions_dir = keepnote.get_user_extensions_dir(pref_dir)
    if not os.path.exists(extensions_dir):
        # make user extensions directory
        os.makedirs(extensions_dir, 0o700)

    extensions_data_dir = keepnote.get_user_extensions_data_dir(pref_dir)
    if not os.path.exists(extensions_data_dir):
        # make user extensions data directory
        os.makedirs(extensions_data_dir, 0o700)


def scan_extensions_dir(extensions_dir):
    """Iterate through the extensions in directory"""
    for filename in os.listdir(extensions_dir):
        path = os.path.join(extensions_dir, filename)
        if os.path.isdir(path):
            yield path


def import_extension(app, name, filename):
    if "notebook_http" in filename:
        print(f"Skipping extension 'notebook_http' due to missing dependencies")
        return None
    """Import an Extension using importlib"""
    filename2 = os.path.join(filename, "__init__.py")

    if not os.path.isfile(filename2):
        raise keepnote.KeepNotePreferenceError(f"Cannot load extension '{filename}' - __init__.py not found")

    try:
        # Load the module using importlib
        spec = importlib.util.spec_from_file_location(name, filename2)
        if spec is None or spec.loader is None:
            raise keepnote.KeepNotePreferenceError(f"Cannot load extension '{filename}' - spec could not be created")

        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)

        # Initialize the extension
        ext = mod.Extension(app)
        ext.key = name
        ext.read_info()

        return ext

    except Exception as e:
        raise keepnote.KeepNotePreferenceError(f"Cannot load extension '{filename}'", e)


def get_extension_info_file(filename):
    """Returns an info for an extension file path"""
    return os.path.join(filename, INFO_FILE)


def read_extension_info(filename):
    """Reads an extensions info"""
    tree = ET.ElementTree(file=get_extension_info_file(filename))

    # parse xml
    # check tree structure matches current version
    root = tree.getroot()
    if root.tag != "extension":
        raise keepnote.KeepNotePreferenceError("bad extension info format")

    p = root.find("dict")
    if p is None:
        raise keepnote.KeepNotePreferenceError("bad extension info format")

    return plist.load_etree(p)


def dependency_satisfied(ext, dep):
    """
    Checks whether an extension satisfies a dependency

    if ext is None, only the 'no' rel is checked
    """
    name, rel, version = dep

    if ext is None:
        return (rel == "no")

    if rel == ">":
        if not (ext.version > version):
            return False
    elif rel == ">=":
        if not (ext.version >= version):
            return False
    elif rel == "==":
        if not (ext.version == version):
            return False
    elif rel == "<=":
        if not (ext.version <= version):
            return False
    elif rel == "<":
        if not (ext.version < version):
            return False
    elif rel == "!=":
        if not (ext.version != version):
            return False

    return True


def parse_extension_version(version_str):
    return tuple(map(int, version_str.split(".")))


def format_extension_version(version):
    return ".".join(map(version, str))


def is_extension_install_file(filename):
    """
    Returns True if file is an extension install file
    """
    return filename.endswith(EXTENSION_EXT)


class Extension (object):
    """KeepNote Extension"""

    version = (1, 0)
    key = ""
    name = "untitled"
    author = "no author"
    website = "http://keepnote.org"
    description = "base extension"
    visible = True

    def __init__(self, app):
        self._app = app
        self._info = {}
        self._enabled = False
        self.type = "system"
        self.enabled = Listeners()

    def read_info(self):
        """Populate extension info"""
        path = self.get_base_dir(False)
        self._info = read_extension_info(path)

        # populate info
        self.version = parse_extension_version(self._info["version"])
        self.name = self._info["name"]
        self.author = self._info["author"]
        self.website = self._info["website"]
        self.description = self._info["description"]

    def get_info(self, key):
        return self._info.get(key, None)

    def enable(self, enable):
        """Enable/disable extension"""

        # check dependencies
        self.check_depends()

        # mark extension as enabled
        self._enabled = enable

        # notify listeners
        self.enabled.notify(enable)

        # return whether the extension is enabled
        return self._enabled

    def is_enabled(self):
        """Returns True if extension is enabled"""
        return self._enabled

    def check_depends(self):
        """Checks whether dependencies are met.  Throws exception on failure"""
        for dep in self.get_depends():
            if not self._app.dependency_satisfied(dep):
                raise DependencyError(self, dep)

    def get_depends(self):
        """
        Returns dependencies of extension

        Dependencies returned as a list of tuples (NAME, REL, EXTRA)

        NAME is a string identify an extension (or 'keepnote' itself).
        EXTRA is an object whose type depends on REL

        REL is a string representing a relation.  Options are:

          Version relations.  For each of these values for REL, the EXTRA
          field is interpreted as VERSION (see below):
            '>='   the version must be greater than or equal to
            '>'    the version must be greater than
            '=='   the version must be exactly equal to
            '<='   the version must less than or equal to
            '<'    the version must be less than
            '!='   the version must not be equal to

          Other relations.
            'no'   the extension must not exist.  EXTRA is None.

        Possible values for EXTRA:

          VERSION   This is a tuple representing a version number.
            ex: the tuple (0, 6, 1) represents version 0.6.1

        All dependencies must be met to enable an extension.  A extension
        name can appear more than once if several relations are required
        (such as specifying a range of valid version numbers).
        """
        return [("keepnote", ">=", (0, 6, 1))]

    #===============================
    # filesystem paths

    def get_base_dir(self, exist=True):
        """
        Returns the directory containing the extension's code

        If 'exists' is True, create directory if it does not exists.
        """
        path = self._app.get_extension_base_dir(self.key)
        if exist and not os.path.exists(path):
            os.makedirs(path)
        return path

    def get_data_dir(self, exist=True):
        """
        Returns the directory for storing data specific to this extension

        If 'exists' is True, create directory if it does not exists.
        """
        path = self._app.get_extension_data_dir(self.key)
        if exist and not os.path.exists(path):
            os.makedirs(path)
        return path

    def get_data_file(self, filename, exist=True):
        """
        Returns a full path to a file within the extension's data directory

        If 'exists' is True, create directory if it does not exists.
        """
        return os.path.join(self.get_data_dir(exist), filename)
