---
name: libchrome-uprev
description: Fix a failing libchrome uprev CL by delegating setup, reproduction, root cause analysis, and fix proposals.
---

# Libchrome Uprev CL Fixing Skill

Use this skill when the user asks you to fix a failing libchrome uprev CL. 
This skill heavily relies on subagent delegation to keep the main context clean and perform tasks efficiently.

## Prerequisites
- The target CL number is provided by the user. An optional patchset may also be provided.
- You have access to the helper script `scripts/get_cq_status.py` located in this skill's directory to check CQ status and find failing boards.

## Execution Steps

### 1. Setup & Reproduce (Delegate to Subagent)
Do NOT perform these steps yourself. Instead, use the `invoke_subagent` tool to spawn a "Reproducer" subagent.
Configure the subagent with the `Workspace: "inherit"` option.
Provide the subagent with these exact instructions:
  1. Run the python script `.agents/skills/libchrome-uprev/scripts/get_cq_status.py <CL_NUMBER> [PATCHSET]` to get the CQ status and pick a representative failing board (e.g., `brya-cq` implies board `brya`). Default to the latest patchset if not provided. Do not pick bazel, staging, sdknext, fuzzer, incremental, or orchestrator boards for the repro step. Note the chosen board name.
  2. Change directory to `src/platform/libchrome` in your workspace.
  3. Run `cros workon --board=<BOARD> stop --all` to stop working on any packages for that board.
  4. Run `cros build-packages --board=<BOARD> libchrome` to warm up building dependencies.
  5. Run `repo download chromiumos/platform/libchrome <CL_NUMBER>` (pulling the specific patchset if the user requested it).
  6. Run `cros workon --board=<BOARD> start libchrome`.
  7. Run `cros build-packages --board=<BOARD> libchrome` again to reproduce the failure.
  8. Redirect the output/error of the failed build into a scratch file named `build_failure.log`.
  9. Run `git log --stat <MERGE_COMMIT>...HEAD` (find the base commit prior to the uprev to diff against) and save it to `git_history.log`.
  10. Tell the main agent you have completed these steps and provide the board name and error summary.

### 2. Root Cause Analysis, Fix Proposal, & Upload (Delegate to Subagent)
Once the "Reproducer" subagent finishes, spawn or message a "Fix Proposer" subagent (using `Workspace: "inherit"`).
Provide the subagent with these exact instructions:
  1. Read the failure logs saved in `build_failure.log` and the git history in `git_history.log`.
  2. Read the playbook at `/google/src/head/depot/google3/chromeos/calcium/g3doc/libchrome/libchrome_uprev_rotation_handbook.md`. (Do NOT read this playbook in the main agent context).
  3. Actively use `git log -p` and other git commands within the workspace (`src/platform/libchrome`) to view individual changes as needed to understand what broke.
  4. Determine the root cause of the failure based on the playbook, logs, and git history.
  5. Apply the necessary fix to the local codebase.
  6. Verify the fix locally by running `cros build-packages --board=<BOARD> libchrome`. If this local build fails, write the new build errors to `build_failure.log` and immediately loop back to step 3 to propose a modified fix. Do NOT invoke a new setup process or recreate the workspace.
  7. If the local build is successful, ask the human user for permission to upload. You MUST include a coherent summary of the fixes you applied compared to the base uprev CL. Do NOT upload without human approval.
  8. Upon human approval, run `repo upload` and apply a CQ+1 label.
  9. CQ verification can take anywhere from 20-30 minutes to many hours. Use the `schedule` tool (e.g., cron expression `*/15 * * * *`) to set up a recurring task to periodically run `.agents/skills/libchrome-uprev/scripts/get_cq_status.py <CL_NUMBER>` to monitor the CQ status without remaining blocked.
  10. If a check reveals the CQ verification failed, update `build_failure.log` with the new CQ failure output, cancel any active schedules/timers, and immediately loop back to step 3 in this subagent to revise the fix. Do NOT restart the entire setup process. If the CQ passes, notify the main agent and the user that the task is complete.
