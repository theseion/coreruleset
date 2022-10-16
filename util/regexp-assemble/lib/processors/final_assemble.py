from typing import TypeVar, List, Set

import re

from lib.processors.assemble import Assemble
from lib.context import Context

T = TypeVar("T", bound="FinalAssemble")


class FinalAssemble(Assemble):
    # We currently only support the `i` flag
    supported_flags = 'i'
    flags_regex = re.compile(r'^\s*##!\+\s*(.*)$')
    prefix_regex = re.compile(r'^\s*##!\^\s*(.*)$')
    suffix_regex = re.compile(r'^\s*##!\$\s*(.*)$')
    double_quotes_regex = re.compile(r'(?<!\\)"')
    literal_backslash_regex = re.compile(r'\\\\')

    def __init__(self, context: Context):
        super().__init__(context)

        self.flags: Set[str] = set()
        self.prefixes = ''
        self.suffixes = ''

    # override
    def process_line(self, line: str):
        match = self.flags_regex.match(line)
        if match:
            group = match.group(1)
            self.logger.debug("Matched flags", group)
            for flag in group:
                if flag in self.supported_flags:
                    self.flags.add(group)
            return
        
        match = self.prefix_regex.match(line)
        if match:
            group = match.group(1)
            self.logger.debug("Matched prefix", group)
            self.prefixes += group
            return

        match = self.suffix_regex.match(line)
        if match:
            group = match.group(1)
            self.logger.debug("Matched suffix", group)
            self.suffixes += group
            return

        super().process_line(line)

    # override
    def complete(self) -> List[str]:
        regex_list = super().complete()

        flags_prefix = ''
        if self.flags:
            sorted_flags = list(self.flags)
            sorted_flags.sort()
            flags_prefix = f'(?{"".join(sorted_flags)})'

        regex = regex_list[0] if regex_list else ''
        if self.prefixes or self.suffixes and regex:
            regex = '(?:' + regex + ')'
        regex = self.prefixes + regex + self.suffixes
        if regex:
            regex = self._run_simplification_assembly(regex)
            regex = self._escape_double_quotes(regex)
            regex = self._use_hex_backslashes(regex)
        if flags_prefix:
            regex = flags_prefix + regex
        return [regex] if regex else []

    # Does the same as the `force_escape_tokens` flag for Regex::Assemble:
    # we need all double quotes to be escaped because we use them
    # as delimiters in rules.
    def _escape_double_quotes(self, input: str) -> str:
        def replace(_):
            return r'\"'

        return self.double_quotes_regex.sub(replace, input)

    # Replace all literal backslashes with `\x5c`, the hexadecimal
    # representation of a backslash. This is for compatibility and
    # readbility reasons, as Apache httpd handles sequences of backslashes
    # differently than nginx.
    def _use_hex_backslashes(self, input: str) -> str:
        def replace(_):
            return r'\x5c'

        return self.literal_backslash_regex.sub(replace, input)

    # Once the entire expression has been assembled, run one last
    # pass to possibly simplify groups and concatenations.
    def _run_simplification_assembly(self, input: str) -> str:
        self.lines.append(input)
        return self._run_assembler()
