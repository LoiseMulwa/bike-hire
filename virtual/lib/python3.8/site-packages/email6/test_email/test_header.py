import datetime
import unittest
from email6 import header
from email6 import errors
from email6.test_email import TestEmailBase


class TestBaseHeaderFeatures(TestEmailBase):

    def test_str(self):
        h = header.HeaderFactory()('subject', 'this is a test')
        self.assertIsInstance(h, str)
        self.assertEqual(h, 'this is a test')
        self.assertEqual(str(h), 'this is a test')

    def test_substr(self):
        h = header.HeaderFactory()('subject', 'this is a test')
        self.assertEqual(h[5:7], 'is')

    def test_has_name(self):
        h = header.HeaderFactory()('subject', 'this is a test')
        self.assertEqual(h.name, 'subject')

    def test_source(self):
        h = header.HeaderFactory()('subject', 'this is a test')
        self.assertIsNone(h.source)
        h = header.HeaderFactory()('subject', 'this is a test', 'unfolded value')
        self.assertEqual(h.source, 'this is a test')

    def test_value(self):
        h = header.HeaderFactory()('subject', 'this is a test')
        self.assertEqual(h.value, 'this is a test')
        h = header.HeaderFactory()('subject', 'this is a test', 'unfolded value',
                       use_decoded=True)
        self.assertEqual(h.value, 'unfolded value')

    def _test_attr_ro(self, attr):
        h = header.HeaderFactory()('subject', 'this is a test')
        with self.assertRaises(AttributeError):
            setattr(h, attr, 'foo')

    def test_name_read_only(self):
        self._test_attr_ro('name')

    def test_source_read_only(self):
        self._test_attr_ro('source')

    def test_value_read_only(self):
        self._test_attr_ro('value')

    def test_defects_read_only(self):
        self._test_attr_ro('defects')

    def test_defects_is_tuple(self):
        h = header.HeaderFactory()('subject', 'this is a test')
        self.assertEqual(len(h.defects), 0)
        self.assertIsInstance(h.defects, tuple)
        # Make sure it is still true when there are defects.
        h = header.HeaderFactory()('date', '')
        self.assertEqual(len(h.defects), 1)
        self.assertIsInstance(h.defects, tuple)


class TestBaseHeaderCompatHackBase:

    # XXX: these should turn into errors in 3.4.

    def test_folded_value_alone_auto_decoded_with_warning(self):
        value = self.NL.join(['this is', ' a test'])
        with self.assertWarnsRegex(DeprecationWarning, "linesep"):
            h = header.HeaderFactory()('subject', value)
        self.assertEqual(h, value)
        self.assertEqual(h.value, 'this is a test')
        self.assertIsNone(h.source)

    def test_RFC2047_value_alone_auto_decoded_with_warning(self):
        value = '=?utf-8?q?this_is_a_test?='
        with self.assertWarnsRegex(DeprecationWarning, "encoded word"):
            h = header.HeaderFactory()('subject', value)
        self.assertEqual(h, value)
        self.assertEqual(h.value, 'this is a test')
        self.assertIsNone(h.source)

class TestBaseHeaderCompatHackLF(TestBaseHeaderCompatHackBase, TestEmailBase):
    NL = '\n'

class TestBaseHeaderCompatHackCRLF(TestBaseHeaderCompatHackBase, TestEmailBase):
    NL = '\r\n'


class TestDateHeader(TestEmailBase):

    datestring = 'Sun, 23 Sep 2001 20:10:55 -0700'
    utcoffset = datetime.timedelta(hours=-7)
    tz = datetime.timezone(utcoffset)
    dt = datetime.datetime(2001, 9, 23, 20, 10, 55, tzinfo=tz)

    def test_parse_date(self):
        h = header.HeaderFactory()('date', self.datestring)
        self.assertEqual(h, self.datestring)
        self.assertEqual(h.datetime, self.dt)
        self.assertEqual(h.datetime.utcoffset(), self.utcoffset)
        self.assertEqual(h.defects, ())

    def test_set_from_datetime(self):
        h = header.HeaderFactory()('date', self.dt)
        self.assertEqual(h, self.datestring)
        self.assertEqual(h.datetime, self.dt)
        self.assertEqual(h.defects, ())

    def test_date_header_properties(self):
        h = header.HeaderFactory()('date', self.datestring)
        self.assertIsInstance(h, header.UniqueDateHeader)
        self.assertEqual(h.max_count, 1)
        self.assertEqual(h.defects, ())

    def test_resent_date_header_properties(self):
        h = header.HeaderFactory()('resent-date', self.datestring)
        self.assertIsInstance(h, header.DateHeader)
        self.assertEqual(h.max_count, None)
        self.assertEqual(h.defects, ())

    def test_no_value_is_defect(self):
        h = header.HeaderFactory()('date', '')
        self.assertEqual(len(h.defects), 1)
        self.assertIsInstance(h.defects[0], errors.HeaderMissingRequiredValue)

    def test_datetime_read_only(self):
        h = header.HeaderFactory()('date', self.datestring)
        with self.assertRaises(AttributeError):
            h.datetime = 'foo'


