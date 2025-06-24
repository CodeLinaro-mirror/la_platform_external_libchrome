#!/usr/bin/env python3
# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for disable_warnings.py"""

import textwrap
import unittest

import disable_warnings


class Test(unittest.TestCase):
    """Unittests for disable_warnings.py."""

    def test_header_to_define_works(self):
        self.assertEqual(
            disable_warnings.header_path_to_define("foo.h"),
            "FOO_H",
        )
        self.assertEqual(
            disable_warnings.header_path_to_define("foo/bar.h"),
            "FOO_BAR_H",
        )
        self.assertEqual(
            disable_warnings.header_path_to_define("b4r_baz.h"),
            "B4R_BAZ_H",
        )
        self.assertEqual(
            disable_warnings.header_path_to_define("base/allocator/partition_allocator/src/partition_alloc/foo.h"),
            "PARTITION_ALLOC_FOO_H",
        )

    def test_header_guard_detection_fails_on_bad_guards(self):
        """Ensures that we `raise` if a header has bad guards."""

        def add_into_header_guards(header_contents: str):
            disable_warnings.add_into_header_guards(
                add_after_ifndef="",
                add_before_endif="",
                header_contents=header_contents,
                header_path="foo.h",
            )
            self.fail("No exception was thrown")

        with self.assertRaisesRegex(ValueError, "^No `#ifndef"):
            add_into_header_guards("")

        with self.assertRaisesRegex(ValueError, "^No `#ifndef"):
            add_into_header_guards(
                textwrap.dedent(
                    """\
                    // Copyright bits here
                    #ifndef FOO_H
                    #define NOT_FOO_H
                    #endif
                    """
                )
            )

        with self.assertRaisesRegex(ValueError, "^No `#endif`"):
            add_into_header_guards(
                textwrap.dedent(
                    """\
                    // Copyright bits here
                    #ifndef FOO_H
                    #define FOO_H
                    int foo();
                    // #endif
                    """
                )
            )

        with self.assertRaisesRegex(ValueError, "^No `#endif`"):
            add_into_header_guards(
                textwrap.dedent(
                    """\
                    // Copyright bits here
                    #endif // FOO_H
                    #ifndef FOO_H
                    #define FOO_H
                    int bar();
                    #endif // broken ending FOO_H comment
                    """
                )
            )

    def test_header_guard_adds_code_after_guards(self):
        """Tests a successful case of pragma-adding."""
        header_before = textwrap.dedent(
            """\
            // Copyright bits here
            #ifndef FOO_H // some comment
            #define FOO_H // some other comment
            int foo();
            #endif  // FOO_H
            """
        )

        fixed_header = disable_warnings.add_warnings_pragmas(
            "foo.h",
            header_before,
            ["-Wwarning1", "-Wwarning2"],
        )
        self.assertEqual(
            fixed_header,
            textwrap.dedent(
                """\
                // Copyright bits here
                #ifndef FOO_H // some comment
                #define FOO_H // some other comment
                #pragma GCC diagnostic push
                #pragma GCC diagnostic ignored "-Wwarning1"
                #pragma GCC diagnostic ignored "-Wwarning2"
                int foo();
                #pragma GCC diagnostic pop
                #endif  // FOO_H
                """
            ),
        )

    def test_outermost_guards_are_selected(self):
        """Tests a successful case of pragma-adding with nested guards."""
        header_before = textwrap.dedent(
            """\
            // Copyright bits here
            #ifndef FOO_H_
            #define FOO_H_

            #ifndef BAR_H
            #define BAR_H
            int foo();
            #endif  // BAR_H

            #endif  // FOO_H_
            """
        )

        fixed_header = disable_warnings.add_warnings_pragmas(
            "foo.h",
            header_before,
            ["-Wwarning"],
        )
        self.assertEqual(
            fixed_header,
            textwrap.dedent(
                """\
                // Copyright bits here
                #ifndef FOO_H_
                #define FOO_H_
                #pragma GCC diagnostic push
                #pragma GCC diagnostic ignored "-Wwarning"

                #ifndef BAR_H
                #define BAR_H
                int foo();
                #endif  // BAR_H

                #pragma GCC diagnostic pop
                #endif  // FOO_H_
                """
            ),
        )


if __name__ == "__main__":
    unittest.main()
