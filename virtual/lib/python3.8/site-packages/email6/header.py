# Copyright (C) 2002-2007 Python Software Foundation
# Author: Ben Gertzfield, Barry Warsaw
# Contact: email-sig@python.org

"""Header encoding and decoding functionality."""

__all__ = [
    'Header',
    'decode_header',
    'make_header',
    ]

import re
import binascii
import warnings
import datetime

from email6 import utils
from email6 import errors
from email6 import charset as _charset
from email6 import quoprimime
from email6 import base64mime
from email6 import _header_value_parser as parser
Charset = _charset.Charset

NL = '\n'
SPACE = ' '
BSPACE = b' '
SPACE8 = ' ' * 8
EMPTYSTRING = ''
MAXLINELEN = 78
FWS = ' \t'

USASCII = Charset('us-ascii')
UTF8 = Charset('utf-8')

# Match encoded-word strings in the form =?charset?q?Hello_World?=
ecre = re.compile(r'''
  =\?                   # literal =?
  (?P<charset>[^?]*?)   # non-greedy up to the next ? is the charset
  \?                    # literal ?
  (?P<encoding>[qb])    # either a "q" or a "b", case insensitive
  \?                    # literal ?
  (?P<encoded>.*?)      # non-greedy up to the next ?= is the encoded string
  \?=                   # literal ?=
  (?=[ \t]|$)           # whitespace or the end of the string
  ''', re.VERBOSE | re.IGNORECASE | re.MULTILINE)

# Field name regexp, including trailing colon, but not separating whitespace,
# according to RFC 2822.  Character range is from tilde to exclamation mark.
# For use with .match()
fcre = re.compile(r'[\041-\176]+:$')

# Find a header embedded in a putative header value.  Used to check for
# header injection attack.
_embeded_header = re.compile(r'\n[^ \t]+:')



# Helpers
_max_append = quoprimime._max_append



def decode_header(header):
    """Decode a message header value without converting charset.

    Returns a list of (string, charset) pairs containing each of the decoded
    parts of the header.  Charset is None for non-encoded parts of the header,
    otherwise a lower-case string containing the name of the character set
    specified in the encoded string.

    header may be a string that may or may not contain RFC2047 encoded words,
    or it may be a Header object.

    An email.errors.HeaderParseError may be raised when certain decoding error
    occurs (e.g. a base64 decoding exception).
    """
    # If it is a Header object, we can just return the encoded chunks.
    if hasattr(header, '_chunks'):
        return [(_charset._encode(string, str(charset)), str(charset))
                    for string, charset in header._chunks]
    # If no encoding, just return the header with no charset.
    if not ecre.search(header):
        return [(header, None)]
    # First step is to parse all the encoded parts into triplets of the form
    # (encoded_string, encoding, charset).  For unencoded strings, the last
    # two parts will be None.
    words = []
    for line in header.splitlines():
        parts = ecre.split(line)
        while parts:
            unencoded = parts.pop(0).strip()
            if unencoded:
                words.append((unencoded, None, None))
            if parts:
                charset = parts.pop(0).lower()
                encoding = parts.pop(0).lower()
                encoded = parts.pop(0)
                words.append((encoded, encoding, charset))
    # The next step is to decode each encoded word by applying the reverse
    # base64 or quopri transformation.  decoded_words is now a list of the
    # form (decoded_word, charset).
    decoded_words = []
    for encoded_string, encoding, charset in words:
        if encoding is None:
            # This is an unencoded word.
            decoded_words.append((encoded_string, charset))
        elif encoding == 'q':
            word = quoprimime.header_decode(encoded_string)
            decoded_words.append((word, charset))
        elif encoding == 'b':
            paderr = len(encoded_string) % 4   # Postel's law: add missing padding
            if paderr:
                encoded_string += '==='[:4 - paderr]
            try:
                word = base64mime.decode(encoded_string)
            except binascii.Error:
                raise errors.HeaderParseError('Base64 decoding error')
            else:
                decoded_words.append((word, charset))
        else:
            raise AssertionError('Unexpected encoding: ' + encoding)
    # Now convert all words to bytes and collapse consecutive runs of
    # similarly encoded words.
    collapsed = []
    last_word = last_charset = None
    for word, charset in decoded_words:
        if isinstance(word, str):
            word = bytes(word, 'raw-unicode-escape')
        if last_word is None:
            last_word = word
            last_charset = charset
        elif charset != last_charset:
            collapsed.append((last_word, last_charset))
            last_word = word
            last_charset = charset
        elif last_charset is None:
            last_word += BSPACE + word
        else:
            last_word += word
    collapsed.append((last_word, last_charset))
    return collapsed



