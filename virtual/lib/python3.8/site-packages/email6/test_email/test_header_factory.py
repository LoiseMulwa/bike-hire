import unittest
from email6 import header
from email6.test_email import TestEmailBase


class TestHeaderFactory(TestEmailBase):

    def test_arbitrary_name_unstructured(self):
        factory = header.HeaderFactory()
        h = factory('foobar', 'test', 'test')
        self.assertIsInstance(h, header.BaseHeader)
        self.assertIsInstance(h, header.UnstructuredHeader)

    def test_name_case_ignored(self):
        factory = header.HeaderFactory()
        # Whitebox check that test is valid
        self.assertNotIn('Subject', factory.registry)
        h = factory('Subject', 'test', 'test')
        self.assertIsInstance(h, header.BaseHeader)
        self.assertIsInstance(h, header.UniqueUnstructuredHeader)

    class FooBase:
        def __init__(self, *args, **kw):
            pass

    def test_override_default_base_class(self):
        factory = header.HeaderFactory(base_class=self.FooBase)
        h = factory('foobar', 'test', 'test')
        self.assertIsInstance(h, self.FooBase)
        self.assertIsInstance(h, header.UnstructuredHeader)

    class FooDefault:
        parse = header.UnstructuredHeader.parse

    def test_override_default_class(self):
        factory = header.HeaderFactory(default_class=self.FooDefault)
        h = factory('foobar', 'test', 'test')
        self.assertIsInstance(h, header.BaseHeader)
        self.assertIsInstance(h, self.FooDefault)

    def test_override_default_class_only_overrides_default(self):
        factory = header.HeaderFactory(default_class=self.FooDefault)
        h = factory('subject', 'test', 'test')
        self.assertIsInstance(h, header.BaseHeader)
        self.assertIsInstance(h, header.UniqueUnstructuredHeader)

    def test_dont_use_default_map(self):
        factory = header.HeaderFactory(use_default_map=False)
        h = factory('subject', 'test', 'test')
        self.assertIsInstance(h, header.BaseHeader)
        self.assertIsInstance(h, header.UnstructuredHeader)

    def test_map_to_type(self):
        factory = header.HeaderFactory()
        h1 = factory('foobar', 'test', 'test')
        factory.map_to_type('foobar', header.UniqueUnstructuredHeader)
        h2 = factory('foobar', 'test', 'test')
        self.assertIsInstance(h1, header.BaseHeader)
        self.assertIsInstance(h1, header.UnstructuredHeader)
        self.assertIsInstance(h2, header.BaseHeader)
        self.assertIsInstance(h2, header.UniqueUnstructuredHeader)


if __name__ == '__main__':
    unittest.main()
