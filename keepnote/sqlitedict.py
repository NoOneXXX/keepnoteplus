#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2011 Radim Rehurek <radimrehurek@seznam.cz>

# Hacked together from:
#  * http://code.activestate.com/recipes/576638-draft-for-an-sqlite3-based-dbm/
#  * http://code.activestate.com/recipes/526618/
#
# Use the code in any way you like (at your own risk), it's public domain.

"""
A lightweight wrapper around Python's sqlite3 database, with a dict-like interface
and multi-thread access support::

>>> mydict = SqliteDict('some.db', autocommit=True) # the mapping will be persisted to file `some.db`
>>> mydict['some_key'] = any_picklable_object
>>> print mydict['some_key']
>>> print len(mydict) # etc... all dict functions work

Pickle is used internally to serialize the values. Keys are strings.

If you don't use autocommit (default is no autocommit for performance), then
don't forget to call `mydict.commit()` when done with a transaction.

"""


import sqlite3
import os
import tempfile
import random
import logging
from pickle import dumps, loads, HIGHEST_PROTOCOL as PICKLE_PROTOCOL
from collections.abc import MutableMapping

logger = logging.getLogger('sqlitedict')
from threading import Thread
from queue import Queue

from threading import Thread
from queue import Queue
import sqlite3
import sys

class SqliteMultithread(Thread):
    """
    Wrap sqlite connection in a way that allows concurrent requests from multiple threads.
    """

    def __init__(self, filename, autocommit, journal_mode):
        super().__init__()
        self.filename = filename
        self.autocommit = autocommit
        self.journal_mode = journal_mode
        self.reqs = Queue()  # use request queue of unlimited size
        self.setDaemon(True)
        self.start()

    def run(self):
        # Initialize SQLite connection
        conn = sqlite3.connect(self.filename, check_same_thread=False)
        conn.execute(f'PRAGMA journal_mode = {self.journal_mode}')
        conn.text_factory = str
        cursor = conn.cursor()

        while True:
            req, arg, res = self.reqs.get()
            if req == '--close--':
                break
            elif req == '--commit--':
                conn.commit()
            else:
                try:
                    cursor.execute(req, arg)
                    if res:
                        for rec in cursor:
                            res.put(rec)
                        res.put('--no more--')
                    if self.autocommit:
                        conn.commit()
                except Exception as e:
                    print(f"SQL Execution Error: {e}")

        conn.close()

    def execute(self, req, arg=None, res=None):
        """Non-blocking execution of SQL statements."""
        self.reqs.put((req, arg or tuple(), res))

    def select(self, req, arg=None):
        """Execute a SELECT statement and return the results."""
        res = Queue()  # results of the select will appear as items in this queue
        self.execute(req, arg, res)
        while True:
            rec = res.get()
            if rec == '--no more--':
                break
            yield rec

    def select_one(self, req, arg=None):
        """Return only the first row of the SELECT, or None if there are no matching rows."""
        try:
            return next(iter(self.select(req, arg)))
        except StopIteration:
            return None

    def commit(self):
        self.execute('--commit--')

    def close(self):
        self.execute('--close--')



def open(*args, **kwargs):
    """See documentation of the SqliteDict class."""
    return SqliteDict(*args, **kwargs)


def encode(obj):
    """Serialize an object using pickle to a binary format accepted by SQLite."""
    return sqlite3.Binary(dumps(obj, protocol=PICKLE_PROTOCOL))


def decode(obj):
    """Deserialize objects retrieved from SQLite."""
    return loads(obj)


