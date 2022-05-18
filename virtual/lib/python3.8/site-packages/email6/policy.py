"""Policy framework for the email package.

Allows fine grained feature control of how the package parses and emits data.
"""

import warnings
from email6 import header

__all__ = [
    'Policy',
    'default',
    'strict',
    'SMTP',
    'HTTP',
    ]


class _PolicyBase:

    """Policy Object basic framework.

    This class is useless unless subclassed.  A subclass should define
    class attributes with defaults for any values that are to be
    managed by the Policy object.  The constructor will then allow
    non-default values to be set for these attributes at instance
    creation time.  The instance will be callable, taking these same
    attributes keyword arguments, and returning a new instance
    identical to the called instance except for those values changed
    by the keyword arguments.  Instances may be added, yielding new
    instances with any non-default values from the right hand
    operand overriding those in the left hand operand.  That is,

        A + B == A(<non-default values of B>)

    The repr of an instance can be used to reconstruct the object
    if and only if the repr of the values can be used to reconstruct
    those values.

    """

    def __init__(self, **kw):
        """Create new Policy, possibly overriding some defaults.

        See class docstring for a list of overridable attributes.

        """
        for name, value in kw.items():
            if hasattr(self, name):
                object.__setattr__(self, name, value)
            else:
                raise TypeError(
                    "{!r} is an invalid keyword argument for {}".format(
                        name, self.__class__.__name__))

    def __repr__(self):
        args = [ "{}={!r}".format(name, value)
                 for name, value in self.__dict__.items() ]
        return "{}({})".format(self.__class__.__name__, args if args else '')

    def clone(self, **kw):
        """Return a new instance with specified attributes changed.

        The new instance has the same attribute values as the current object,
        except for the changes passed in as keyword arguments.

        """
        newpolicy = self.__class__.__new__(self.__class__)
        for attr, value in self.__dict__.items():
            object.__setattr__(newpolicy, attr, value)
        for attr, value in kw.items():
            if not hasattr(self, attr):
                raise TypeError(
                    "{!r} is an invalid keyword argument for {}".format(
                        attr, self.__class__.__name__))
            object.__setattr__(newpolicy, attr, value)
        return newpolicy

    def __setattr__(self, name, value):
        if hasattr(self, name):
            msg = "{!r} object attribute {!r} is read-only"
        else:
            msg = "{!r} object has no attribute {!r}"
        raise AttributeError(msg.format(self.__class__.__name__, name))

    def __add__(self, other):
        """Non-default values from right operand override those from left.

        The object returned is a new instance of the subclass.

        """
        return self.clone(**other.__dict__)


class Policy(_PolicyBase):

    """Controls for how messages are interpreted and formatted.

    Most of the classes and many of the methods in the email package
    accept Policy objects as parameters.  A Policy object contains a set
    of values and functions that control how input is interpreted and how
    output is rendered.  For example, the parameter 'raise_on_defect'
    controls whether or not an RFC violation throws an error or not,
    while 'max_line_length' controls the maximum length of output lines
    when a Message is serialized.

    Any valid attribute may be overridden when a Policy is created by
    passing it as a keyword argument to the constructor.  Policy
    objects are immutable, but a new Policy object can be created
    with only certain values changed by calling the Policy instance
    with keyword arguments.  Policy objects can also be added,
    producing a new Policy object in which the non-default attributes
    set in the right hand operand overwrite those specified in the
    left operand.

    Settable attributes:

    raise_on_defect     -- If true, then defects should be raised as errors.
                           Default False.

    linesep             -- string containing the value to use as separation
                           between output lines.  Default '\n'.

    must_be_7bit        -- output must contain only 7bit clean data.
                           Default False.

    max_line_length     -- maximum length of lines, excluding 'linesep',
                           during serialization.  None means no line wrapping
                           is done.  Default is 78.

    decoded_headers     -- if false (the default), the value of a header is
                           equal to the value of its 'source_value' attribute.
                           If True, the value of a header is equal to the value
                           of its 'decodeed' attribute.  In Python 3.4 the
                           default value of this attribute will become True.

    header_factory      -- a callable that can be used to create a new header
                           object given a name and a value.  See the header
                           documentation for details on the expected API.

    Methods:

    register_defect(obj, defect)
        defect is a Defect instance.  The default implementation appends defect
        to the objs 'defects' attribute.

    handle_defect(obj, defect)
        intended to be called by parser code that finds a defect.  If
        raise_on_defect is True, defect is raised as an error, otherwise
        register_defect is called.

    make_header(name, source_value, unfolded_value)
        intended to be called by parser code that identifies a header to be
        attached to a message objecct.  source_value is the value exactly as
        obtained from the source, unfolded_value is the the header with just
        the folding linesep characters removed.

    """

    raise_on_defect = False
    linesep = '\n'
    must_be_7bit = False
    max_line_length = 78
    decoded_headers = None
    header_factory = header.HeaderFactory()

    def __init__(self, **kw):
        if 'header_factory' not in kw:
            object.__setattr__(self, 'header_factory', header.HeaderFactory())
        _PolicyBase.__init__(self, **kw)

    def handle_defect(self, obj, defect):
        """Based on policy, either raise defect or call register_defect.

            handle_defect(obj, defect)

        defect should be a Defect subclass, but in any case must be an
        Exception subclass.  obj is the object on which the defect should be
        registered if it is not raised.  If the raise_on_defect is True, the
        defect is raised as an error, otherwise the object and the defect are
        passed to register_defect.

        This class is intended to be called by parsers that discover defects,
        and will not be called from code using the library unless that code is
        implementing an alternate parser.

        """
        if self.raise_on_defect:
            raise defect
        self.register_defect(obj, defect)

    def register_defect(self, obj, defect):
        """Record 'defect' on 'obj'.

        Called by handle_defect if raise_on_defect is False.  This method is
        part of the Policy API so that Policy subclasses can implement custom
        defect handling.  The default implementation calls the append method
        of the defects attribute of obj.

        """
        obj.defects.append(defect)

    def make_header(self, name, unparsed, unfolded=None):
        """Return a header object containing parsed data from the value.

        unparsed is the value obtained from the source data, including any
        linesep characters.  unfolded is the same value with just the folding
        linesep characters removed.  This parameter is separate because a
        parser may have more knowledge of actual message line breaks than would
        be apparent from examining the source_value string, specifically in the
        instance of a file containing both os.linesep strings and individual
        \\r or \\n characters.  Note that any such individual characters that
        are present in unfolded_value will be reported as RFC defects under the
        default policy.  If unfolded is None, unparsed should be a unicode
        string that does not contain encoded words or linesep characters.

        header_factory will be called with these three parameters, plus the value
        of the decoded_headers flag passed as the third parameter, use_decoded.

        """
        if unfolded is not None and self.decoded_headers is None:
            warnings.warn("The default for the decoded_headers policy option "
                "will change to True in Python 3.4", DeprecationWarning, 2)
        return self.header_factory(name, unparsed, unfolded,
                                   self.decoded_headers)

default = Policy()
# Make the default Policy use the class default.
del default.header_factory
strict = default.clone(raise_on_defect=True)
SMTP = default.clone(linesep='\r\n')
HTTP = default.clone(linesep='\r\n', max_line_length=None)
email5_defaults = default.clone(decoded_headers=False)
email6_defaults = default.clone(decoded_headers=True)
