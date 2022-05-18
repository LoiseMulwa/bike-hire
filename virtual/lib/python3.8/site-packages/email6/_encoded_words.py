""" Routines for manipulating RFC2047 encoded words. """

# An ecoded word looks like this:
#
#        =?charset?cte?encoded_string?=
#
# for more information about charset see the charset module.  Here it is a one
# of the preferred MIME charset names (hopefully, you never know when parsing).
# cte, Content Transfer Encoding, is either 'q' or 'b' (ignoring case).  In
# theory other letters could be used for other encodings, but in practice this
# (almost?) never happens.  (XXX There could be a public API for adding entries
# to to the CTE tables, but YAGNI for now.)  'q' is Quoted Printable, 'b' is
# Base64.  The meaning of encode_string should be obvious.
#
# The general interface for a CTE decoder is that it takes the encoded_string as
# its argument, and returns a tuple (cte_decoded_string, defects).  The
# cte_decoded_string is the original binary that was encoded using the
# specified cte.  'defects' is a list of MessageDefect instances indicating any
# problems encountered during conversion.

import re
import base64
import binascii
from email6 import errors

#
# Quoted Printable
#

_q_byte_subber = re.compile(br'=([a-fA-F0-9]{2})').sub

def decode_q(encoded):
    encoded = encoded.replace(b'_', b' ')
    return _q_byte_subber(
        lambda m: bytes([int(m.group(1), 16)]), encoded), []

#
# Base64
#

def decode_b(encoded):
    defects = []
    pad_err = len(encoded) % 4
    if pad_err:
        defects.append(errors.InvalidBase64PaddingDefect())
        padded_encoded = encoded + b'==='[:4-pad_err]
    else:
        padded_encoded = encoded
    try:
        return base64.b64decode(padded_encoded, validate=True), defects
    except binascii.Error:
        # Since we had correct padding, this must an invalid char error.
        defects = [errors.InvalidBase64CharactersDefect()]
        # The non-alphabet characters are ignored as far as padding
        # goes, but we don't know how many there are.  So we'll just
        # try various padding lengths until something works.
        for i in 0, 1, 2, 3:
            try:
                return base64.b64decode(encoded+b'='*i, validate=False), defects
            except binascii.Error:
                if i==0:
                    defects.append(errors.InvalidBase64PaddingDefect())
        else:
            # This should never happen.
            raise AssertionError("unexpected binascii.Error")

cte_decoders = {
    'q': decode_q,
    'b': decode_b,
    }

def decode(ew):
    """Decode encoded word and return (string, defects) tuple.

    An encoded word has the form:

        =?charset?cte?encoded_string?=

    This function expects exactly such a string, and returns the encoded_string
    decoded first from its Content Transfer Encoding and then from the
    resulting bytes into unicode using the specified charset.  If the
    cte-decoded string does not successfully decode using the specified
    character set, a defect added to the defects list and the unknown octets
    are replaced by the unicode 'unknown' character \uFDFF.

    """
    #XXX: We could perhaps do some heuristic recovery here.
    _, charset, cte, cte_string, _ = ew.split('?')
    cte = cte.lower()
    # Recover the original bytes and do CTE decoding.
    bstring = cte_string.encode('ascii', 'surrogateescape')
    bstring, defects = cte_decoders[cte](bstring)
    # Turn the CTE decoded bytes into unicode.
    try:
        string = bstring.decode(charset)
    except UnicodeError:
        defects.append(errors.UndecodableBytesDefect())
        string = bstring.decode(charset, 'replace')
    # XXX: more code to handle malformed ews?
    return string, defects
