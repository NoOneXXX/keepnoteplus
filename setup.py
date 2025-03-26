#!/usr/bin/env python3
#
# setup for KeepNote
#
# use the following command to install KeepNote:
#   pip install -e .
#
# =============================================================================

#
#  KeepNote
#  Copyright (c) 2008-2011 Matt Rasmussen
#  Author: Matt Rasmussen <rasmus@mit.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.
#

# =============================================================================
# Constants

import keepnote
KEEPNOTE_VERSION = keepnote.PROGRAM_VERSION_TEXT

# =============================================================================
# Python and setuptools imports
from setuptools import setup, find_packages
import itertools
import os

# =============================================================================
# Helper functions

def split_path(path):
    """Splits a path into all of its directories"""
    pathlist = []
    while path:
        path, tail = os.path.split(path)
        pathlist.append(tail)
    pathlist.reverse()
    return pathlist

def get_files(path, exclude=lambda f: False):
    """Recursively get files from a directory"""
    files = []

    if isinstance(exclude, list):
        exclude_list = exclude

        def exclude(filename):
            for ext in exclude_list:
                if filename.endswith(ext):
                    return True
            return False

    def walk(path):
        for f in os.listdir(path):
            filename = os.path.join(path, f)
            if exclude(filename):
                # Exclude certain files
                continue
            elif os.path.isdir(filename):
                # Recurse directories
                walk(filename)
            else:
                # Record all other files
                files.append(filename)
    walk(path)

    return files

def get_file_lookup(files, prefix_old, prefix_new, exclude=lambda f: False):
    """Create a dictionary lookup of files"""
    if files is None:
        files = get_files(prefix_old, exclude=exclude)

    prefix_old = split_path(prefix_old)
    prefix_new = split_path(prefix_new)
    lookup = {}

    for f in files:
        path = prefix_new + split_path(f)[len(prefix_old):]
        dirpath = os.path.join(*path[:-1])
        lookup.setdefault(dirpath, []).append(f)

    return lookup

def remove_package_dir(filename):
    i = filename.index("/")
    return filename[i+1:]

# =============================================================================
# Resource files/data

# Get resources
rc_files = get_file_lookup(None, "keepnote/rc", "rc")
image_files = get_file_lookup(None, "keepnote/images", "images")
efiles = get_file_lookup(None, "keepnote/extensions", "extensions",
                         exclude=[".pyc"])
freedesktop_files = [
    # Application icon
    ("share/icons/hicolor/48x48/apps",
     ["desktop/keepnote.png"]),

    # Desktop menu entry
    ("share/applications",
     ["desktop/keepnote.desktop"])
]

# Get data files
data_files = freedesktop_files
package_data = {'keepnote': []}
for v in itertools.chain(list(rc_files.values()),
                         list(image_files.values()),
                         list(efiles.values())):
    package_data['keepnote'].extend([remove_package_dir(f) for f in v])

# =============================================================================
# Setup

setup(
    name='keepnote',
    version=KEEPNOTE_VERSION,
    description='A cross-platform note taking application',
    long_description="""
        KeepNote is a cross-platform note taking application. Its features
        include:

        - rich text editing

          - bullet points
          - fonts/colors
          - hyperlinks
          - inline images

        - hierarchical organization for notes
        - full text search
        - integrated screenshot
        - spell checking (via gtkspell)
        - backup and restore
        - HTML export
    """,
    author='Matt Rasmussen',
    author_email='rasmus@alum.mit.edu',
    url='http://keepnote.org',
    download_url='http://keepnote.org/download/keepnote-%s.tar.gz' % KEEPNOTE_VERSION,

    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Environment :: Win32 (MS Windows)',
        'Environment :: X11 Applications',
        'Intended Audience :: Developers',
        'Intended Audience :: Education',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
    license="GPL",

    packages=[
        'keepnote',
        'keepnote.compat',
        'keepnote.gui',
        'keepnote.gui.richtext',
        'keepnote.notebook',
        'keepnote.notebook.connection',
        'keepnote.notebook.connection.fs',
        'keepnote.server',
        'keepnote.mswin'
    ],
    install_requires=[
        'pygobject>=3.50.0',
        'pywin32; platform_system=="Windows"',
    ],
    entry_points={
        'console_scripts': [
            'keepnote = keepnote.main:main',  # Adjust if script is moved
        ],
    },
    data_files=data_files,
    package_data=package_data,
)