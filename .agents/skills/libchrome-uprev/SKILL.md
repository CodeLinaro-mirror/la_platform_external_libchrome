---
name: libchrome-uprev
description: Fix a failing libchrome uprev CL.
---

# Libchrome Uprev CL Fixing Skill

Use this skill when the user asks you to fix a failing libchrome uprev CL.
This skill relies on subagent delegation to keep the main context clean and perform tasks efficiently.

## Prerequisites & Modes

- **Target CL**: The target Gerrit CL number is provided by the user (an optional patchset number may also be provided).
- **Unified Helper Script**: Use `.agents/skills/libchrome-uprev/scripts/get_cq_status.py` (located inside the `libchrome` repository) for checking CQ/tryjob status, launching fast single-board `<board>-cq` tryjobs via `bb add` (`--tryjob <BOARD>`), selecting a representative failing board, downloading remote failure logs via `bb log` (`--fetch-logs`), and setting Gerrit `Commit-Queue` labels or comments (`--set-cq` / `--comment`).
- **Automatic Environment Detection**:
  - **Mode A: Local Chroot Mode (Fast Workflow)**: Selected when `/etc/cros_chroot_version` exists or an ancestor directory contains `.repo`, `chromite`, and `chroot`. Uses local `cros build-packages` for fast reproduction and verification.
  - **Mode B: Standalone Tryjob Mode (Chrootless Workflow)**: Selected when starting in an empty workspace or standalone `libchrome` git checkout without a ChromeOS chroot. Uses `git clone` / `git fetch`, remote failure logs from `get_cq_status.py --fetch-logs`, and fast single-board CQ tryjobs (`chromeos/<BOARD>/<BOARD>-cq` via `get_cq_status.py <CL> --tryjob <BOARD>`) for verification.

## Execution Steps

### 1. Setup & Reproduce (Delegate to Subagent)
Do NOT perform these steps yourself. Instead, use the `invoke_subagent` tool to spawn a "Reproducer" subagent.
Configure the subagent with `Workspace: "inherit"`.
Provide the subagent with these exact instructions:

1. **Detect Environment & Setup Workspace**:
   - Check whether `/etc/cros_chroot_version` exists or an ancestor directory contains `.repo`, `chromite`, and `chroot`.
   - **If YES (`Local Chroot Mode`)**:
     - Change directory to `src/platform/libchrome` in your workspace.
   - **If NO (`Standalone Tryjob Mode`)**:
     - Check if the current working directory (or `./libchrome`) is already a git repository tracking `chromiumos/platform/libchrome`.
     - If starting from an empty directory, clone the standalone `libchrome` repository and enter it:
       ```bash
       git clone https://chromium.googlesource.com/chromiumos/platform/libchrome .
       ```
2. **Check Status & Download Remote Failure Logs**:
   - Run `get_cq_status.py` with `--fetch-logs` to inspect Buildbucket status, identify a representative failing board, and download remote failure logs:
     ```bash
     python3 .agents/skills/libchrome-uprev/scripts/get_cq_status.py <CL_NUMBER> [PATCHSET] --fetch-logs build_failure.log
     ```
   - Record the printed `Representative Failing Board: <BOARD>` (which automatically excludes bazel, staging-cq, sdknext, fuzzer, incremental, and orchestrator builders) and `Gerrit Fetch Ref: <GERRIT_REF>`.
   - *Edge Case (Standalone Mode only)*: If `CQ Status: UNKNOWN (No builds found)` is reported because no builds have run on the CL yet, launch an initial single-board tryjob on `brya` using `python3 .agents/skills/libchrome-uprev/scripts/get_cq_status.py <CL_NUMBER> --tryjob brya` and wait for it to produce logs.
