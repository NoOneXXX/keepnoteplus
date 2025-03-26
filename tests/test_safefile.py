import os
import unittest

from keepnote import safefile

from . import make_clean_dir, TMP_DIR


_tmpdir = os.path.join(TMP_DIR, 'safefile')


class TestCaseSafeFile (unittest.TestCase):

    def setUp(self):
        make_clean_dir(_tmpdir)

    def test1(self):
        """test successful write"""

        filename = _tmpdir + "/safefile"

        out = safefile.open(filename, "w", codec="utf-8")
        tmp = out.get_tempfile()

        out.write("\u2022 hello\n")
        out.write("there")
        out.close()

        self.assertEqual(safefile.open(filename, codec="utf-8").read(),
                          "\u2022 hello\nthere")
        self.assertEqual(os.path.exists(tmp), False)

    def test2(self):
        """test unsuccessful write"""

        filename = _tmpdir + "/safefile"

        # make file
        self.test1()

        try:
            out = safefile.open(filename, "w")

            out.write("hello2\n")
            raise Exception("oops")
            out.write("there2")
            out.close()
        except:
            pass

        self.assertEqual(safefile.open(filename, codec="utf-8").read(),
                          "\u2022 hello\nthere")
        self.assertEqual(os.path.exists(out.get_tempfile()), True)

    def test3(self):

        filename = _tmpdir + "/safefile"

        out = safefile.open(filename, "w", codec="utf-8")
        out.write("\u2022 hello\nthere\nagain\n")
        out.close()

        lines = safefile.open(filename, codec="utf-8").readlines()

        self.assertEqual(lines, ["\u2022 hello\n",
                                  "there\n",
                                  "again\n"])

        lines = list(safefile.open(filename, codec="utf-8"))

        self.assertEqual(lines, ["\u2022 hello\n",
                                  "there\n",
                                  "again\n"])

    def test4(self):

        filename = _tmpdir + "/safefile"

        out = safefile.open(filename, "w", codec="utf-8")

        out.writelines(["\u2022 hello\n",
                        "there\n",
                        "again\n"])
        out.close()

        lines = safefile.open(filename, codec="utf-8").readlines()

        self.assertEqual(lines, ["\u2022 hello\n",
                                  "there\n",
                                  "again\n"])
