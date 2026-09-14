#!/usr/bin/env python3
# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re
import unittest

import filter_config
import filters
import utils


class TestFilters(unittest.TestCase):

    def _build_file_list(self, files):
        return [
            utils.GitFile(path.encode(), None, hash(path)) for path in files
        ]

    def test_filters(self):
        test_filter = filters.Filter(
            [re.compile(rb"want.*")],
            [re.compile(rb"want_excluded.*")],
            [re.compile(rb"want_excluded_always.*")],
        )

        self.assertEqual(
            test_filter.filter_files(
                self._build_file_list(
                    [
                        "want/xxx",
                        "want_excluded/xxx",
                        "want_excluded_always/xxx",
                        "unrelated_upstream_file",
                    ]
                )
            ),
            self._build_file_list(["want/xxx", "want_excluded_always/xxx"]),
        )

    def test_path_filter(self):
        test_filter = filters.Filter(
            [filters.PathFilter([b"a/b/c", b"d"])], [], []
        )

        self.assertEqual(
            test_filter.filter_files(
                self._build_file_list(
                    ["a", "b", "c", "a/b", "b/c", "a/b/c", "d"]
                )
            ),
            self._build_file_list(["a/b/c", "d"]),
        )

    def test_filter_config_owners(self):
        libchrome_filter = filters.Filter(
            filter_config.WANT,
            filter_config.WANT_EXCLUDE,
            filter_config.ALWAYS_WANT,
        )

        # OWNERS files and variations should be excluded.
        self.assertFalse(libchrome_filter.want_file(b"base/OWNERS"))
        self.assertFalse(
            libchrome_filter.want_file(b"base/metrics/METRICS_OWNERS")
        )
        self.assertFalse(
            libchrome_filter.want_file(b"base/memory/MIRACLE_PTR_OWNERS")
        )
        self.assertFalse(libchrome_filter.want_file(b"base/SECURITY_OWNERS"))
        self.assertFalse(libchrome_filter.want_file(b"base/OWNERS.android"))

        # Files that are not owners should be kept.
        self.assertTrue(
            libchrome_filter.want_file(b"base/metrics/histogram.cc")
        )
        self.assertTrue(libchrome_filter.want_file(b"base/OWNERS.x/foo.cc"))
