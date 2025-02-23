# Copyright 2004-2022 Tom Rothamel <pytom@bishoujo.us>
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# This module contains code to support user-defined statements.

from __future__ import division, absolute_import, with_statement, print_function, unicode_literals
from renpy.compat import PY2, basestring, bchr, bord, chr, open, pystr, range, str, tobytes, unicode # *


import renpy

# The statement registry. It's a map from tuples giving the prefixes of
# statements to dictionaries giving the methods used for that statement.
registry = { }

parsers = renpy.parser.ParseTrie()


def register(
        name,
        parse=None,
        lint=None,
        execute=None,
        predict=None,
        next=None,
        scry=None,
        block=False,
        init=False,
        translatable=False,
        execute_init=None,
        init_priority=0,
        label=None,
        warp=None,
        translation_strings=None,
        force_begin_rollback=False,
        post_execute=None,
        post_label=None,
        predict_all=True,
        predict_next=None,
):
    """
    :doc: statement_register
    :name: renpy.register_statement

    This registers a user-defined statement.

    `name`
        This is either a space-separated list of names that begin the statement, or the
        empty string to define a new default statement (the default statement will
        replace the say statement).

    `block`
        When this is False, the statement does not expect a block. When True, it
        expects a block, but leaves it up to the lexer to parse that block. If the
        string "script", the block is interpreted as containing one or more
        Ren'Py script language statements. If the string "possible", the
        block expect condition is determined by the parse function.

    `parse`
        This is a function that takes a Lexer object. This function should parse the
        statement, and return an object. This object is passed as an argument to all the
        other functions.

    `lint`
        This is called to check the statement. It is passed a single argument, the
        object returned from parse. It should call renpy.error to report errors.

    `execute`
        This is a function that is called when the statement executes. It is passed a
        single argument, the object returned from parse.

    `execute_init`
        This is a function that is called at init time, at priority 0.

    `predict`
        This is a function that is called to predict the images used by the statement.
        It is passed a single argument, the object returned from parse. It should return
        a list of displayables used by the statement.

    `next`
        This is a function that is called to determine the next statement.

        If `block` is not "script", this is passed a single argument, the object
        returned from the parse function. If `block` is "script", an additional
        argument is passed, an object that names the first statement in the block.

        The function should return either a string giving a label to jump to,
        the second argument to transfer control into the block, or None to
        continue to the statement after this one.

    `label`
        This is a function that is called to determine the label of this
        statement. If it returns a string, that string is used as the statement
        label, which can be called and jumped to like any other label.

    `warp`
        This is a function that is called to determine if this statement
        should execute during warping. If the function exists and returns
        true, it's run during warp, otherwise the statement is not run
        during warp.

    `scry`
        Used internally by Ren'Py.

    `init`
        True if this statement should be run at init-time. (If the statement
        is not already inside an init block, it's automatically placed inside
        an init block.) This calls the execute function, in addition to the
        execute_init function.

    `init_priority`
        An integer that determines the priority of initialization of the
        init block.

    `translation_strings`
        A function that is called with the parsed block. It's expected to
        return a list of strings, which are then reported as being available
        to be translated.

    `force_begin_rollback`
        This should be set to true on statements that are likely to cause the
        end of a fast skip, similar to ``menu`` or ``call screen``.

    `post_execute`
        A function that is executed as part the next statement after this
        one. (Adding a post_execute function changes the contents of the RPYC
        file, meaning a Force Compile is necessary.)

    `post_label`
        This is a function that is called to determine the label of this
        the post execute statement. If it returns a string, that string is used
        as the statement label, which can be called and jumped to like any other
        label. This can be used to create a unique return point.

    `predict_all`
        If True, then this predicts all sub-parses of this statement and
        the statement after this statement.

    `predict_next`
        This is called with a single argument, the label of the statement
        that would run after this statement.

        This should be called to predict the statements that can run after
        this one. It's expected to return a list of of labels or SubParse
        objects. This is not called if `predict_all` is true.
    """

    name = tuple(name.split())

    if label:
        force_begin_rollback = True

    registry[name] = dict(
        parse=parse,
        lint=lint,
        execute=execute,
        execute_init=execute_init,
        predict=predict,
        next=next,
        scry=scry,
        label=label,
        warp=warp,
        translation_strings=translation_strings,
        rollback="force" if force_begin_rollback else "normal",
        post_execute=post_execute,
        post_label=post_label,
        predict_all=predict_all,
        predict_next=predict_next,

    )

    if block not in [True, False, "script", "possible" ]:
        raise Exception("Unknown \"block\" argument value: {}".format(block))

    # The function that is called to create an ast.UserStatement.
    def parse_user_statement(l, loc):

        renpy.exports.push_error_handler(l.error)

        old_subparses = l.subparses

        try:
            l.subparses = [ ]

            text = l.text
            subblock = l.subblock

            code_block = None

            if block is False:
                l.expect_noblock(" ".join(name) + " statement")
            elif block is True:
                l.expect_block(" ".join(name) + " statement")
            elif block == "script":
                l.expect_block(" ".join(name) + " statement")
                code_block = renpy.parser.parse_block(l.subblock_lexer())

            start_line = l.line

            parsed = name, parse(l)

            if l.line == start_line:
                l.advance()

            rv = renpy.ast.UserStatement(loc, text, subblock, parsed)
            rv.translatable = translatable
            rv.translation_relevant = bool(translation_strings)
            rv.code_block = code_block
            rv.subparses = l.subparses

        finally:
            l.subparses = old_subparses
            renpy.exports.pop_error_handler()

        if (post_execute is not None) or (post_label is not None):
            post = renpy.ast.PostUserStatement(loc, rv)
            rv = [ rv, post ]

        if init and not l.init:
            rv = renpy.ast.Init(loc, [rv], init_priority + l.init_offset)

        return rv

    renpy.parser.statements.add(name, parse_user_statement)

    # The function that is called to get our parse data.
    def parse_data(l):
        return (name, registry[name]["parse"](l))

    parsers.add(name, parse_data)


def parse(node, line, subblock):
    """
    This is used for runtime parsing of CDSes that were created before 7.3.
    """

    block = [ (node.filename, node.linenumber, line, subblock) ]
    l = renpy.parser.Lexer(block)
    l.advance()

    renpy.exports.push_error_handler(l.error)
    try:

        pf = parsers.parse(l)
        if pf is None:
            l.error("Could not find user-defined statement at runtime.")

        return pf(l)

    finally:
        renpy.exports.pop_error_handler()


def call(method, parsed, *args, **kwargs):
    name, parsed = parsed

    method = registry[name].get(method)
    if method is None:
        return None

    return method(parsed, *args, **kwargs)


def get(key, parsed):
    name, parsed = parsed
    return registry[name].get(key, None)


def get_name(parsed):
    name, _parsed = parsed
    return " ".join(name)
