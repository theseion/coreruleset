import pytest

from .fixtures import *
from lib.operators.assembler import Assembler, Peekerator, NestingError

class TestFileFormat:
    def test_preprocess_ignores_simple_comments(self, context):
        contents = '''##!line1
##! line2
##!\tline3
'''
        assembler = Assembler(context)

        output = list(assembler.preprocess_assembler(Peekerator(contents.splitlines())))

        assert len(output) == 0

    def test_preprocess_does_not_ignore_special_comments(self, context):
        contents = '''##!+i
##!+ smx
##!^prefix
##!^ prefix
##!$suffix
##!$ suffix
'''
        assembler = Assembler(context)

        output = list(assembler.preprocess_assembler(Peekerator(contents.splitlines())))

        assert output == contents.splitlines()


    def test_preprocess_does_not_require_comments_to_start_line(self, context):
        contents = '''##!line1
 ##! line2
 not blank ##!+smx 
\t\t##!foo
\t ##! bar
##!\tline3
'''
        assembler = Assembler(context)

        output = list(assembler.preprocess_assembler(Peekerator(contents.splitlines())))

        assert len(output) == 1
        assert output[0] == ' not blank ##!+smx '

    def test_preprocess_handles_preprocessor_comments(self, context):
        contents = '##!> assemble'
        assembler = Assembler(context)

        output = list(assembler.preprocess_assembler(Peekerator(contents.splitlines())))

        assert len(output) == 0

    def test_preprocess_ignores_empty_lines(self, context):
        contents = '''some line

another line'''
        assembler = Assembler(context)

        output = list(assembler.preprocess_assembler(Peekerator(contents.splitlines())))

        assert output == [
            'some line',
            'another line'
        ]

    def test_preprocess_fails_on_too_many_end_markers(self, context):
        contents = '''##!> assemble
##!> assemble
##!<
##!<
##!<
'''
        assembler = Assembler(context)

        with pytest.raises(NestingError):
            assembler.preprocess_assembler(Peekerator(contents.splitlines()))

    def test_preprocess_fails_on_too_few_end_markers(self, context):
        contents = '''##!> assemble
##!> assemble'''
        assembler = Assembler(context)

        with pytest.raises(NestingError):
            assembler.preprocess_assembler(Peekerator(contents.splitlines()))

    def test_preprocess_does_not_require_final_end_marker(self, context):
        contents = '''##!> assemble
##!> assemble
##!<
'''
        assembler = Assembler(context)

        output = list(assembler.preprocess_assembler(Peekerator(contents.splitlines())))

        assert len(output) == 0


class TestSpecialComments:
    def test_handles_ignore_case_flag(self, context):
        for contents in ['##!+i', '##!+ i', '##!+   i' ]:
            assembler = Assembler(context)
            output = assembler._run(Peekerator(contents.splitlines()))

            assert output == "(?i)"

    def test_handles_single_line_flag(self, context):
        for contents in ['##!+s', '##!+ s', '##!+   s' ]:
            assembler = Assembler(context)
            output = assembler._run(Peekerator(contents.splitlines()))

            assert output == "(?s)"

    def test_handles_no_other_flags(self, context):
        contents = '##!+mx'
        assembler = Assembler(context)
        output = assembler._run(Peekerator(contents.splitlines()))

        assert len(output) == 0

    def test_handles_prefix_comment(self, context):
        contents = '''##!^ a prefix
a
b'''
        assembler = Assembler(context)
        output = assembler._run(Peekerator(contents.splitlines()))

        assert output == 'a prefix[a-b]'

    def test_handles_suffix_comment(self, context):
        contents = '''##!$ a suffix
a
b'''
        assembler = Assembler(context)
        output = assembler._run(Peekerator(contents.splitlines()))

        assert output == '[a-b]a suffix'

