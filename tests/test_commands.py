import unittest

# keepnote.py imports
from keepnote import commands


class Commands (unittest.TestCase):

    def setUp(self):
        pass

    def test1(self):
        args = ['a b', 'c d']
        args2 = commands.parse_command(commands.format_command(args))

        self.assertEqual(args, args2)
