import os


# Constants.
NODE_META_FILE = "node.xml"


def get_node_meta_file(nodepath):
    """Return the metadata file for a node."""
    return os.path.join(nodepath, NODE_META_FILE)


def path_local2node(filename):


    if os.path.sep == "/":
        return filename
    return filename.replace(os.path.sep, "/")


def path_node2local(filename):


    if os.path.sep == "/":
        return filename
    return filename.replace("/", os.path.sep)
