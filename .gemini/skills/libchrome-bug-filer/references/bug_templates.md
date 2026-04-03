# libchrome Bug Templates

## 1. Backward Compatibility Patch Clean-up Tracking Bug
- **Template ID**: `1991344`
- **Component ID**: `656538`
- **Type**: `INTERNAL_CLEANUP`
- **Priority**: `P1`
- **Severity**: `S2`
- **Hotlist IDs**: `4448649`
- **CC**: `chromeos-libchrome@google.com`
- **Title Pattern**: `r<revision> uprev: remove <patch name>`
- **Description Body**:
```text
This is a tracking bug for removal of patch <patch name>, added at libchrome r<uprev revision> uprev (crrev.com/c/<change-id>).

In crrev.com/<incompatible chromium commit revision>, <-- describe change -->.
This patch <-- describe what the patch does -->.

<-- Describe what to be done on client side as clearly as possible, preferably with examples if change is not trivial -->.

CS link to remaining usages: <cs link>
```

## 2. Upstream Local Changes to Chromium
- **Component ID**: `656538`
- **Type**: `INTERNAL_CLEANUP`
- **Priority**: `P2`
- **Severity**: `S2`
- **Hotlist IDs**: `4448649`
- **CC**: `chromeos-libchrome@google.com`
- **Title Pattern**: `upstream change in patch <patch filename>`
- **Description Body**:
```text
When uprev to r<uprev revision> (crrev.com/c/<change-id>), a patch is created to <-- please describe change and reason for adding it, e.g. causing build failure in foo package -->.
Upstream the change to Chromium and move the patch to cherry-pick section once submitted.
```

## 3. Local Divergence from Upstream
- **Component ID**: `656538`
- **Type**: `BUG`
- **Priority**: `P2`
- **Severity**: `S2`
- **Hotlist IDs**: `4448649`
- **CC**: `chromeos-libchrome@google.com`
- **Title Pattern**: `divergence with upstream in <filenames>`
- **Description Body**:
```text
When uprev to r<uprev revision> (<commit hash on cros/upstream>), following merge conflict happened in <filename>:
<-- please paste content with git merge conflict markers -->
```

## 4. Other libchrome Issues
- **Template ID**: `1991316`
- **Component ID**: `656538`
- **CC**: `chromeos-libchrome@google.com`
- **Description Body**: `Misc bugs related to uprev workflow/ process`
