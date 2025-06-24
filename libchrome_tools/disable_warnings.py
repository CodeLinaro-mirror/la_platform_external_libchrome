#!/usr/bin/env python3
# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
Tool to add `#pragma`s to libchrome files, so warnings can be disabled.

Some ChromeOS projects require libchrome headers, and want to use more strict
warnings than Chrome cares to use. This results in the need for `#pragma
GCC warning disable` blocks around libchrome headers, which get repetitive and
can be a bit error-prone to work with if used at `#include` sites.

Rather than forcing ChromeOS projects to scatter these `#pragma`s around their
codebases, this script lets us centralize them in libchrome without having to
worry about merge conflicts.
"""

import argparse
import logging
import os
import re
from pathlib import Path
import stat
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence


# A dict of header paths mapped to the series of warnings to disable for the
# given header.
WARNINGS_TO_SILENCE: Dict[str, Iterable[str]] = {
    "base/memory/scoped_refptr.h": ("-Wsign-conversion",),
    "base/numerics/clamped_math_impl.h": ("-Wimplicit-int-float-conversion",),
    "base/time/time.h": ("-Wimplicit-int-float-conversion",),
    "base/allocator/partition_allocator/src/partition_alloc/partition_alloc_base/check.h": ("-Wunused-parameter",),
}


def header_path_to_define(header_path: str) -> str:
    """Turns a header name into a include-guard-like string.

    The returned value is safe for use in a regexp without escaping.

    >>> header_name_to_define("foo.h")
    "FOO_H"
    >>> header_name_to_define("foo/bar.h")
    "FOO_BAR_H"
    >>> header_name_to_define("base/allocator/partition_allocator/src/partition_alloc/foo.h")
    "PARTITION_ALLOC_FOO_H"
    """
    # The include guard for partition_allocator needs special treatment.
    header_path = header_path.removeprefix("base/allocator/partition_allocator/src/")
    return re.sub(r"[^a-zA-Z0-9_]", "_", header_path).upper()


def add_into_header_guards(
    add_after_ifndef: str,
    add_before_endif: str,
    header_contents: str,
    header_path: str,
) -> str:
    """Adds content between header guards in a C or C++ header.

    Most C and C++ header files have header guards, like:

    ```
    #ifndef _FOO_H
    #define _FOO_H
    /* Meaningful header contents go here. */
    #endif
    ```

    For style and build speed reasons, it's best to put all header content
    between these guards. This function exists to identify these guards, and
    place text between them.

    Args:
        add_after_ifndef: Text to add a line after the `#ifdef ... #define`
           lines in the header.
        add_before_endif: Text to add on the line before the `#endif` in the
            header.
        header_contents: The text of the header to modify.
        header_path: The path to the header, rooted at libchrome's source.

    Returns:
        The text of the modified header.

    Raises:
        ValueError if include guards could not be detected in
        `header_contents`.
    """
    # The heuristc here was selected after discussion on
    # http://crrev.com/c/4859386.
    header_define = header_path_to_define(header_path)

    ifndef_regex_text = (
        r"^\#ifndef\s+("
        + header_define
        + r"_?)\b.*?\n"
        + r"\#define\s+\1\b.*?$"
    )
    ifndef_regex = re.compile(ifndef_regex_text, re.MULTILINE)

    found = ifndef_regex.search(header_contents)
    if not found:
        raise ValueError("No `#ifndef ... #define` guard found in header")

    # Add 1 so we get past the newline at the end of ifndef_regex.
    after_ifndef = found.end() + 1
    endif_regex = re.compile(
        r"^#endif\s+//\s*" + re.escape(found.group(1)),
        re.MULTILINE,
    )

    found = endif_regex.search(header_contents, after_ifndef)
    if not found:
        raise ValueError("No `#endif` found after include guard in header")

    before_endif = found.start()
    return "".join(
        (
            header_contents[:after_ifndef],
            add_after_ifndef,
            header_contents[after_ifndef:before_endif],
            add_before_endif,
            header_contents[before_endif:],
        )
    )


def add_warnings_pragmas(
    header_path: str, file_contents: str, warnings: List[str]
) -> str:
    """Adds pragmas to ignore `warnings` to the given file."""
    assert warnings, "warnings lists shouldn't be empty"

    add_after_ifndef_lines = ["#pragma GCC diagnostic push"]
    for warning in warnings:
        # No actual warning contains these, and if `warning` has neither
        # backslashes nor quotes, we can skip quoting the warning.
        if '"' in warning or "\\" in warning:
            raise ValueError(f"invalid warning: {repr(warning)}")
        add_after_ifndef_lines.append(
            f'#pragma GCC diagnostic ignored "{warning}"'
        )

    # Ensure we append a trailing '\n' to `add_after_ifndef_lines`.
    add_after_ifndef_lines.append("")
    return add_into_header_guards(
        add_after_ifndef="\n".join(add_after_ifndef_lines),
        add_before_endif="#pragma GCC diagnostic pop\n",
        header_contents=file_contents,
        header_path=header_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Disable warnings for select parts of libchrome."
    )
    parser.add_argument(
        "--libchrome-path",
        default=Path(__file__).resolve().parent.parent,
        type=Path,
        help=(
            "Path of libchrome to apply warnings patches. "
            "Defaults to parent of this file's directory."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="If specified, patched files won't actually be written.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    libchrome_path = args.libchrome_path
    dry_run = args.dry_run

    for file_path, all_warnings in sorted(WARNINGS_TO_SILENCE.items()):
        path = libchrome_path / file_path
        if path.suffix != ".h":
            raise ValueError("WARNINGS_TO_SILENCE should only contain headers")
        warnings = sorted(all_warnings)
        logging.info("Patching %s to ignore %s...", path, warnings)

        file_contents = path.read_text(encoding="utf-8")
        new_contents = add_warnings_pragmas(file_path, file_contents, warnings)
        if dry_run:
            logging.info("--dry-run passed; skipping write to %s", path)
        else:
            path.write_text(new_contents, encoding="utf-8")


if __name__ == "__main__":
    main()