def make_header(decoded_seq, maxlinelen=None, header_name=None,
                continuation_ws=' '):
    """Create a Header from a sequence of pairs as returned by decode_header()

    decode_header() takes a header value string and returns a sequence of
    pairs of the format (decoded_string, charset) where charset is the string
    name of the character set.

    This function takes one of those sequence of pairs and returns a Header
    instance.  Optional maxlinelen, header_name, and continuation_ws are as in
    the Header constructor.
    """
    h = Header(maxlinelen=maxlinelen, header_name=header_name,
               continuation_ws=continuation_ws)
    for s, charset in decoded_seq:
        # None means us-ascii but we can simply pass it on to h.append()
        if charset is not None and not isinstance(charset, Charset):
            charset = Charset(charset)
        h.append(s, charset)
    return h



class Header:
    def __init__(self, s=None, charset=None,
                 maxlinelen=None, header_name=None,
                 continuation_ws=' ', errors='strict'):
        """Create a MIME-compliant header that can contain many character sets.

        Optional s is the initial header value.  If None, the initial header
        value is not set.  You can later append to the header with .append()
        method calls.  s may be a byte string or a Unicode string, but see the
        .append() documentation for semantics.

        Optional charset serves two purposes: it has the same meaning as the
        charset argument to the .append() method.  It also sets the default
        character set for all subsequent .append() calls that omit the charset
        argument.  If charset is not provided in the constructor, the us-ascii
        charset is used both as s's initial charset and as the default for
        subsequent .append() calls.

        The maximum line length can be specified explicitly via maxlinelen. For
        splitting the first line to a shorter value (to account for the field
        header which isn't included in s, e.g. `Subject') pass in the name of
        the field in header_name.  The default maxlinelen is 78 as recommended
        by RFC 2822.

        continuation_ws must be RFC 2822 compliant folding whitespace (usually
        either a space or a hard tab) which will be prepended to continuation
        lines.

        errors is passed through to the .append() call.
        """
        if charset is not None and not isinstance(charset, Charset):
            charset = Charset(charset)
        self._charset = charset
        self._continuation_ws = continuation_ws
        self._chunks = []
        if s is not None:
            self.append(s, charset, errors)
        if maxlinelen is None:
            maxlinelen = MAXLINELEN
        self._maxlinelen = maxlinelen
        if header_name is None:
            self._headerlen = 0
        else:
            # Take the separating colon and space into account.
            self._headerlen = len(header_name) + 2
        self.name = header_name

    def __str__(self):
        """Return the string value of the header."""
        self._normalize()
        uchunks = []
        lastcs = None
        for string, charset in self._chunks:
            # We must preserve spaces between encoded and non-encoded word
            # boundaries, which means for us we need to add a space when we go
            # from a charset to None/us-ascii, or from None/us-ascii to a
            # charset.  Only do this for the second and subsequent chunks.
            nextcs = charset
            if nextcs == _charset.UNKNOWN8BIT:
                original_bytes = string.encode('ascii', 'surrogateescape')
                string = original_bytes.decode('ascii', 'replace')
            if uchunks:
                if lastcs not in (None, 'us-ascii'):
                    if nextcs in (None, 'us-ascii'):
                        uchunks.append(SPACE)
                        nextcs = None
                elif nextcs not in (None, 'us-ascii'):
                    uchunks.append(SPACE)
            lastcs = nextcs
            uchunks.append(string)
        return EMPTYSTRING.join(uchunks)

    # Rich comparison operators for equality only.  BAW: does it make sense to
    # have or explicitly disable <, <=, >, >= operators?
    def __eq__(self, other):
        # other may be a Header or a string.  Both are fine so coerce
        # ourselves to a unicode (of the unencoded header value), swap the
        # args and do another comparison.
        return other == str(self)

    def __ne__(self, other):
        return not self == other

    def append(self, s, charset=None, errors='strict'):
        """Append a string to the MIME header.

        Optional charset, if given, should be a Charset instance or the name
        of a character set (which will be converted to a Charset instance).  A
        value of None (the default) means that the charset given in the
        constructor is used.

        s may be a byte string or a Unicode string.  If it is a byte string
        (i.e. isinstance(s, str) is false), then charset is the encoding of
        that byte string, and a UnicodeError will be raised if the string
        cannot be decoded with that charset.  If s is a Unicode string, then
        charset is a hint specifying the character set of the characters in
        the string.  In either case, when producing an RFC 2822 compliant
        header using RFC 2047 rules, the string will be encoded using the
        output codec of the charset.  If the string cannot be encoded to the
        output codec, a UnicodeError will be raised.

        Optional `errors' is passed as the errors argument to the decode
        call if s is a byte string.
        """
        if charset is None:
            charset = self._charset
        elif not isinstance(charset, Charset):
            charset = Charset(charset)
        if not isinstance(s, str):
            if charset is None:
                charset = USASCII
            input_charset = charset.input_codec or 'us-ascii'
            if input_charset == _charset.UNKNOWN8BIT:
                s = s.decode('us-ascii', 'surrogateescape')
            else:
                s = s.decode(input_charset, errors)
        elif charset is None:
            # If there are non-ASCII characters and no specified encoding,
            # default to utf-8.
            try:
                s.encode('us-ascii')
                charset = USASCII
            except UnicodeEncodeError:
                charset = UTF8
        # Ensure that the bytes we're storing can be encoded to the output
        # character set, otherwise an early error is thrown.
        output_charset = charset.output_codec or 'us-ascii'
        if output_charset != _charset.UNKNOWN8BIT:
            s.encode(output_charset, errors)
        self._chunks.append((s, charset))

    def encode(self, splitchars=';, \t', maxlinelen=None, linesep='\n'):
        r"""Encode a message header into an RFC-compliant format.

        There are many issues involved in converting a given string for use in
        an email header.  Only certain character sets are readable in most
        email clients, and as header strings can only contain a subset of
        7-bit ASCII, care must be taken to properly convert and encode (with
        Base64 or quoted-printable) header strings.  In addition, there is a
        75-character length limit on any given encoded header field, so
        line-wrapping must be performed, even with double-byte character sets.

        Optional maxlinelen specifies the maximum length of each generated
        line, exclusive of the linesep string.  Individual lines may be longer
        than maxlinelen if a folding point cannot be found.  The first line
        will be shorter by the length of the header name plus ": " if a header
        name was specified at Header construction time.  The default value for
        maxlinelen is determined at header construction time.

        Optional splitchars is a string containing characters which should be
        given extra weight by the splitting algorithm during normal header
        wrapping.  This is in very rough support of RFC 2822's `higher level
        syntactic breaks':  split points preceded by a splitchar are preferred
        during line splitting, with the characters preferred in the order in
        which they appear in the string.  Space and tab may be included in the
        string to indicate whether preference should be given to one over the
        other as a split point when other split chars do not appear in the line
        being split.  Splitchars does not affect RFC 2047 encoded lines.

        Optional linesep is a string to be used to separate the lines of
        the value.  The default value is the most useful for typical
        Python applications, but it can be set to \r\n to produce RFC-compliant
        line separators when needed.
        """
        self._normalize()
        if maxlinelen is None:
            maxlinelen = self._maxlinelen
        # A maxlinelen of 0 means don't wrap.  For all practical purposes,
        # choosing a huge number here accomplishes that and makes the
        # _ValueFormatter algorithm much simpler.
        if maxlinelen == 0:
            maxlinelen = 1000000
        formatter = _ValueFormatter(self._headerlen, maxlinelen,
                                    self._continuation_ws, splitchars)
        for string, charset in self._chunks:
            lines = string.splitlines()
            if lines:
                formatter.feed('', lines[0], charset)
            else:
                formatter.feed('', '', charset)
            for line in lines[1:]:
                formatter.newline()
                if charset.header_encoding is not None:
                    formatter.feed(self._continuation_ws, ' ' + line.lstrip(),
                                   charset)
                else:
                    sline = line.lstrip()
                    fws = line[:len(line)-len(sline)]
                    formatter.feed(fws, sline, charset)
            if len(lines) > 1:
                formatter.newline()
            formatter.add_transition()
        value = formatter._str(linesep)
        if _embeded_header.search(value):
            raise errors.HeaderParseError("header value appears to contain "
                "an embedded header: {!r}".format(value))
        return value

    def _normalize(self):
        # Step 1: Normalize the chunks so that all runs of identical charsets
        # get collapsed into a single unicode string.
        chunks = []
        last_charset = None
        last_chunk = []
        for string, charset in self._chunks:
            if charset == last_charset:
                last_chunk.append(string)
            else:
                if last_charset is not None:
                    chunks.append((SPACE.join(last_chunk), last_charset))
                last_chunk = [string]
                last_charset = charset
        if last_chunk:
            chunks.append((SPACE.join(last_chunk), last_charset))
        self._chunks = chunks



