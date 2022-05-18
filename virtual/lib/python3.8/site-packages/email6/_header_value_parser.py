"""Header value parser implementing various email-related RFC parsing rules.

The parsing methods defined in this module implement various email related
parsing rules.  Principal among them is RFC 5322, which is the followon
to RFC 2822 and primarily a clarification of the former.  It also implements
RFC 2047 encoded word decoding.

RFC 5322 goes to considerable trouble to maintain backward compatibility with
RFC 822 in the parse phase, while cleaning up the structure on the generation
phase.  This parser supports correct RFC 5322 generation by tagging white space
as folding white space only when folding is allowed in the non-obsolete rule
sets.  Actually, the parser is even more generous when accepting input than RFC
5322 mandates, following the spirit of Postel's Law, which RFC 5322 encourages.
Where possible deviations from the standard are annotated on the 'defects'
attribute of tokens that deviate.

The general structure of the parser follows RFC 5322, and uses its terminology
where there is a direct correspondence.  Where the implementation requires a
somewhat different structure than that used by the formal grammar, new terms
that mimic the closest existing terms are used.  Thus, it really helps to have
a copy of RFC 5322 handy when studying this code.

Input to the parser is a string that has already been unfolded according to
RFC 5322 rules.  According to the RFC this unfolding is the very first step, and
this parser leaves the unfolding step to a higher level message parser, which
will have already detected the line breaks that need unfolding while
determining the beginning and end of each header.

The output of the parser is a TokenList object, which is a list subclass.  A
TokenList is a recursive data structure.  The terminal nodes of the structure
are Terminal objects, which are subclasses of str.  These do not correspond
directly to terminal objects in the formal grammar, but are instead more
practical higher level combinations of true terminals.

All TokenList and Terminal objects have a 'value' attribute, which produces the
semantically meaningful value of that part of the parse subtree.  The value of
all whitespace tokens (no matter how many sub-tokens they may contain) is a
single space, as per the RFC rules.  This includes 'CFWS', which is herein
included in the general class of whitespace tokens.  There is one exception to
the rule that whitespace tokens are collapsed into single spaces in values: in
the value of a 'bare-quoted-string' (a quoted-string with no leading or
trailing whitespace), any whitespace that appeared between the quotation marks
is preserved in the returned value.  Note that in all Terminal strings quoted
pairs are turned into their unquoted values.

All TokenList and Terminal objects also have a string value, which attempts to
be a "canonical" representation of the RFC-compliant form of the substring that
produced the parsed subtree, including minimal use of quoted pair quoting.
Whitespace runs are not collapsed.

Comment tokens also have a 'content' attribute providing the string found
between the parens (including any nested comments) with whitespace preserved.

All TokenList and Terminal objects have a 'defects' attribute which is a
possibly empty list all of the defects found while creating the token.  Defects
may appear on any token in the tree, and a composite list of all defects in the
subtree is available through the 'all_defects' attribute of any node.  (For
Terminal notes x.defects == x.all_defects.)

Each object in a parse tree is called a 'token', and each has a 'token_type'
attribute that gives the name from the RFC 5322 grammar that it represents.
Not all RFC 5322 nodes are produced, and there is one non-RFC 5322 node that
may be produced: 'ptext'.  A 'ptext' is a string of printable ascii characters.
It is returned in place of lists of (ctext/quoted-pair) and
(qtext/quoted-pair).

XXX: provide complete list of token types.
"""

import re
from email6 import _encoded_words as _ew
from email6 import errors
from email6 import utils

#
# Useful constants and functions
#

WSP = set(' \t')
CFWS_LEADER = WSP | set('(')
SPECIALS = set(r'()<>@,:;.\"[]')
ATOM_ENDS = SPECIALS | WSP
# '.', '"', and '(' do not end phrases in order to support obs-phrase
PHRASE_ENDS = SPECIALS - set('."(')

def quote_string(value):
    return '"'+str(value).replace('\\', '\\\\').replace('"', r'\"')+'"'

#
# TokenList and its subclasses
#

class TokenList(list):

    token_type = None

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.defects = []

    def __str__(self):
        return ''.join(str(x) for x in self)

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__,
                             super().__repr__())

    @property
    def value(self):
        return ''.join(x.value for x in self if x.value)

    @property
    def all_defects(self):
        return sum((x.all_defects for x in self), self.defects)

    def pprint(self, indent=''):
        print('{}{}/{}('.format(
            indent,
            self.__class__.__name__,
            self.token_type))
        for token in self:
            token.pprint(indent+'    ')
        if self.defects:
            extra = ' Defects: {}'.format(self.defects)
        else:
            extra = ''
        print('{}){}'.format(indent, extra))


class WhiteSpaceTokenList(TokenList):

    @property
    def value(self):
        return ' '

    @property
    def comments(self):
        return [x.content for x in self if x.token_type=='comment']

class UnstructuredTokenList(TokenList):

    token_type = 'unstructured'


class Phrase(TokenList):

    token_type = 'phrase'


class Word(TokenList):

    token_type = 'word'


class CFWSList(WhiteSpaceTokenList):

    token_type = 'cfws'


class Atom(TokenList):

    token_type = 'atom'


class QuotedString(TokenList):

    token_type = 'quoted-string'

    @property
    def content(self):
        for x in self:
            if x.token_type == 'bare-quoted-string':
                return x.value

    @property
    def quoted_value(self):
        res = []
        for x in self:
            if x.token_type == 'bare-quoted-string':
                res.append(str(x))
            else:
                res.append(x.value)
        return ''.join(res)


class BareQuotedString(QuotedString):

    token_type = 'bare-quoted-string'

    def __str__(self):
        return quote_string(''.join(self))

    @property
    def value(self):
        return ''.join(str(x) for x in self)