class TestSpecialCases:
    def test_ignores_empty_lines(self, context):
        contents = '''some line

another line'''
        assembler = Assembler(context)
        output = assembler._run(Peekerator(contents.splitlines()))

        assert output == '(?:some|another) line'

    def test_returns_no_output_for_empty_input(self, context):
        contents = '''##!+ _

'''
        assembler = Assembler(context)
        output = assembler._run(Peekerator(contents.splitlines()))

        assert len(output) == 0

    def test_handles_backslash_escape_correctly(self, context):
        contents = r'\x5c\x5ca'
        assembler = Assembler(context)
        output = assembler._run(Peekerator(contents.splitlines()))

        assert output == r'\x5c\x5ca'

    def test_does_not_destroy_hex_escapes(self, context):
        contents = r'a\x5c\x48\\x48b'
        assembler = Assembler(context)
        output = assembler._run(Peekerator(contents.splitlines()))

        assert output == r'a\x5cH\x5cx48b'

    def test_does_not_destroy_hex_escapes_in_alternations(self, context):
        contents = r'''a\x5c\x48
b\x5c\x48
'''
        assembler = Assembler(context)
        output = assembler._run(Peekerator(contents.splitlines()))

        assert output == r'[a-b]\x5cH'

    def test_handles_escaped_alternations_correctly(self, context):
        contents = r'\|\|something|or other'
        assembler = Assembler(context)
        output = assembler._run(Peekerator(contents.splitlines()))

        assert output == r'\|\|something|or other'

    def test_always_escapes_double_quotes(self, context):
        contents = r'(?:"\"\\"a)'
        assembler = Assembler(context)
        output = assembler._run(Peekerator(contents.splitlines()))

        assert output == r'\"\"\x5c"a'

    def test_does_not_convert_hex_escapes_of_non_printable_characters(self, context):
        contents = r'(?:\x48\xe2\x93\xab)'
        assembler = Assembler(context)
        output = assembler._run(Peekerator(contents.splitlines()))

        assert output == r'H\xe2\x93\xab'

    def test_backslash_s_replaces_perl_equivalent_character_class(self, context):
        # rassemble-go returns `[\t-\n\f-\r ]` for `\s`, which is correct for Perl
        # but does not include `\v`, which `\s` does in PCRE (3 and 2).
        contents = r'\s'
        assembler = Assembler(context)
        output = assembler._run(Peekerator(contents.splitlines()))

        assert output == r'\s'

class TestPreprocessors:
    def test_sequential_preprocessors(self, context):
        contents = '''##!> cmdline unix
foo
##!<
##!> cmdline windows
bar
##!<
##!> assemble
one
two
three
##!<
four
five
'''
        assembler = Assembler(context)

        output = list(assembler.preprocess_assembler(Peekerator(contents.splitlines())))

        assert output == [
            'f[\\x5c\'\\"\\[]*(?:\\$[a-z0-9_@?!#{*-]*)?(?:\\x5c)?o[\\x5c\'\\"\\[]*(?:\\$[a-z0-9_@?!#{*-]*)?(?:\\x5c)?o',
            'b[\\"\\^]*a[\\"\\^]*r',
            '(?:one|t(?:wo|hree))',
            'four',
            'five'
        ]

    def test_nested_preprocessors(self, context):
        contents = '''##!> assemble
    ##!> cmdline unix
foo
    ##!<
    ##!> cmdline windows
bar
    ##!<
##!<
four
five
'''
        assembler = Assembler(context)

        output = list(assembler.preprocess_assembler(Peekerator(contents.splitlines())))


        assert output == [
            '(?:f[\\x5c\'\\"\\[]*(?:\\$[a-z0-9_@?!#{*-]*)?(?:\\x5c)?o[\\x5c\'\\"\\[]*(?:\\$[a-z0-9_@?!#{*-]*)?(?:\\x5c)?o|b[\\"\\^]*a[\\"\\^]*r)',
            'four',
            'five'
        ]

    def test_complex_nested_preprocessors(self, context):
        contents = '''##!> assemble
    ##!> cmdline unix
foo
        ##!> assemble
ab
cd
        ##!<
    ##!<
    ##!> cmdline windows
bar
    ##!<
##!<
four
five
##!> assemble
six
seven
##!<
eight
'''
        assembler = Assembler(context)

        output = list(assembler.preprocess_assembler(Peekerator(contents.splitlines())))


        assert output == [
            r'''(?:f["'\\]*o["'\\]*o|((?:["'\\]*?["'\\]*:["'\\]*a["'\\]*b|["'\\]*c["'\\]*d)["'\\]*)|b["\^]*a["\^]*r)''',
            'four',
            'five',
            '(?:s(?:ix|even))',
            'eight'
        ]
