#!/usr/bin/env python3
import sys
import json
import urllib.request
import urllib.error
import subprocess

def get_auth_token():
    try:
        return subprocess.check_output(['luci-auth', 'token'], stderr=subprocess.DEVNULL).decode('utf-8').strip()
    except subprocess.CalledProcessError:
        print("Error: luci-auth failed. Please run 'luci-auth login' or 'bb auth-login'")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: luci-auth command not found. Please ensure it is installed and in your PATH.")
        sys.exit(1)

def get_change_info(cl_number):
    url = f"https://chromium-review.googlesource.com/changes/{cl_number}?o=CURRENT_REVISION"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as response:
            data = response.read().decode('utf-8')
            if data.startswith(")]}'\n"):
                data = data[5:]
            return json.loads(data)
    except Exception as e:
        print(f"Error fetching Gerrit data: {e}")
        sys.exit(1)

def search_builds(cl, patchset):
    token = get_auth_token()
    url = "https://cr-buildbucket.appspot.com/prpc/buildbucket.v2.Builds/SearchBuilds"
    req_data = {
        "predicate": {
            "gerritChanges": [{"host": "chromium-review.googlesource.com", "change": int(cl), "patchset": int(patchset)}]
        },
        "pageSize": 1000,
        "mask": {
            "fields": "id,status,builder"
        }
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
            return json.loads(data).get('builds', [])
    except urllib.error.HTTPError as e:
        print(f"Error fetching Buildbucket data: {e.read().decode('utf-8')}")
        sys.exit(1)

def get_cq_status(cl_number, patchset=None):
    change = get_change_info(cl_number)
    # Determine latest patchset if not provided
    latest_ps_num = change.get("revisions", {}).get(change.get("current_revision", ""), {}).get("_number")
    if patchset is None:
        patchset = latest_ps_num

    print(f"CL: {cl_number}")
    print(f"Patchset: {patchset}")

    builds = search_builds(cl_number, patchset)

    if not builds:
        if change.get("status") == "MERGED" and int(patchset) >= int(latest_ps_num):
            print("CQ Status: SUCCESS (MERGED)")
            print("No failing boards identified (CL was submitted).")
        else:
            print("CQ Status: UNKNOWN (No builds found)")
            print("No failing boards identified.")
        return

    # Sort builds by ID ascending (smallest ID = most recent)
    builds.sort(key=lambda b: int(b['id']))

    latest_by_builder = {}
    for b in builds:
        name = b['builder']['builder']
        if name not in latest_by_builder:
            latest_by_builder[name] = b

    orch = latest_by_builder.get('cq-orchestrator')
    if orch:
        if orch['status'] == 'SUCCESS':
            cq_status = 'SUCCESS'
        elif orch['status'] in ('FAILURE', 'INFRA_FAILURE', 'CANCELED'):
            cq_status = orch['status']
        else:
            cq_status = 'RUNNING'  # STARTED, SCHEDULED, etc.
    else:
        # Check if any builders are still running, else assume UNKNOWN/FAILED based on individual bots
        running = any(b['status'] in ('STARTED', 'SCHEDULED') for b in latest_by_builder.values())
        if running:
            cq_status = 'RUNNING'
        else:
            cq_status = 'FAILED'

    print(f"CQ Status: {cq_status}")
    
    if cq_status != 'SUCCESS':
        fails = set()
        for k, v in latest_by_builder.items():
            if k != 'cq-orchestrator' and v['status'] in ('FAILURE', 'INFRA_FAILURE'):
                board_name = k.replace('-cq', '').replace('-snapshot', '').strip()
                if board_name:
                    fails.add(board_name)
                    
        if fails:
            print(f"Failing Boards: {', '.join(sorted(fails))}")
        else:
            print("No failing boards identified.")
    else:
        print("No failing boards identified.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: get_cq_status.py <CL_NUMBER> [PATCHSET]")
        sys.exit(1)
        
    cl_number = sys.argv[1]
    patchset = sys.argv[2] if len(sys.argv) > 2 else None
    
    get_cq_status(cl_number, patchset)