class Comment(WhiteSpaceTokenList):

    token_type = 'comment'

    def __str__(self):
        return ''.join(sum([
                            ["("],
                            [self.quote(x) for x in self],
                            [")"],
                            ], []))

    def quote(self, value):
        if value.token_type == 'comment':
            return str(value)
        return str(value).replace('\\', '\\\\').replace(
                                  '(', '\(').replace(
                                  ')', '\)')

    @property
    def content(self):
        return ''.join(str(x) for x in self)

    @property
    def comments(self):
        return [self.content]

class AddressList(TokenList):

    token_type = 'address-list'

    @property
    def addresses(self):
        return [x for x in self if x.token_type=='address']

    @property
    def mailboxes(self):
        return sum((x.mailboxes
                    for x in self if x.token_type=='address'), [])

    @property
    def all_mailboxes(self):
        return sum((x.all_mailboxes
                    for x in self if x.token_type=='address'), [])


class Address(TokenList):

    token_type = 'address'

    @property
    def display_name(self):
        if self[0].token_type == 'group':
            return self[0].display_name

    @property
    def mailboxes(self):
        if self[0].token_type == 'mailbox':
            return [self[0]]
        elif self[0].token_type == 'invalid-mailbox':
            return []
        return self[0].mailboxes

    @property
    def all_mailboxes(self):
        if self[0].token_type == 'mailbox':
            return [self[0]]
        elif self[0].token_type == 'invalid-mailbox':
            return [self[0]]
        return self[0].all_mailboxes

class MailboxList(TokenList):

    token_type = 'mailbox-list'

    @property
    def mailboxes(self):
        return [x for x in self if x.token_type=='mailbox']

    @property
    def all_mailboxes(self):
        return [x for x in self
            if x.token_type in ('mailbox', 'invalid-mailbox')]


class GroupList(TokenList):

    token_type = 'group-list'

    @property
    def mailboxes(self):
        if not self or self[0].token_type != 'mailbox-list':
            return []
        return self[0].mailboxes

    @property
    def all_mailboxes(self):
        if not self or self[0].token_type != 'mailbox-list':
            return []
        return self[0].all_mailboxes


class Group(TokenList):

    token_type = "group"

    @property
    def mailboxes(self):
        if self[2].token_type != 'group-list':
            return []
        return self[2].mailboxes

    @property
    def all_mailboxes(self):
        if self[2].token_type != 'group-list':
            return []
        return self[2].all_mailboxes

    @property
    def display_name(self):
        return self[0].display_name


class NameAddr(TokenList):

    token_type = 'name-addr'

    @property
    def display_name(self):
        if len(self) == 1:
            return None
        return self[0].display_name

    @property
    def local_part(self):
        return self[-1].local_part

    @property
    def domain(self):
        return self[-1].domain

    @property
    def route(self):
        return self[-1].route

    @property
    def addr_spec(self):
        return self[-1].addr_spec


class AngleAddr(TokenList):

    token_type = 'angle-addr'

    @property
    def local_part(self):
        for x in self:
            if x.token_type == 'addr-spec':
                return x.local_part

    @property
    def domain(self):
        for x in self:
            if x.token_type == 'addr-spec':
                return x.domain

    @property
    def route(self):
        for x in self:
            if x.token_type == 'obs-route':
                return x.domains

    @property
    def addr_spec(self):
        for x in self:
            if x.token_type == 'addr-spec':
                return x.addr_spec


class ObsRoute(TokenList):

    token_type = 'obs-route'

    @property
    def domains(self):
        return [x.domain for x in self if x.token_type == 'domain']


class Mailbox(TokenList):

    token_type = 'mailbox'

    @property
    def display_name(self):
        if self[0].token_type == 'name-addr':
            return self[0].display_name

    @property
    def local_part(self):
        return self[0].local_part

    @property
    def domain(self):
        return self[0].domain

    @property
    def route(self):
        if self[0].token_type == 'name-addr':
            return self[0].route

    @property
    def addr_spec(self):
        return self[0].addr_spec


class InvalidMailbox(TokenList):

    token_type = 'invalid-mailbox'

    @property
    def display_name(self):
        return None

    local_part = domain = route = addr_spec = display_name


class Domain(TokenList):

    token_type = 'domain'

    @property
    def domain(self):
        return ''.join(super().value.split())


class DotAtom(TokenList):

    token_type = 'dot-atom'


class DotAtomText(TokenList):

    token_type = 'dot-atom-text'


class AddrSpec(TokenList):

    token_type = 'addr-spec'

    @property
    def local_part(self):
        return self[0].local_part

    @property
    def domain(self):
        if len(self) < 3:
            return None
        return self[-1].domain

    @property
    def value(self):
        if len(self) < 3:
            return self[0].value
        return self[0].value.rstrip()+self[1].value+self[2].value.lstrip()

    @property
    def addr_spec(self):
        nameset = set(self.local_part)
        if len(nameset) > len(nameset-ATOM_ENDS):
            lp = quote_string(self.local_part)
        else:
            lp = self.local_part
        if self.domain is not None:
            return lp + '@' + self.domain
        return lp


class ObsLocalPart(TokenList):

    token_type = 'obs-local-part'


class DisplayName(TokenList):

    token_type = 'display-name'

    @property
    def display_name(self):
        res = TokenList(self)
        if res[0].token_type == 'cfws':
            res.pop(0)
        else:
            if res[0][0].token_type == 'cfws':
                res[0] = TokenList(res[0][1:])
        if res[-1].token_type == 'cfws':
            res.pop()
        else:
            if res[-1][-1].token_type == 'cfws':
                res[-1] = TokenList(res[-1][:-1])
        return res.value

    @property
    def value(self):
        quote = False
        if self.defects:
            quote = True
        else:
            for x in self:
                if x.token_type == 'quoted-string':
                    quote = True
        if quote:
            pre = post = ''
            if self[0].token_type=='cfws' or self[0][0].token_type=='cfws':
                pre = ' '
            if self[-1].token_type=='cfws' or self[-1][-1].token_type=='cfws':
                post = ' '
            return pre+quote_string(self.display_name)+post
        else:
            return super().value


