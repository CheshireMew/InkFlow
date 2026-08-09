# Prompt file licensing boundary

Prompt files in this directory do not all have the same origin.

Files whose JSON `source.kind` is `100x-working-tree`, `100x-git-history`, or `100x-archived-git-history` are source-form copies synchronized from 100x-learning. Those files, including InkFlow-specific modifications to them, remain under MPL-2.0. Each JSON `source` object records the upstream path and, for historical copies, the Git revision. The MPL notice and attribution are reproduced in the repository-level `THIRD_PARTY_NOTICES.md`.

InkFlow-authored operational prompts, output contracts, components, and seed files without one of those three source markers are part of InkFlow and follow the repository-level AGPL-3.0-or-later grant unless their own file says otherwise.

Imported reference cases, hooks, user prompts, model responses, and user writing are runtime data. They are not bundled here and are not licensed by either repository-level grant merely because InkFlow can read them.
