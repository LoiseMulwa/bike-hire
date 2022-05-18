import io
import textwrap
import unittest
from email6 import message_from_string, message_from_bytes
from email6.generator import Generator, BytesGenerator
from email6 import policy
from email6 import message
from email6.test_email import TestEmailBase

# XXX: move generator tests from test_email into here at some point.
# XXX: also need to test both old_policy_defaults and future_policy_defaults.


#
# ASCII only in source
#

class TestGeneratorASCIIBase():

    long_subject = {
        0: textwrap.dedent("""\
            To: whom_it_may_concern@example.com
            From: nobody_you_want_to_know@example.com
            Subject: We the willing led by the unknowing are doing the
             impossible for the ungrateful. We have done so much for so long with so little
             we are now qualified to do anything with nothing.

            None
            """),
        40: textwrap.dedent("""\
            To: whom_it_may_concern@example.com
            From:\x20
             nobody_you_want_to_know@example.com
            Subject: We the willing led by the
             unknowing are doing the
             impossible for the ungrateful. We have
             done so much for so long with so little
             we are now qualified to do anything
             with nothing.

            None
            """),
        20: textwrap.dedent("""\
            To:\x20
             whom_it_may_concern@example.com
            From:\x20
             nobody_you_want_to_know@example.com
            Subject: We the
             willing led by the
             unknowing are doing
             the
             impossible for the
             ungrateful. We have
             done so much for so
             long with so little
             we are now
             qualified to do
             anything with
             nothing.

            None
            """),
        }
    long_subject[100] = long_subject[0]

    def maxheaderlen_parameter_test(self, n):
        msg = self.msgmaker(self.long_subject[0],
            policy=self.policy)
        s = self.ioclass()
        g = self.genclass(s, maxheaderlen=n)
        g.flatten(msg)
        self.assertEqual(s.getvalue(), self.long_subject[n])

    def test_maxheaderlen_parameter_0(self):
        self.maxheaderlen_parameter_test(0)

    def test_maxheaderlen_parameter_100(self):
        self.maxheaderlen_parameter_test(100)

    def test_maxheaderlen_parameter_40(self):
        self.maxheaderlen_parameter_test(40)

    def test_maxheaderlen_parameter_20(self):
        self.maxheaderlen_parameter_test(20)

    def maxheaderlen_policy_test(self, n):
        msg = self.msgmaker(self.long_subject[0],
            policy=self.policy)
        s = self.ioclass()
        g = self.genclass(s, policy=policy.default.clone(max_line_length=n))
        g.flatten(msg)
        self.assertEqual(s.getvalue(), self.long_subject[n])

    def test_maxheaderlen_policy_0(self):
        self.maxheaderlen_policy_test(0)

    def test_maxheaderlen_policy_100(self):
        self.maxheaderlen_policy_test(100)

    def test_maxheaderlen_policy_40(self):
        self.maxheaderlen_policy_test(40)

    def test_maxheaderlen_policy_20(self):
        self.maxheaderlen_policy_test(20)

    def maxheaderlen_parm_overrides_policy_test(self, n):
        msg = self.msgmaker(self.long_subject[0],
            policy=self.email5_policy)
        s = self.ioclass()
        g = self.genclass(s, maxheaderlen=n,
                          policy=policy.default.clone(max_line_length=10))
        g.flatten(msg)
        self.assertEqual(s.getvalue(), self.long_subject[n])

    def test_maxheaderlen_parm_overrides_policy_0(self):
        self.maxheaderlen_parm_overrides_policy_test(0)

    def test_maxheaderlen_parm_overrides_policy_100(self):
        self.maxheaderlen_parm_overrides_policy_test(100)

    def test_maxheaderlen_parm_overrides_policy_40(self):
        self.maxheaderlen_parm_overrides_policy_test(40)

    def test_maxheaderlen_parm_overrides_policy_20(self):
        self.maxheaderlen_parm_overrides_policy_test(20)


class TestGeneratorASCII(TestGeneratorASCIIBase, TestEmailBase):

    msgmaker = staticmethod(message_from_string)
    genclass = Generator
    ioclass = io.StringIO
    policy = TestEmailBase.email5_policy


class TestGeneratorASCIIEmail6Policy(TestGeneratorASCII):

    policy = TestEmailBase.email6_policy


class TestBytesGeneratorASCII(TestGeneratorASCIIBase, TestEmailBase):

    msgmaker = staticmethod(message_from_bytes)
    genclass = BytesGenerator
    ioclass = io.BytesIO
    policy = TestEmailBase.email5_policy

    long_subject = {key: x.encode('ascii')
        for key, x in TestGeneratorASCIIBase.long_subject.items()}


class TestBytesGeneratorASCIIEmail6Policy(TestBytesGeneratorASCII):

    policy = TestEmailBase.email6_policy


#
# Non ASCII in source/model
#

class TestGeneratorNonASCIIBase:

    unicode_subject = textwrap.dedent("""\
        To: whom_it_may_concern@example.com
        From: nobody_you_want_to_know@example.com
        Subject: Mein kleiner grüner Kaktus, Es hat viele Stacheln und
            beißt mich oft.

        Aber ich liebe ihn trotzdem.
        """)

    def test_flatten_nonascii_model(self):
        msg = message.Message(policy=self.policy)
        msg['Subject'] = ("Subject: Mein kleiner grüner Kaktus, "
            "Es hat viele Stacheln und beißt mich oft.")
        self.assertGeneratesEqual(msg, textwrap.dedent("""\
            Subject: =?utf-8?q?Subject=3A_Mein_kleiner_gr=C3=BCner_Kaktus=2C_Es_hat_viel?=
             =?utf-8?q?e_Stacheln_und_bei=C3=9Ft_mich_oft=2E?=

            """))


class TestGeneratorNonASCII(TestGeneratorNonASCIIBase):

    def assertGeneratesEqual(self, msg, expected):
        s = io.StringIO()
        g = Generator(s)
        g.flatten(msg)
        self.assertEqual(s.getvalue(), expected)


class TestBytesGeneratorNonASCII(TestGeneratorNonASCIIBase):

    def assertGeneratesEqual(self, msg, expected):
        s = io.BytesIO()
        g = BytesGenerator(s)
        g.flatten(msg)
        self.assertEqual(s.getvalue(), expected.encode('ascii'))


class TestGeneratorNonASCIIEamil5(TestGeneratorNonASCII, TestEmailBase):

    policy = TestEmailBase.email5_policy


class TestGeneratorNonASCIIEmail6(TestGeneratorNonASCII, TestEmailBase):

    policy = TestEmailBase.email6_policy


class TestBytesGeneratorNonASCIIEamil5(TestBytesGeneratorNonASCII,
                                       TestEmailBase):

    policy = TestEmailBase.email5_policy


class TestBytesGeneratorNonASCIIEmail6(TestBytesGeneratorNonASCII,
                                       TestEmailBase):

    policy = TestEmailBase.email6_policy


if __name__ == '__main__':
    unittest.main()