class LocalPart(TokenList):

    token_type = 'local-part'

    @property
    def value(self):
        if self[0].token_type == "quoted-string":
            return self[0].quoted_value
        else:
            return self[0].value

    @property
    def local_part(self):
        res = TokenList(self[0])
        if res[0].token_type == 'cfws':
            res.pop(0)
        else:
            if res[0][0].token_type == 'cfws':
                res[0] = TokenList(res[0][1:])
        if res[-1].token_type == 'cfws':
            res.pop()
        else:
            if res[-1][-1].token_type == 'cfws':
                res[-1] = TokenList(res[-1][:-1])
        return res.value


class DomainLiteral(TokenList):

    token_type = 'domain-literal'

    @property
    def domain(self):
        return ''.join(super().value.split())

    @property
    def ip(self):
        for x in self:
            if x.token_type == 'ptext':
                return x.value


#
# Terminal classes and instances
#

class Terminal(str):

    def __new__(cls, value, token_type):
        self = super().__new__(cls, value)
        self.token_type = token_type
        self.defects = []
        return self

    def __repr__(self):
        return "{}({})".format(self.__class__.__name__, super().__repr__())

    @property
    def all_defects(self):
        return list(self.defects)

    def pprint(self, indent=''):
        print("{}{}/{}({})".format(
            indent,
            self.__class__.__name__,
            self.token_type,
            super().__repr__()))


class WhiteSpaceTerminal(Terminal):

    @property
    def value(self):
        return ' '


class ValueTerminal(Terminal):

    @property
    def value(self):
        return self


# XXX these need to become classes and used as instances so
# that a program can't change them in a parse tree and screw
# up other parse trees.  Maybe should have  tests for that, too.
DOT = ValueTerminal('.', 'dot')
ListSeparator = ValueTerminal(',', 'list-separator')
RouteComponentMarker = ValueTerminal('@', 'route-component-marker')

#
# Parser
#

"""Parse strings according to RFC822/2047/2822/5322 rules.

This is a stateless parser.  Each get_XXX function accepts a string and
returns either a Terminal or a TokenList representing the RFC object named
by the method and a string containing the remaining unparsed characters
from the input.  Thus a parser method consumes the next syntactic construct
of a given type and returns a token representing the construct plus the
unparsed remainder of the input string.

For example, if the first element of a structured header is a 'phrase',
then:

    phrase, value = get_phrase(value)

returns the complete phrase from the start of the string value, plus any
characters left in the string after the phrase is removed.

"""

_wsp_splitter = re.compile(r'([{}]+)'.format(''.join(WSP))).split
_non_atom_end_matcher = re.compile(r"[^{}]+".format(
    ''.join(ATOM_ENDS).replace('\\','\\\\').replace(']','\]'))).match
_non_printable_finder = re.compile(r"[\x00-\x20\x7F]").findall

def _sanitize(string):
    # Turn any escaped bytes into unicode 'unknown' char.
    original_bytes = string.encode('ascii', 'surrogateescape')
    return original_bytes.decode('ascii', 'replace')

def _validate_xtext(xtext):
    """If input token contains ASCII non-printables, register a defect."""

    non_printables = _non_printable_finder(xtext)
    if non_printables:
        xtext.defects.append(errors.NonPrintableDefect(non_printables))

def _get_ptext_to_endchars(value, endchars):
    """Scan printables/quoted-pairs until endchars and return unquoted ptext.

    This function turns a run of qcontent, ccontent-without-comments, or
    dtext-with-quoted-printables into a single string by unquoting any
    quoted printables.  It returns the string, the remaining value, and
    a flag that is True iff there were any quoted printables decoded.

    """
    fragment, *remainder = _wsp_splitter(value, 1)
    vchars = []
    escape = False
    had_qp = False
    for pos in range(len(fragment)):
        if fragment[pos] == '\\':
            if escape:
                escape = False
                had_qp = True
            else:
                escape = True
                continue
        if escape:
            escape = False
        elif fragment[pos] in endchars:
            break
        vchars.append(fragment[pos])
    else:
        pos = pos + 1
    return ''.join(vchars), ''.join([fragment[pos:]] + remainder), had_qp

def _decode_ew_run(value):
    """ Decode a run of RFC2047 encoded words.

        _decode_ew_run(value) -> (text, value, defects)

    Scans the supplied value for a run of tokens that look like they are RFC
    2047 encoded words, decodes those words into text according to RFC 2047
    rules (whitespace between encoded words is discarded), and returns the text
    and the remaining value (including any leading whitespace on the remaining
    value), as well as a list of any defects encoutered while decoding.  The
    input value may not have any leading whitespace.

    """
    res = []
    defects = []
    last_ws = ''
    while value:
        try:
            tok, ws, value = _wsp_splitter(value, 1)
        except ValueError:
            tok, ws, value = value, '', ''
        if not (tok.startswith('=?') and tok.endswith('?=')):
            return ''.join(res), last_ws + tok + ws + value, defects
        text, new_defects = _ew.decode(tok)
        res.append(text)
        defects.extend(new_defects)
        last_ws = ws
    return ''.join(res), last_ws, defects

