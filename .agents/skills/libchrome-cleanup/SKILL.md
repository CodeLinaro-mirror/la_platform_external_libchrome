---
name: libchrome-cleanup
description: Triage, manage, and resolve ChromeOS libchrome backward-compatibility patch cleanup bugs (hotlistid:4448649).
---

# Libchrome Cleanup & Hotlist Triage Skill (`hotlistid:4448649`)

This skill automates triaging, juggling, and resolving open `libchrome-uprev-cleanup` issues (`hotlistid:4448649 status:open`) during the weekly `libchrome` uprev rotation.

---

## 1. Automated Hotlist Audit (`audit_cleanup_bugs.py`)

Run the bundled audit script to cross-reference every open bug in `hotlistid:4448649` against the actual files in `libchrome_tools/patches/` and open/merged Gerrit CLs:

```bash
python3 .agents/skills/libchrome-cleanup/scripts/audit_cleanup_bugs.py
```

The script categorizes every open cleanup bug into one of 5 actionable buckets:
1. **`ALREADY_REMOVED` (Close as `FIXED`)**: The referenced `backward-compatibility-*.patch` no longer exists in `libchrome_tools/patches/` on `main`.
   - Find the merged CL (`git log -S "<patch-name>" --oneline -n 1`) and close the bug:
     ```bash
     /google/bin/releases/issues-cli/issues mutate comment --issue_id=<BUG_ID> --comment="Closing as Fixed: <PATCH> was removed in crrev.com/c/<CL>."
     /google/bin/releases/issues-cli/issues mutate update status <BUG_ID> FIXED
     ```
2. **`LONG_TERM_PATCH` (Remove from Hotlist `4448649`)**: The bug tracks a `long-term-*.patch` rather than a temporary `backward-compatibility-*.patch`.
   - Remove `long-term` patches from `hotlistid:4448649` so they are not auto-assigned to each weekly rotation engineer:
     ```bash
     /google/bin/releases/issues-cli/issues mutate update remove-hotlist --issue_id=<BUG_ID> --hotlist_id=4448649
     ```
3. **`BLOCKED_NEEDS_BUGJUGGLER`**: The bug is blocked on an external toolchain/library migration or pending partner CLs, and is not currently assigned to `bugjuggler@google.com`.
   - Post a `Bugjuggler:` directive comment:
     ```bash
     /google/bin/releases/issues-cli/issues mutate comment --issue_id=<BUG_ID> --comment=$'Blocked on b/<BLOCKER_ID>.\n\nBugjuggler: b/<BLOCKER_ID> -> chromeos-libchrome@google.com'
     ```
   - Remind the user to set the Assignee in the Buganizer UI to `bugjuggler@google.com` so Bugjuggler holds ownership until the blocker resolves.
4. **`SNOOZED_ON_BUGJUGGLER`**: Already assigned to `bugjuggler@google.com` waiting on external blockers. No weekly action required.
5. **`ACTIONABLE` (Unblocked or Active LSC)**: The `backward-compatibility-*.patch` still exists in `libchrome_tools/patches/` and is not blocked on external toolchain dependencies. Proceed to Step 2.

---

## 2. Removing a Backward-Compatibility Patch & Discovering Dependent Packages

For any `ACTIONABLE` bug:

1. **Check Existing Patch-Removal CL**:
   - Check the Gerrit CL output from `audit_cleanup_bugs.py` (or search `https://chromium-review.googlesource.com/changes/?q=project:chromiumos/platform/libchrome+<PATCH_NUMBER>`).
   - If an open patch-removal CL exists and all its dependent `platform2` / Floss CLs have `MERGED`, rebase the patch-removal CL onto `origin/main`, push with `--push`, and trigger `Commit-Queue+1`:
     ```bash
     GIT_CONFIG_GLOBAL=/dev/null git fetch https://chromium.googlesource.com/chromiumos/platform/libchrome refs/heads/main
     git checkout -B remove-patch-<NUM> FETCH_HEAD
     git rm libchrome_tools/patches/backward-compatibility-<NUM>-*.patch
     git commit -m $'libchrome: Remove backward-compatibility-<NUM> patch\n\nBUG=b:<BUG_ID>\nTEST=CQ\nChange-Id: <EXISTING_CHANGE_ID>'
     python3 .agents/skills/libchrome-uprev/scripts/get_cq_status.py <CL_NUMBER> --push --set-cq 1
     ```
2. **Discover Remaining Failing Packages via Tryjob/CQ**:
   - If no patch-removal CL exists yet, create one (`git rm libchrome_tools/patches/backward-compatibility-<NUM>-*.patch`), upload it via `get_cq_status.py --push`, and launch a fast tryjob (`--tryjob amd64-generic --wait --fetch-logs cleanup_failure.log`) or `CQ+1` dry run (`--set-cq 1`) to identify all ChromeOS packages that still rely on the deprecated API/header.

---

## 3. Executing Multi-Repo ChromeOS LSC Migrations

When removing a `backward-compatibility-*.patch` breaks downstream ChromeOS packages:

1. **Header Moves / Renames**:
   - Use `libchrome_tools/developer-tools/change_header.py` to automatically rewrite `#include` directives and preserve header ordering across target repositories.
2. **Splitting CLs by `OWNERS` Boundaries**:
   - For `chromiumos/platform2`, group changed files by top-level package subdirectory (`<subdir>/OWNERS`) and create one CL per subdirectory (or up to 2-3 related directories) with `BUG=b:<BUG_ID>` and `TEST=CQ` so domain owners can review and `CQ+2` quickly.
3. **Floss (`chromiumos/platform/floss`) Special Handling**:
   - Floss mirrors upstream Android `packages/modules/Bluetooth`. Upstream your fix to Android `main` (`aosp`) or backport the upstream commit to `chromiumos/platform/floss` (`UPSTREAM:` / `BACKPORT:`) before landing the `libchrome` patch removal CL.
4. **Co-Testing Dependent CLs via `Cq-Depend` & Tracking with Bugjuggler**:
   - Add `Cq-Depend: chromium:<CL1>, chrome-internal:<CL2>` to the `libchrome` patch-removal CL commit message and run `get_cq_status.py <CL_NUMBER> --set-cq 1` to verify the patch removal together with all unmerged downstream fixes on CQ.
   - When running a fast single-board tryjob (`get_cq_status.py <CL_NUMBER> --tryjob <BOARD>`), `get_cq_status.py` automatically parses `Cq-Depend:` lines from the commit message and passes `-cl <dep_cl_url>` to `bb add` for all unmerged `chromium:` and `chrome-internal:` CLs.
   - **Preserve `Cq-Depend:` Footers After Dependencies Merge**: Keep `Cq-Depend:` lines in the commit message even after the dependent CLs are `MERGED` to preserve cross-repo auditability and prevent `cq-orchestrator` `manifest-internal` snapshot lag.
   - For internal repositories (`https://chrome-internal.googlesource.com/chromeos/...`), clone and push over HTTPS in `Standalone Tryjob Mode` using `luci-auth token -scopes "https://www.googleapis.com/auth/gerritcodereview https://www.googleapis.com/auth/userinfo.email"` with `git -c 'credential.helper=!f() { echo username=git-luci; echo "password=${GERRIT_TOKEN}"; }; f'`.
   - Link the pending CLs on the cleanup bug (`Bugjuggler: cl/<CL1>, cl/<CL2>, wait 1w -> <ldap>@google.com`) so Bugjuggler wakes the bug up automatically once all dependent CLs merge.
