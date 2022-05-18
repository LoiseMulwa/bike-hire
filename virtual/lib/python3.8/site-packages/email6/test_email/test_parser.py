import sys
import unittest
from email6.test_email import TestEmailBase
from email6 import policy
from email6 import errors
from email6.feedparser import FeedParser, BytesFeedParser


class TestAllFeedParserBase:

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.sNL = self.NL
        self.bNL = self.sNL.encode('ascii')

    def make_input(self, lines):
        return self.bNL.join(lines)

    #
    # decoded_headers
    #

    def decoded_headers_test(self, setting=None, restype=None):
        if setting is None:
            mypolicy = policy.default
        else:
            mypolicy = policy.default.clone(decoded_headers=setting)
        p = self.parser(policy=mypolicy)
        p.feed(self.make_input([
            b"Test: test",
            b" =?utf-8?q?test?=",
            b"",
            b"test"]))
        msg = p.close()
        expected = {
            'raw': self.sNL.join(["test", " =?utf-8?q?test?="]),
            'decoded': 'test test'
            }[restype]
        self.assertEqual(msg['Test'], expected)

    def test_decoded_headers_false(self):
        self.decoded_headers_test(False, 'raw')

    def test_decoded_headers_true(self):
        self.decoded_headers_test(True, 'decoded')

    def test_decode_policy_default(self):
        # This will fail with the first 3.4 version until the default
        # is switched.  Sorry, Georg, but you OKed this kind of thing :)
        if sys.hexversion < 0x3040000:
            with self.assertWarnsRegex(DeprecationWarning, "decoded_headers"):
                self.decoded_headers_test(None, 'raw')
        else:
            self.decoded_headers_test(None, 'decoded')

    #
    # Defect detection
    #

    def duplicate_header_msg_testbed(self, headername, *, duplicate):
        count = 2 if duplicate else 1
        p = self.parser(policy=self.email6_policy)
        p.feed(self.make_input(
            [(headername.encode('ascii') + b": test")] * count))
        return p.close()

    def test_single_nonunique_header_nodefect(self):
        msg = self.duplicate_header_msg_testbed('foobar', duplicate=False)
        self.assertEqual([], msg.defects)

    def test_multiple_nonunique_header_nodefect(self):
        msg = self.duplicate_header_msg_testbed('foobar', duplicate=True)
        self.assertEqual([], msg.defects)

    def test_single_unique_header_nodefect(self):
        msg = self.duplicate_header_msg_testbed('Subject', duplicate=False)
        self.assertEqual([], msg.defects)

    def test_multiple_unique_header_defect(self):
        msg = self.duplicate_header_msg_testbed('Subject', duplicate=True)
        self.assertEqual(len(msg.defects), 1)
        self.assertIsInstance(msg.defects[0], errors.DuplicateHeaderDefect)
        self.assertEqual(msg.defects[0].header_name, 'subject')


class TestFeedParserBase(TestAllFeedParserBase):

    def make_input(self, lines):
        return TestAllFeedParserBase.make_input(self, lines).decode('ascii')

class TestFeedParserLF(TestFeedParserBase, TestEmailBase):
    NL = '\n'
    parser = FeedParser

class TestFeedParserCRLF(TestFeedParserBase, TestEmailBase):
    NL = '\r\n'
    parser = FeedParser


class TestBytesFeedParserBase(TestAllFeedParserBase):

    # XXX: check the defects list
    # XXX: uncomment 'v.decoded' tests once Header is a BaseHeader.

    def _test_invalid_byte_in_header(self, decode):
        p = self.parser(policy=policy.default.clone(decoded_headers=decode))
        p.feed(self.make_input([
            b"Test: a b\xbfd test",
            b"",
            b"test"]))
        msg = p.close()
        v = msg['test']
        #self.assertEqual(v.decoded, "a b\uFFFDd test")
        if not decode:
            v = str(v)
        self.assertEqual(v, "a b\uFFFDd test")

    def _test_invalid_byte_in_q_encoded_word(self, decode):
        p = self.parser(policy=policy.default.clone(decoded_headers=decode))
        p.feed(self.make_input([
            b"Test: a =?utf-8?q?h\xbfader?=",
            b"",
            b"test"]))
        msg = p.close()
        v = msg['test']
        #self.assertEqual(v.decoded, "a h\uFFFDader")
        if not decode:
            v = str(v)
        self.assertEqual(v, "a h\uFFFDader")

    def _test_invalid_byte_in_b_encoded_word(self, decode):
        p = self.parser(policy=policy.default.clone(decoded_headers=decode))
        p.feed(self.make_input([
            b"Test: a =?utf-8?b?a\xbaGVhZGVy?=",
            b"",
            b"test"]))
        msg = p.close()
        v = msg['test']
        #self.assertEqual(v.decoded, "a header")
        if not decode:
            v = str(v)
        self.assertEqual(v, "a header")

    def _test_invalid_byte_in_both(self, decode):
        p = self.parser(policy=policy.default.clone(decoded_headers=decode))
        p.feed(self.make_input([
            b"Test: a b\xbfd =?utf-8?q?h\xbfader?=",
            b"",
            b"test"]))
        msg = p.close()
        v = msg['test']
        #self.assertEqual(v.decoded, "a b\uFFFDd h\uFFFDader")
        if not decode:
            v = str(v)
        self.assertEqual(v, "a b\uFFFDd h\uFFFDader")

    def test_invalid_byte_in_header_decode_true(self):
        self._test_invalid_byte_in_header(True)

    def test_invalid_byte_in_q_enooded_word_decode_true(self):
        self._test_invalid_byte_in_q_encoded_word(True)

    def test_invalid_byte_in_b_enooded_word_decode_true(self):
        self._test_invalid_byte_in_b_encoded_word(True)

    def test_invalid_byte_in_both_decode_true(self):
        self._test_invalid_byte_in_both(True)

    # XXX: These tests fails because of a bug in email 5.1 that it isn't
    # clear how to fix.
    def test_invalid_byte_in_header_decode_false(self):
        self._test_invalid_byte_in_header(False)

    def XXXtest_invalid_byte_in_q_enooded_word_decode_false(self):
        self._test_invalid_byte_in_q_encoded_word(False)

    def XXXtest_invalid_byte_in_b_enooded_word_decode_false(self):
        self._test_invalid_byte_in_b_encoded_word(False)

    def XXXtest_invalid_byte_in_both_decode_false(self):
        self._test_invalid_byte_in_both(False)


class TestBytesFeedParserLF(TestBytesFeedParserBase, TestEmailBase):
    NL = '\n'
    parser = BytesFeedParser

class TestBytesFeedParserCRLF(TestBytesFeedParserBase, TestEmailBase):
    NL = '\r\n'
    parser = BytesFeedParser