def get_unstructured(value):
    """unstructured = (*([FWS] vchar) *WSP) / obs-unstruct
       obs-unstruct = *((*LF *CR *(obs-utext) *LF *CR)) / FWS)
       obs-utext = %d0 / obs-NO-WS-CTL / LF / CR

       obs-NO-WS-CTL is control characters except WSP/CR/LF.

    So, basically, we have printable runs, plus control characters or nulls in
    the obsolete syntax, separated by whitespace.  Since RFC 2047 uses the
    obsolete syntax in its specification, but requires whitespace on either
    side of the encoded words, I can see no reason to need to separate the
    non-printable-non-whitespace from the printable runs if they occur, so we
    parse this into xtext tokens separated by WSP tokens.

    Because an 'unstructured' value must by definition constitute the entire
    value, this 'get' routine does not return a remaining value, only the
    parsed TokenList.

    """
    # XXX: but what about bare CR and LF?  They might signal the start or
    # end of an encoded word.

    # The dance with the ws is so that we combine leading ws that is encoded
    # in an encoded word with trailing whitespace leading up to it.  Not
    # strictly necessary, but probably what the composer intended.
    unstructured = UnstructuredTokenList()
    last_ws = ''
    while value:
        try:
            tok, ws, value = _wsp_splitter(value, 1)
        except ValueError:
            tok, ws, value = value, '', ''
        if not tok:
            if ws:
                last_ws += ws
            if not value:
                break
            continue
        if tok.startswith('=?') and tok.endswith('?='):
            text, value, defects = _decode_ew_run(tok + ws + value)
            value = text + value
            unstructured.defects.extend(defects)
        else:
            if last_ws:
                unstructured.append(WhiteSpaceTerminal(last_ws, 'fws'))
            if utils._has_surrogates(tok):
                tok = _sanitize(tok)
            vtext = ValueTerminal(tok, 'vtext')
            _validate_xtext(vtext)
            unstructured.append(vtext)
            last_ws = ws
    if last_ws:
        unstructured.append(WhiteSpaceTerminal(last_ws, 'fws'))
    return unstructured

def get_qp_ctext(value):
    """ctext = <printable ascii except \ ( )>

    This is not the RFC ctext, since we are handling nested comments in comment
    and unquoting quoted-pairs here.  We allow anything except the '()'
    characters, but if we find any ASCII other than the RFC defined printable
    ASCII an NonPrintableDefect is added to the token's defects list.  Since
    quoted pairs are converted to their unquoted values, what is returned is
    a 'ptext' token.  In this case it is a WhiteSpaceTerminal, so it's value
    is ' '.

    """
    ptext, value, _ = _get_ptext_to_endchars(value, '()')
    ptext = WhiteSpaceTerminal(ptext, 'ptext')
    _validate_xtext(ptext)
    return ptext, value

def get_qcontent(value):
    """qcontent = qtext / quoted-pair

    We allow anything except the DQUOTE character, but if we find any ASCII
    other than the RFC defined printable ASCII an NonPrintableDefect is
    added to the token's defects list.  Any quoted pairs are converted to their
    unquoted values, so what is returned is a 'ptext' token.  In this case it
    is a ValueTerminal.

    """
    ptext, value, _ = _get_ptext_to_endchars(value, '"')
    ptext = ValueTerminal(ptext, 'ptext')
    _validate_xtext(ptext)
    return ptext, value

def get_atext(value):
    """atext = <matches _atext_matcher>

    We allow any non-ATOM_ENDS in atext, but add an InvalidATextDefect to
    the token's defects list if we find non-atext characters.
    """
    m = _non_atom_end_matcher(value)
    if not m:
        raise errors.HeaderParseError(
            "expected atext but found '{}'".format(value))
    atext = m.group()
    value = value[len(atext):]
    atext = ValueTerminal(atext, 'atext')
    _validate_xtext(atext)
    return atext, value

def get_fws(value):
    """FWS = 1*WSP

    This isn't the RFC definition.  We're using fws to represent tokens where
    folding can be done, but when we are parsing the *un*folding has already
    been done so we don't need to watch out for CRLF.

    """
    newvalue = value.lstrip()
    fws = WhiteSpaceTerminal(value[:len(value)-len(newvalue)], 'fws')
    return fws, newvalue

def get_bare_quoted_string(value):
    """bare-quoted-string = DQUOTE *([FWS] qcontent) [FWS] DQUOTE

    A quoted-string without the leading or trailing white space.  Its
    value is the text between the quote marks, with whitespace
    preserved and quoted pairs decoded.
    """
    if value[0] != '"':
        raise errors.HeaderParseError(
            "expected '\"' but found '{}'".format(value))
    bare_quoted_string = BareQuotedString()
    value = value[1:]
    while value and value[0] != '"':
        if value[0] in WSP:
            token, value = get_fws(value)
        else:
            token, value = get_qcontent(value)
        bare_quoted_string.append(token)
    if not value:
        bare_quoted_string.defects.append(errors.InvalidHeaderDefect(
            "end of header inside quoted string"))
        return bare_quoted_string, value
    return bare_quoted_string, value[1:]

def get_comment(value):
    """comment = "(" *([FWS] ccontent) [FWS] ")"
       ccontent = ctext / quoted-pair / comment

    We handle nested comments here, and quoted-pair in our qp-ctext routine.
    """
    if value and value[0] != '(':
        raise errors.HeaderParseError(
            "expected '(' but found '{}'".format(value))
    comment = Comment()
    value = value[1:]
    while value and value[0] != ")":
        if value[0] in WSP:
            token, value = get_fws(value)
        elif value[0] == '(':
            token, value = get_comment(value)
        else:
            token, value = get_qp_ctext(value)
        comment.append(token)
    if not value:
        comment.defects.append(errors.InvalidHeaderDefect(
            "end of header inside comment"))
        return comment, value
    return comment, value[1:]

def get_cfws(value):
    """CFWS = (1*([FWS] comment) [FWS]) / FWS

    """
    cfws = CFWSList()
    while value and value[0] in CFWS_LEADER:
        if value[0] in WSP:
            token, value = get_fws(value)
        else:
            token, value = get_comment(value)
        cfws.append(token)
    return cfws, value

def get_quoted_string(value):
    """quoted-string = [CFWS] <bare-quoted-string> [CFWS]

    'bare-quoted-string' is an intermediate class defined by this
    parser and not by the RFC grammar.  It is the quoted string
    without any attached CFWS.
    """
    quoted_string = QuotedString()
    if value and value[0] in CFWS_LEADER:
        token, value = get_cfws(value)
        quoted_string.append(token)
    token, value = get_bare_quoted_string(value)
    quoted_string.append(token)
    if value and value[0] in CFWS_LEADER:
        token, value = get_cfws(value)
        quoted_string.append(token)
    return quoted_string, value

