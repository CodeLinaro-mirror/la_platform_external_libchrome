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


def get_unmerged_cq_depend_urls(commit_msg):
  """Parse Cq-Depend lines and return Gerrit patchset URLs for any unmerged dependent CLs."""
  import re
  dep_urls = []
  token = None
  for line in commit_msg.splitlines():
    if not line.lower().startswith('cq-depend:'):
      continue
    rhs = line.split(':', 1)[1]
    for item in rhs.split(','):
      item = item.strip()
      m = re.match(r'^(?:(chromium|chrome-internal):)?(\d+)$', item)
      if not m:
        continue
      host_prefix = m.group(1) or 'chromium'
      dep_cl = m.group(2)
      host = (
          'chrome-internal-review.googlesource.com'
          if host_prefix == 'chrome-internal'
          else 'chromium-review.googlesource.com'
      )
      api_prefix = '/a' if host_prefix == 'chrome-internal' else ''
      url = f'https://{host}{api_prefix}/changes/{dep_cl}?o=CURRENT_REVISION'
      req = urllib.request.Request(url)
      if host_prefix == 'chrome-internal':
        if token is None:
          token = get_auth_token(
              scopes=(
                  'https://www.googleapis.com/auth/gerritcodereview'
                  ' https://www.googleapis.com/auth/userinfo.email'
              )
          )
        req.add_header('Authorization', f'Bearer {token}')
      try:
        with urllib.request.urlopen(req, timeout=5) as resp:
          raw = resp.read().decode('utf-8')
          if raw.startswith(")]}'"):
            raw = raw.split('\n', 1)[1]
          data = json.loads(raw)
          if data.get('status') == 'NEW':
            proj = data.get('project', '')
            ps = (
                data.get('revisions', {})
                .get(data.get('current_revision', ''), {})
                .get('_number', 1)
            )
            dep_urls.append(f'https://{host}/c/{proj}/+/{dep_cl}/{ps}')
      except Exception:
        continue
  return dep_urls


def launch_single_board_tryjob(cl_number, board, patchset=None):
  """Schedule a single-board <board>-cq build directly via `bb add`."""
  change = get_change_info(cl_number)
  cur_rev = change.get('revisions', {}).get(
      change.get('current_revision', ''), {}
  )
  latest_ps_num = cur_rev.get('_number')
  if patchset is None:
    patchset = latest_ps_num

  cl_url = f'https://chromium-review.googlesource.com/c/chromiumos/platform/libchrome/+/{cl_number}/{patchset}'
  builder = resolve_cq_builder(board)
  bb_bin = get_bb_binary()

  cmd = [bb_bin, 'add', '-cl', cl_url]
  commit_msg = cur_rev.get('commit', {}).get('message', '')
  for dep_url in get_unmerged_cq_depend_urls(commit_msg):
    print(f'Including unmerged Cq-Depend CL in tryjob: {dep_url}')
    cmd.extend(['-cl', dep_url])
  cmd.append(builder)

  print(f'Launching single-board CQ tryjob: {builder} for CL {cl_number} (patchset {patchset})...')
  try:
    output = subprocess.check_output(
        cmd,
        stderr=subprocess.STDOUT,
    ).decode('utf-8', errors='replace')
    print(output.strip())
  except subprocess.CalledProcessError as e:
    print(f'Error launching tryjob via bb add:\n{e.output.decode("utf-8", errors="replace")}')
    sys.exit(1)


def get_change_info(cl_number):
  url = f'https://chromium-review.googlesource.com/changes/{cl_number}?o=CURRENT_REVISION&o=CURRENT_COMMIT'
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
      scopes=(
          'https://www.googleapis.com/auth/gerritcodereview'
          ' https://www.googleapis.com/auth/userinfo.email'
      )
  )
  url = f'https://chromium-review.googlesource.com/a/changes/{cl_number}/revisions/current/review'
  payload = {}
  if cq_vote is not None:
    payload['labels'] = {'Commit-Queue': int(cq_vote)}
    if int(cq_vote) == 2:
      payload['labels']['Verified'] = 1
  if comment:
    payload['message'] = comment

  # Also propagate matching CQ vote to any unmerged Cq-Depend CLs so LUCI CV
  # does not reject the run due to missing/mismatched dependency CQ modes.
  if cq_vote in (1, 2):
    try:
      change = get_change_info(cl_number)
      cur_rev = change.get('revisions', {}).get(
          change.get('current_revision', ''), {}
      )
      commit_msg = cur_rev.get('commit', {}).get('message', '')
      for dep_url in get_unmerged_cq_depend_urls(commit_msg):
        dep_host = (
            'chrome-internal-review.googlesource.com'
            if 'chrome-internal-review' in dep_url
            else 'chromium-review.googlesource.com'
        )
        parts = dep_url.rstrip('/').split('/')
        dep_cl = parts[-2]
        dep_rev_url = f'https://{dep_host}/a/changes/{dep_cl}/revisions/current/review'
        dep_payload = {'labels': dict(payload['labels'])}
        dep_req = urllib.request.Request(
            dep_rev_url,
            data=json.dumps(dep_payload).encode('utf-8'),
            method='POST',
        )
        dep_req.add_header('Authorization', f'Bearer {token}')
        dep_req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(dep_req, timeout=5)
        print(
            f'Propagated {dep_payload["labels"]} to unmerged Cq-Depend CL'
            f' {dep_host} {dep_cl}'
        )
    except Exception as e:
      print(f'Warning: Failed to propagate CQ label to Cq-Depend CLs: {e}')

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

  if builder_name == 'libchrome-uprev':
    return 'amd64-generic'

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


