#!/usr/bin/env python3
# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""
Utility to check if deprecated libchrome calls are introduced.
"""

from __future__ import print_function

import argparse
import os
import re
import subprocess
import sys

# BAD_KEYWORDS are mapping from bad_keyword_in_regex to
# error_msg_if_match_found.
BAD_KEYWORDS = {
    # removal of deprecated base::Bind APIs
    r'base::(Bind|Closure|Callback|CancelableCallback|CancelableClosure)(\(|<)':
    'Deprecated base::Bind APIs. Please use the Once or Repeating variants. See crbug/714018.',
    # unify *::optionals to std::optional
    r'(include.*absl/types/optional.h|absl::(optional|make_optional|nullopt))':
    'Use std::optional. absl::optional is an alias of std::optional. See go/use-std-optional-in-cros for discussion.',
    # Migrate base::Delete* to brillo::Delete* to fix security bugs
    r'base::Delete(File|PathRecursively)\(':
    'Deprecated base::Delete* APIs. Use brillo::Delete* instead. See b/272503861',
    # removal of deprecated base::ThreadLocal(Pointer|Boolean) APIs
    r'base::(ThreadLocalBoolean|ThreadLocalPointer)':
    'Use `thread_local bool|T*` instead. See https://chromium.googlesource.com/chromium/src/+/main/styleguide/c++/c++.md#thread_local-variables for discussion. (b/274724518)',
    # base::StringPiece will be deprecated and replaced by std:string_view.
    r'(include.*base/strings/string_piece.h|base::StringPiece)':
    'Use the now equivalent std::string_view (crrev.com/c/4294483). See upstream bug crbug.com/691162 for details.',
    # UMA_HISTOGRAM macros send their metrics into the void on CrOS.
    r'UMA_(?:STABILITY_){0,1}HISTOGRAM[_A-Z0-9]*\(': 'Chromium UMA macros don\'t work on CrOS. See crsrc.org/o/src/platform2/metrics/metrics_library.h if you want to collect metrics on CrOS.',
    # UmaHistogram functions send their metrics into the void on CrOS.
    r'(?:base::){0,1}UmaHistogram[a-zA-Z0-9]*\(': 'Chromium UmaHistogram functions don\'t work on CrOS. See crsrc.org/o/src/platform2/metrics/metrics_library.h if you want to collect metrics on CrOS.',
    # base::SupportsWeakPtr will be deprecated
    r'base::SupportsWeakPtr': 'Deprecated base::SupportsWeakPtr.  See crbug.com/40485134 for details.',
    r'NOTREACHED_IN_MIGRATION\(':
    'CrOS libchrome NOTREACHED migration, do NOT use NOTREACHED_IN_MIGRATION. Use NOTREACHED which is now fatal and [[noreturn]]. See b/356312475',
    r'HistogramBase::Sample[^3]': 'base::HistogramBase::Sample is deprecated. Use base::HistogramBase::Sample32.',
}

LINE_NUMBER_RE=re.compile(r'^@@ [0-9\,\+\-]+ \+([0-9]+)[ \,][0-9 ]*@@')

def addedLinesFromCommit(filename, commit):
  '''Return list of (line number, line) pairs added to file by the given commit.
  '''
  diff = subprocess.check_output(
      ['git', 'show', '--oneline', commit, '--', filename]).decode(
          sys.stdout.encoding).split('\n')
  line_number = -1
  lines = []
  for line in diff:
    m = LINE_NUMBER_RE.match(line)
    if m:
      line_number = int(m.groups(1)[0])-1
      continue
    if not line.startswith('-'):
      line_number += 1
    if line.startswith('+++') or not line.startswith('+'):
      continue
    lines.append((line_number, line[1:]))

  return lines

def checkFileLines(filename, lines, keywords):
  '''Check for forbidden patterns in given lines of a file.

  Args:
    filename: of the source file.
    lines: a list of (line number, line) pairs to be checked.
    keywords: a list of (regex, description) pairs of forbidden patterns

  Returns:
    A list of error messages reporting forbidden patterns found.
  '''
  errors = []
  for line_number, line in lines:
    for bad_pattern, error_message in keywords.items():
      m = re.search(bad_pattern, line)
      if m:
        errors.append('In File %s line %s col %s, found %s (pattern: %s), %s' %
                      (filename, line_number, m.span()[0]+1, m.group(0),
                       bad_pattern, error_message))
        break

  return errors


def checkFiles(files, commit, keywords=BAD_KEYWORDS):
  '''Check for forbidden patterns from given list of files.

  Args:
    files: a list of filenames.
    commit: hash of a commit. If given, only lines added to this commit will be
    checked; otherwise check all lines.
    keywords: a list of (regex, description) pairs of forbidden patterns

  Returns:
    A list of error messages reporting forbidden patterns found.
  '''
  errors = []

  for filename in files:
    if not (filename.endswith('.h') or filename.endswith('.cc')):
        continue
    if commit:
      lines = addedLinesFromCommit(filename, commit)
    else:
      with open(filename) as f:
        lines = [(i+1, line) for i, line in enumerate(f.readlines())]
    errors += checkFileLines(filename, lines, keywords)

  return errors


def main():
  parser = argparse.ArgumentParser(
      description='Check no forbidden libchrome features are used.')

  parser.add_argument('--commit',
                      help='Hash of commit to check. Only show errors on ' \
                           'lines added in the commit if set.')
  parser.add_argument('files', nargs='*')
  args = parser.parse_args()

  errors = checkFiles(args.files, args.commit)

  if errors:
      print('\n'.join(errors), file=sys.stderr)
      sys.exit(1)


if __name__ == '__main__':
    main()