def get_atom(value):
    """atom = [CFWS] 1*atext [CFWS]

    """
    atom = Atom()
    if value and value[0] in CFWS_LEADER:
        token, value = get_cfws(value)
        atom.append(token)
    if value and value[0] in ATOM_ENDS:
        raise errors.HeaderParseError(
            "expected atom but found '{}'".format(value))
    token, value = get_atext(value)
    atom.append(token)
    if value and value[0] in CFWS_LEADER:
        token, value = get_cfws(value)
        atom.append(token)
    return atom, value

def get_dot_atom_text(value):
    """ dot-text = 1*atext *("." 1*atext)

    """
    dot_atom_text = DotAtomText()
    if not value or value[0] in ATOM_ENDS:
        raise errors.HeaderParseError("expected atom at a start of "
            "dot-atom-text but found '{}'".format(value))
    while value and value[0] not in ATOM_ENDS:
        token, value = get_atext(value)
        dot_atom_text.append(token)
        if value and value[0] == '.':
            dot_atom_text.append(DOT)
            value = value[1:]
    if dot_atom_text[-1] is DOT:
        raise errors.HeaderParseError("expected atom at end of dot-atom-text "
            "but found '{}'".format('.'+value))
    return dot_atom_text, value

def get_dot_atom(value):
    """ dot-atom = [CFWS] dot-atom-text [CFWS]

    """
    dot_atom = DotAtom()
    if value[0] in CFWS_LEADER:
        token, value = get_cfws(value)
        dot_atom.append(token)
    token, value = get_dot_atom_text(value)
    dot_atom.append(token)
    if value and value[0] in CFWS_LEADER:
        token, value = get_cfws(value)
        dot_atom.append(token)
    return dot_atom, value

def get_word(value):
    """word = atom / quoted-string

    Either atom or quoted-string may start with CFWS.  We have to peel off this
    CFWS first to determine which type of word to parse.  Afterward we splice
    the leading CFWS, if any, into the parsed sub-token.

    If neither an atom or a quoted-string is found before the next special, a
    HeaderParseError is raised.

    The token returned is either an Atom or a QuotedString, as appropriate.
    This means the 'word' level of the formal grammar is not represented in the
    parse tree; this is because having that extra layer when manipulating the
    parse tree is more confusing than it is helpful.

    """
    if value[0] in CFWS_LEADER:
        leader, value = get_cfws(value)
    else:
        leader = None
    if value[0]=='"':
        token, value = get_quoted_string(value)
    elif value[0] in SPECIALS:
        raise errors.HeaderParseError("Expected 'atom' or 'quoted-string' "
                                      "but found '{}'".format(value))
    else:
        token, value = get_atom(value)
    if leader is not None:
        token[:0] = [leader]
    return token, value

def get_phrase(value):
    """ phrase = 1*word / obs-phrase
        obs-phrase = word *(word / "." / CFWS)

    This means a phrase can be a sequence of words, periods, and CFWS in any
    order as long as it starts with at least one word.  If anything other than
    words is detected, an ObsoleteHeaderDefect is added to the token's defect
    list.  We also accept a phrase that starts with CFWS followed by a dot;
    this is registered as an InvalidHeaderDefect, since it is not supported by
    even the obsolete grammar.

    """
    phrase = Phrase()
    try:
        token, value = get_word(value)
        phrase.append(token)
    except errors.HeaderParseError:
        phrase.defects.append(errors.InvalidHeaderDefect(
            "phrase does not start with word"))
    while value and value[0] not in PHRASE_ENDS:
        if value[0]=='.':
            phrase.append(DOT)
            phrase.defects.append(errors.ObsoleteHeaderDefect(
                "period in 'phrase'"))
            value = value[1:]
        else:
            try:
                token, value = get_word(value)
            except errors.HeaderParseError:
                if value[0] in CFWS_LEADER:
                    token, value = get_cfws(value)
                    phrase.defects.append(errors.ObsoleteHeaderDefect(
                        "comment found without atom"))
                else:
                    raise
            phrase.append(token)
    return phrase, value

def get_local_part(value):
    """ local-part = dot-atom / quoted-string / obs-local-part
        obs-local-part = word *("." word)

    """
    local_part = LocalPart()
    leader = None
    if value[0] in CFWS_LEADER:
        leader, value = get_cfws(value)
    if not value:
        raise errors.HeaderParseError(
            "expected local-part but found '{}'".format(value))
    try:
        token, value = get_dot_atom(value)
    except errors.HeaderParseError:
        token, value = get_word(value)
    if leader is not None:
        token[:0] = [leader]
    local_part.append(token)
    if value and (value[0]=='\\' or value[0] not in PHRASE_ENDS):
        obs_local_part = ObsLocalPart()
        if local_part[0].token_type == 'dot-atom':
            obs_local_part[:] = local_part[0]
        else:
            obs_local_part.append(local_part[0])
        while value and (value[0]=='\\' or value[0] not in PHRASE_ENDS):
            if value[0] == '.':
                obs_local_part.append(DOT)
                value = value[1:]
            else:
                if value[0]=='\\':
                    obs_local_part.append(ValueTerminal(value[0],
                                                        'misplaced-special'))
                    value = value[1:]
                    obs_local_part.defects.append(errors.InvalidHeaderDefect(
                        "'\\' character outside of quoted-string/ccontent"))
                    continue
                else:
                    obs_local_part.defects.append(errors.InvalidHeaderDefect(
                        "missing '.' between words"))
            token, value = get_word(value)
            obs_local_part.append(token)
        if obs_local_part.defects:
            local_part.defects.append(errors.InvalidHeaderDefect(
                "local-part is not dot-atom, quoted-string, or obs-local-part"))
            obs_local_part.token_type = 'invalid-obs-local-part'
        else:
            local_part.defects.append(errors.ObsoleteHeaderDefect(
                "local-part is not a dot-atom (contains CFWS)"))
        local_part[0] = obs_local_part
    return local_part, value

