---
name: libchrome-bug-filer
description: File libchrome-specific bugs in Buganizer for uprev cleanup, upstreaming patches, local divergences, or general libchrome issues. Use when you need to track backward compatibility patches, Chromium upstream changes, or merge conflicts during uprevs.
---

# Libchrome Bug Filer

## Overview

This skill streamlines filing common bug types for the `libchrome` team. It ensures the correct component ID, templates, hotlists, and CC lists are used for various libchrome-related activities, particularly during the uprev process.

## Task Categories

### 1. File a Backward Compatibility Patch Clean-up Bug
Use this when a new backward compatibility patch is added during a `libchrome` uprev and needs a tracking bug for future removal.
- **Workflow**: 
  1. Identify the patch name and the `libchrome` revision (e.g., `r1234567`).
  2. Locate the CL that added the patch (`crrev.com/c/<change-id>`).
  3. Determine the incompatible Chromium commit (`crrev.com/<revision>`).
  4. Summarize what the patch does and what clients need to do to remove it.
  5. Read [bug_templates.md](references/bug_templates.md) for the exact template and field values.
  6. Ask the user if they have a codesearch remaining usages link to add to the bug.

### 2. File an Upstream Patch Bug
Use this when a local patch has been created to fix a build failure or issue in `libchrome` and should be upstreamed to Chromium.
- **Workflow**:
  1. Identify the patch filename and the `libchrome` uprev revision.
  2. Describe the change and the reason for adding it (e.g., build failure in a specific package).
  3. Read [bug_templates.md](references/bug_templates.md) for the field values.

### 3. File a Local Divergence Bug
Use this when a merge conflict occurs during an uprev that results in a divergence from upstream.
- **Workflow**:
  1. Identify the filenames and the `libchrome` uprev revision.
  2. Note the commit hash on `cros/upstream`.
  3. Capture the content with git merge conflict markers.
  4. Read [bug_templates.md](references/bug_templates.md) for the field values.

### 4. File Other libchrome Issues
Use this for miscellaneous bugs related to the `libchrome` uprev workflow or general process issues.
- **Workflow**:
  1. Describe the issue clearly.
  2. Read [bug_templates.md](references/bug_templates.md) for the field values.

## Usage Guidelines

When filing any of these bugs:
1. **Preview**: Always give the user a preview of the bug and ask for feedback
   before attempting to file it.
2. **Component ID**: Always use `656538`.
3. **CC**: Always include `chromeos-libchrome@google.com`.
4. **Hotlists**: Use hotlist `4448649` for patch/divergence issues.
5. **Reference Templates**: Consult [bug_templates.md](references/bug_templates.md) for the specific structure and default fields (Type, Priority, Severity) for each bug type.
