#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request


def get_luci_auth_binary():
  auth_path = shutil.which('luci-auth')
  if auth_path:
    return auth_path
  fallback = os.path.expanduser('~/depot_tools/luci-auth')
  if os.path.exists(fallback):
    return fallback
  return 'luci-auth'


def get_auth_token(scopes=None):
  cmd = [get_luci_auth_binary(), 'token']
  if scopes:
    cmd.extend(['-scopes', scopes])
  try:
    return (
        subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        .decode('utf-8')
        .strip()
    )
  except subprocess.CalledProcessError:
    print(
        "Error: luci-auth failed. Please run 'luci-auth login' or 'bb"
        " auth-login'"
    )
    sys.exit(1)
  except FileNotFoundError:
    print(
        'Error: luci-auth command not found. Please ensure it is installed and'
        ' in your PATH.'
    )
    sys.exit(1)


def get_bb_binary():
  bb_path = shutil.which('bb')
  if bb_path:
    return bb_path
  fallback = os.path.expanduser('~/depot_tools/bb')
  if os.path.exists(fallback):
    return fallback
  return 'bb'


def resolve_cq_builder(board):
  """Resolve full Buildbucket builder path (project/bucket/builder) for a board."""
  if '/' in board:
    parts = board.split('/')
    if len(parts) == 3:
      return board
    if len(parts) == 2:
      return f'chromeos/{board}'

  builder_name = board if board.endswith('-cq') else f'{board}-cq'
  base_board = builder_name[:-3]

  token = get_auth_token()
  url = 'https://cr-buildbucket.appspot.com/prpc/buildbucket.v2.Builders/GetBuilder'
  for bucket in [base_board, 'cq', 'all-partners']:
    payload = {
        'id': {
            'project': 'chromeos',
            'bucket': bucket,
            'builder': builder_name,
        }
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode('utf-8'), method='POST'
    )
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Accept', 'application/json')
    try:
      with urllib.request.urlopen(req) as _:
        return f'chromeos/{bucket}/{builder_name}'
    except Exception:
      continue

  return f'chromeos/{base_board}/{builder_name}'


def launch_single_board_tryjob(cl_number, board, patchset=None):
  """Schedule a single-board <board>-cq build directly via `bb add`."""
  change = get_change_info(cl_number)
  latest_ps_num = (
      change.get('revisions', {})
      .get(change.get('current_revision', ''), {})
      .get('_number')
  )
  if patchset is None:
    patchset = latest_ps_num

  cl_url = f'https://chromium-review.googlesource.com/c/chromiumos/platform/libchrome/+/{cl_number}/{patchset}'
  builder = resolve_cq_builder(board)
  bb_bin = get_bb_binary()

  print(f'Launching single-board CQ tryjob: {builder} for CL {cl_number} (patchset {patchset})...')
  try:
    output = subprocess.check_output(
        [bb_bin, 'add', '-cl', cl_url, builder],
        stderr=subprocess.STDOUT,
    ).decode('utf-8', errors='replace')
    print(output.strip())
  except subprocess.CalledProcessError as e:
    print(f'Error launching tryjob via bb add:\n{e.output.decode("utf-8", errors="replace")}')
    sys.exit(1)



def get_change_info(cl_number):
  url = f'https://chromium-review.googlesource.com/changes/{cl_number}?o=CURRENT_REVISION'
  req = urllib.request.Request(url)
  try:
    with urllib.request.urlopen(req) as response:
      data = response.read().decode('utf-8')
      if data.startswith(")]}'\n"):
        data = data[5:]
      return json.loads(data)
  except Exception as e:
    print(f'Error fetching Gerrit data: {e}')
    sys.exit(1)


def set_gerrit_review(cl_number, cq_vote=None, comment=None):
  token = get_auth_token(
      scopes='https://www.googleapis.com/auth/gerritcodereview'
  )
  url = f'https://chromium-review.googlesource.com/a/changes/{cl_number}/revisions/current/review'
  payload = {}
  if cq_vote is not None:
    payload['labels'] = {'Commit-Queue': int(cq_vote)}
  if comment:
    payload['message'] = comment

  req = urllib.request.Request(
      url, data=json.dumps(payload).encode('utf-8'), method='POST'
  )
  req.add_header('Authorization', f'Bearer {token}')
  req.add_header('Content-Type', 'application/json')
  req.add_header('Accept', 'application/json')

  try:
    with urllib.request.urlopen(req) as response:
      data = response.read().decode('utf-8')
      if data.startswith(")]}'\n"):
        data = data[5:]
      print(f'Successfully updated Gerrit CL {cl_number}: {payload}')
      return json.loads(data) if data.strip() else {}
  except urllib.error.HTTPError as e:
    print(f"Error updating Gerrit CL: {e.read().decode('utf-8')}")
    sys.exit(1)


