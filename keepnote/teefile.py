"""

    KeepNote
    Tee File Streams

    Allow one file stream to multiplex for multiple file streams

"""



class TeeFileStream (object):
    """Create a file stream that forwards writes to multiple streams"""

    def __init__(self, streams, autoflush=False):
        self._streams = list(streams)
        self._autoflush = autoflush

    def add(self, stream):
        """Adds a new stream to teefile"""
        self._streams.append(stream)

    def remove(self, stream):
        """Removes a stream from teefile"""
        self._streams.remove(stream)

    def get_streams(self):
        """Returns a list of streams associated with teefile"""
        return list(self._streams)

    def write(self, data):
        """Write data to streams"""
        for stream in self._streams:
            stream.write(data)
            if self._autoflush:
                stream.flush()

    def flush(self):
        """Flush streams"""
        for stream in self._streams:
            stream.flush()