class TestAddressHeader(TestEmailBase):

    def test_address_read_only(self):
        h = header.HeaderFactory()('sender', 'abc@xyz.com')
        with self.assertRaises(AttributeError):
            h.address = 'foo'

    def test_addresses_read_only(self):
        h = header.HeaderFactory()('sender', 'abc@xyz.com')
        self.assertIsInstance(h.groups, tuple)
        with self.assertRaises(AttributeError):
            h.addresses = 'foo'

    def test_groups_read_only(self):
        h = header.HeaderFactory()('sender', 'abc@xyz.com')
        self.assertIsInstance(h.addresses, tuple)
        with self.assertRaises(AttributeError):
            h.groups = 'foo'

    def _test_single_addr(self, source, unfolded, decoded, defects, reformatted,
                          name, addr_spec, username, domain, comment):
        h = header.HeaderFactory()('sender', source, unfolded,
                                   use_decoded=True)
        self.assertEqual(h, decoded)
        self.assertEqual(h.source, source)
        self.assertEqual(h.value, decoded)
        self.assertDefectsEqual(h.defects, defects)
        a = h.address
        self.assertEqual([a], list(h.groups))
        self.assertEqual([a], list(h.addresses))
        self.assertEqual(a.reformatted, reformatted)
        self.assertEqual(a.name, name)
        self.assertEqual(a.addr_spec, addr_spec)
        self.assertEqual(a.username, username)
        self.assertEqual(a.domain, domain)
        #self.assertEqual(a.comment, comment)

    examples = {

        'empty':
            ('<>',
             '<>',
             '<>',
             [errors.InvalidHeaderDefect],
             '',
             '',
             '',
             '',
             '',
             None),

        'address_only':
            ('zippy@pinhead.com',
             'zippy@pinhead.com',
             'zippy@pinhead.com',
             [],
             'zippy@pinhead.com',
             '',
             'zippy@pinhead.com',
             'zippy',
             'pinhead.com',
             None),

        'name_and_address':
            ('Zaphrod Beblebrux <zippy@pinhead.com>',
             'Zaphrod Beblebrux <zippy@pinhead.com>',
             'Zaphrod Beblebrux <zippy@pinhead.com>',
             [],
             'Zaphrod Beblebrux <zippy@pinhead.com>',
             'Zaphrod Beblebrux',
             'zippy@pinhead.com',
             'zippy',
             'pinhead.com',
             None),

        'quoted_local_part':
            ('Zaphrod Beblebrux <"foo bar"@pinhead.com>',
             'Zaphrod Beblebrux <"foo bar"@pinhead.com>',
             'Zaphrod Beblebrux <"foo bar"@pinhead.com>',
             [],
             'Zaphrod Beblebrux <"foo bar"@pinhead.com>',
             'Zaphrod Beblebrux',
             '"foo bar"@pinhead.com',
             'foo bar',
             'pinhead.com',
             None),

        # The decoded differs from what formataddr produces: formataddr produces
        # the ()s as quoted pairs.  By RFC there is no need to quote ()s inside
        # a quoted string, and minimal use of qp is encouraged.
        'quoted_parens_in_name':
            (r'"A \(Special\) Person" <person@dom.ain>',
             r'"A \(Special\) Person" <person@dom.ain>',
             '"A (Special) Person" <person@dom.ain>',
             [],
             '"A (Special) Person" <person@dom.ain>',
             'A (Special) Person',
             'person@dom.ain',
             'person',
             'dom.ain',
             None),

        'quoted_backslashes_in_name':
            (r'"Arthur \\Backslash\\ Foobar" <person@dom.ain>',
             r'"Arthur \\Backslash\\ Foobar" <person@dom.ain>',
             r'"Arthur \\Backslash\\ Foobar" <person@dom.ain>',
             [],
             r'"Arthur \\Backslash\\ Foobar" <person@dom.ain>',
             r'Arthur \Backslash\ Foobar',
             'person@dom.ain',
             'person',
             'dom.ain',
             None),

        'name_with_dot':
            ('John X. Doe <jxd@example.com>',
             'John X. Doe <jxd@example.com>',
             'John X. Doe <jxd@example.com>',
             [errors.ObsoleteHeaderDefect],
             '"John X. Doe" <jxd@example.com>',
             'John X. Doe',
             'jxd@example.com',
             'jxd',
             'example.com',
             None),

        'quoted_strings_in_local_part':
            ('""example" example"@example.com',
             '""example" example"@example.com',
             '""example" example"@example.com',
             [errors.InvalidHeaderDefect]*3,
             '"example example"@example.com',
             '',
             '"example example"@example.com',
             'example example',
             'example.com',
             None),

        'escaped_quoted_strings_in_local_part':
            (r'"\"example\" example"@example.com',
             r'"\"example\" example"@example.com',
             r'"\"example\" example"@example.com',
             [],
             r'"\"example\" example"@example.com',
             '',
             r'"\"example\" example"@example.com',
             r'"example" example',
             'example.com',
            None),

        'escaped_escapes_in_local_part':
            (r'"\\"example\\" example"@example.com',
             r'"\\"example\\" example"@example.com',
             r'"\\"example\\" example"@example.com',
             [errors.InvalidHeaderDefect]*5,
             r'"\\example\\\\ example"@example.com',
             '',
             r'"\\example\\\\ example"@example.com',
             r'\example\\ example',
             'example.com',
            None),

        }

    for name in examples:
        locals()['test_'+name] = (
            lambda self, name=name:
                self._test_single_addr(*self.examples[name]))

    # XXX: a quick and dirty address list test, more later.
    def test_simple_address_list(self):
        value = ('Fred <dinsdale@python.org>, foo@example.com, '
                    '"Harry W. Hastings" <hasty@example.com>')
        h = header.HeaderFactory()('to', value, value)
        self.assertEqual(h, value)
        self.assertEqual(h.value, value)
        self.assertEqual(h.source, value)
        self.assertEqual(len(h.groups), 3)
        self.assertEqual(len(h.addresses), 3)
        self.assertEqual(h.groups[0], 'Fred <dinsdale@python.org>')
        self.assertEqual(h.groups[1], 'foo@example.com')
        self.assertEqual(h.groups[2],
            '"Harry W. Hastings" <hasty@example.com>')
        self.assertEqual(h.addresses[2].name,
            'Harry W. Hastings')



if __name__ == '__main__':
    unittest.main()
