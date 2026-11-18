---
name: libchrome-rotation
description: >-
  Manages the weekly ChromeOS libchrome uprev on-duty rotation: initializes and
  updates the standardized weekly log in Libchrome Uprev Rotation On-duty Notes
  (go/libchrome-uprev-onduty), audits daily automated uprev CLs (including
  auto-abandoned runs, stale-parent regeneration, and 2-parent merge conflict
  rebases), routes tasks across libchrome-uprev, libchrome-cleanup, and
  libchrome-bug-filer, and executes end-of-shift handoff (incoming rotator
  lookup, bug reassignment, and Handover Notes summary). Use when starting,
  running, or handing off a ChromeOS libchrome uprev rotation shift, updating
  the weekly on-duty notes doc, or resolving merge conflicts on automated uprev
  CLs. Don't use for Android/Clank browser rolls or non-ChromeOS library uprevs.
---

# ChromeOS Libchrome Uprev Rotation

Coordinates the weekly `chromiumos/platform/libchrome` rotation ([handbook](http://google3/chromeos/calcium/g3doc/libchrome/libchrome_uprev_rotation_handbook.md)): land **>= 3 uprevs/week** (`< 14d` lag at [go/libchrome-daily-uprev-metrics](http://go/libchrome-daily-uprev-metrics)) before burning down open `backward-compatibility-*.patch` bugs on [http://b/hotlists/4448649](http://b/hotlists/4448649).

## 1. Workspace & Sibling Skill Routing

- Work in `src/platform/libchrome` (chroot) or a standalone local Git clone outside CitC (`/google/src/cloud/...`), writing temp files to `{scratch_dir}`.
- Refresh `origin/main` explicitly (`git fetch` without a refspec only updates `FETCH_HEAD` and leaves `origin/main` stale):
  ```bash
  GIT_CONFIG_GLOBAL=/dev/null git fetch https://chromium.googlesource.com/chromiumos/platform/libchrome refs/heads/main:refs/remotes/origin/main
  ```
- Delegate specialized work to sibling `.agents/skills/`:
  - **Failing uprev build / CQ triage**: `.agents/skills/libchrome-uprev/SKILL.md` (`get_cq_status.py`)
  - **Hotlist `4448649` audit & LSC migrations**: `.agents/skills/libchrome-cleanup/SKILL.md` (`audit_cleanup_bugs.py`)
  - **Filing cleanup / upstream / divergence bugs**: `.agents/skills/libchrome-bug-filer/SKILL.md`

## 2. Weekly On-Duty Notes (`go/libchrome-uprev-onduty`)

- **Doc URL** (keep `resourcekey` and `--tab t.0`; use Granular Safe Mode only—never overwrite the tab, which holds 140+ Smart Chips and shared Dropdown definitions):
  `https://docs.google.com/document/d/1IfC4OtRRlWLCVs9M-bvVKYOK30IYcwxbhc6GTdWpawE/edit?resourcekey=0-N5OcgmPSDC24ugo9wXa7MA&tab=t.0`
- **Insertion point**: Locate `# Weekly Logs` via `gdocs readonly find-offset <DOC_URL> "Weekly Logs" --tab t.0 --json` and insert at `matches[0].paragraphEndIndex` via `gdocs mutate batch --direct` so the new week sits above last week's `HEADING_2`.
- **Required 4-part weekly schema**:
  1. `HEADING_2`: `Week of <Date chip: {monday_yyyy_mm_dd}T12:00:00Z> (<Person chip: {ldap}@google.com>)` (`12:00:00Z` avoids timezone date shift).
  2. `HEADING_3`: `Handover Notes` — `- TBD` during the shift (`- N/A` or concrete handover items at shift end).
  3. `HEADING_3`: `Uprevs` (**newest first**) — include **every** shift `Automated commit: libchrome r<REV> uprev` CL (merged, `CQ`/`WIP`, **and** `Auto-abandoned`), formatted as `[Automated commit: ...](https://chromium-review.googlesource.com/c/<CL>) ` + Uprev Dropdown chip, with `\t` sub-bullets for fixes or conflict notes.
  4. `HEADING_3`: `Cleanup Bugs` — open `hotlistid:4448649` bugs at shift start + newly filed bugs, formatted as `[b/<ID>: <Title>](https://b.corp.google.com/issues/<ID>) ` + Cleanup Dropdown chip, with `\t` sub-bullets for migration/removal CLs.
- **Dropdown Smart Chip IDs & `TextRun` rule**:
  - Reuse existing `tab=t.0` definitions (never `--create-title` / `--preset`):
    - **Uprevs (`kix.id8xyhuv1z3q`)**: `Committed`, `CQ`, `WIP`, `Auto-abandoned`, `Abandoned`
    - **Cleanup Bugs (`kix.3fjprwl01tlo`)**: `New`, `WIP (updated)`, `WIP (no update)`, `Fixed`
  - Because hyperlinks and trailing spaces split across `TextRun`s, `insert-dropdown --after` fails to match; resolve `endIndex - 1` via `find-offset --json` (or `dump-body`) and run `mutate insert-dropdown --index` in **descending index order**. Flip existing chips in-place with `mutate update-dropdown --set kix.<id>="<Option>" --direct`.

## 3. Daily Uprev Discovery & Merge Conflicts

- **Find all recent automated uprevs (including abandoned)**: Use `-age:7d` (`age:7d` in Gerrit means *older* than 7 days):
  ```bash
  /google/bin/releases/gemini-agents-gerrit/gerrit search --host https://chromium-review.googlesource.com \
    'project:chromiumos/platform/libchrome "Automated commit: libchrome" -age:7d' --limit 20
  ```
- **When an uprev CL has `Mergeable: false` on `main` (2-parent merge conflict)**:
  - **Untouched robot PS1 (stale parent / `BASE_VER` only)**: Clear `CQ=0` on the stale CL and run `bb add chromeos/infra/libchrome-uprev`. Do **not** manually rebase/push as a human—that strips `Bot-Commit+1` and forces manual `CR+2` + `V+1`. Log the superseded CL as `Auto-abandoned`.
  - **Manual `BUILD.gn` / patch fix also required**: Do **not** run `git rebase origin/main` (flattens the 2-parent merge and replays upstream commits). Recreate the 2-parent merge on `origin/main` (`git checkout -B uprev-{cl} origin/main && git merge --no-commit --no-ff {upstream_hash}`), update `BASE_VER` + fixes, verify `python3 libchrome_tools/apply_patches.py` (then `git reset --hard HEAD-before-patching && git tag -d HEAD-before-patching`), preserve `Change-Id:`, confirm with the user before pushing, and run `libchrome-uprev`.

## 4. End-of-Shift Handoff

When wrapping up the week (shifts rotate Saturday PDT / Sunday APAC with no handover meeting—the incoming rotator relies entirely on [go/libchrome-uprev-onduty](http://go/libchrome-uprev-onduty) and Buganizer):

1. **Look up the incoming rotator**:
   ```bash
   /google/bin/releases/gemini-agents-rotations/rotations_cli --action=get_rotation --rotation_id=4615501217529856
   ```
   Take the `schedule_range.primary` entry immediately following `current_primary`'s week (`{next_ldap}@google.com`).
2. **Finalize `Handover Notes` & Dropdown chips in `go/libchrome-uprev-onduty`**:
   - Update every Uprev (`kix.id8xyhuv1z3q`) and Cleanup Bug (`kix.3fjprwl01tlo`) Dropdown Smart Chip to its end-of-week state (`Committed` / `CQ` / `WIP` / `Auto-abandoned` and `Fixed` / `WIP (updated)` / `WIP (no update)`).
   - Replace `- TBD` under `Handover Notes` with the exact last working context so `{next_ldap}` can resume without re-investigating: any unmerged uprev CL (root cause, staged fix/tryjob, pending reviewers), any in-flight downstream migration or patch-removal CLs (who was pinged for `CR+2`, `Cq-Depend` links), or `- N/A` if all uprevs and cleanups landed cleanly.
3. **Handoff open cleanup bugs (`hotlistid:4448649`)**:
   - List open cleanup bugs via `/google/bin/releases/issues-cli/issues readonly search "hotlistid:4448649 status:open" --limit=50`.
   - Exclude bugs snoozed on `bugjuggler@google.com` or already in final patch-removal CQ verification. After getting explicit user authorization for `issues mutate`, post a concise status comment with the latest CL links/remaining blockers and reassign each active bug to `{next_ldap}@google.com` (`issues mutate comment` + `issues mutate update safe-reassign --issue_id={id} --assignee={next_ldap}`).
