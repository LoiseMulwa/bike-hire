import unittest
from email6 import _encoded_words as _ew
from email6 import errors
from email6.test_email import TestEmailBase


class TestDecodeQ(TestEmailBase):

    def _test(self, source, ex_result, ex_defects=[]):
        result, defects = _ew.decode_q(source)
        self.assertEqual(result, ex_result)
        self.assertDefectsEqual(defects, ex_defects)

    def test_no_encoded(self):
        self._test(b'foobar', b'foobar')

    def test_spaces(self):
        self._test(b'foo=20bar=20', b'foo bar ')

    def test_run_of_encoded(self):
        self._test(b'foo=20=20=21bar', b'foo  !bar')


class TestDecodeB(TestEmailBase):

    def _test(self, source, ex_result, ex_defects=[]):
        result, defects = _ew.decode_b(source)
        self.assertEqual(result, ex_result)
        self.assertDefectsEqual(defects, ex_defects)

    def test_simple(self):
        self._test(b'Zm9v', b'foo')

    def test_missing_padding(self):
        self._test(b'dmk', b'vi', [errors.InvalidBase64PaddingDefect])

    def test_invalid_character(self):
        self._test(b'dm\x01k===', b'vi', [errors.InvalidBase64CharactersDefect])

    def test_invalid_character_and_bad_padding(self):
        self._test(b'dm\x01k', b'vi', [errors.InvalidBase64CharactersDefect,
                                       errors.InvalidBase64PaddingDefect])


class TestDecode(TestEmailBase):

    def test_wrong_format_input_raises(self):
        with self.assertRaises(ValueError):
            _ew.decode('=?badone?=')
        with self.assertRaises(ValueError):
            _ew.decode('=?')
        with self.assertRaises(ValueError):
            _ew.decode('')

    def _test(self, source, ex_result, ex_defects=[]):
        result, defects = _ew.decode(source)
        self.assertEqual(result, ex_result)
        self.assertDefectsEqual(defects, ex_defects)

    def test_simple_q(self):
        self._test('=?us-ascii?q?foo?=', 'foo')

    def test_simple_b(self):
        self._test('=?us-ascii?b?dmk=?=', 'vi')

    def test_q_case_ignored(self):
        self._test('=?us-ascii?Q?foo?=', 'foo')

    def test_b_case_ignored(self):
        self._test('=?us-ascii?B?dmk=?=', 'vi')

    def test_non_trivial_q(self):
        self._test('=?latin-1?q?=20F=fcr=20Elise=20?=', ' Für Elise ')

    def test_q_undecodable_bytes_transformed(self):
        self._test(b'=?us-ascii?q?=20\xACfoo?='.decode('us-ascii',
                                                       'surrogateescape'),
                   ' \uFFFDfoo',
                   [errors.UndecodableBytesDefect])

    def test_b_undecodable_bytes_ignored_with_defect(self):
        self._test(b'=?us-ascii?b?dm\xACk?='.decode('us-ascii',
                                                   'surrogateescape'),
                   'vi',
                   [errors.InvalidBase64CharactersDefect,
                    errors.InvalidBase64PaddingDefect])

    def test_b_invalid_bytes_ignored_with_defect(self):
        self._test('=?us-ascii?b?dm\x01k===?=',
                   'vi',
                   [errors.InvalidBase64CharactersDefect])

    def test_b_invalid_bytes_incorrect_padding(self):
        self._test('=?us-ascii?b?dm\x01k?=',
                   'vi',
                   [errors.InvalidBase64CharactersDefect,
                    errors.InvalidBase64PaddingDefect])

    def test_b_padding_defect(self):
        self._test('=?us-ascii?b?dmk?=',
                   'vi',
                    [errors.InvalidBase64PaddingDefect])



if __name__ == '__main__':
    unittest.main()