class _ValueFormatter:
    def __init__(self, headerlen, maxlen, continuation_ws, splitchars):
        self._maxlen = maxlen
        self._continuation_ws = continuation_ws
        self._continuation_ws_len = len(continuation_ws)
        self._splitchars = splitchars
        self._lines = []
        self._current_line = _Accumulator(headerlen)

    def _str(self, linesep):
        self.newline()
        return linesep.join(self._lines)

    def __str__(self):
        return self._str(NL)

    def newline(self):
        end_of_line = self._current_line.pop()
        if end_of_line != (' ', ''):
            self._current_line.push(*end_of_line)
        if len(self._current_line) > 0:
            if self._current_line.is_onlyws():
                self._lines[-1] += str(self._current_line)
            else:
                self._lines.append(str(self._current_line))
        self._current_line.reset()

    def add_transition(self):
        self._current_line.push(' ', '')

    def feed(self, fws, string, charset):
        # If the charset has no header encoding (i.e. it is an ASCII encoding)
        # then we must split the header at the "highest level syntactic break"
        # possible. Note that we don't have a lot of smarts about field
        # syntax; we just try to break on semi-colons, then commas, then
        # whitespace.  Eventually, this should be pluggable.
        if charset.header_encoding is None:
            self._ascii_split(fws, string, self._splitchars)
            return
        # Otherwise, we're doing either a Base64 or a quoted-printable
        # encoding which means we don't need to split the line on syntactic
        # breaks.  We can basically just find enough characters to fit on the
        # current line, minus the RFC 2047 chrome.  What makes this trickier
        # though is that we have to split at octet boundaries, not character
        # boundaries but it's only safe to split at character boundaries so at
        # best we can only get close.
        encoded_lines = charset.header_encode_lines(string, self._maxlengths())
        # The first element extends the current line, but if it's None then
        # nothing more fit on the current line so start a new line.
        try:
            first_line = encoded_lines.pop(0)
        except IndexError:
            # There are no encoded lines, so we're done.
            return
        if first_line is not None:
            self._append_chunk(fws, first_line)
        try:
            last_line = encoded_lines.pop()
        except IndexError:
            # There was only one line.
            return
        self.newline()
        self._current_line.push(self._continuation_ws, last_line)
        # Everything else are full lines in themselves.
        for line in encoded_lines:
            self._lines.append(self._continuation_ws + line)

    def _maxlengths(self):
        # The first line's length.
        yield self._maxlen - len(self._current_line)
        while True:
            yield self._maxlen - self._continuation_ws_len

    def _ascii_split(self, fws, string, splitchars):
        # The RFC 2822 header folding algorithm is simple in principle but
        # complex in practice.  Lines may be folded any place where "folding
        # white space" appears by inserting a linesep character in front of the
        # FWS.  The complication is that not all spaces or tabs qualify as FWS,
        # and we are also supposed to prefer to break at "higher level
        # syntactic breaks".  We can't do either of these without intimate
        # knowledge of the structure of structured headers, which we don't have
        # here.  So the best we can do here is prefer to break at the specified
        # splitchars, and hope that we don't choose any spaces or tabs that
        # aren't legal FWS.  (This is at least better than the old algorithm,
        # where we would sometimes *introduce* FWS after a splitchar, or the
        # algorithm before that, where we would turn all white space runs into
        # single spaces or tabs.)
        parts = re.split("(["+FWS+"]+)", fws+string)
        if parts[0]:
            parts[:0] = ['']
        else:
            parts.pop(0)
        for fws, part in zip(*[iter(parts)]*2):
            self._append_chunk(fws, part)

    def _append_chunk(self, fws, string):
        self._current_line.push(fws, string)
        if len(self._current_line) > self._maxlen:
            # Find the best split point, working backward from the end.
            # There might be none, on a long first line.
            for ch in self._splitchars:
                for i in range(self._current_line.part_count()-1, 0, -1):
                    if ch.isspace():
                        fws = self._current_line[i][0]
                        if fws and fws[0]==ch:
                            break
                    prevpart = self._current_line[i-1][1]
                    if prevpart and prevpart[-1]==ch:
                        break
                else:
                    continue
                break
            else:
                fws, part = self._current_line.pop()
                if self._current_line._initial_size > 0:
                    # There will be a header, so leave it on a line by itself.
                    self.newline()
                    if not fws:
                        # We don't use continuation_ws here because the whitespace
                        # after a header should always be a space.
                        fws = ' '
                self._current_line.push(fws, part)
                return
            remainder = self._current_line.pop_from(i)
            self._lines.append(str(self._current_line))
            self._current_line.reset(remainder)


