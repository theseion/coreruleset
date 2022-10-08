from typing import TypeVar, List

from subprocess import Popen, PIPE, TimeoutExpired
import sys, re

from lib.processors.processor import Processor
from lib.context import Context

T = TypeVar("T", bound="Assemble")


class Assemble(Processor):
    input_regex = re.compile(r'^\s*##!=<\s*(.*)$')
    output_regex = re.compile(r'^\s*##!=>\s*(.*)$')
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
        regex = self._run_assembler()
        result = self.output + regex
        self.logger.debug('Completed assembly: %s', result)

        return result if result == '' else [result]

    def _run_assembler(self) -> str:
        self.logger.debug('Running assembler with lines: %s', self.lines)
        if len(self.lines) == 0:
            return ''

        args = [str(self.context.regexp_assemble_pl_path)]
        outs = None
        errs = None
        proc = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        for line in self.lines:
            proc.stdin.write(line.encode("utf-8"))
            proc.stdin.write(b"\n")
        try:
            outs, errs = proc.communicate(timeout=30)
            self.logger.debug('Assembler errors: %s, output %s', errs, outs)
        except TimeoutExpired:
            proc.kill()
            self.logger.error("Assembling regex timed out")
            self.logger.err("Stderr: %s", errs)
            sys.exit(1)

        if errs:
            self.logger.error("Failed to assemble regex")
            self.logger.error("Stderr: %s", errs)
            sys.exit(1)

        self.lines = []

        try:
            return outs.split(b"\n")[0].decode("utf-8")
        except Exception as e:
            print(sys.exc_info())


    def _store(self, identifier: str):
        if not identifier:
            raise ValueError('missing identifier for input marker')

        self._append(None)
        self.logger.debug('Storing expression at %s: %s', identifier, self.output)
        self.stash[identifier] = self.output
        # reset output, the next call to `complete` should not print
        # the value we just stored
        self.output = ''

    def _append(self, identifier: str):
        if not identifier:
            self.output += self._run_assembler()
        else:
            self.logger.debug('Appending stored expression at %s', identifier)
            self.output += self.stash[identifier]

    # def _remove_extra_groups(self, output: str) -> str:
    #     if not (output.startswith('(?:(?:') and output.endswith('))')):
    #         return output

    #     def replace(matchobj) -> str:
    #         return matchobj.group(0).replace(')', '_')
                    

    #     junk = re.sub(r'\\\)|\[[^\]]+\)', replace, output)

    #     balance = 0
    #     index = 5
    #     while True:
    #         next_open = junk.find('(?:', index)
    #         next_close = junk.find(')', index)
    #         if next_open > -1 and next_open < next_close:
    #             balance += 1
    #             index = next_open + 1
    #         elif next_close > -1 and (next_close < next_open or next_open == -1):
    #             balance -= 1
    #             index = next_close + 1
    #         elif next_close == next_open and next_open == -1:
    #             break

    #     if balance == -2:
    #         return output[3:-1]
