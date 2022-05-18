import os
import sys
import unittest
import warnings
import test.support
from email6 import message_from_file
from email6 import policy
from email6.test_email import __file__ as landmark

# used by regrtest and __main__.
def test_main():
    here = os.path.dirname(__file__)
    # Unittest mucks with the path, so we have to save and restore
    # it to keep regrtest happy.
    savepath = sys.path[:]
    test.support._run_suite(unittest.defaultTestLoader.discover(here))
    sys.path[:] = savepath


# helper code used by a number of test modules.

def openfile(filename, *args, **kws):
    path = os.path.join(os.path.dirname(landmark), 'data', filename)
    return open(path, *args, **kws)


# Base test class
class TestEmailBase(unittest.TestCase):

    maxDiff = None
    # We put these here so we can see what happens to the tests if
    # we change some defaults.
    email5_policy = policy.email5_defaults
    email6_policy = policy.email6_defaults

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.addTypeEqualityFunc(bytes, self.assertBytesEqual)

    ndiffAssertEqual = unittest.TestCase.assertEqual

    def _msgobj(self, filename):
        with openfile(filename) as fp:
            return message_from_file(fp, policy=self.email5_policy)

    def _bytes_repr(self, b):
        return [repr(x) for x in b.splitlines(True)]

    def assertBytesEqual(self, first, second, msg):
        """Our byte strings are really encoded strings; improve diff output"""
        self.assertEqual(self._bytes_repr(first), self._bytes_repr(second))

    def assertDefectsEqual(self, actual, expected):
        self.assertEqual(len(actual), len(expected), actual)
        for i in range(len(actual)):
            self.assertIsInstance(actual[i], expected[i],
                                    'item {}'.format(i))