class _Accumulator(list):

    def __init__(self, initial_size=0):
        self._initial_size = initial_size
        super().__init__()

    def push(self, fws, string):
        self.append((fws, string))

    def pop_from(self, i=0):
        popped = self[i:]
        self[i:] = []
        return popped

    def pop(self):
        if self.part_count()==0:
            return ('', '')
        return super().pop()

    def __len__(self):
        return sum((len(fws)+len(part) for fws, part in self),
                   self._initial_size)

    def __str__(self):
        return EMPTYSTRING.join((EMPTYSTRING.join((fws, part))
                                for fws, part in self))

    def reset(self, startval=None):
        if startval is None:
            startval = []
        self[:] = startval
        self._initial_size = 0

    def is_onlyws(self):
        return self._initial_size==0 and (not self or str(self).isspace())

    def part_count(self):
        return super().__len__()


#### New style Headers ####

# Address Support Classes #

class Address(str):

    def __new__(cls, value, name, username, domain, defects):
        self = str.__new__(cls, value)
        self._name = name if name is not None else ''
        self._username = username if username is not None else ''
        self._domain = domain if domain is not None else ''
        self._defects = tuple(defects)
        return self

    @property
    def name(self):
        return self._name

    @property
    def username(self):
        return self._username

    @property
    def domain(self):
        return self._domain

    @property
    def defects(self):
        return self._defects

    @property
    def addr_spec(self):
        nameset = set(self.username)
        if len(nameset) > len(nameset-parser.ATOM_ENDS):
            lp = parser.quote_string(self.username)
        else:
            lp = self.username
        if self.domain:
            return lp + '@' + self.domain
        return lp

    @property
    def reformatted(self):
        nameset = set(self.name)
        if len(nameset) > len(nameset-parser.SPECIALS):
            disp = parser.quote_string(self.name)
        else:
            disp = self.name
        if disp:
            return "{} <{}>".format(disp, self.addr_spec)
        return self.addr_spec if self.addr_spec else ''

    def __getnewargs__(self):
        return (str(self), self.name, self.username, self.domain, self.defects)


