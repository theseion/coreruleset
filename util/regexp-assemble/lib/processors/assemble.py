from typing import TypeVar, List

from subprocess import Popen, PIPE, TimeoutExpired
import sys, re

from lib.processors.processor import Processor
from lib.context import Context

T = TypeVar("T", bound="Assemble")


class Assemble(Processor):
    input_regex = re.compile(r'^\s*##!=<\s*(.*)$')
    output_regex = re.compile(r'^\s*##!=>\s*(.*)$')
    hex_escape_regex = re.compile(r'\[(?:[^]]|\\\])*\\x[0-9a-f]{2}|(?<!\\)(\\x[0-9a-f]{2})')
    hex_escape_recovery_regex = re.compile(r'_x_\\(\\x[0-9a-f]{2})_x_')
    stash = {}

    def __init__(self, context: Context):
        super().__init__(context)

        self.output = ''

    # override
    @classmethod
    def create(cls: T, context: Context, args: List[str]) -> T:
        return cls(context)

    # override
    def process_line(self, line: str):
        match = self.input_regex.match(line)
        if match:
            self._store(match.group(1) if match.groups() else '')
            return

        match = self.output_regex.match(line)
        if match:
            self._append(match.group(1) if match.groups() else '')
        else:
            self.lines.append(line)

    # override
    def complete(self) -> List[str]:
        self.logger.debug('Completing assembly')
        # if self.output.startswith(r'\s*;\s*'):
        #     import pdb; pdb.set_trace()
        regex = self._run_assembler()

        result = self._wrap_completed_assembly(regex)
        self.logger.debug('Completed assembly: %s', result)

        return [result] if len(result) > 0 else []

    def _wrap_completed_assembly(self, regex: str) -> str:
        if not regex and not self.output:
            return ''

        elif self.output and regex:
            result = f'(?:{self.output}(?:{regex}))'
        elif self.output:
            result = '(?:' + self.output + ')'
        elif not regex:
            result = ''
        else:
            result = '(?:' + regex + ')'

        return result

    def _run_assembler(self) -> str:
        self.logger.debug('Running assembler with lines: %s', self.lines)
        if not self.lines:
            return ''

        args = ['rassemble']
        outs = None
        errs = None
        proc = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        for line in self.lines:
            line = self._guard_hex_escapes(line)
            proc.stdin.write(line.encode("utf-8"))
            proc.stdin.write(b"\n")
        try:
            outs, errs = proc.communicate(timeout=30)
            self.logger.debug('Assembler errors: %s, output %s', errs, outs)
        except TimeoutExpired:
            proc.kill()
            self.logger.error("Assembling regex timed out")
            self.logger.error("Stderr: %s", errs)
            sys.exit(1)

        if errs:
            self.logger.error("Failed to assemble regex")
            self.logger.error("Stderr: %s", errs)
            sys.exit(1)

        self.lines = []

        try:
            result = outs.split(b"\n")[0].decode("utf-8")
            return self._recover_guarded_hex_escapes(result)
        except Exception:
            print(sys.exc_info())
            sys.exit(1)


    def _store(self, identifier: str):
        if not identifier:
            raise ValueError('missing identifier for input marker')

        self._append(None)
        self.logger.debug('Storing expression at %s: %s', identifier, self.output)
        self.stash[identifier] = self.output
        # reset output, the next call to `complete` should not print
        # the value we just stored
        self.output = ''

    def _append(self, identifier: str|None):
        if not identifier:
            if len(self.lines) == 1:
                # Treat as literal, could be start of a group or a range expresssion.
                # Those can not be parsed by rassemble-go, since they are not valid
                # expressions.
                self.output += self.lines[0]
                self.lines = []
            else:
                self.output += '(?:' + self._run_assembler() + ')'
        else:
            self.logger.debug('Appending stored expression at %s', identifier)
            self.output += self.stash[identifier]

    # rassemble-go doesn't provide an option to specify literals.
    # Go itself would, via the `Literal` flag to `syntax.Parse`.
    # As we don't have access to Go anyway, the only recourse is to
    # use Perl quotemeta to mark the hex escape as a literal. If
    # we didn't do this, the Go `regexp/syntax` package would convert
    # the escapes to their actual value.
    # Unfortunately, `regexp/syntax` parses Perl quotemeta but it doesn't
    # provide a way to include it in the string form of the parsed expression.
    # We try to work around this issue by adding a marker around the escape,
    # so that we know where the quotemeta escapes used to be.
    #
    # Note: Must not escape inside character classes, where escapes are treated
    # as literals anyway (Go will throw an exception, saying that quotemta escapes
    # aren't allowed within character classes).
    def _guard_hex_escapes(self, input: str) -> str:
        def replace(matchobject):
            # Don't escape in character class
            if matchobject.group(0).startswith('['):
                return matchobject.group(0)
            return rf'\Q_x_{matchobject.group(1)}_x_\E'
        return self.hex_escape_regex.sub(replace, input)

    # When we receive the output from rassemble-go, the quotemeta escapes
    # will have been removed and an additional backslash will have been added.
    # Look for the markers and strip the backslash away. We need the markers
    # so we don't accidentally alter an intended double backslash.
    def _recover_guarded_hex_escapes(self, input: str) -> str:
        def replace(matchobject):
            return f'{matchobject.group(1)}'

        return self.hex_escape_recovery_regex.sub(replace, input)
