#!/usr/bin/env python3
# Copyright 2026 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Audits open libchrome-uprev-cleanup bugs (hotlistid:4448649) against libchrome_tools/patches/ and Gerrit CLs."""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request


PATCHES_DIR = os.path.join('libchrome_tools', 'patches')
HOTLIST_ID = '4448649'
PATCH_RE = re.compile(
    r'((?:backward-compatibility|long-term|cherry-pick)-\d{4}-[^\s`"\'):]+\.patch)'
)
CL_RE = re.compile(
    r'(?:crrev\.com/c/|chromium-review\.googlesource\.com/c/[^\s+]+/\+/)(\d+)'
)


def query_open_hotlist_bugs(issues_bin):
  cmd = [
      issues_bin,
      'readonly',
      'search',
      f'--query=hotlistid:{HOTLIST_ID} status:open',
      '--limit=50',
  ]
  try:
    raw = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('utf-8')
  except Exception as e:
    print(f'Error querying Buganizer via {issues_bin}: {e}', file=sys.stderr)
    sys.exit(1)

  bugs = []
  current = {}
  for line in raw.splitlines():
    if line.startswith('Issue ID: '):
      if current.get('issueId'):
        bugs.append(current)
      current = {'issueId': line.split('Issue ID: ', 1)[1].strip()}
    elif line.startswith('Assignee: '):
      current['assignee'] = line.split('Assignee: ', 1)[1].strip()
    elif line.startswith('Title: '):
      current['title'] = line.split('Title: ', 1)[1].strip()
    elif line.startswith('Blocked By Issue IDs: '):
      current['blockers'] = [
          x.strip()
          for x in line.split('Blocked By Issue IDs: ', 1)[1].split(',')
          if x.strip()
      ]
  if current.get('issueId'):
    bugs.append(current)
  return bugs


def get_bug_comments_text(issues_bin, bug_id):
  cmd = [
      issues_bin,
      'readonly',
      'list-updates',
      f'--issue_id={bug_id}',
      '--limit=50',
  ]
  try:
    return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode(
        'utf-8'
    )
  except Exception:
    return ''


def get_gerrit_cl_status(cl_num):
  url = f'https://chromium-review.googlesource.com/changes/{cl_num}'
  try:
    with urllib.request.urlopen(url, timeout=5) as resp:
      raw = resp.read().decode('utf-8')
      if raw.startswith(")]}'"):
        raw = raw[4:]
      data = json.loads(raw)
      return data.get('status', 'UNKNOWN'), data.get('subject', '')
  except Exception:
    return 'UNKNOWN', ''


def main():
  parser = argparse.ArgumentParser(
      description='Audit open libchrome-uprev-cleanup bugs in hotlist 4448649.'
  )
  parser.add_argument(
      '--issues-bin',
      default='/google/bin/releases/issues-cli/issues',
      help='Path to Buganizer issues CLI binary',
  )
  args = parser.parse_args()

  if not os.path.isdir(PATCHES_DIR):
    print(
        f'Error: {PATCHES_DIR} not found. Run from root of libchrome repo.',
        file=sys.stderr,
    )
    sys.exit(1)

  existing_patches = set(os.listdir(PATCHES_DIR))
  backward_compat_patches = sorted(
      p for p in existing_patches if p.startswith('backward-compatibility-')
  )
  print(
      f'Found {len(backward_compat_patches)} backward-compatibility-*.patch'
      f' files in {PATCHES_DIR}:'
  )
  for p in backward_compat_patches:
    print(f'  - {p}')
  print()

  bugs = query_open_hotlist_bugs(args.issues_bin)
  print(f'Auditing {len(bugs)} open bugs in hotlistid:{HOTLIST_ID}...\n')

  for b in bugs:
    bug_id = b.get('issueId')
    title = b.get('title', '')
    assignee = b.get('assignee', 'unassigned')
    blockers = b.get('blockers', [])

    comments_text = get_bug_comments_text(args.issues_bin, bug_id)
    full_text = title + '\n' + comments_text

    patches_mentioned = sorted(set(PATCH_RE.findall(full_text)))
    cls_mentioned = []
    for cl in CL_RE.findall(full_text):
      if cl not in cls_mentioned:
        cls_mentioned.append(cl)

    active_patches = [p for p in patches_mentioned if p in existing_patches]
    deleted_patches = [
        p for p in patches_mentioned if p not in existing_patches
    ]

    if assignee == 'bugjuggler@google.com':
      category = 'SNOOZED_ON_BUGJUGGLER'
    elif any(p.startswith('long-term-') for p in active_patches):
      category = 'LONG_TERM_PATCH (Remove from hotlist 4448649)'
    elif patches_mentioned and not active_patches:
      category = 'ALREADY_REMOVED (Ready to close as FIXED)'
    elif (
        blockers or 'Bugjuggler:' in comments_text
    ) and assignee != 'bugjuggler@google.com':
      category = (
          f'BLOCKED_NEEDS_BUGJUGGLER_ASSIGNEE (blockers: {blockers or ["see Bugjuggler comment"]})'
      )
    else:
      category = 'ACTIONABLE'

    print(f'=== b/{bug_id} [{category}] ===')
    print(f'  Title:    {title}')
    print(f'  Assignee: {assignee}')
    if active_patches:
      print(f'  Active Patches in Repo:  {", ".join(active_patches)}')
    if deleted_patches:
      print(f'  Deleted Patches (Fixed): {", ".join(deleted_patches)}')
    if cls_mentioned:
      cl_summaries = []
      for cl in cls_mentioned[-5:]:
        st, _ = get_gerrit_cl_status(cl)
        cl_summaries.append(f'crrev.com/c/{cl} ({st})')
      print(f'  Recent CLs: {", ".join(cl_summaries)}')
    print()


if __name__ == '__main__':
  main()
