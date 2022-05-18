import types
import unittest
from email6 import header
from email6 import policy as _policy

class PolicyAPITests(unittest.TestCase):

    longMessage = True

    # These default values are the ones set on _policy.default.
    # If any of these defaults change, the docs must be updated.
    policy_defaults = {
        'max_line_length':          78,
        'linesep':                  '\n',
        'must_be_7bit':             False,
        'raise_on_defect':          False,
        'decoded_headers':           None,
        'header_factory':           _policy.Policy.header_factory,
        }

    policies = [
        _policy.Policy(),
        _policy.default,
        _policy.SMTP,
        _policy.HTTP,
        _policy.strict,
        _policy.email5_defaults,
        _policy.email6_defaults,
        ]

    def settings_test(self, policy, changed_from_default):
        expected = self.policy_defaults.copy()
        expected.update(changed_from_default)
        for attr, value in expected.items():
            self.assertEqual(getattr(policy, attr), value,
                            ("change docs/docstrings if defaults have changed"))

    def test_new_policy(self):
        new_policy = _policy.Policy()
        self.settings_test(new_policy, {'header_factory': new_policy.header_factory})

    def test_default_policy(self):
        self.settings_test(_policy.default, {})

    def test_SMTP_policy(self):
        self.settings_test(_policy.SMTP, {'linesep': '\r\n'})

    def test_HTTP_policy(self):
        self.settings_test(_policy.HTTP, {'linesep': '\r\n',
                                               'max_line_length': None})

    def test_strict_policy(self):
        self.settings_test(_policy.strict, {'raise_on_defect': True})

    def test_email5_defaults_policy(self):
        self.settings_test(_policy.email5_defaults,
                            {'decoded_headers': False})

    def test_email6_defaults_policy(self):
        self.settings_test(_policy.email6_defaults,
                            {'decoded_headers': True})

    def test_all_attributes_covered(self):
        for attr in dir(_policy.default):
            if (attr.startswith('_') or
               isinstance(getattr(_policy.Policy, attr),
                          types.FunctionType)):
                continue
            else:
                self.assertIn(attr, self.policy_defaults,
                              "{} is not fully tested".format(attr))

    def test_policy_is_immutable(self):
        for policy in self.policies:
            for attr in self.policy_defaults:
                with self.assertRaisesRegex(AttributeError, attr+".*read-only"):
                    setattr(policy, attr, None)
            with self.assertRaisesRegex(AttributeError, 'no attribute.*foo'):
                policy.foo = None

    def test_set_policy_attrs_when_cloned(self):
        testattrdict = { attr: None for attr in self.policy_defaults }
        for policyclass in self.policies:
            policy = policyclass.clone(**testattrdict)
            for attr in self.policy_defaults:
                self.assertIsNone(getattr(policy, attr))

    def test_reject_non_policy_keyword_when_cloned(self):
        for policyclass in self.policies:
            with self.assertRaises(TypeError):
                policyclass.clone(this_keyword_should_not_be_valid=None)
            with self.assertRaises(TypeError):
                policyclass.clone(newtline=None)

    def test_policy_addition(self):
        expected = self.policy_defaults.copy()
        p1 = _policy.default.clone(max_line_length=100)
        p2 = _policy.default.clone(max_line_length=50)
        added = p1 + p2
        expected.update(max_line_length=50)
        for attr, value in expected.items():
            self.assertEqual(getattr(added, attr), value)
        added = p2 + p1
        expected.update(max_line_length=100)
        for attr, value in expected.items():
            self.assertEqual(getattr(added, attr), value)
        added = added + _policy.default
        for attr, value in expected.items():
            self.assertEqual(getattr(added, attr), value)

    def test_register_defect(self):
        class Dummy:
            def __init__(self):
                self.defects = []
        obj = Dummy()
        defect = object()
        policy = _policy.Policy()
        policy.register_defect(obj, defect)
        self.assertEqual(obj.defects, [defect])
        defect2 = object()
        policy.register_defect(obj, defect2)
        self.assertEqual(obj.defects, [defect, defect2])

    class MyObj:
        def __init__(self):
            self.defects = []

    class MyDefect(Exception):
        pass

    def test_handle_defect_raises_on_strict(self):
        foo = self.MyObj()
        defect = self.MyDefect("the telly is broken")
        with self.assertRaisesRegex(self.MyDefect, "the telly is broken"):
            _policy.strict.handle_defect(foo, defect)

    def test_handle_defect_registers_defect(self):
        foo = self.MyObj()
        defect1 = self.MyDefect("one")
        _policy.default.handle_defect(foo, defect1)
        self.assertEqual(foo.defects, [defect1])
        defect2 = self.MyDefect("two")
        _policy.default.handle_defect(foo, defect2)
        self.assertEqual(foo.defects, [defect1, defect2])

    class MyPolicy(_policy.Policy):
        defects = []
        def register_defect(self, obj, defect):
            self.defects.append(defect)

    def test_overridden_register_defect_still_raises(self):
        foo = self.MyObj()
        defect = self.MyDefect("the telly is broken")
        with self.assertRaisesRegex(self.MyDefect, "the telly is broken"):
            self.MyPolicy(raise_on_defect=True).handle_defect(foo, defect)

    def test_overriden_register_defect_works(self):
        foo = self.MyObj()
        defect1 = self.MyDefect("one")
        my_policy = self.MyPolicy()
        my_policy.handle_defect(foo, defect1)
        self.assertEqual(my_policy.defects, [defect1])
        self.assertEqual(foo.defects, [])
        defect2 = self.MyDefect("two")
        my_policy.handle_defect(foo, defect2)
        self.assertEqual(my_policy.defects, [defect1, defect2])
        self.assertEqual(foo.defects, [])

    def test_default_header_factory(self):
        h = _policy.default.header_factory('Test', 'test')
        self.assertEqual(h.name, 'Test')
        self.assertIsInstance(h, header.UnstructuredHeader)
        self.assertIsInstance(h, header.BaseHeader)

    class Foo:
        parse = header.UnstructuredHeader.parse

    def test_each_Policy_gets_unique_factory(self):
        policy1 = _policy.Policy()
        policy2 = _policy.Policy()
        policy1.header_factory.map_to_type('foo', self.Foo)
        h = policy1.header_factory('foo', 'test')
        self.assertIsInstance(h, self.Foo)
        self.assertNotIsInstance(h, header.UnstructuredHeader)
        h = policy2.header_factory('foo', 'test')
        self.assertNotIsInstance(h, self.Foo)
        self.assertIsInstance(h, header.UnstructuredHeader)

    def test_clone_copies_factory(self):
        policy1 = _policy.Policy()
        policy2 = policy1.clone()
        policy1.header_factory.map_to_type('foo', self.Foo)
        h = policy1.header_factory('foo', 'test')
        self.assertIsInstance(h, self.Foo)
        h = policy2.header_factory('foo', 'test')
        self.assertIsInstance(h, self.Foo)

    def test_new_factory_overrides_default(self):
        mypolicy = _policy.Policy()
        myfactory = mypolicy.header_factory
        newpolicy = mypolicy + _policy.strict
        self.assertEqual(newpolicy.header_factory, myfactory)
        newpolicy = _policy.strict + mypolicy
        self.assertEqual(newpolicy.header_factory, myfactory)

    def test_adding_default_policies_prserves_default_factory(self):
        newpolicy = _policy.default + _policy.strict
        self.assertEqual(newpolicy.header_factory,
                         _policy.Policy.header_factory)
        self.assertEqual(newpolicy.__dict__, {'raise_on_defect': True})

    def test_make_header(self):
        with self.assertWarnsRegex(DeprecationWarning, 'decoded_headers'):
            h = _policy.default.make_header('Test', 'test', 'test')
        self.assertIsInstance(h, header.UnstructuredHeader)
        self.assertEqual(h.name, 'Test')
        self.assertEqual(h, 'test')

    def test_make_header_with_no_unfolded(self):
        h = _policy.default.make_header('Test', 'test')
        self.assertIsInstance(h, header.UnstructuredHeader)
        self.assertEqual(h.name, 'Test')
        self.assertEqual(h, 'test')
        self.assertIsNone(h.source)
        self.assertEqual(h.value, 'test')

    def test_make_header_sets_decoded(self):
        mypolicy1 = _policy.default.clone(decoded_headers=False)
        h = mypolicy1.make_header('Test', 'test\n test', 'test test')
        self.assertEqual(h, 'test\n test')
        mypolicy2 = _policy.default.clone(decoded_headers=True)
        h = mypolicy2.make_header('Test', 'test\n test', 'test test')
        self.assertEqual(h, 'test test')

    # XXX: Need subclassing tests.
    # For adding subclassed objects, make sure the usual rules apply (subclass
    # wins), but that the order still works (right overrides left).

if __name__ == '__main__':
    unittest.main()