class Group(str):

    def __new__(cls, value, name, addresses):
        self = str.__new__(cls, value)
        self._name = name
        self._addresses = tuple(addresses)
        return self

    @property
    def name(self):
        return self._name

    @property
    def addresses(self):
        return self._addresses

    def __getnewargs__(self):
        return (str(self), self.name, self.addresses)


# Header Classes #

class BaseHeader(str):

    """Base class for message headers.

    Implements generic behavior and provides tools for subclasses.

    A subclass must define a classmethod named 'parse' that takes an unfolded
    value string and a dictionary as its arguments.  The dictionary will
    contain one key, 'defects', initialized to an empty list.  After the call
    the dictionary must contain an additional key, 'decoded', set to the string
    value of the idealized representation of the data from the value.  (That
    is, encoded words are decoded, and values that have canonical
    representations are so represented.)

    The defects key is intended to collect parsing defects, which the message
    parser will subsequently dispose of as appropriate.  The parser should not,
    insofar as practical, raise any errors.  Defects should be added to the
    list instead.  The standard header parsers register defects for RFC
    compliance issues, for obsolete RFC syntax, and for unrecoverable parsing
    errors.

    The parse method may add additional keys to the dictionary.  In this case
    the subclass must define an 'init' method, which will be passed the
    dictionary as its keyword arguments.  The method should use (usually by
    setting them as the value of similarly named attributes) and remove all the
    extra keys added by its parse method, and then use super to call its parent
    class with the remaining arguments and keywords.

    The subclass should also make sure that a 'max_count' attribute is defined
    that is either None or 1. XXX: need to better define this API.

    """

    def __new__(cls, name, unparsed, unfolded=None, *, use_decoded=False):
        # If unfolded is None then 'unparsed' comes from an application
        # program, if it is not None then unfolded comes from a parse of some
        # sort of source data, and we save unparsed as the source value.  When the
        # unparsed value comes from an application program it may not be a string.
        #
        # XXX: Currently we can have up to three copies of the header value.
        # We can reduce this to two copies plus some metadata, at a slight cost
        # in speed, but to do so now would be a premature optimization.
        if isinstance(unparsed, str):
            lines = unparsed.splitlines()
            has_ec = ecre.search(unparsed)
            source = unparsed
            if len(lines) > 1 or has_ec:
                # Deprecation plan: in 3.4 direct assignment of a folded/encoded
                # value becomes an error, so the only way to set one as the value
                # is to specify the unfolded arg.  In 3.4 the value being the decoded
                # header will be the default, and has_ec can go away here.
                if unfolded is None:
                    source = None
                    warnings.warn("Direct assignment of header values containing "
                        "linesep characters or encoded words is deprecated.",
                        DeprecationWarning, 5)
                    unfolded = ''.join(lines)
            elif unfolded is None:
                source = None
                unfolded = unparsed
        else:
            has_ec = False
            use_decoded = True
            source = None
            unfolded = unparsed
        kwds = {'defects': []}
        cls.parse(unfolded, kwds)
        self = str.__new__(cls, kwds['decoded'] if use_decoded else unparsed)
        self.init(name, source=source, **kwds)
        return self

    def init(self, name, *, source, decoded, defects):
        self._name = name
        self._source = source
        self._value = decoded
        self._defects = defects

    @property
    def name(self):
        return self._name

    @property
    def source(self):
        return self._source

    @property
    def value(self):
        return self._value

    @property
    def defects(self):
        return tuple(self._defects)

    def __reduce__(self):
        return (
            _reconstruct_header,
            (
                self.__class__.__name__,
                self.__class__.__bases__,
                str(self),
            ),
            self.__dict__)

    @classmethod
    def _reconstruct(cls, value):
        return str.__new__(cls, value)