def get_dtext(value):
    """ dtext = <printable ascii except \ [ ]> / obs-dtext
        obs-dtext = obs-NO-WS-CTL / quoted-pair

    We allow anything except the excluded characters, but but if we find any
    ASCII other than the RFC defined printable ASCII an NonPrintableDefect is
    added to the token's defects list.  Quoted pairs are converted to their
    unquoted values, so what is returned is a ptext token, in this case a
    ValueTerminal.  If there were quoted-printables, an ObsoleteHeaderDefect is
    added to the returned token's defect list.

    """
    ptext, value, had_qp = _get_ptext_to_endchars(value, '[]')
    ptext = ValueTerminal(ptext, 'ptext')
    if had_qp:
        ptext.defects.append(errors.ObsoleteHeaderDefect(
            "quoted printable found in domain-literal"))
    _validate_xtext(ptext)
    return ptext, value

def _check_for_early_dl_end(value, domain_literal):
    if value:
        return False
    domain_literal.append(errors.InvalidHeaderDefect(
        "end of input inside domain-literal"))
    domain_literal.append(ValueTerminal(']', 'domain-literal-end'))
    return True

def get_domain_literal(value):
    """ domain-literal = [CFWS] "[" *([FWS] dtext) [FWS] "]" [CFWS]

    """
    domain_literal = DomainLiteral()
    if value[0] in CFWS_LEADER:
        token, value = get_cfws(value)
        domain_literal.append(token)
    if not value:
        raise errors.HeaderParseError("expected domain-literal")
    if value[0] != '[':
        raise errors.HeaderParseError("expected '[' at start of domain-literal "
                "but found '{}'".format(value))
    value = value[1:]
    if _check_for_early_dl_end(value, domain_literal):
        return domain_literal, value
    domain_literal.append(ValueTerminal('[', 'domain-literal-start'))
    if value[0] in WSP:
        token, value = get_fws(value)
        domain_literal.append(token)
    token, value = get_dtext(value)
    domain_literal.append(token)
    if _check_for_early_dl_end(value, domain_literal):
        return domain_literal, value
    if value[0] in WSP:
        token, value = get_fws(value)
        domain_literal.append(token)
    if _check_for_early_dl_end(value, domain_literal):
        return domain_literal, value
    if value[0] != ']':
        raise errors.HeaderParseError("expected ']' at end of domain-literal "
                "but found '{}'".format(value))
    domain_literal.append(ValueTerminal(']', 'domain-literal-end'))
    value = value[1:]
    if value and value[0] in CFWS_LEADER:
        token, value = get_cfws(value)
        domain_literal.append(token)
    return domain_literal, value

def get_domain(value):
    """ domain = dot-atom / domain-literal / obs-domain
        obs-domain = atom *("." atom))

    """
    domain = Domain()
    leader = None
    if value[0] in CFWS_LEADER:
        leader, value = get_cfws(value)
    if not value:
        raise errors.HeaderParseError(
            "expected domain but found '{}'".format(value))
    if value[0] == '[':
        token, value = get_domain_literal(value)
        if leader is not None:
            token[:0] = [leader]
        domain.append(token)
        return domain, value
    try:
        token, value = get_dot_atom(value)
    except errors.HeaderParseError:
        token, value = get_atom(value)
    if leader is not None:
        token[:0] = [leader]
    domain.append(token)
    if value and value[0] == '.':
        domain.defects.append(errors.ObsoleteHeaderDefect(
            "domain is not a dot-atom (contains CFWS)"))
        if domain[0].token_type == 'dot-atom':
            domain[:] = domain[0]
        while value and value[0] == '.':
            domain.append(DOT)
            token, value = get_atom(value[1:])
            domain.append(token)
    return domain, value

def get_addr_spec(value):
    """ addr-spec = local-part "@" domain

    """
    addr_spec = AddrSpec()
    token, value = get_local_part(value)
    addr_spec.append(token)
    if not value or value[0] != '@':
        #raise errors.HeaderParseError(
        #    "expected @domain but found '{}'".format(value))
        addr_spec.defects.append(errors.InvalidHeaderDefect(
            "add-spec local part with no domain"))
        return addr_spec, value
    addr_spec.append(ValueTerminal('@', 'address-at-symbol'))
    token, value = get_domain(value[1:])
    addr_spec.append(token)
    return addr_spec, value

def get_obs_route(value):
    """ obs-route = obs-domain-list ":"
        obs-domain-list = *(CFWS / ",") "@" domain *("," [CFWS] ["@" domain])

        Returns an obs-route token with the appropriate sub-tokens (that is,
        there is no obs-domain-list in the parse tree).
    """
    obs_route = ObsRoute()
    while value and (value[0]==',' or value[0] in CFWS_LEADER):
        if value[0] in CFWS_LEADER:
            token, value = get_cfws(value)
            obs_route.append(token)
        elif value[0] == ',':
            obs_route.append(ListSeparator)
            value = value[1:]
    if not value or value[0] != '@':
        raise errors.HeaderParseError(
            "expected obs-route domain but found '{}'".format(value))
    obs_route.append(RouteComponentMarker)
    token, value = get_domain(value[1:])
    obs_route.append(token)
    while value and value[0]==',':
        obs_route.append(ListSeparator)
        value = value[1:]
        if not value:
            break
        if value[0] in CFWS_LEADER:
            token, value = get_cfws(value)
            obs_route.append(token)
        if value[0] == '@':
            obs_route.append(RouteComponentMarker)
            token, value = get_domain(value[1:])
            obs_route.append(token)
    if not value:
        raise errors.HeaderParseError("end of header while parsing obs-route")
    if value[0] != ':':
        raise errors.HeaderParseError( "expected ':' marking end of "
            "obs-route but found '{}'".format(value))
    obs_route.append(ValueTerminal(':', 'end-of-obs-route-marker'))
    return obs_route, value[1:]