def is_compile_or_unit_test_failure(details, summary_markdown=''):
  """Return True if a builder failed during compilation, package install, or unit tests."""
  compile_keywords = (
      'build_packages',
      'buildpackages',
      'installpackages',
      'install_packages',
      'verify uprev commit',
      'ebuild_tests',
      'testpackages',
      'unit tests',
      'failed compilation',
      'emerge',
  )
  test_only_prefixes = (
      'suite executions',
      'summarize|bvt-',
      'summarize|cq-',
      'bvt-tast',
      'hw test',
  )
  steps = details.get('steps', [])
  failed_steps = [s for s in steps if s.get('status') == 'FAILURE']
  for s in failed_steps:
    name_lower = s.get('name', '').lower()
    reason_lower = s.get('summaryMarkdown', '').lower()
    if any(k in name_lower or k in reason_lower for k in compile_keywords):
      return True
  summary_lower = (
      summary_markdown or details.get('summaryMarkdown', '')
  ).lower()
  if any(k in summary_lower for k in compile_keywords):
    return True
  if details.get('status') == 'INFRA_FAILURE':
    return False
  if failed_steps and all(
      any(p in s.get('name', '').lower() for p in test_only_prefixes)
      or s.get('name', '').lower() == 'summarize'
      for s in failed_steps
  ):
    return False
  return True


def push_to_gerrit(remote_ref=None):
  """Push current HEAD to Gerrit over HTTPS using luci-auth OAuth2 token."""
  token = get_auth_token(
      scopes=(
          'https://www.googleapis.com/auth/gerritcodereview'
          ' https://www.googleapis.com/auth/userinfo.email'
      )
  )
  env = os.environ.copy()
  env['GIT_CONFIG_GLOBAL'] = '/dev/null'
  env['GERRIT_TOKEN'] = token
  helper = (
      '!f() { echo username=git-luci; echo "password=${GERRIT_TOKEN}"; }; f'
  )

  # Ensure HEAD commit has a Gerrit Change-Id footer before pushing
  try:
    commit_msg = subprocess.check_output(
        ['git', 'log', '-1', '--format=%B'],
        env=env,
        stderr=subprocess.DEVNULL,
    ).decode('utf-8', errors='replace')
    if 'Change-Id:' not in commit_msg:
      git_dir = (
          subprocess.check_output(
              ['git', 'rev-parse', '--git-dir'],
              env=env,
              stderr=subprocess.DEVNULL,
          )
          .decode('utf-8')
          .strip()
      )
      hook_path = os.path.join(git_dir, 'hooks', 'commit-msg')
      os.makedirs(os.path.dirname(hook_path), exist_ok=True)
      if not os.path.exists(hook_path):
        urllib.request.urlretrieve(
            'https://chromium-review.googlesource.com/tools/hooks/commit-msg',
            hook_path,
        )
        os.chmod(hook_path, 0o755)
      subprocess.check_call(
          ['git', 'commit', '--amend', '--no-edit'],
          env=env,
      )
  except Exception:
    pass

  repo_url = 'https://chromium.googlesource.com/chromiumos/platform/libchrome'
  try:
    origin_url = (
        subprocess.check_output(
            ['git', 'remote', 'get-url', 'origin'],
            env=env,
            stderr=subprocess.DEVNULL,
        )
        .decode('utf-8')
        .strip()
    )
    if origin_url.startswith('sso://chromium/'):
      repo_url = 'https://chromium.googlesource.com/' + origin_url[
          len('sso://chromium/') :
      ]
    elif origin_url.startswith('sso://chrome-internal/'):
      repo_url = 'https://chrome-internal.googlesource.com/' + origin_url[
          len('sso://chrome-internal/') :
      ]
    elif origin_url.startswith('https://'):
      repo_url = origin_url
  except Exception:
    pass

  if not remote_ref:
    branch = 'main'
    try:
      sym = (
          subprocess.check_output(
              ['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'],
              env=env,
              stderr=subprocess.DEVNULL,
          )
          .decode('utf-8')
          .strip()
      )
      if sym.endswith('/master'):
        branch = 'master'
    except Exception:
      pass
    remote_ref = f'HEAD:refs/for/{branch}'

  cmd = [
      'git',
      '-c',
      f'credential.helper={helper}',
      'push',
      repo_url,
      remote_ref,
  ]
  print(f'Pushing {remote_ref} to {repo_url} via luci-auth...')
  try:
    output = subprocess.check_output(
        cmd, env=env, stderr=subprocess.STDOUT
    ).decode('utf-8', errors='replace')
    print(output.strip())
  except subprocess.CalledProcessError as e:
    err_text = e.output.decode('utf-8', errors='replace')
    if 'branch main not found' in err_text and 'refs/for/main' in remote_ref:
      fallback_ref = remote_ref.replace('refs/for/main', 'refs/for/master')
      cmd[-1] = fallback_ref
      print(f'Retrying with {fallback_ref}...')
      output = subprocess.check_output(
          cmd, env=env, stderr=subprocess.STDOUT
      ).decode('utf-8', errors='replace')
      print(output.strip())
      return
    print(f'Error pushing to Gerrit:\n{err_text}')
    sys.exit(1)


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
        if (
            log_name.endswith(' log') or 'libchrome' in log_name
        ) and log_name not in seen_log_names:
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