def _reconstruct_header(cls_name, bases, value):
    return type(cls_name, bases, {})._reconstruct(value)


class UnstructuredHeader:

    max_count = None

    @classmethod
    def parse(cls, value, kwds):
        kwds['decoded'] = str(parser.get_unstructured(value))


class UniqueUnstructuredHeader(UnstructuredHeader):

    max_count = 1


class DateHeader:

    """Header whose value consists of a single timestamp.

    Provides an additional attribute, datetime, which is either an aware
    datetime using a timezone, or a naive datetime if the timezone
    in the input string is -0000.  Also accepts a datetime as input.
    The 'value' attribute is the normalized form of the timestamp,
    which means it is the output of format_datetime on the datetime.
    """

    max_count = None

    @classmethod
    def parse(cls, value, kwds):
        if not value:
            kwds['defects'].append(errors.HeaderMissingRequiredValue())
            kwds['datetime'] = None
            kwds['decoded'] = ''
            return
        if isinstance(value, str):
            *dtuple, tz = utils.parsedate_tz(value)
            value = datetime.datetime(*dtuple[:6],
                tzinfo=datetime.timezone(datetime.timedelta(seconds=tz)))
        kwds['datetime'] = value
        kwds['decoded'] = utils.format_datetime(kwds['datetime'])

    def init(self, *args, **kw):
        self._datetime = kw.pop('datetime')
        super().init(*args, **kw)

    @property
    def datetime(self):
        return self._datetime


