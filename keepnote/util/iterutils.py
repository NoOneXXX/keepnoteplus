class PushIter:
    """
    A wrapper around an iterator that allows pushing items back onto the front.
    """
    def __init__(self, iterable):
        self._iter = iter(iterable)
        self._pushback = []

    def __iter__(self):
        return self

    def __next__(self):
        if self._pushback:
            return self._pushback.pop()
        return next(self._iter)

    def push(self, item):
        self._pushback.append(item)
