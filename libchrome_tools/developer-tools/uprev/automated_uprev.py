#!/usr/bin/env python3
# Copyright 2022 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Script to generate and upload libchrome uprev commit.

Given uprev target, generate the uprev commit and upload to gerrit for review.

This should be run inside chroot (for emerge command) from
CHROMIUM_SRC/src/platform/libchrome/ directory.

For a typical automated daily uprev to cros/upstream HEAD (run locally):
  libchrome_tools/developer-tools/uprev/automated_uprev.py
This is equivalent to:
  libchrome_tools/developer-tools/uprev/automated_uprev.py --head

Provide the hash of target commit directly:
  libchrome_tools/developer-tools/uprev/automated_uprev.py --hash <hash>

For incremental uprev, use:
  libchrome_tools/developer-tools/uprev/automated_uprev.py --days <n>
to uprev up to the commit submitted n days after current latest on tracked
branch (default cros/main).
Or provide the target date manually (anything git log takes as --before arg):
  libchrome_tools/developer-tools/uprev/automated_uprev.py --datetime <datetime>
Format could be e.g. "yyyy-MM-dd" or "yyyy-MM-dd'T'HH:mm:ssZ".

For aid to manual uprev:
  libchrome_tools/developer-tools/uprev/automated_uprev.py
    --before_revision <revision target>
If creating for local experiment on top of local (or remote) branch:
  libchrome_tools/developer-tools/uprev/automated_uprev.py
    --before_revision <revision target>
    --track_branch <on-going uprev branch>
Use --track_active option to find the most recent active uprev commit on gerrit:
  libchrome_tools/developer-tools/uprev/automated_uprev.py
    --before_revision <revision target>
    --track_active
