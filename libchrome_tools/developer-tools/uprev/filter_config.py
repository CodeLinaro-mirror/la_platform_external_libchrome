# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Provide filter rules for libchrome tools."""

import re

# Libchrome wants WANT but mot WANT_EXCLUDE
# aka files matching WANT will be copied from upstream_files
WANT = [
    re.compile(rb'base/((?!(third_party)/).*$)'),
    re.compile(rb'base/third_party/(dynamic_annotation|icu|nspr|valgrind|cityhash|superfasthash)'),
    re.compile(
        rb'build/(android/(gyp/util|pylib/([^/]*$|constants))|[^/]*\.(h|py)$|buildflag_header.gni)'),
    re.compile(rb'mojo/'),
    re.compile(rb'dbus/'),
    re.compile(rb'ipc/.*(\.cc|\.h|\.mojom)$'),
    re.compile(rb'ui/gfx/(gfx_export.h|geometry|range)'),
    re.compile(rb'testing/[^/]*\.(cc|h)$'),
    re.compile(rb'third_party/(ipcz|jinja2|markupsafe|ply)'),
    re.compile(
        rb'components/(json_schema|policy/core/common/[^/]*$|policy/policy_export.h|timers)'
    ),
    re.compile(
        rb'device/bluetooth/bluetooth_(common|advertisement|uuid|export)\.*(h|cc)'
    ),
    re.compile(
        rb'device/bluetooth/bluez/bluetooth_service_attribute_value_bluez.(h|cc)'
    ),
    re.compile(
        rb'chromeos/ash/components/policy/device_local_account/device_local_account_type.h'
    ),
]

# WANT_EXCLUDE will be excluded from WANT
WANT_EXCLUDE = [
    re.compile(rb'(.*/)?BUILD.gn$'),
    re.compile(rb'(.*/)?PRESUBMIT.py$'),
    re.compile(rb'(.*/)?OWNERS$'),
    re.compile(rb'(.*/)?SECURITY_OWNERS$'),
    re.compile(rb'(.*/)?DEPS$'),
    re.compile(rb'(.*/)?DIR_METADATA$'),
    re.compile(rb'base/android/java/src/org/chromium/base/BuildConfig.java'),
    re.compile(rb'base/(.*/)?(ios|win|fuchsia|mac|openbsd|freebsd|nacl)/.*'),
    re.compile(rb'.*_(ios|win|mac|fuchsia|openbsd|freebsd|nacl)[_./]'),
    re.compile(rb'.*/(ios|win|mac|fuchsia|openbsd|freebsd|nacl)_'),
    re.compile(rb'dbus/(test_serv(er|ice)\.cc|test_service\.h)$')
]

# ALWAYS_WANT is a WANT, but not excluded by WANT_EXCLUDE
ALWAYS_WANT = [re.compile(rb'base/hash/(md5|sha1)_nacl\.(h|cc)$')]