def get_angle_addr(value):
    """ angle-addr = [CFWS] "<" addr-spec ">" [CFWS] / obs-angle-addr
        obs-angle-addr = [CFWS] "<" obs-route addr-spec ">" [CFWS]

    """
    angle_addr = AngleAddr()
    if value[0] in CFWS_LEADER:
        token, value = get_cfws(value)
        angle_addr.append(token)
    if not value or value[0] != '<':
        raise errors.HeaderParseError(
            "expected angle-addr but found '{}'".format(value))
    angle_addr.append(ValueTerminal('<', 'angle-addr-start'))
    value = value[1:]
    try:
        token, value = get_addr_spec(value)
    except errors.HeaderParseError:
        try:
            token, value = get_obs_route(value)
            angle_addr.defects.append(errors.ObsoleteHeaderDefect(
                "obsolete route specification in angle-addr"))
        except errors.HeaderParseError:
            raise errors.HeaderParseError(
                "expected addr-spec or but found '{}'".format(value))
        angle_addr.append(token)
        token, value = get_addr_spec(value)
    angle_addr.append(token)
    if value and value[0] == '>':
        value = value[1:]
    else:
        angle_addr.defects.append(errors.InvalidHeaderDefect(
            "missing trailing '>' on angle-addr"))
    angle_addr.append(ValueTerminal('>', 'angle-addr-end'))
    if value and value[0] in CFWS_LEADER:
        token, value = get_cfws(value)
        angle_addr.append(token)
    return angle_addr, value

def get_display_name(value):
    """ display-name = phrase

    Because this is simply a name-rule, we don't return a display-name
    token containing a phrase, but rather a display-name token with
    the content of the phrase.

    """
    display_name = DisplayName()
    token, value = get_phrase(value)
    display_name.extend(token[:])
    display_name.defects = token.defects[:]
    return display_name, value


def get_name_addr(value):
    """ name-addr = [display-name] angle-addr

    """
    name_addr = NameAddr()
    # Both the optional display name and the angle-addr can start with cfws.
    leader = None
    if value[0] in CFWS_LEADER:
        leader, value = get_cfws(value)
        if not value:
            raise errors.HeaderParseError(
                "expected name-addr but found '{}'".format(leader))
    if value[0] != '<':
        if value[0] in PHRASE_ENDS:
            raise errors.HeaderParseError(
                "expected name-addr but found '{}'".format(value))
        token, value = get_display_name(value)
        if not value:
            raise errors.HeaderParseError(
                "expected name-addr but found '{}'".format(token))
        if leader is not None:
            token[0][:0] = [leader]
            leader = None
        name_addr.append(token)
    token, value = get_angle_addr(value)
    if leader is not None:
        token[:0] = [leader]
    name_addr.append(token)
    return name_addr, value

def get_mailbox(value):
    """ mailbox = name-addr / addr-spec

    """
    # The only way to figure out if we are dealing with a name-addr or an
    # addr-spec is to try parsing each one.
    mailbox = Mailbox()
    try:
        token, value = get_name_addr(value)
    except errors.HeaderParseError:
        try:
            token, value = get_addr_spec(value)
        except errors.HeaderParseError:
            raise errors.HeaderParseError(
                "expected mailbox but found '{}'".format(value))
    if any(isinstance(x, errors.InvalidHeaderDefect)
                       for x in token.all_defects):
        mailbox.token_type = 'invalid-mailbox'
    mailbox.append(token)
    return mailbox, value

def get_invalid_mailbox(value, endchars):
    """ Read everything up to one of the chars in endchars.

    This is outside the formal grammar.  The InvalidMailbox TokenList that is
    returned acts like a Mailbox, but the data attributes are None.

    """
    invalid_mailbox = InvalidMailbox()
    while value and value[0] not in endchars:
        if value[0] in PHRASE_ENDS:
            invalid_mailbox.append(ValueTerminal(value[0],
                                                 'misplaced-special'))
            value = value[1:]
        else:
            token, value = get_phrase(value)
            invalid_mailbox.append(token)
    return invalid_mailbox, value

def get_mailbox_list(value):
    """ mailbox-list = (mailbox *("," mailbox)) / obs-mbox-list
        obs-mbox-list = *([CFWS] ",") mailbox *("," [mailbox / CFWS])

    For this routine we go outside the formal grammar in order to improve error
    handling.  We recognize the end of the mailbox list only at the end of the
    value or at a ';' (the group terminator).  This is so that we can turn
    invalid mailboxes into InvalidMailbox tokens and continue parsing any
    remaining valid mailboxes.  We also allow all mailbox entries to be null,
    and this condition is handled appropriately at a higher level.

    """
    mailbox_list = MailboxList()
    while value and value[0] != ';':
        try:
            token, value = get_mailbox(value)
            mailbox_list.append(token)
        except errors.HeaderParseError:
            leader = None
            if value[0] in CFWS_LEADER:
                leader, value = get_cfws(value)
                if not value or value[0] in ',;':
                    mailbox_list.append(leader)
                    mailbox_list.defects.append(errors.ObsoleteHeaderDefect(
                        "empty element in mailbox-list"))
                else:
                    token, value = get_invalid_mailbox(value, ',;')
                    if leader is not None:
                        token[:0] = [leader]
                    mailbox_list.append(token)
                    mailbox_list.defects.append(errors.InvalidHeaderDefect(
                        "invalid mailbox in mailbox-list"))
            elif value[0] == ',':
                mailbox_list.defects.append(errors.ObsoleteHeaderDefect(
                    "empty element in mailbox-list"))
            else:
                token, value = get_invalid_mailbox(value, ',;')
                if leader is not None:
                    token[:0] = [leader]
                mailbox_list.append(token)
                mailbox_list.defects.append(errors.InvalidHeaderDefect(
                    "invalid mailbox in mailbox-list"))
        if value and value[0] not in ',;':
            # Crap after mailbox; treat it as an invalid mailbox.
            # The mailbox info will still be available.
            mailbox = mailbox_list[-1]
            mailbox.token_type = 'invalid-mailbox'
            token, value = get_invalid_mailbox(value, ',;')
            mailbox.extend(token)
            mailbox_list.defects.append(errors.InvalidHeaderDefect(
                "invalid mailbox in mailbox-list"))
        if value and value[0] == ',':
            mailbox_list.append(ListSeparator)
            value = value[1:]
    return mailbox_list, value


