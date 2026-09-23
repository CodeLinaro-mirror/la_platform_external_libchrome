#!/usr/bin/env python
# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import subprocess
import tempfile
import unittest
from pathlib import Path
from shutil import copy

from automated_uprev import *


class TestGetRevisionFromHash(unittest.TestCase):
    def test_simple_commit(self):
        self.assertEqual(
            GetRevisionFromHash("6871907594466edadc668dfeb951b456954c1336"),
            1044017,
        )

    def test_revert_commit(self):
        self.assertEqual(
            GetRevisionFromHash("92f9f98919b98120af01cc367443a9e035d4fe17"),
            1043792,
        )

    def test_reland_commit(self):
        self.assertEqual(
            GetRevisionFromHash("1fa681a83e9f86cff2f46931886b255f4fed58df"),
            1035760,
        )

    def test_invalid_commit_hash(self):
        with self.assertRaises(Exception) as context:
            GetRevisionFromHash("foobar")
        self.assertTrue(
            "Commit hash foobar not found on cros/upstream."
            in str(context.exception)
        )

    def test_bot_commit(self):
        with self.assertRaises(Exception) as context:
            GetRevisionFromHash("6a63e55d715595d77b9565e07d921c71835b0854")
        self.assertTrue(
            "Cannot find revision number from commit message"
            in str(context.exception)
        )


class TestGetLatestCommitHashBeforeRevision(unittest.TestCase):
    def test_exact_equal(self):
        self.assertEqual(
            GetLatestCommitHashBeforeRevision(998985),
            "7de51b4212c6c5801f8ef6d1f77d91d5ab55516c", # r998985
        )

    def test_target_no_zero(self):
        self.assertEqual(
            GetLatestCommitHashBeforeRevision(998965),
            "9e12f276bc064d1d8b951ca25a23cd6e0f41480d", # r998960
        )

    def test_target_some_zeros(self):
        self.assertEqual(
            GetLatestCommitHashBeforeRevision(1005160),
            "19b05f75d1839fba3a511e44c2b89c5043577018", # r1005098
        )

    def test_result_less_digits_than_target(self):
        self.assertEqual(
            GetLatestCommitHashBeforeRevision(1000000),
            "b2330d97c31cb6006ecc133625e9a40c8d56cfc8", # r999946
        )


class TestGetTargetCommitFromDateTime(unittest.TestCase):
    def test_valid_datetime(self):
        self.assertEqual(
            GetTargetCommitFromDateTime("2022-05-10T00:00:00+0000"),
            ("760c45a4f789e395a430455e9c476803f1199641", 1001216),
        )

    def test_no_commit(self):
        with self.assertRaises(Exception) as context:
            GetTargetCommitFromDateTime("2001-01-01"),
        self.assertTrue(
            "Invalid date or no commit submitted before 2001-01-01"
            in str(context.exception)
        )


class TestGetLibchromeDate(unittest.TestCase):
    def test_valid_libchrome_commit(self):
        self.assertEqual(
            GetLibchromeDate("921d6b1ae10abb974230a6399c2af4bf7a2d2f9a"),
            datetime.datetime.strptime("2022-05-28", "%Y-%m-%d"),
        )

    def test_invalid_chromium_commit(self):
        with self.assertRaises(Exception) as context:
            GetLibchromeDate("eadc2d77660dbbee054646def03415aed4db9fbf"),
        self.assertTrue(
            "Cannot get BASE_VER on given branch" in str(context.exception)
        )


class TestGetLibchromeRevision(unittest.TestCase):
    def test_valid_libchrome_commit(self):
        self.assertEqual(
            GetLibchromeRevision("921d6b1ae10abb974230a6399c2af4bf7a2d2f9a"),
            1008611,
        )

    def test_invalid_chromium_commit(self):
        with self.assertRaises(Exception) as context:
            GetLibchromeDate("eadc2d77660dbbee054646def03415aed4db9fbf"),
        self.assertTrue(
            "Cannot get BASE_VER on given branch" in str(context.exception)
        )