3. **Checkout CL & Reproduce Failure**:
   - **If `Local Chroot Mode`**:
     1. Run `cros workon --board=<BOARD> stop --all` to stop working on any packages for that board.
     2. Run `cros build-packages --board=<BOARD> libchrome` to warm up building dependencies.
     3. Run `repo download chromiumos/platform/libchrome <CL_NUMBER>` (pulling the specific patchset if requested).
     4. Run `cros workon --board=<BOARD> start libchrome`.
     5. Run `cros build-packages --board=<BOARD> libchrome` again to reproduce the failure locally and redirect the output/error into `build_failure.log`. (Note: If `libchrome` builds cleanly locally because the failure was in a downstream client package unit test such as `update_engine`, keep the remote `build_failure.log` downloaded by `--fetch-logs` in step 2).
   - **If `Standalone Tryjob Mode`**:
     1. Fetch and check out the target CL directly via Git using `<GERRIT_REF>` from `get_cq_status.py` (prefixing with `GIT_CONFIG_GLOBAL=/dev/null` so `sso://chromium/` rewrites in `~/.gitconfig` do not fail when CorpSSO cookies expire):
        ```bash
        GIT_CONFIG_GLOBAL=/dev/null git fetch https://chromium.googlesource.com/chromiumos/platform/libchrome <GERRIT_REF>
        git checkout -B uprev-fix FETCH_HEAD
        ```
     2. Check `Build Compilation Status` printed by `get_cq_status.py`:
        - If `Build Compilation Status: PASSED (All failures are downstream HW/VM test suites; no compilation fixes needed)` and `Representative Failing Board: None`, **skip local/tryjob compilation** and proceed directly to Step 2.6 (Full CQ Monitoring & Failure Triage) to check if the failing HW/VM Tast tests have open Buganizer bugs and re-trigger CQ!
        - Otherwise, use the remote failure log already downloaded into `build_failure.log` by `get_cq_status.py --fetch-logs` (including `Generator Build (libchrome-uprev)` failures when the automated uprev builder failed before CQ).
4. **Generate Git History**:
   - Find the base commit prior to the uprev merge commit (`<MERGE_COMMIT>`) and save the commit history diff:
     ```bash
     git log --stat <MERGE_COMMIT>...HEAD > git_history.log
     ```
5. **Report to Main Agent**:
   - Tell the main agent you have completed setup, stating the detected mode (`Local Chroot Mode` or `Standalone Tryjob Mode`), `Build Compilation Status`, the chosen `<BOARD>`, and a brief summary of the failure from `build_failure.log`.

---

### 2. Root Cause Analysis, Fix Proposal, Verification, & Upload (Delegate to Subagent)
Once the "Reproducer" subagent finishes, spawn or message a "Fix Proposer" subagent (using `Workspace: "inherit"`).
Provide the subagent with these exact instructions:

1. **Analyze Failure Logs & History**:
   - Read the failure logs saved in `build_failure.log` and the git history in `git_history.log`.
2. **Consult Rotation Handbook**:
   - Read the playbook at `/google/src/head/depot/google3/chromeos/calcium/g3doc/libchrome/libchrome_uprev_rotation_handbook.md` if accessible on the machine. (Do NOT read this playbook in the main agent context).
3. **Inspect Commits & Determine Root Cause**:
   - Actively use `git log -p` and other git commands within the `libchrome` repository to inspect individual upstream changes and determine what broke based on the handbook, logs, and git history.
4. **Apply Fix**:
   - Apply the necessary fix (e.g. backward compatibility patch, header fix, or build flag adjustment) to the local `libchrome` codebase.