def get_group_list(value):
    """ group-list = mailbox-list / CFWS / obs-group-list
        obs-group-list = 1*([CFWS] ",") [CFWS]

    """
    group_list = GroupList()
    if not value:
        group_list.defects.append(errors.InvalidHeaderDefect(
            "end of header before group-list"))
        return group_list, value
    leader = None
    if value and value[0] in CFWS_LEADER:
        leader, value = get_cfws(value)
        if not value:
            # This should never happen in email parsing, since CFWS-only is a
            # legal alternative to group-list in a group, which is the only
            # place group-list appears.
            group_list.defects.append(errors.InvalidHeaderDefect(
                "end of header in group-list"))
            group_list.append(leader)
            return group_list, value
        if value[0] == ';':
            group_list.append(leader)
            return group_list, value
    token, value = get_mailbox_list(value)
    if len(token.mailboxes)==0:
        if leader is not None:
            group_list.append(leader)
        group_list.extend(token)
        group_list.defects.append(errors.ObsoleteHeaderDefect(
            "group-list with empty entries"))
        return group_list, value
    if leader is not None:
        token[:0] = [leader]
    group_list.append(token)
    return group_list, value

def get_group(value):
    """ group = display-name ":" [group-list] ";" [CFWS]

    """
    group = Group()
    token, value = get_display_name(value)
    if not value or value[0] != ':':
        raise errors.HeaderParseError("expected ':' at end of group "
            "display name but found '{}'".format(value))
    group.append(token)
    group.append(ValueTerminal(':', 'group-display-name-terminator'))
    value = value[1:]
    if value and value[0] == ';':
        group.append(ValueTerminal(';', 'group-terminator'))
        return group, value[1:]
    token, value = get_group_list(value)
    group.append(token)
    if not value:
        group.defects.append(errors.InvalidHeaderDefect(
            "end of header in group"))
    if value[0] != ';':
        raise errors.HeaderParseError(
            "expected ';' at end of group but found {}".format(value))
    group.append(ValueTerminal(';', 'group-terminator'))
    value = value[1:]
    if value and value[0] in CFWS_LEADER:
        token, value = get_cfws(value)
        group.append(token)
    return group, value

def get_address(value):
    """ address = mailbox / group

    Note that counter-intuitively, an address can be either a single address or
    a list of addresses (a group).  This is why the returned Address object has
    a 'mailboxes' attribute which treats a single address as a list of length
    one.  When you need to differentiate between to two cases, extract the single
    element, which is either a mailbox or a group token.

    """
    # The formal grammar isn't very helpful when parsing an address.  mailbox
    # and group, especially when allowing for obsolete forms, start off very
    # similarly.  It is only when you reach one of @, <, or : that you know
    # what you've got.  So, we try each one in turn, starting with the more
    # likely of the two.  We could perhaps make this more efficient by looking
    # for a phrase and then branching based on the next character, but that
    # would be a premature optimization.
    address = Address()
    try:
        token, value = get_group(value)
    except errors.HeaderParseError:
        try:
            token, value = get_mailbox(value)
        except errors.HeaderParseError:
            raise errors.HeaderParseError(
                "expected address but found '{}'".format(value))
    address.append(token)
    return address, value

def get_address_list(value):
    """ address_list = (address *("," address)) / obs-addr-list
        obs-addr-list = *([CFWS] ",") address *("," [address / CFWS])

    We depart from the formal grammar here by continuing to parse until the end
    of the input, assuming the input to be entirely composed of an
    address-list.  This is always true in email parsing, and allows us
    to skip invalid addresses to parse additional valid ones.

    """
    address_list = AddressList()
    while value:
        try:
            token, value = get_address(value)
            address_list.append(token)
        except errors.HeaderParseError as err:
            leader = None
            if value[0] in CFWS_LEADER:
                leader, value = get_cfws(value)
                if not value or value[0] == ',':
                    address_list.append(leader)
                    address_list.defects.append(errors.ObsoleteHeaderDefect(
                        "address-list entry with no content"))
                else:
                    token, value = get_invalid_mailbox(value, ',')
                    if leader is not None:
                        token[:0] = [leader]
                    address_list.append(Address([token]))
                    address_list.defects.append(errors.InvalidHeaderDefect(
                        "invalid address in address-list"))
            elif value[0] == ',':
                address_list.defects.append(errors.ObsoleteHeaderDefect(
                    "empty element in address-list"))
            else:
                token, value = get_invalid_mailbox(value, ',')
                if leader is not None:
                    token[:0] = [leader]
                address_list.append(Address([token]))
                address_list.defects.append(errors.InvalidHeaderDefect(
                    "invalid address in address-list"))
        if value and value[0] != ',':
            # Crap after address; treat it as an invalid mailbox.
            # The mailbox info will still be available.
            mailbox = address_list[-1][0]
            mailbox.token_type = 'invalid-mailbox'
            token, value = get_invalid_mailbox(value, ',')
            mailbox.extend(token)
            address_list.defects.append(errors.InvalidHeaderDefect(
                "invalid address in address-list"))
        if value:  # Must be a , at this point.
            address_list.append(ValueTerminal(',', 'list-separator'))
            value = value[1:]
    return address_list, value