class TestOutdatedPatches(unittest.TestCase):
    def setUp(self):
        self.repo_dir = tempfile.TemporaryDirectory()
        self.orig_dir = os.getcwd()
        os.chdir(self.repo_dir.name)
        Path(os.path.join(self.repo_dir.name, "cherry-pick-0000-r201-bar.patch")).touch()
        Path(os.path.join(self.repo_dir.name, "cherry-pick-0100-r101-foo.patch")).touch()
        Path(os.path.join(self.repo_dir.name, "cherry-pick-0200-r876-baz.patch")).touch()

    def tearDown(self):
        os.chdir(self.orig_dir)
        self.repo_dir.cleanup()

    def test_no_update(self):
        self.assertEqual(OutdatedPatches(100, self.repo_dir.name), [])

    def test_remove_after_another_patch(self):
        self.assertEqual(
            OutdatedPatches(105, self.repo_dir.name),
            ["cherry-pick-0100-r101-foo.patch"]
        )

    def test_remove_after_section_header(self):
        self.assertEqual(
            set(OutdatedPatches(250, self.repo_dir.name)),
            set(["cherry-pick-0000-r201-bar.patch",
                 "cherry-pick-0100-r101-foo.patch",])
        )

    def test_remove_after_empty_line(self):
        self.assertEqual(
            set(OutdatedPatches(900, self.repo_dir.name)),
            set(["cherry-pick-0000-r201-bar.patch",
                 "cherry-pick-0100-r101-foo.patch",
                 "cherry-pick-0200-r876-baz.patch",],)
        )


class TestParseGitMergeSummary(unittest.TestCase):
    def setUp(self):
        self.repo_dir = tempfile.TemporaryDirectory()
        self.orig_dir = os.getcwd()
        os.chdir(self.repo_dir.name)
        subprocess.check_call(["git", "init"])
        with open(os.path.join(self.repo_dir.name, "init_file.cc"), "w+") as f:
            f.write("// foo")
        subprocess.check_call(["git", "add", "init_file.cc"])
        subprocess.check_call(["git", "commit", "-m", "initial commit"])
        subprocess.check_call(["git", "checkout", "-b", "new-branch"])

    def tearDown(self):
        os.chdir(self.orig_dir)
        self.repo_dir.cleanup()

    def test_modified_only(self):
        os.chdir(self.repo_dir.name)
        with open(os.path.join(self.repo_dir.name, "init_file.cc"), "w+") as f:
            f.write("// bar")
        subprocess.check_call(
            ["git", "commit", "-a", "-m", "modified init_file.cc"]
        )
        subprocess.check_call(["git", "checkout", "main"])
        merge_summary = subprocess.check_output(
            ["git", "merge", "new-branch", "-m", "merging"],
            universal_newlines=True,
        ).splitlines()
        added_files, removed_files = ParseGitMergeSummary(merge_summary)
        self.assertEqual(added_files, [])
        self.assertEqual(removed_files, [])

    def test_added_files(self):
        os.chdir(self.repo_dir.name)
        with open(os.path.join(self.repo_dir.name, "new_file.cc"), "w+") as f:
            f.write("// this is a new file")
        subprocess.check_call(["git", "add", "new_file.cc"])
        subprocess.check_call(["git", "commit", "-m", "added new_file.cc"])
        subprocess.check_call(["git", "checkout", "main"])
        merge_summary = subprocess.check_output(
            ["git", "merge", "new-branch", "-m", "merging"],
            universal_newlines=True,
        ).splitlines()
        added_files, removed_files = ParseGitMergeSummary(merge_summary)
        self.assertEqual(added_files, ["new_file.cc"])
        self.assertEqual(removed_files, [])

    def test_deleted_files(self):
        os.chdir(self.repo_dir.name)
        os.remove(os.path.join(self.repo_dir.name, "init_file.cc"))
        subprocess.check_call(
            ["git", "commit", "-a", "-m", "removed init_file.cc"]
        )
        subprocess.check_call(["git", "checkout", "main"])
        merge_summary = subprocess.check_output(
            ["git", "merge", "new-branch", "-m", "merging"],
            universal_newlines=True,
        ).splitlines()
        added_files, removed_files = ParseGitMergeSummary(merge_summary)
        self.assertEqual(added_files, [])
        self.assertEqual(removed_files, ["init_file.cc"])

    def test_renamed_files(self):
        merge_summary = [
            " rename base/{old_foo.cc => new_foo.cc} (94%)",
            " rename ipc/old_bar.cc => mojo/new_bar.cc (88%)",
            " rename base/{foo_unittest.cc => bar_unittest.cc} (99%)",
        ]
        added_files, removed_files = ParseGitMergeSummary(merge_summary)
        self.assertEqual(added_files, ["base/new_foo.cc", "mojo/new_bar.cc"])
        self.assertEqual(removed_files, ["base/old_foo.cc", "ipc/old_bar.cc"])