def search_builds(cl, patchset):
  token = get_auth_token()
  url = 'https://cr-buildbucket.appspot.com/prpc/buildbucket.v2.Builds/SearchBuilds'
  all_builds = []
  page_token = None

  while True:
    req_data = {
        'predicate': {
            'gerritChanges': [{
                'host': 'chromium-review.googlesource.com',
                'change': int(cl),
                'patchset': int(patchset),
            }]
        },
        'pageSize': 1000,
        'mask': {
            'fields': 'id,status,builder,summaryMarkdown,createTime,endTime,ancestorIds'
        },
    }
    if page_token:
      req_data['pageToken'] = page_token

    req = urllib.request.Request(url, data=json.dumps(req_data).encode('utf-8'))
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Accept', 'application/json')

    try:
      with urllib.request.urlopen(req) as response:
        data = response.read().decode('utf-8')
        if data.startswith(")]}'\n"):
          data = data[5:]
        parsed = json.loads(data)
        all_builds.extend(parsed.get('builds', []))
        page_token = parsed.get('nextPageToken')
        if not page_token:
          break
    except urllib.error.HTTPError as e:
      print(f"Error fetching Buildbucket data: {e.read().decode('utf-8')}")
      sys.exit(1)

  return all_builds


def get_build_details(build_id):
  token = get_auth_token()
  url = 'https://cr-buildbucket.appspot.com/prpc/buildbucket.v2.Builds/GetBuild'
  req_data = {
      'id': str(build_id),
      'mask': {
          'fields': 'id,builder,status,summaryMarkdown,output,steps,infra'
      },
  }
  req = urllib.request.Request(url, data=json.dumps(req_data).encode('utf-8'))
  req.add_header('Authorization', f'Bearer {token}')
  req.add_header('Content-Type', 'application/json')
  req.add_header('Accept', 'application/json')

  try:
    with urllib.request.urlopen(req) as response:
      data = response.read().decode('utf-8')
      if data.startswith(")]}'\n"):
        data = data[5:]
      return json.loads(data)
  except Exception:
    return {}


def extract_board_name(builder_name):
  """Extract board name from builder name if it is a valid reproducer board."""
  excluded_substrings = [
      'orchestrator',
      'bazel',
      'sdknext',
      'fuzzer',
      'incremental',
      'host-packages',
      'chromite',
      'paygen',
      'test_runner',
      'cros_test_platform',
  ]
  for ex in excluded_substrings:
    if ex in builder_name:
      return None

  # Exclude staging CQ builders (e.g. staging-brya-cq), but allow cros-try builders (staging-brya-release-main)
  if builder_name.startswith('staging-') and builder_name.endswith('-cq'):
    return None

  if builder_name.endswith('-cq'):
    board = builder_name[:-3]
    if board.startswith('staging-'):
      board = board[len('staging-') :]
    return board

  if builder_name.endswith('-release-main'):
    board = builder_name[: -len('-release-main')]
    if board.startswith('staging-'):
      board = board[len('staging-') :]
    return board

  return None


def fetch_failure_logs(failing_builders_details, output_path):
  """Fetch failed step logs using `bb log` and write them to output_path."""
  bb_bin = get_bb_binary()
  collected_logs = []
  seen_log_names = set()

  # First pass: look for specific package build/test logs (e.g. "chromeos-base/libchrome log")
  for builder_name, b_info, details in failing_builders_details:
    build_id = b_info['id']
    steps = details.get('steps', [])
    failed_steps = [s for s in steps if s.get('status') == 'FAILURE']
    for s in failed_steps:
      step_name = s.get('name', '')
      for log_meta in s.get('logs', []):
        log_name = log_meta.get('name', '')
        if log_name.endswith(' log') and log_name not in seen_log_names:
          seen_log_names.add(log_name)
          collected_logs.append((builder_name, build_id, step_name, log_name))

  # Second pass: fallback to stdout of leaf failed steps if no package log found
  if not collected_logs:
    for builder_name, b_info, details in failing_builders_details:
      build_id = b_info['id']
      steps = details.get('steps', [])
      failed_steps = [s for s in steps if s.get('status') == 'FAILURE']
      for s in failed_steps[-2:]:
        step_name = s.get('name', '')
        log_names = [l.get('name', '') for l in s.get('logs', [])]
        target_log = (
            'stdout'
            if 'stdout' in log_names
            else (log_names[0] if log_names else None)
        )
        if target_log:
          collected_logs.append((builder_name, build_id, step_name, target_log))
      if collected_logs:
        break

  if not collected_logs:
    print('Warning: No downloadable step logs found for failing builders.')
    return

  with open(output_path, 'w', encoding='utf-8') as f:
    for builder_name, build_id, step_name, log_name in collected_logs:
      header = (
          f'=== Builder: {builder_name} (Build ID: {build_id}) | '
          f'Step: {step_name} | Log: {log_name} ===\n'
      )
      f.write(header)
      try:
        log_content = subprocess.check_output(
            [bb_bin, 'log', str(build_id), step_name, log_name],
            stderr=subprocess.STDOUT,
        ).decode('utf-8', errors='replace')
        f.write(log_content)
        f.write('\n\n')
      except subprocess.CalledProcessError as e:
        f.write(
            'Failed to fetch log via bb:'
            f' {e.output.decode("utf-8", errors="replace")}\n\n'
        )

  size_bytes = os.path.getsize(output_path)
  print(f'\nSaved detailed failure logs to: {output_path} ({size_bytes} bytes)')


