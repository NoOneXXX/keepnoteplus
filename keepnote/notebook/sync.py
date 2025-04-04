"""

    KeepNote

    Syncing features for NoteBookConnection's

"""


from keepnote.notebook.connection import NodeExists
from keepnote.notebook.connection import path_join
from keepnote.notebook.connection import UnknownNode


#=============================================================================
# syncing


def on_conflict_reject(nodeid, conn1, conn2, attr1=None, attr2=None):
    """
    Existing node (conn2) always wins conflict
    """
    pass


def on_conflict_newer(nodeid, conn1, conn2, attr1=None, attr2=None):
    """
    Node with newer modified_time wins conflict

    conn2 wins ties
    """
    if attr1 is None:
        attr1 = conn1.read_node(nodeid)
    if attr2 is None:
        try:
            attr2 = conn2.read_node(nodeid)
        except UnknownNode:
            conn2.create_node(nodeid, attr1)
            sync_files(conn1, nodeid, conn2, nodeid)

    if attr1.get("modified_time", 0) > attr2.get("modified_time", 0):
        conn2.update_node(nodeid, attr1)
        sync_files(conn1, nodeid, conn2, nodeid)
    else:
        # leave node in conn2 unchanged
        pass


def sync_node(nodeid, conn1, conn2, attr=None,
              on_conflict=on_conflict_newer):
    """
    Sync a node 'nodeid' from connection 'conn1' to 'conn2'

    Conflicts are resolved based on on_conflict (newer node by default)
    """
    if attr is None:
        attr = conn1.read_node(nodeid)

    try:
        conn2.create_node(nodeid, attr)
        sync_files(conn1, nodeid, conn2, nodeid)
    except NodeExists:
        # conflict
        on_conflict(nodeid, conn1, conn2, attr)


def sync_files(conn1, nodeid1, conn2, nodeid2, path1="/", path2="/"):
    """Sync files from conn1.nodeid1 to conn2.nodeid2"""
    files = list(conn1.list_dir(nodeid1, path1))

    # ensure target path exists
    if not conn2.has_file(nodeid2, path2):
        conn2.create_dir(nodeid2, path2)

    # remove files in node2 that don't exist in node1
    for f in list(conn2.list_dir(nodeid2, path2)):
        f2 = path_join(path2, f)
        if not conn1.has_file(nodeid1, f2):
            conn2.delete_file(nodeid2, f2)

    # copy files from node1 to node2
    for f in files:
        file1 = f
        file2 = path_join(path2, f[len(path1):])

        if f.endswith("/"):
            # recurse into directories
            sync_files(conn1, nodeid1, conn2, nodeid2, file1, file2)
            continue

        copy_file(conn1, nodeid1, file1, conn2, nodeid2, file2)


def copy_file(conn1, nodeid1, file1, conn2, nodeid2, file2):
    """Copy a file from conn1.nodeid1.file1 to conn2.nodeid2.file2"""

    stream1 = conn1.open_file(nodeid1, file1, "r")
    stream2 = conn2.open_file(nodeid2, file2, "w")

    while True:
        data = stream1.read(1024*4)
        if len(data) == 0:
            break
        stream2.write(data)

    stream1.close()
    stream2.close()
