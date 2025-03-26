"""
    XmlObject

    This module allows concise definitions of XML file formats for python
    objects.
"""

#
#  KeepNote
#  Copyright (c) 2008-2009 Matt Rasmussen
#  Author: Matt Rasmussen <rasmus@alum.mit.edu>
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

# Python imports
import sys
import codecs
import builtins  # Explicitly import builtins to access set

# XML imports
import xml.parsers.expat
from xml.sax.saxutils import escape

# KeepNote imports
from keepnote import safefile


class XmlError(Exception):
    """Error for parsing XML"""
    pass


def bool2str(b):
    """Convert a bool into a string"""
    return str(int(b))


def str2bool(s):
    """Convert a string into a bool"""
    return bool(int(s))


def str_no_none(x):
    if x is None:
        return ""
    return x


class Tag:
    def __init__(self, name, get=None, set=None, attr=None, tags=None):
        if tags is None:
            tags = []
        self.name = name

        self._tag_list = list(tags)
        self._read_data = get
        self._write_data = set
        self._object = None
        self._data = []

        # Set read/write based on 'attr'
        if attr is not None:
            attr_name, attr_get, attr_set = attr

            if attr_get is None:
                self._read_data = lambda s, x: s.__setattr__(attr_name, x)
            else:
                self._read_data = lambda s, x: s.__setattr__(attr_name, attr_get(x))

            if attr_set is None:
                self._write_data = lambda s: str_no_none(s.__dict__[attr_name])
            else:
                self._write_data = lambda s: attr_set(s.__dict__[attr_name])

        # Init tag lookup
        self._tags = {}
        for tag in tags:
            self._tags[tag.name] = tag

        # Set of initialized tags, using builtins.set to avoid namespace issues
        self._init_tags = builtins.set()

    #===========================================
    # Reading

    def init(self):
        """Initialize the tag before its first use"""
        self._init_tags.clear()

    def set_object(self, obj):
        self._object = obj

    def new_tag(self, name):
        """Create new child tag"""
        tag = self._tags.get(name, None)
        if tag:
            # Initialize new tag
            tag.set_object(self._object)

            if tag not in self._init_tags:
                tag.init()
                self._init_tags.add(tag)
        return tag

    def start_tag(self):
        """Start tag callback"""
        self._data = []

    def queue_data(self, data):
        """Content data callback"""
        if self._read_data:
            self._data.append(data)

    def end_tag(self):
        """End tag callback"""
        # Read queued data if read function is supplied
        if self._read_data:
            data = "".join(self._data)
            self._data = []

            try:
                self._read_data(self._object, data)
            except Exception as e:
                raise XmlError(f"Error parsing tag '{self.name}': {str(e)}")

    def add(self, tag):
        """Add a tag child to this tag"""
        self._tag_list.append(tag)
        self._tags[tag.name] = tag

    #===================
    # Writing

    def write(self, obj, out):
        """Write tag to output stream"""
        # Write opening
        if self.name != "":
            out.write(f"<{self.name}>")

        if len(self._tags) > 0:
            out.write("\n")
            for child_tag in self._tag_list:
                child_tag.write(obj, out)
        elif self._write_data:
            text = self._write_data(obj)
            if not isinstance(text, str):
                raise XmlError(f"bad text ({self.name},{str(self._object)}): {str(type(text))}")
            out.write(escape(text))

        if self.name != "":
            out.write(f"</{self.name}>\n")


class TagMany(Tag):
    def __init__(self, name, iterfunc, get=None, set=None, before=None, after=None, tags=None):
        if tags is None:
            tags = []
        super().__init__(name, get=None, set=set, tags=tags)

        self._iterfunc = iterfunc
        self._read_item = get
        self._write_item = set
        self._beforefunc = before
        self._afterfunc = after
        self._index = 0

    #=============================
    # Reading

    def init(self):
        """Initialize the tag before its first use"""
        self._init_tags.clear()
        self._index = 0

    def new_tag(self, name):
        """Create new child tag"""
        tag = self._tags.get(name, None)
        if tag:
            # Initialize new tag
            tag.set_object((self._object, self._index))

            if tag not in self._init_tags:
                tag.init()
                self._init_tags.add(tag)
        return tag

    def start_tag(self):
        """Start tag callback"""
        self._data = []
        if self._beforefunc:
            self._beforefunc((self._object, self._index))

    def queue_data(self, data):
        """Content data callback"""
        if self._read_item:
            self._data.append(data)

    def end_tag(self):
        """End tag callback"""
        if self._read_item:
            data = "".join(self._data)
            self._data = []

            if self._read_item is not None:
                self._read_item((self._object, self._index), data)

        if self._afterfunc:
            self._afterfunc((self._object, self._index))
        self._index += 1

    #=====================
    # Writing

    def write(self, obj, out):
        # Write opening
        if len(self._tags) == 0:
            assert self._write_item is not None

            for i in self._iterfunc(obj):
                out.write(f"<{self.name}>{escape(self._write_item((obj, i)))}</{self.name}>\n")
        else:
            for i in self._iterfunc(obj):
                out.write(f"<{self.name}>\n")
                for child_tag in self._tag_list:
                    child_tag.write((obj, i), out)
                out.write(f"</{self.name}>\n")


