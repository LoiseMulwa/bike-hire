import datetime
from email6 import utils
import unittest

class FormatDateTimeTests(unittest.TestCase):

    datestring = 'Sun, 23 Sep 2001 20:10:55'
    dateargs = (2001, 9, 23, 20, 10, 55)
    offsetstring = ' -0700'
    utcoffset = datetime.timedelta(hours=-7)
    tz = datetime.timezone(utcoffset)
    naive_dt = datetime.datetime(*dateargs)
    aware_dt = datetime.datetime(*dateargs, tzinfo=tz)

    def test_naive_datetime(self):
        self.assertEqual(utils.format_datetime(self.naive_dt),
                         self.datestring + ' -0000')

    def test_aware_datetime(self):
        self.assertEqual(utils.format_datetime(self.aware_dt),
                         self.datestring + self.offsetstring)

    def test_usegmt(self):
        utc_dt = datetime.datetime(*self.dateargs,
                                   tzinfo=datetime.timezone.utc)
        self.assertEqual(utils.format_datetime(utc_dt, usegmt=True),
                         self.datestring + ' GMT')

    def test_usegmt_with_naive_datetime_raises(self):
        with self.assertRaises(ValueError):
            utils.format_datetime(self.naive_dt, usegmt=True)

    def test_usegmt_with_non_utc_datetime_raises(self):
        with self.assertRaises(ValueError):
            utils.format_datetime(self.aware_dt, usegmt=True)


class LocaltimeTests(unittest.TestCase):

    def test_localtime(self):
        # Based on Issue 9527 patch
        t = utils.localtime()
        self.assertIsNot(t.tzinfo, None)
        t0 = datetime.datetime(1970, 1, 1, tzinfo = datetime.timezone.utc)
        t1 = utils.localtime(t0)
        self.assertEqual(t0, t1)
        t2 = utils.localtime(t1.replace(tzinfo=None))
        self.assertEqual(t1, t2)
        # The following tests use local time that is ambiguous in the
        # US, but should work in any location
        t0 = datetime.datetime(2010, 11, 7, 1, 30)
        t1 = utils.localtime(t0, isdst=0)
        t2 = utils.localtime(t1)
        self.assertEqual(t1, t2)
        t1 = utils.localtime(t0, isdst=1)
        t2 = utils.localtime(t1)
        self.assertEqual(t1, t2)


if __name__ == '__main__':
    unittest.main()