class SqliteDict(MutableMapping):
    def __init__(self, filename=None, tablename='unnamed', flag='c',
                 autocommit=False, journal_mode="DELETE"):
        self.in_temp = filename is None
        if self.in_temp:
            randpart = hex(random.randint(0, 0xffffff))[2:]
            filename = os.path.join(tempfile.gettempdir(), 'sqldict' + randpart)
        if flag == 'n' and os.path.exists(filename):
            os.remove(filename)

        self.filename = filename
        self.tablename = tablename

        logger.info("Opening Sqlite table %r in %s", tablename, filename)
        MAKE_TABLE = f'CREATE TABLE IF NOT EXISTS {self.tablename} (key TEXT PRIMARY KEY, value BLOB)'
        self.conn = SqliteMultithread(filename, autocommit=autocommit, journal_mode=journal_mode)
        self.conn.execute(MAKE_TABLE)
        self.conn.commit()

        if flag == 'w':
            self.clear()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def __len__(self):
        GET_LEN = f'SELECT COUNT(*) FROM {self.tablename}'
        rows = self.conn.select_one(GET_LEN)[0]
        return rows if rows is not None else 0

    def __bool__(self):
        GET_LEN = f'SELECT MAX(ROWID) FROM {self.tablename}'
        return self.conn.select_one(GET_LEN) is not None

    def keys(self):
        GET_KEYS = f'SELECT key FROM {self.tablename} ORDER BY rowid'
        return [key[0] for key in self.conn.select(GET_KEYS)]

    def values(self):
        GET_VALUES = f'SELECT value FROM {self.tablename} ORDER BY rowid'
        return [decode(value[0]) for value in self.conn.select(GET_VALUES)]

    def items(self):
        GET_ITEMS = f'SELECT key, value FROM {self.tablename} ORDER BY rowid'
        return [(key, decode(value)) for key, value in self.conn.select(GET_ITEMS)]

    def __contains__(self, key):
        HAS_ITEM = f'SELECT 1 FROM {self.tablename} WHERE key = ?'
        return self.conn.select_one(HAS_ITEM, (key,)) is not None

    def __getitem__(self, key):
        GET_ITEM = f'SELECT value FROM {self.tablename} WHERE key = ?'
        item = self.conn.select_one(GET_ITEM, (key,))
        if item is None:
            raise KeyError(key)
        return decode(item[0])

    def __setitem__(self, key, value):
        ADD_ITEM = f'REPLACE INTO {self.tablename} (key, value) VALUES (?, ?)'
        self.conn.execute(ADD_ITEM, (key, encode(value)))

    def __delitem__(self, key):
        if key not in self:
            raise KeyError(key)
        DEL_ITEM = f'DELETE FROM {self.tablename} WHERE key = ?'
        self.conn.execute(DEL_ITEM, (key,))

    def clear(self):
        CLEAR_ALL = f'DELETE FROM {self.tablename};'
        self.conn.commit()
        self.conn.execute(CLEAR_ALL)
        self.conn.commit()

    def commit(self):
        if self.conn is not None:
            self.conn.commit()
    sync = commit

    def close(self):
        logger.debug("Closing %s", self)
        if self.conn is not None:
            if self.conn.autocommit:
                self.conn.commit()
            self.conn.close()
            self.conn = None
        if self.in_temp:
            try:
                os.remove(self.filename)
            except Exception:
                pass

    def __iter__(self):
        return iter(self.keys())

    def __str__(self):
        return f"SqliteDict({self.conn.filename})"

    def __del__(self):
        try:
            if self.conn is not None:
                if self.conn.autocommit:
                    self.conn.commit()
                self.conn.close()
                self.conn = None
            if self.in_temp:
                os.remove(self.filename)
        except Exception:
            pass

#endclass SqliteMultithread


# running sqlitedict.py as script will perform a simple unit test
if __name__ in '__main___':
    logging.basicConfig(format='%(asctime)s : %(levelname)s : %(module)s:%(lineno)d : %(funcName)s(%(threadName)s) : %(message)s')
    logging.root.setLevel(level=logging.INFO)
    for d in SqliteDict(), SqliteDict('example', flag='n'):
        assert list(d) == []
        assert len(d) == 0
        assert not d
        d['abc'] = 'rsvp' * 100
        assert d['abc'] == 'rsvp' * 100
        assert len(d) == 1
        d['abc'] = 'lmno'
        assert d['abc'] == 'lmno'
        assert len(d) == 1
        del d['abc']
        assert not d
        assert len(d) == 0
        d['abc'] = 'lmno'
        d['xyz'] = 'pdq'
        assert len(d) == 2
        assert list(d.items()) == [('abc', 'lmno'), ('xyz', 'pdq')]
        assert list(d.items()) == [('abc', 'lmno'), ('xyz', 'pdq')]
        assert list(d.values()) == ['lmno', 'pdq']
        assert list(d.keys()) == ['abc', 'xyz']
        assert list(d) == ['abc', 'xyz']
        d.update(p='x', q='y', r='z')
        assert len(d) == 5
        assert list(d.items()) == [('abc', 'lmno'), ('xyz', 'pdq'), ('q', 'y'), ('p', 'x'), ('r', 'z')]
        del d['abc']
        try:
            error = d['abc']
        except KeyError:
            pass
        else:
            assert False
        try:
            del d['abc']
        except KeyError:
            pass
        else:
            assert False
        assert list(d) == ['xyz', 'q', 'p', 'r']
        assert d
        d.clear()
        assert not d
        assert list(d) == []
        d.update(p='x', q='y', r='z')
        assert list(d) == ['q', 'p', 'r']
        d.clear()
        assert not d
        d.close()
    print('all tests passed :-)')
