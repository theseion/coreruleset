import string
from typing import TypeVar, List

from subprocess import Popen, PIPE, TimeoutExpired
import sys, re
from uuid import uuid4

from lib.processors.processor import Processor
from lib.context import Context

T = TypeVar("T", bound="Assemble")


class Assemble(Processor):
    input_regex = re.compile(r'^\s*##!=<\s*(.*)$')
    output_regex = re.compile(r'^\s*##!=>\s*(.*)$')
    hex_escape_regex = re.compile(r'\[(?:[^]]|\\\])*\\x[0-9a-f]{2}|(?<!\\)(\\x[0-9a-f]{2})')
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
            # escaped_line = self._guard_hex_escapes(line)
            # if escaped_line != line:
                # self.logger.debug('Escaped line: %s', escaped_line)

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
            result = self._use_hex_escapes(result)
            return result
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
    # As it is, escapes that are printable runes will be returned as such,
    # which means we will have weird looking characters in our regex
    # instead of hex escapes.
    # To replace the characters with their hex escape sequence, we can simply
    # take the decimal value of each byte (this might be a single byte of a
    # multi-byte sequnce), check whether it is a printable character and
    # then either append it to the output string or create the equivalent
    # escape code.
    #
    # Note: presumes that hexadecimal escapes in the input create UTF-8
    # sequences.
    #
    # Note: not all hex escapes in the input will be escaped in the
    # output, but all printable non-printable characters, including
    # `\v\n\r` and space (`\x32`).
    def _use_hex_escapes(self, input: str) -> str:
        result = ''
        for char in input:
            dec_value = ord(char)
            if dec_value < 32 or dec_value > 126:
                result += f'\\x{format(dec_value, "x")}'
            else:
                result += char
        return result