5. **Verify Fix & Upload (Branch by Mode)**:

   - **If `Local Chroot Mode`**:
     1. Verify the fix locally by running `cros build-packages --board=<BOARD> libchrome`. If this local build fails, write the new build errors to `build_failure.log` and immediately loop back to step 3 to propose a modified fix. Do NOT invoke a new setup process or recreate the workspace.
     2. Once the local build succeeds, **ask the human user for permission to upload**. You MUST include a coherent summary of the fixes you applied compared to the base uprev CL. Do NOT upload without human approval.
     3. Upon human approval, amend your commit (`git commit -a --amend`) and **update the commit message body** so that any changes made on top of the automated uprev are clearly described in the commit body (do NOT use `--no-edit` without describing the fixes). Then push to Gerrit and apply a `CQ+1` label using `get_cq_status.py --push --set-cq 1`:
        ```bash
        python3 .agents/skills/libchrome-uprev/scripts/get_cq_status.py <CL_NUMBER> --push --set-cq 1
        ```
     4. Proceed to step 6 (Full CQ Monitoring).

   - **If `Standalone Tryjob Mode`**:
     1. Because remote tryjobs build patches directly from Gerrit, testing a fix requires uploading a new patchset first. **Ask the human user for permission** to upload the candidate patchset to Gerrit, launch a single-board `<BOARD>-cq` tryjob, and automatically trigger `CQ+1` if the tryjob passes. You MUST include a coherent summary of the proposed fixes. Do NOT upload without human approval.
     2. Upon human approval, amend the commit (`git commit -a --amend`) and **update the commit message body** so that any changes made on top of the automated uprev are clearly described in the commit body (do NOT use `--no-edit` without describing the fixes), then push the new patchset and launch the single-board tryjob using `get_cq_status.py`:
        ```bash
        git commit -a --amend -m "<updated commit message with description of uprev fixes in body>"
        python3 .agents/skills/libchrome-uprev/scripts/get_cq_status.py <CL_NUMBER> --push --tryjob <BOARD>
        ```
     3. Wait for the single-board tryjob to finish (either via `--wait --fetch-logs build_failure.log` in a background task or via the `schedule` tool with cron expression `*/10 * * * *`):
        ```bash
        python3 .agents/skills/libchrome-uprev/scripts/get_cq_status.py <CL_NUMBER> --wait --fetch-logs build_failure.log
        ```
     4. When the tryjob status check completes (`Run Type: Single-Board Tryjob`):
        - If `CQ Status: FAILURE` or `INFRA_FAILURE`: Cancel active schedules/timers, inspect the newly downloaded `build_failure.log`, loop back to step 3 to revise the fix, request human approval to upload the updated patchset, and re-run `--tryjob <BOARD>`.
        - If `CQ Status: SUCCESS`: Cancel the tryjob timer, verify that the commit message body describes all changes made on top of the automated uprev (amending and re-pushing if needed), and trigger full `CQ+1` on Gerrit:
          ```bash
          python3 .agents/skills/libchrome-uprev/scripts/get_cq_status.py <CL_NUMBER> --set-cq 1 --comment "Verified fix on <BOARD>-cq tryjob"
          ```
          and proceed to step 6 (Full CQ Monitoring).

6. **Full CQ Monitoring & Failure Triage (Both Modes)**:
   - Full CQ verification can take anywhere from 30 minutes to several hours. Use the `schedule` tool (cron expression `*/15 * * * *`) to set up a recurring task to periodically run:
     ```bash
     python3 .agents/skills/libchrome-uprev/scripts/get_cq_status.py <CL_NUMBER> --fetch-logs build_failure.log
     ```
   - When a CQ status check completes:
     - Inspect the output from `get_cq_status.py`.
     - **Agent Failure Analysis**:
       - For any test step failures (e.g. `Results|tast.some.TestName`), use Buganizer CLI (`/google/bin/releases/issues-cli/issues readonly search "<TEST_NAME>"`) to check for open bugs.
       - Evaluate whether failures are:
         a) **Flake / Infra Failure**: Unrelated test step failures with open Buganizer bugs, hardware skip conditions, or GCE VM resource stockout errors.
         b) **Libchrome Regression or Build Failure**:
            - C++ compilation or GN build errors on any board builder. Note that an initial fix may expose build failures further down the line or on specific board configurations; multiple iterative rounds of fixes may be required.
            - Test failures directly caused by API/behavioral changes in the libchrome uprev.
            - Test failures due to seccomp policy violations (`seccomp kill`) caused by underlying syscall changes in the libchrome implementation.
     - **Action**:
       - If **Flake / Infra Failure**: Re-trigger `CQ+1` and post a comment on the Gerrit CL detailing the evidence (linked Buganizer bug IDs or stockout logs):
         ```bash
         python3 .agents/skills/libchrome-uprev/scripts/get_cq_status.py <CL_NUMBER> --set-cq 1 --comment "<evidence>"
         ```
         Notify the user in chat that `CQ+1` is being retried due to suspected flake.
       - If **Libchrome Regression or Build Failure**: Cancel active schedules/timers. `build_failure.log` has already been updated by `--fetch-logs`. Loop back to step 3 in this subagent to analyze the new failure, reproduce/verify on `<FAILING_BOARD>` (via local build in `Local Chroot Mode` or via `--tryjob <FAILING_BOARD>` in `Standalone Tryjob Mode`), request human approval to upload, and re-trigger CQ.
       - If **CQ Status: SUCCESS**: Cancel active schedules/timers and notify the main agent and user that CQ verification passed.