Run with --no_upload option to skip uploading the created change to Gerrit.
"""

import argparse
import datetime
import logging
import os
import re
import subprocess
import sys
import typing
from pathlib import Path

# Path to the libchrome dir.
LIBCHROME_DIR = Path(__file__).resolve().parent.parent.parent.parent
# Find chromite relative to $CHROMEOS_CHECKOUT/src/platform/libchrome/, so
# go up four dirs. For importing following the chromite libraries.
sys.path.insert(0, str(LIBCHROME_DIR.parent.parent.parent))

# pylint: disable=wrong-import-position
from chromite.lib import gerrit
from chromite.lib import gob_util

chromium_helper = gerrit.GetGerritHelper(gob="chromium", print_cmd=False)

BASE_VER_FILE = "BASE_VER"
BUILD_GN_FILE = "BUILD.gn"
PATCHES_DIRECTORY = "libchrome_tools/patches"
PATCHES_CONFIG_FILE = os.path.join(PATCHES_DIRECTORY, "patches.config")

COMMIT_REVISION_RE = re.compile(
    r"\s*Cr-Commit-Position: refs\/heads\/\w+@\{#([0-9]+)\}$"
)
PATCH_RE = re.compile(r"^.+\.patch$")
SECTION_HEADER_RE = re.compile(r"^# ={5}=* .* ={5}=*$")
CHERRY_PICK_PATCH_RE = re.compile(r"^cherry-pick-[0-9]{4}-r([0-9]+)-.+\.patch$")
BUILD_GN_SOURCE_FILE_LINE_RE = re.compile(r"\s*([\"\'])(.*)\1,")
EMERGE_LIBCHROME_LOG_FILE_RE = re.compile(r" \* Build log: (.+)")

MergeResult = typing.NamedTuple(
    "MergeResult", [("succeed", bool), ("message", typing.List[str])]
)
Commit = typing.NamedTuple("Commit", [("hash", str), ("revision", int)])
GitMergeSummary = typing.NamedTuple(
    "GitMergeSummary",
    [("files_added", typing.List[str]), ("files_removed", typing.List[str])],
)


def ChangeDirectoryToLibchrome() -> str:
    """Change directory to libchrome for running git commands. Return cwd before changing."""
    cwd = os.getcwd()
    libchrome_directory = Path(
        os.path.realpath(__file__)
    ).parent.parent.parent.parent
    os.chdir(libchrome_directory)
    return cwd


def IsInsideChroot() -> bool:
    """Checks that the script is run inside chroot. Copied from chromite/lib/cros_build_lib.py"""
    return os.path.exists("/etc/cros_chroot_version")


def GetRevisionFromHash(commit_hash: str) -> int:
    """Parses trailer of upstream commit (by hash) and returns revision number."""
    try:
        # `git log <commit>` shows history before <commit>. Use `-1` to restrict it
        # to output the most recent commit only i.e. the specified one.
        commit_log = subprocess.check_output(
            ["git", "log", commit_hash, "-1"], universal_newlines=True
        ).splitlines()
    except subprocess.CalledProcessError as e:
        raise ValueError(
            f"Commit hash {commit_hash} not found on cros/upstream.\n"
            f"Error: {e.output}"
        )

    for line in commit_log:
        m = COMMIT_REVISION_RE.match(line)
        if m:
            return int(m.group(1))

    raise Exception(
        "Cannot find revision number from commit message of " f"{commit_hash}"
    )


def GetLatestCommitHashBeforeRevision(revision: int) -> str:
    """Returns hash of commit with revision number <= the given number.

    git's --grep option provides the most efficient way of filtering commits by
    matching for pattern in commit message. (Compared to e.g. output the entire
    history each with a complete commit message and then search in python.)
    Unfortunately, it does not support printing only the matched pattern. So it
    is not possible to e.g. print the Cr-Commit-Position information (and commit
    hash) for all commits on cros/upstream and search on that concise output
    here.

    The compromised solution is to run git rev-list with grep in rounds with
    a matching pattern decreasing in accuracy, so that once some match is found,
    the first result will be the one closest to the target revision and we can
    terminate the loop.

    Starts from the pattern exactly the same as the given revison, then at each
    iteration gets rid of the rightmost digit and replaces it with the list
    numbers 0 up to the one before it, and padding [0-9] for correct number of
    digits.
    Special handling when the last digit is 0.
    Only the beginning part of this numerical sequence is matched as the full
    pattern contains the trailer header ("Cr-Commit-Position...").

    E.g. if it is looking for 98706, first searches for revision number starting
    with 98706, followed by that (starting with) 9870[0-5], 986[0-9][0-9],
    98[0-5][0-9][0-9], and so on.
    (Note we cannot just search directly with the patterning matching all
    revision numbers that starts with 9 since the first result returned could be
    99xxxx which is after the target.)
    """
    # Beginning part of pattern for revision number, kept as int for performing
    # arithmetic operations when updating at each iteration(//10 and -1).
    revision_prefix = revision
    # Ending part of pattern for revision number, consists of [0-n][0-9]*.
    pattern = ""

    # l is the number of [0-9] for padding in the pattern, goes from 0 (search
    # for exact match of target revision) to
    # (# number of digit in target revision - 1).
    for l in range(len(str(revision))):
        grep_pattern = (
            r"^\s*Cr-Commit-Position: refs\/heads\/\w\+@{#"
            + str(revision_prefix)
            + pattern
            + "}"
        )
        try:
            commit_hash = subprocess.check_output(
                [
                    "git",
                    "rev-list",
                    "cros/upstream",
                    "--grep",
                    grep_pattern,
                    "-n1",
                ],
                universal_newlines=True,
            ).strip()
        except subprocess.CalledProcessError as e:
            raise ValueError(
                "Failed to format git rev-list query for revision "
                f"matching pattern {revision_prefix}{pattern}.\n"
                f"Error: {e.output}"
            )

        if commit_hash:
            return commit_hash

        last_digit = revision_prefix % 10
        if last_digit:
            pattern = r"[0-%d][0-9]\{%d\}" % (last_digit - 1, l)
            revision_prefix //= 10
        else:
            pattern = r"[0-9]\{%d\}" % (l + 1)
            revision_prefix = revision_prefix // 10 - 1

    # No commit has revision number with the same number of digits as the target
    # revision number.
    l = len(str(revision)) - 1
    grep_pattern = r"^\s*Cr-Commit-Position: refs\/heads\/\w\+@{#[0-9]\{,l\}}"
    try:
        commit_hash = subprocess.check_output(
            [
                "git",
                "rev-list",
                "cros/upstream",
                "--grep",
                grep_pattern,
                "-n1",
            ],
            universal_newlines=True,
        ).strip()
    except subprocess.CalledProcessError as e:
        raise ValueError(
            "Failed to format git rev-list query for revision "
            f"matching pattern {revision_prefix}{pattern}.\n"
            f"Error: {e.output}"
        )

    if commit_hash:
        return commit_hash

    raise ValueError(
        f"No commit with revision number <= {revision} found on "
        "cros/upstream."
    )


def GetTargetCommitFromDateTime(end_date: str) -> Commit:
    """Returns the last commit up to end_date (in any format accepted by git)."""
    try:
        commit_hash = subprocess.check_output(
            ["git", "rev-list", "cros/upstream", "--before", end_date, "-n1"],
            universal_newlines=True,
        ).strip()
    except subprocess.CalledProcessError as e:
        raise ValueError(
            f"git rev-list getting commit submitted before {end_date} "
            f"on cros/upstream failed.\n"
            f"Error: {e.output}"
        )

    if not commit_hash:
        raise ValueError(
            f"Invalid date or no commit submitted before {end_date} "
            "found on cros/upstream.\n"
        )

    return commit_hash, GetRevisionFromHash(commit_hash)


def GetLibchromeDate(track_branch: str = "cros/main") -> datetime.datetime:
    """Returns libchrome date.

    I.e. submission date (to upstream chromium) of the commit at r<BASE_VER> at
    branch track_branch (default is cros/main).
    """
    revision = GetLibchromeRevision(track_branch)
    grep_pattern = "^\s*Cr-Commit-Position: refs\/heads\/\w\+@{#%d}" % revision
    try:
        current_date = subprocess.check_output(
            [
                "git",
                "log",
                track_branch,
                "--grep",
                grep_pattern,
                "-n1",
                '--pretty="%cs"',
            ],
            universal_newlines=True,
        ).strip()
        logging.info(
            f"Tracked branch {track_branch} at revision r{revision} was "
            f"submitted on {current_date}."
        )
    except subprocess.CalledProcessError as e:
        raise ValueError(
            "Cannot find upstream commit with version BASE_VER "
            f"{base_ver} on cros/main. \n"
            f"Error: {e.output}"
        )

    return datetime.datetime.strptime(current_date, '"%Y-%m-%d"')


def GetLatestUpstreamCommit() -> Commit:
    """Returns latest commit on cros/upstream."""
    try:
        commit_hash = subprocess.check_output(
            ["git", "rev-list", "cros/upstream", "-n1"], universal_newlines=True
        ).strip()
    except subprocess.CalledProcessError as e:
        raise ValueError(
            f"Cannot find latest commit on cros/upstream.\n"
            f"Error: {e.output}"
        )

    return commit_hash, GetRevisionFromHash(commit_hash)


def GetTargetCommit(args, track_branch: str) -> Commit:
    """Returns hash and revision number of uprev target commit on cros/upstream
    based on input argument.
    """
    if args.hash:
        logging.info(f"Target option: use hash {args.hash}")
        return args.hash, GetRevisionFromHash(args.hash)
    if args.before_revision:
        logging.info(
            f"Target option: use latest commit before revision {args.before_revision}"
        )
        commit_hash = GetLatestCommitHashBeforeRevision(args.before_revision)
        return commit_hash, GetRevisionFromHash(commit_hash)
    if args.datetime:
        logging.info(f"Target option: use latest commit before {args.datetime}")
        return GetTargetCommitFromDateTime(args.datetime)
    if args.days:
        logging.info(
            f"Target option: use latest commit {args.days} after HEAD of branch {track_branch}"
        )
        assert args.days >= 0, "Invalid args for --days; must be non-negative."
        target_date = GetLibchromeDate(track_branch) + datetime.timedelta(
            days=args.days
        )
        return GetTargetCommitFromDateTime(str(target_date))
    # default option --head
    logging.info(f"Target default: use latest commit on cros/upstream")
    return GetLatestUpstreamCommit()


def CreateNewBranchFromGerritCommit(ref: str, commit_number: str) -> str:
    """Create new branch by downloading given commit ref and return its name."""
    branch_name = f"change-{commit_number}"
    subprocess.run(
        [
            "git",
            "fetch",
            "https://chromium.googlesource.com/chromiumos/platform/libchrome",
            ref,
            "--quiet",
        ]
    )
    subprocess.run(
        ["git", "checkout", "-B", branch_name, "FETCH_HEAD", "--quiet"]
    )
    logging.info(f"Created new branch {branch_name} for tracking")
    return branch_name


def GetTrackingBranch(args) -> str:
    """Returns name of branch to track when creating the new uprev commit.
    Create new branch by downloading from gerrit if in track_active mode.
    """
    if args.track_active:
        logging.info(
            f"Tracking option: track active commit on gerrit, fetching..."
        )
        # Get a list of all open libchrome uprev CLs on gerrit.
        open_uprev_cls = gob_util.QueryChanges(
            chromium_helper.host,
            {
                "repo": "chromiumos/platform/libchrome",
                "status": "open",
                "topic": "libchrome-automated-uprev",
            },
            o_params=["CURRENT_REVISION", "DOWNLOAD_COMMANDS"],
        )
        if open_uprev_cls:
            # Create a local branch using the most recently updated uprev commit
            # (gerrit query result is sorted).
            try:
                current_revision = open_uprev_cls[0]["current_revision"]
                commit_number = open_uprev_cls[0]["_number"]
                ref = open_uprev_cls[0]["revisions"][current_revision]["ref"]
                logging.info(
                    f"Found most recent active uprev commit: crrev.com/c/{commit_number}"
                )
                return CreateNewBranchFromGerritCommit(ref, commit_number)
            except subprocess.CalledProcessError as e:
                logging.warning(
                    f"Failed to create new branch from active uprev commit crrev.com/c/{commit_number}: {e.output}, fallback to cros/main."
                )
        else:
            logging.info(
                f"No active uprev commit on gerrit, fallback to cros/main"
            )
    if args.track_branch:
        logging.info(f"Tracking option: track branch {args.track_branch}")
        branches = subprocess.run(
            ["git", "rev-parse", "--verify", args.track_branch],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not branches.retcode:
            logging.info(f"Tracking branch {args.track_branch}")
            return args.track_branch
        else:
            logging.info(
                f"Cannot find {args.track_branch}, fallback to cros/main"
            )
    return "cros/main"


def GetLibchromeRevision(track_branch: str = "cros/main") -> int:
    """Reads BASE_VER to return current revision number on cros/main (or any other
    specified) branch.
    """
    try:
        base_ver = subprocess.check_output(
            ["git", "show", f"{track_branch}:{BASE_VER_FILE}"],
            universal_newlines=True,
        ).strip()
    except subprocess.CalledProcessError as e:
        raise ValueError(
            f"Cannot get BASE_VER on given branch {track_branch}.\n"
            f"Error: {e.output}"
        )
    return int(base_ver)


def UpdateBaseVer(revision: int) -> None:
    """Overwrites BASE_VER with uprev target revision number."""
    with open(BASE_VER_FILE, "w") as f:
        f.write(f"{revision}\n")


def OutdatedPatches(revision: int, directory: str = PATCHES_DIRECTORY):
    """Return list of otudated patches in libchrome_tools/patches/."""
    obsolete_patches = []
    for patch in os.listdir(directory):
        m = CHERRY_PICK_PATCH_RE.match(patch)
        # Remove cherry-pick patch if uprev passed its revision.
        if m and revision >= int(m.group(1)):
            obsolete_patches.append(patch)
    return obsolete_patches


def UpdatePatches(revision: int) -> (typing.List[str]):
    """Removes outdated patches and updates the list in
    libchrome_tools/patches/patches.config.

    Returns list of removed patches.
    """
    obsolete_patches = OutdatedPatches(revision)

    if not obsolete_patches:  # Return early if no patch should be removed.
        return []

    for patch in obsolete_patches:
        os.remove(os.path.join(PATCHES_DIRECTORY, patch))

    with open(PATCHES_CONFIG_FILE, "r+") as f:
        sources = f.read().splitlines()

    # Check if config file contains any of the removed patches.
    deleted_lines = []
    for idx, line in enumerate(sources):
        if not line or line.startswith("#"):  # Ignore empty line and comments.
            continue
        if line.split()[0] in obsolete_patches:
            deleted_lines.append(idx)
            if sources[idx - 1] == "":  # Remove leading empty line as well.
                deleted_lines.append(idx - 1)

    if deleted_lines:
        # Delete lines from config file, if any, in reverse order to avoid
        # reindexing.
        deleted_lines.sort(reverse=True)
        for idx in deleted_lines:
            del sources[idx]

        # To avoid eating the newline at the end of the file.
        sources.append("")
        # Write new patches config file.
        with open(PATCHES_CONFIG_FILE, "w") as f:
            f.write("\n".join(sources))

    return obsolete_patches


def _ExpandGitRenamePath(rename_expr: str) -> typing.Tuple[str, str]:
    """Expands a git rename expression (e.g. 'base/{old.cc => new.cc}' or 'a.cc => b.cc')."""
    # Strip trailing similarity score such as ' (95%)'
    if " (" in rename_expr and rename_expr.endswith("%)"):
        rename_expr = rename_expr[: rename_expr.rfind(" (")].strip()
    if "{" in rename_expr and "}" in rename_expr and " => " in rename_expr:
        prefix = rename_expr[: rename_expr.index("{")]
        suffix = rename_expr[rename_expr.index("}") + 1 :]
        inner = rename_expr[rename_expr.index("{") + 1 : rename_expr.index("}")]
        old_part, new_part = inner.split(" => ", 1)
        old_path = os.path.normpath(f"{prefix}{old_part}{suffix}")
        new_path = os.path.normpath(f"{prefix}{new_part}{suffix}")
        return old_path, new_path
    if " => " in rename_expr:
        old_path, new_path = rename_expr.split(" => ", 1)
        return old_path.strip(), new_path.strip()
    return "", ""


def ParseGitMergeSummary(merge_summary: typing.List[str]) -> GitMergeSummary:
    """Returns list of non-test .cc source files added and deleted according to
    git merge command output.
    """
    # Each of the added, deleted, or renamed files will be shown in a line in form
    # 'create mode <permission> foo.cc', 'delete mode <permission> foo.cc', or
    # 'rename path/{old.cc => new.cc} (95%)'.
    added_files = []
    deleted_files = []
    for line in merge_summary:
        line = line.strip()
        if line.startswith("rename "):
            old_file, new_file = _ExpandGitRenamePath(line[len("rename ") :])
            if old_file.endswith(".cc") and "unittest" not in old_file:
                deleted_files.append(old_file)
            if new_file.endswith(".cc") and "unittest" not in new_file:
                added_files.append(new_file)
            continue
        if not line.startswith("create") and not line.startswith("delete"):
            continue

        file = line.split()[-1]
        if file.endswith(".cc") and "unittest" not in file:
            if line.startswith("create"):
                added_files.append(file)
            else:  # The line starts with "delete".
                deleted_files.append(file)
    return added_files, deleted_files


def UpdateBuildGn(deleted_files: typing.List[str]) -> typing.List[str]:
    """Removes deleted .cc files from BUILD.gn sources lists.

    Returns the list of deleted files.
    """
    with open(BUILD_GN_FILE, "r") as f:
        source = f.read().splitlines()

    delete_idx = []
    build_gn_deleted_files = []
    for idx, line in enumerate(source):
        m = BUILD_GN_SOURCE_FILE_LINE_RE.match(line)
        if m and m.group(2) in deleted_files:
            delete_idx.append(idx)
            deleted_files.remove(m.group(2))
            build_gn_deleted_files.append(m.group(2))

    if delete_idx:
        for idx in reversed(delete_idx):
            del source[idx]

        with open(BUILD_GN_FILE, "w") as f:
            source.append(
                ""
            )  # To avoid eating the newline at the end of the file.
            f.write("\n".join(source))

    return build_gn_deleted_files


def EmergeLibchrome() -> typing.Optional[bool]:
    """Run `emerge libchrome` and returns whether or not it succeeded.
    """
    try:
        process = subprocess.Popen(
            ["sudo", "cros-workon", "--host", "start", "libchrome"],
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        process_output, _ = process.communicate()
    except (OSError, subprocess.CalledProcessError) as e:
        logging.warning('! `cros-workon --host start libchrome` failed, see log below:')
        logging.warning(e.stderr)
        return None

    logging.info("`sudo emerge libchrome` running...")
    try:
        process = subprocess.Popen(
            ["sudo", "emerge", "libchrome"],
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        process_output, _ = process.communicate()
    except (OSError, subprocess.CalledProcessError) as e:
        logging.warning('! `emerge libchrome` failed, see log below:')
        logging.warning(e.stderr)
        return False
    else:
        if process.returncode == 0:
            logging.info(process_output)
        else:
            logging.warning('! `emerge libchrome` failed, see log below:')
            logging.warning(process_output)
        return process.returncode == 0


def CreateUprevCommit(
    commit_hash: str,
    revision: int,
    track_branch: str,
) -> MergeResult:
    """Runs git merge and conduct typical changes (update BASE_VER, etc).

    Returns whether the merge succeeds, and the final commit message as list of strings (each str is one line).
    """
    subprocess.run(
        [
            "git",
            "checkout",
            "-B",
            f"r{revision}-uprev",
            "--track",
            track_branch,
            "--quiet",
        ],
        check=True,
    )

    message = [
        f"Automated commit: libchrome r{revision} uprev\n",
        f"Merge with upstream commit {commit_hash}",
    ]

    try:
        merge_summary = subprocess.check_output(
            ["git", "merge", commit_hash, "-m", "\n".join(message)],
            universal_newlines=True,
        ).splitlines()
    except subprocess.CalledProcessError as e:
        # Provide target hash in an empty commit for further local debugging.
        subprocess.run(["git", "merge", "--abort"])
        message.insert(2, "GIT MERGE FAILED")
        subprocess.run(
            [
                "git",
                "commit",
                "--allow-empty",
                "--quiet",
                "-m",
                "\n".join(message),
            ],
            check=True,
        )
        logging.error("Failed to `git merge` and create uprev commit")
        return False, message

    UpdateBaseVer(revision)

    added_files, removed_files = ParseGitMergeSummary(merge_summary)
    removed_from_gn_files = UpdateBuildGn(removed_files)
    if removed_from_gn_files:
        message.append(f"Update to {BUILD_GN_FILE} sources:")
        message.extend(["  * remove " + f for f in removed_from_gn_files])
    if added_files:
        message.append("Added non-test .cc files in upstream merge:")
        message.extend(["  * " + f for f in added_files])

    removed_patches = UpdatePatches(revision)
    if removed_patches:
        message.append(f"Remove following patches:")
        message.extend(["  * " + f for f in removed_patches])

    message.append(f"\nBUG=None")
    message.append(f"TEST=sudo emerge libchrome")

    subprocess.run(
        [
            "git",
            "add",
            "BASE_VER",
            "BUILD.gn",
            "libchrome_tools/patches/",
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "commit",
            "--amend",
            "--quiet",
            "--allow-empty",
            "-m",
            "\n".join(message),
        ],
        check=True,
    )

    logging.info("Created uprev commit")
    return True, message


def PushOptions(git_merge_success, emerge_success, recipe: bool) -> str:
    """
    Returns options to be used with `git push`.

    Args:
      git_merge_success: bool
      emerge_success: bool or None (not run)
      recipe: in recipe mode
    """
    push_options = (
        "%"
        +
        # Add libchrome team to cc
        "cc=chromeos-libchrome@google.com,"
        +
        # Set topic for easy searching of commits on gerrit
        "topic=libchrome-automated-uprev,"
    )
    # Add votes according to `sudo emerge libchrome` result.
    # Note bot submit votes will be added in the recipe after verifying
    # `emerge libchrome` succeeded (or not).
    if emerge_success and not recipe:
        push_options += "l=Verified+1,"
    # Flag git merge and emerge failure by Verified-1 in both modes.
    elif not git_merge_success or emerge_success == False:
        push_options += "l=Verified-1,"

    # Submit CL to CQ automatically after approval
    if not recipe:
        push_options += "l=Auto-Submit+1,"

    return push_options


def UploadUprevCommit(push_options: str) -> None:
    subprocess.run(
        ["git", "push", "cros", "HEAD:refs/for/main" + push_options],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate and upload libchrome uprev commit."
    )

    parser_target_group = parser.add_mutually_exclusive_group()
    parser_target_group.add_argument(
        "--hash",
        type=str,
        help="Uprev to the given hash, exit with error if not found.",
    )
    parser_target_group.add_argument(
        "--before_revision",
        type=int,
        help="Uprev to the latest commit on or before the given revision number.",
    )
    parser_target_group.add_argument(
        "--datetime",
        type=str,
        help="Uprev to the latest commit on or before the given date time.",
    )
    parser_target_group.add_argument(
        "--days",
        type=int,
        help="Uprev to the latest commit submitted n days after current latest on"
        " cros/main.",
    )
    parser_target_group.add_argument(
        "--head",
        action="store_true",
        help="Uprev to (latest commit) HEAD on cros/upstream.",
    )

    parser_track_group = parser.add_mutually_exclusive_group()
    parser_track_group.add_argument(
        "--track_branch",
        type=str,
        help="(Local or remote) branch to be tracked by the uprev commit.",
        default="",
    )
    parser_track_group.add_argument(
        "--track_active",
        action="store_true",
        help="Track most recent active uprev commit on gerrit.",
        default=False,
    )

    parser.add_argument(
        "--query_commit",
        action="store_true",
        help="Only output hash and revision number and do not perform merge.",
        default=False,
    )

    parser.add_argument(
        "--no_upload",
        action="store_true",
        help="Do not upload uprev commit to gerrit.",
        default=False,
    )

    parser.add_argument(
        "--recipe",
        action="store_true",
        help="The command is running as a recipe, i.e. not running manually."
        "Output git push options instead of running git push directly.",
        default=False,
    )

    args = parser.parse_args()

    logging.getLogger().setLevel("INFO")

    initial_directory = ChangeDirectoryToLibchrome()

    # Ensure upstream branch is up-to-date.
    logging.info("Git fetch cros to ensure cros/upstream is up-to-date")
    subprocess.run(
        [
            "git",
            "fetch",
            "cros"
        ],
        check=True,
    )

    track_branch = GetTrackingBranch(args)
    logging.info(f"Uprev commit will track {track_branch}")

    target_commit_hash, target_commit_revision = GetTargetCommit(
        args, track_branch
    )
    logging.info(
        f"Uprev to revision {target_commit_revision} with hash "
        f"{target_commit_hash}"
    )
    if args.query_commit:
        exit()

    if target_commit_revision <= GetLibchromeRevision(track_branch):
        raise Exception(
            f"Target revision {target_commit_revision} has been reached already: "
            f"libchrome is currently at {GetLibchromeRevision(args.track_branch)}."
        )

    if subprocess.run(["git", "diff", "--quiet"]).returncode:  # if git dirty
        raise Exception(
            "Git working directory is dirty. Abort creating uprev commit."
        )

    merge_success, commit_message = CreateUprevCommit(
        target_commit_hash, target_commit_revision, track_branch
    )

    emerge_success = None
    if args.recipe:
        logging.info(f"In --recipe mode; emerge libchrome is not run.")
    elif merge_success and IsInsideChroot():
        emerge_success = EmergeLibchrome()
        if emerge_success == False:
            logging.warning(f"emerge libchrome failed.")
            commit_message.insert(2, "EMERGE LIBCHROME IS FAILING\n")
        elif emerge_success == None:
            commit_message.insert(2, "DID NOT EMERGE LIBCHROME\n")
    else:
        reason = (
            "git merge failed" if not merge_success else "Not inside chroot"
        )
        logging.warning(f"{reason}, emerge libchrome is not run.")
        commit_message.insert(2, "DID NOT EMERGE LIBCHROME\n")
    subprocess.run(
        [
            "git",
            "commit",
            "--amend",
            "--quiet",
            "--allow-empty",
            "-m",
            "\n".join(commit_message),
        ],
        check=True,
    )

    push_options = PushOptions(merge_success, emerge_success, args.recipe)
    if args.recipe:
        print(push_options)
        return

    if not args.no_upload:
        UploadUprevCommit(push_options)

    os.chdir(initial_directory)


if __name__ == "__main__":
    sys.exit(main())
