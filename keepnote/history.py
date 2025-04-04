"""

    KeepNote
    Node history data structure

"""



class NodeHistory (object):
    """Data structure of node history"""

    def __init__(self, maxsize=40):
        self._list = []
        self._pos = 0
        self._suspend = 0
        self._maxsize = maxsize

    def add(self, nodeid):

        if self._suspend == 0:
            # truncate list to current position
            if self._list:
                self._list = self._list[:self._pos+1]

            # add page to history
            self._list.append(nodeid)
            self._pos = len(self._list) - 1

            # keep history to max size
            if len(self._list) > self._maxsize:
                self._list = self._list[-self._maxsize:]
                self._pos = len(self._list) - 1

    def move(self, offset):
        self._pos += offset
        if self._pos < 0:
            self._pos = 0
        if self._pos >= len(self._list):
            self._pos = len(self._list) - 1

        if self._list:
            return self._list[self._pos]
        else:
            return None

    def begin_suspend(self):
        self._suspend += 1

    def end_suspend(self):
        self._suspend -= 1
        assert self._suspend >= 0

    def has_back(self):
        return self._pos > 0

    def has_forward(self):
        return self._pos < len(self._list) - 1