class XmlObject:
    """Represents an object <--> XML document binding"""

    def __init__(self, *tags):
        self._object = None
        self._root_tag = Tag("", tags=tags)
        self._current_tags = [self._root_tag]

    def __start_element(self, name, attrs):
        """Start tag callback"""
        if len(self._current_tags) > 0:
            last_tag = self._current_tags[-1]
            if last_tag:
                new_tag = last_tag.new_tag(name)
                self._current_tags.append(new_tag)
                if new_tag:
                    new_tag.start_tag()

    def __end_element(self, name):
        """End tag callback"""
        if len(self._current_tags) > 0:
            last_tag = self._current_tags.pop()
            if last_tag:
                if last_tag.name == name:
                    last_tag.end_tag()
                else:
                    raise XmlError("Malformed XML")

    def __char_data(self, data):
        """Read character data and give it to current tag"""
        if len(self._current_tags) > 0:
            tag = self._current_tags[-1]
            if tag:
                tag.queue_data(data)

    def read(self, obj, filename):
        """Read XML from 'filename' and store data into object 'obj'"""
        if isinstance(filename, str):
            infile = open(filename, "r", encoding="utf-8")
        else:
            infile = filename
        self._object = obj
        self._root_tag.set_object(self._object)
        self._current_tags = [self._root_tag]
        self._root_tag.init()

        parser = xml.parsers.expat.ParserCreate()
        parser.StartElementHandler = self.__start_element
        parser.EndElementHandler = self.__end_element
        parser.CharacterDataHandler = self.__char_data

        try:
            parser.ParseFile(infile)
        except xml.parsers.expat.ExpatError as e:
            raise XmlError(f"Error reading file '{filename}': {str(e)}")

        if len(self._current_tags) > 1:
            print([x.name for x in self._current_tags])
            raise XmlError(f"Incomplete file '{filename}'")

        infile.close()

    def write(self, obj, filename):
        """Write object 'obj' to file 'filename'"""
        if isinstance(filename, str):
            out = safefile.open(filename, "w", codec="utf-8")
            need_close = True
        else:
            out = filename
            need_close = False

        out.write('<?xml version="1.0" encoding="UTF-8"?>')
        self._root_tag.write(obj, out)
        out.write("\n")
        if need_close:
            out.close()


if __name__ == "__main__":
    import io

    parser = XmlObject(
        Tag("notebook", tags=[
            Tag("window_size",
                attr=("window_size",
                      lambda x: tuple(map(int, x.split(","))),
                      lambda x: f"{x[0]},{x[1]}")),
            Tag("window_pos",
                attr=("window_pos",
                      lambda x: tuple(map(int, x.split(","))),
                      lambda x: f"{x[0]},{x[1]}")),
            Tag("vsash_pos",
                attr=("vhash_pos", int, str)),
            Tag("hsash_pos",
                attr=("hsash_pos", int, str)),
            Tag("external_apps", tags=[
                TagMany("app",
                        iterfunc=lambda s: list(range(len(s.apps))),
                        get=lambda s_i, x: s_i[0].apps.append(x),
                        set=lambda s_i: s_i[0].apps[s_i[1]]),
            ]),
            Tag("external_apps2", tags=[
                TagMany("app",
                        iterfunc=lambda s: list(range(len(s.apps2))),
                        before=lambda s_i: s_i[0].apps2.append([None, None]),
                        tags=[
                            Tag("name",
                                get=lambda s_i, x: s_i[0].apps2[s_i[1]].__setitem__(0, x),
                                set=lambda s_i: s_i[0].apps2[s_i[1]][0]),
                            Tag("prog",
                                get=lambda s_i, x: s_i[0].apps2[s_i[1]].__setitem__(1, x),
                                set=lambda s_i: s_i[0].apps2[s_i[1]][1])
                        ])
            ]),
        ])
    )

    class Pref:
        def __init__(self):
            self.window_size = (0, 0)
            self.window_pos = (0, 0)
            self.vsash_pos = 0
            self.hsash_pos = 0
            self.apps = []
            self.apps2 = []

        def read(self, filename):
            parser.read(self, filename)

        def write(self, filename):
            parser.write(self, filename)

    infile = io.StringIO("""<?xml version="1.0" encoding="UTF-8"?>
       <notebook>
       <window_size>1053,905</window_size>
<window_pos>0,0</window_pos>
<vsash_pos>0</vsash_pos>
<hsash_pos>250</hsash_pos>
<external_apps>
<app>web_browser</app>
<app>image_editor</app>
</external_apps>
<external_apps2>
<app><name>web_browser</name><prog>firefox</prog></app>
<app><name>image_editor</name><prog>gimp</prog></app>
</external_apps2>
       </notebook>
    """)

    for i in range(1):  # 0000):
        pref = Pref()
        pref.read(infile)
        pref.write(sys.stdout)