def get_cq_status(cl_number, patchset=None, fetch_logs_path=None):
  change = get_change_info(cl_number)
  latest_ps_num = (
      change.get('revisions', {})
      .get(change.get('current_revision', ''), {})
      .get('_number')
  )
  if patchset is None:
    patchset = latest_ps_num

  last_two = str(cl_number)[-2:].zfill(2)
  gerrit_ref = f'refs/changes/{last_two}/{cl_number}/{patchset}'

  print(f'CL: {cl_number}')
  print(f'Patchset: {patchset}')
  print(f'Gerrit Fetch Ref: {gerrit_ref}')

  builds = search_builds(cl_number, patchset)

  if not builds:
    if change.get('status') == 'MERGED' and int(patchset) >= int(latest_ps_num):
      print('CQ Status: SUCCESS (MERGED)')
      print('No failing boards identified (CL was submitted).')
    else:
      print('CQ Status: UNKNOWN (No builds found)')
      print('No failing boards identified.')
    return

  # Buildbucket IDs use inverted timestamps: smaller int(id) == newer build
  builds.sort(key=lambda b: int(b['id']))

  # Find all orchestrator runs sorted newest first
  orchestrators = [
      b
      for b in builds
      if b['builder']['builder']
      in ('cq-orchestrator', 'staging-release-main-orchestrator')
  ]

  def get_builds_for_orch(orch_index):
    """Return latest build per builder within the time window of orchestrators[orch_index]."""
    orch_build = orchestrators[orch_index]
    max_id = int(orch_build['id'])
    min_id = int(orchestrators[orch_index - 1]['id']) if orch_index > 0 else 0
    window_builds = {}
    for b in builds:
      bid = int(b['id'])
      # Child builds are spawned after or at the same time as their parent orchestrator (bid <= max_id)
      # and before the newer orchestrator started (bid > min_id)
      if min_id < bid <= max_id:
        name = b['builder']['builder']
        if name not in window_builds:
          window_builds[name] = b
    return window_builds

  # Standalone single-board tryjobs are root builds (no ancestorIds) that are not orchestrators
  all_standalone = [
      b
      for b in builds
      if not b.get('ancestorIds')
      and 'orchestrator' not in b['builder']['builder']
  ]
  standalone_builds = []
  if all_standalone:
    if not orchestrators:
      standalone_builds = all_standalone
    else:
      latest_orch_id = int(orchestrators[0]['id'])
      # Inverted timestamps: smaller int(id) == newer build
      standalone_builds = [
          b for b in all_standalone if int(b['id']) < latest_orch_id
      ]

  if standalone_builds or not orchestrators:
    run_type = 'Single-Board Tryjob'
    target_pool = standalone_builds if standalone_builds else builds
    active_builders = {}
    for b in target_pool:
      name = b['builder']['builder']
      if name not in active_builders:
        active_builders[name] = b
    running = any(
        b['status'] in ('STARTED', 'SCHEDULED')
        for b in active_builders.values()
    )
    failed = any(
        b['status'] in ('FAILURE', 'INFRA_FAILURE', 'CANCELED')
        for b in active_builders.values()
    )
    if running:
      cq_status = 'RUNNING'
    elif failed:
      cq_status = 'FAILURE'
    else:
      cq_status = 'SUCCESS'
    failing_builders = {
        k: v
        for k, v in active_builders.items()
        if v['status'] in ('FAILURE', 'INFRA_FAILURE')
    }
  else:
    orch = orchestrators[0]
    run_type = (
        'cros-try'
        if orch['builder']['builder'] == 'staging-release-main-orchestrator'
        else 'CQ'
    )
    active_builders = get_builds_for_orch(0)

    if orch['status'] == 'SUCCESS':
      cq_status = 'SUCCESS'
    elif orch['status'] in ('FAILURE', 'INFRA_FAILURE', 'CANCELED'):
      cq_status = orch['status']
    else:
      cq_status = 'RUNNING'

    failing_builders = {
        k: v
        for k, v in active_builders.items()
        if v['status'] in ('FAILURE', 'INFRA_FAILURE')
    }

    # If the newest orchestrator is RUNNING and has no failures yet, check if a previous orchestrator failed
    if cq_status == 'RUNNING' and not failing_builders and len(orchestrators) > 1:
      for prev_idx in range(1, len(orchestrators)):
        prev_orch = orchestrators[prev_idx]
        if prev_orch['status'] in ('FAILURE', 'INFRA_FAILURE'):
          prev_builders = get_builds_for_orch(prev_idx)
          prev_failing = {
              k: v
              for k, v in prev_builders.items()
              if v['status'] in ('FAILURE', 'INFRA_FAILURE')
          }
          if prev_failing:
            print(
                f'Note: A new {run_type} run is currently RUNNING with no'
                ' failures yet. Showing failures from previous failed run.'
            )
            failing_builders = prev_failing
            break

  print(f'Run Type: {run_type}')
  print(f'CQ Status: {cq_status}')

  if run_type == 'Single-Board Tryjob':
    print('\nSingle-Board Tryjob Builders:')
    for name, b in active_builders.items():
      print(
          f"- {name}: {b['status']}"
          f" (http://cr-buildbucket.appspot.com/build/{b['id']})"
      )

  if cq_status == 'SUCCESS':
    print('No failing builders identified.')
    return

  if not failing_builders:
    if cq_status == 'RUNNING':
      print('No failing builders identified yet. Build is in progress.')
    else:
      print('No failing builders identified.')
    return

  # Pick representative failing board
  rep_board = None
  rep_builder_name = None
  for name in failing_builders:
    candidate = extract_board_name(name)
    if candidate:
      rep_board = candidate
      rep_builder_name = name
      # Prefer non-generic board if available
      if 'generic' not in candidate and 'vm' not in candidate:
        break

  if rep_board:
    print(f'Representative Failing Board: {rep_board} (from {rep_builder_name})')

  # Separate board builders from auxiliary test runners
  board_failing = {
      k: v
      for k, v in failing_builders.items()
      if 'orchestrator' not in k
      and not k.startswith('test_runner')
      and k != 'cros_test_platform'
  }
  display_builders = board_failing if board_failing else failing_builders

  print('\nFailing Builders & Failed Steps:')
  failing_details_list = []
  for name, b in display_builders.items():
    if 'orchestrator' in name:
      continue
    print(f"- {name} ({b['status']})")
    details = get_build_details(b['id'])
    failing_details_list.append((name, b, details))
    steps = details.get('steps', [])
    failed_steps = [s for s in steps if s.get('status') == 'FAILURE']

    if not failed_steps and 'summaryMarkdown' in b:
      print(f"  Summary: {b['summaryMarkdown']}")

    for s in failed_steps:
      step_name = s.get('name', '')
      reason = s.get('summaryMarkdown', '').strip()
      print(f'  Failed Step: {step_name}')
      if reason:
        print(f'    Reason: {reason}')

  if fetch_logs_path and failing_details_list:
    # Prioritize representative failing builder when fetching logs
    if rep_builder_name:
      failing_details_list.sort(
          key=lambda x: 0 if x[0] == rep_builder_name else 1
      )
    fetch_failure_logs(failing_details_list, fetch_logs_path)


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
      description='Check CQ or tryjob status, launch single-board tryjobs, extract failing boards/logs, or update Gerrit labels.'
  )
  parser.add_argument('cl_number', help='Gerrit CL number')
  parser.add_argument(
      'patchset', nargs='?', default=None, help='Optional patchset number'
  )
  parser.add_argument(
      '--tryjob',
      dest='tryjob_board',
      metavar='BOARD',
      help='Launch a fast single-board <BOARD>-cq tryjob directly via bb add',
  )
  parser.add_argument(
      '--fetch-logs',
      dest='fetch_logs',
      metavar='FILE',
      help='Download failed build/test step logs from Buildbucket into FILE using bb log',
  )
  parser.add_argument(
      '--set-cq',
      dest='set_cq',
      type=int,
      choices=[0, 1, 2],
      help='Set Commit-Queue label on Gerrit CL (e.g., 1 for CQ+1, 2 for CQ+2)',
  )
  parser.add_argument(
      '--comment',
      dest='comment',
      help='Post a review comment on the Gerrit CL',
  )

  args = parser.parse_args()

  if args.tryjob_board:
    launch_single_board_tryjob(
        args.cl_number, args.tryjob_board, patchset=args.patchset
    )
  elif args.set_cq is not None or args.comment:
    set_gerrit_review(args.cl_number, cq_vote=args.set_cq, comment=args.comment)
  else:
    get_cq_status(
        args.cl_number,
        patchset=args.patchset,
        fetch_logs_path=args.fetch_logs,
    )