class UniqueDateHeader(DateHeader):

    max_count = 1


class AddressHeader:

    max_count = None

    @classmethod
    def parse(cls, value, kwds):
        # We are translating here from the RFC language (address/mailbox)
        # to our API language (group/address).
        address_list, value = parser.get_address_list(value)
        assert not value
        #self.structured_ew_decode(address_list)
        groups = []
        for addr in address_list.addresses:
            groups.append(Group(str(addr).lstrip(),
                                addr.display_name,
                                [Address(str(mb).lstrip(),
                                         mb.display_name,
                                         mb.local_part,
                                         mb.domain,
                                         mb.all_defects)
                                 for mb in addr.all_mailboxes]))
        kwds['groups'] = groups
        # The 'Address' object generates no defects, so all defects are on the
        # mailbox objects except those on address_list itself.
        kwds['defects'] = list(address_list.all_defects)
        kwds['decoded'] = ', '.join([str(item) for item in groups])

    def init(self, *args, **kw):
        self._groups = kw.pop('groups')
        self._flattened = tuple(self._flatten())
        super().init(*args, **kw)

    @property
    def groups(self):
        return tuple(self._groups)

    @property
    def addresses(self):
        return tuple(self._flattened)

    def _flatten(self):
        for group in self._groups:
            for address in group.addresses:
                yield address


class UniqueAddressHeader(AddressHeader):

    max_count = 1


class SingleAddressHeader(AddressHeader):

    @property
    def address(self):
        if len(self.addresses)!=1:
            raise ValueError(("value of single address header {} is not "
                "a single address").format(self.name))
        return self.addresses[0]


class UniqueSingleAddressHeader(SingleAddressHeader):

    max_count = 1


# The header factory #

_default_header_map = {
    'subject':          UniqueUnstructuredHeader,
    'date':             UniqueDateHeader,
    'resent-date':      DateHeader,
    'orig-date':        UniqueDateHeader,
    'sender':           UniqueSingleAddressHeader,
    'resent-sender':    SingleAddressHeader,
    'to':               UniqueAddressHeader,
    'resent-to':        AddressHeader,
    'cc':               UniqueAddressHeader,
    'resent-cc':        AddressHeader,
    'bcc':              UniqueAddressHeader,
    'resent-bcc':       AddressHeader,
    'from':             UniqueAddressHeader,
    'resent-from':      AddressHeader,
    'reply-to':         UniqueAddressHeader,
    }

class HeaderFactory:

    """A header_factory and header registry."""

    def __init__(self, base_class=BaseHeader, default_class=UnstructuredHeader,
                       use_default_map=True):
        """Create a header_factory that works with the Policy API.

        base_class is the class that will be the last class in the created
        header class's __bases__ list.  default_class is the class that will be
        used if "name" (see __call__) does not appear in the registry.
        use_default_map controls whether or not the default mapping of names to
        specialized classes is copied in to the registry when the factory is
        created.  The default is True.

        """
        self.registry = {}
        self.base_class = base_class
        self.default_class = default_class
        if use_default_map:
            self.registry.update(_default_header_map)

    def map_to_type(self, name, cls):
        """Register cls as the specialized class for handling "name" headers.

        """
        self.registry[name.lower()] = cls

    def __getitem__(self, name):
        cls = self.registry.get(name.lower(), self.default_class)
        return type('_'+cls.__name__, (cls, self.base_class), {})

    def __call__(self, name, unparsed, unfolded=None, use_decoded=False):
        """Create a header instance for header "name".

        Creates a header instance by creating a specialized class for parsing
        and representing the specified header by combining the factory
        base_class with a specialized class from the registry or the
        default_class, and passing the name, unparsed, unfolded, and
        use_decoded arguments to the constructed class's constructor.

        """
        return self[name](name, unparsed, unfolded, use_decoded=use_decoded)