def get_cq_status(
    cl_number,
    patchset=None,
    fetch_logs_path=None,
    wait=False,
    poll_interval=120,
):
  import time

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

  while True:
    builds = search_builds(cl_number, patchset)
    if not builds:
      if (
          change.get('status') == 'MERGED'
          and int(patchset) >= int(latest_ps_num)
      ):
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
        if min_id < bid <= max_id:
          name = b['builder']['builder']
          if name not in window_builds:
            window_builds[name] = b
      return window_builds

    # Standalone single-board tryjobs are root builds (no ancestorIds) that are not orchestrators
    # Exclude `libchrome-uprev` generator build if an orchestrator or board tryjob also exists
    all_standalone = [
        b
        for b in builds
        if not b.get('ancestorIds')
        and 'orchestrator' not in b['builder']['builder']
    ]
    non_generator_standalone = [
        b
        for b in all_standalone
        if b['builder']['builder'] != 'libchrome-uprev'
    ]
    standalone_builds = []
    if non_generator_standalone:
      if not orchestrators:
        standalone_builds = non_generator_standalone
      else:
        latest_orch_id = int(orchestrators[0]['id'])
        standalone_builds = [
            b
            for b in non_generator_standalone
            if int(b['id']) < latest_orch_id
        ]
    elif not orchestrators and all_standalone:
      standalone_builds = all_standalone

    if standalone_builds or not orchestrators:
      if (
          len(standalone_builds) == 1
          and standalone_builds[0]['builder']['builder'] == 'libchrome-uprev'
      ):
        run_type = 'Generator Build (libchrome-uprev)'
      else:
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

      if (
          cq_status == 'RUNNING'
          and not failing_builders
          and len(orchestrators) > 1
      ):
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

    if wait and cq_status == 'RUNNING':
      print(
          f'[{time.strftime("%H:%M:%S")}] {run_type} status is RUNNING;'
          f' polling again in {poll_interval}s...'
      )
      time.sleep(poll_interval)
      continue
    break

  print(f'Run Type: {run_type}')
  print(f'CQ Status: {cq_status}')

  if run_type in ('Single-Board Tryjob', 'Generator Build (libchrome-uprev)'):
    print(f'\n{run_type} Builders:')
    for name, b in active_builders.items():
      print(
          f"- {name}: {b['status']}"
          f" (http://cr-buildbucket.appspot.com/build/{b['id']})"
      )

  if cq_status == 'SUCCESS':
    print('Build Compilation Status: PASSED')
    print('No failing builders identified.')
    return

  if not failing_builders:
    if cq_status == 'RUNNING':
      print('No failing builders identified yet. Build is in progress.')
    else:
      print('No failing builders identified.')
    return

  # Separate board builders from auxiliary test runners
  board_failing = {
      k: v
      for k, v in failing_builders.items()
      if 'orchestrator' not in k
      and not k.startswith('test_runner')
      and k != 'cros_test_platform'
  }
  display_builders = board_failing if board_failing else failing_builders

  failing_details_list = []
  compile_failing_builders = []
  test_only_failing_builders = []
  for name, b in display_builders.items():
    if 'orchestrator' in name:
      continue
    details = get_build_details(b['id'])
    failing_details_list.append((name, b, details))
    if is_compile_or_unit_test_failure(details, b.get('summaryMarkdown', '')):
      compile_failing_builders.append(name)
    else:
      test_only_failing_builders.append(name)

  if compile_failing_builders:
    print(
        'Build Compilation Status: FAILED'
        f' ({len(compile_failing_builders)} builder(s) failed compilation/unit'
        ' tests)'
    )
  else:
    print(
        'Build Compilation Status: PASSED (All failures are downstream HW/VM'
        ' test suites; no compilation fixes needed)'
    )

  # Pick representative failing board ONLY from compile/unit-test failing builders
  rep_board = None
  rep_builder_name = None
  for name in compile_failing_builders:
    candidate = extract_board_name(name)
    if candidate:
      rep_board = candidate
      rep_builder_name = name
      if 'generic' not in candidate and 'vm' not in candidate:
        break

  if rep_board:
    print(
        f'Representative Failing Board: {rep_board} (from {rep_builder_name})'
    )
  else:
    print('Representative Failing Board: None')

  pkg_to_builders = {}
  for name, b, details in failing_details_list:
    for s in details.get('steps', []):
      if s.get('status') == 'FAILURE':
        for log_meta in s.get('logs', []):
          log_name = log_meta.get('name', '')
          if log_name.endswith(' log') and '/' in log_name:
            pkg = log_name[: -len(' log')]
            pkg_to_builders.setdefault(pkg, []).append(name)

  if pkg_to_builders:
    print('\nFailed Packages Summary:')
    for pkg, b_names in sorted(
        pkg_to_builders.items(), key=lambda x: (-len(x[1]), x[0])
    ):
      sample = ', '.join(b_names[:3])
      more = f' +{len(b_names) - 3} more' if len(b_names) > 3 else ''
      print(f'- {pkg}: {len(b_names)} builder(s) ({sample}{more})')

  print('\nFailing Builders & Failed Steps:')
  for name, b, details in failing_details_list:
    if name in compile_failing_builders:
      failure_kind = 'COMPILE/UNIT-TEST'
    elif b.get('status') == 'INFRA_FAILURE':
      failure_kind = 'INFRA-FAILURE'
    else:
      failure_kind = 'HW/VM-TEST-ONLY'
    print(f"- {name} ({b['status']}) [{failure_kind}]")
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
    if rep_builder_name:
      failing_details_list.sort(
          key=lambda x: 0 if x[0] == rep_builder_name else 1
      )
    fetch_failure_logs(failing_details_list, fetch_logs_path)


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
      description=(
          'Check CQ or tryjob status, launch single-board tryjobs, extract'
          ' failing boards/logs, push to Gerrit, or update Gerrit labels.'
      )
  )
  parser.add_argument('cl_number', nargs='?', default=None, help='Gerrit CL number')
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
      '--wait',
      action='store_true',
      help='Poll Buildbucket until the active tryjob or CQ run finishes',
  )
  parser.add_argument(
      '--poll-interval',
      dest='poll_interval',
      type=int,
      default=120,
      help='Polling interval in seconds when --wait is enabled (default: 120)',
  )
  parser.add_argument(
      '--fetch-logs',
      dest='fetch_logs',
      metavar='FILE',
      help='Download failed build/test step logs from Buildbucket into FILE using bb log',
  )
  parser.add_argument(
      '--push',
      dest='push_ref',
      nargs='?',
      const='HEAD:refs/for/main',
      default=None,
      help='Push HEAD to Gerrit over HTTPS using luci-auth (default ref: HEAD:refs/for/main)',
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

  if args.push_ref:
    push_to_gerrit(args.push_ref)
    if not args.cl_number:
      sys.exit(0)

  if not args.cl_number:
    parser.error('cl_number is required unless --push is used alone')

  if args.tryjob_board:
    launch_single_board_tryjob(
        args.cl_number, args.tryjob_board, patchset=args.patchset
    )
    if args.wait:
      get_cq_status(
          args.cl_number,
          patchset=args.patchset,
          fetch_logs_path=args.fetch_logs,
          wait=True,
          poll_interval=args.poll_interval,
      )
  elif args.set_cq is not None or args.comment:
    set_gerrit_review(args.cl_number, cq_vote=args.set_cq, comment=args.comment)
  else:
    get_cq_status(
        args.cl_number,
        patchset=args.patchset,
        fetch_logs_path=args.fetch_logs,
        wait=args.wait,
        poll_interval=args.poll_interval,
    )

