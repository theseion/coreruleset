#!/usr/bin/env perl
#
# Create one regexp from a set of regexps.
# Regexps can be submitted via standard input, one per line.
#
# Requires Regexp::Assemble Perl module.
# To install: cpan install Regexp::Assemble
#
# See: https://coreruleset.org/20190826/optimizing-regular-expressions/
#

use strict;
use FindBin qw( $RealBin );

# load Regexp::Assemble from the submodule, not from any other location
use lib "$RealBin/lib/lib";
use Regexp::Assemble;

my $re_nested;
$re_nested = qr{
	\(                   # open paren
	((?:                 # start capture  
		(?>[^()]+)       | # Non-parens w/o backtracking or ...
		(??{ $re_nested }) # Group with matching parens
	)*)                  # end capture
	\)                   # close paren
}msx;

my $re_optimize = qr{(?<=[^\\])\|}ms;

my @lines = ();

while (<>)
{
  # strip new lines
  CORE::chomp($_);

  # skip comments
  next if $_ =~ /^##!/;
  # skip empty lines
  next if $_ =~ /^\s*$/;

  push(@lines, $_);
}

print _run_assembly(@lines);


sub _assemble {
	my $str = shift;
	if ( $str !~ m/[(]/ms ) {
		return _optimize($str);
	}
	$str =~ s{$re_nested}{
		no warnings 'uninitialized';
		my $sub = $1;
		if ($sub =~ m/\A\?(?:[\?\{\(PR]|[\+\-]?[0-9])/ms) {
			"($sub)";  # (?{CODE}) and like ruled out
		}else{
			my $mod = ($sub =~ s/\A\?//) ? '?' : '';
			if ($mod) {
				$sub =~ s{\A(
							  [\w\^\-]*: | # modifier
							  [<]?[=!]   | # assertions
							  [<]\w+[>]  | # named capture
							  [']\w+[']  | # ditto
							  [|]          # branch reset
						  )
					 }{}msx;
				$mod .= $1;
			}
			'(' . $mod . _assemble($sub) . ')'
		}
	}msxge;
	$str;
}

sub _optimize {
	my $str = shift;

	# cook_hex: disable replacing hex escapes with decodec bytes
	# force_escape_tokens: we embed the resulting regex within double quotes,
	#                      so they all need to be escaped
	my $ra = Regexp::Assemble->new(cook_hex => 0, force_escape_tokens => q("));
	my @parts;
	if ($str =~ $re_optimize) {
		@parts = split(m{[|]}, $str);
	} else {
		@parts = ($str);
	}

	# The code below does nearly the same thing as add(), which is enough for our pruposes.
	for my $part (@parts)
	{
		# We explicitly don't use `_fastlex` or `split` here (as is done in `_add`).
		# `lexstr` uses `_lex`, which is more expensive but produces more reliable output.
		# On the downside, some characters will be escaped (or will retain their escape),
		# even though they don't need to be.
		#
		# Example issue solved by `_lex`: `\(?` produces `\(\?` with `_fastlex`
		# Example escape introduced by `_lex`: `/` produces `\/`
		my $arr = $ra->lexstr($part);
		_fix_possessive_plus($arr);
		$ra->insert(@$arr);
	}
	# call as_string() to make stats_length() work
	my $pattern = $ra->as_string();
	# don't print the assembled string if nothing was added,
	# the module will produce an all-matching pattern (`^\b\x00`)
	return $pattern if $ra->stats_length() > 0;
	return ""
}

sub _fix_possessive_plus {
	# Fix bad parsing of possessive ++
	# https://rt.cpan.org/Public/Bug/Display.html?id=50228#txn-672717
	#
	# Example input to script: `(a++|b)++|b`
	# Sub would be called with: `[a+, +]`
	# Sub would transform input to `[a++]`
	#
	# The transformation below will find consecutive pairs, where the first
	# element ends with `+` and the alst element is only `+`.
	my $arr = shift;

	for (my $n = 0; $n < $#$arr; ++$n)
	{
		if ($arr->[$n] =~ /\+$/ and $arr->[$n + 1] eq '+') {
			# delete the second of the pair, concatenating it with the first element
			$arr->[$n] .= splice(@$arr, $n + 1, 1);
		}
	}
}
 
sub _run_assembly {
	my @lines = @_;
	my $result = '';

	for my $str (@lines) {
		my ($mod) = ($str =~ m/\A\(\?(.*?):/);
		if ( $mod =~ /x/ ) {
			$str =~ s{^\s+}{}mg;
			$str =~ s{(?<=[^\\])\s*?#.*?$}{}mg;
			$str =~ s{\s+[|]\s+}{|}mg;
			$str =~ s{(?:\r\n?|\n)}{}msg;
			$str =~ s{[ ]+}{ }msgx;
			# warn $str;
		}
		# escape all occurance of '\(' and '\)'
		$str =~ s/\\([\(\)])/sprintf "\\x%02x" , ord $1/ge;
		# escape '|' in character classes
		$str =~ s/((?<!\\)\[[^[\]]*[^\\])\|/$1\\|/g;
		my $assembled = _assemble($str);
		if (length($result) > 0) {
			$result .= '|' . $assembled;
		} else {
			$result = $assembled;
		}

	}
  return $result if length($result) == 0;
  # Make sure the result is wrapped in a non-capturing group
  # to allow the returned expression to be used directly, e.g.,
  # by appending a qauntifier.
  $result = "(?:" . $result . ")";
  $result = _remove_extra_groups($result);
  return $result;
}

# Simple heuristic for removing extra non-capturing groups that encompass
# the entire expression. This routine only touches expressions without nested
# groups or even escaped parentheses for simplities sake.
sub _remove_extra_groups {
  my $result = shift;

  while ($result =~ /(?:\(\?:){2}[^)]+\)\)/) {
    $result =~ s/(?:\(\?:){2}([^)]+)\)\)/(?:$1)/;
  }
  return $result;
}
