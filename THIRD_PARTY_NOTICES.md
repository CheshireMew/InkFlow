# Third-party notices

InkFlow's own code is licensed as described in `LICENSING.md`. The following material keeps its original license; its inclusion does not relicense it under InkFlow's AGPL grant.

## 100x-learning prompt sources

Prompt JSON files under `src/inkflow/prompt_files/` whose embedded `source.kind` is `100x-working-tree`, `100x-git-history`, or `100x-archived-git-history` were synchronized from the 100x-learning repository. Original and modified copies of those prompt sources are covered by the Mozilla Public License 2.0. The source form is included in this repository, and every file records its upstream source path or Git revision in the `source` object.

This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not distributed with this file, You can obtain one at <https://mozilla.org/MPL/2.0/>.

The MPL grant from 100x-learning does not cover imported case studies, source articles, social posts, screenshots, user libraries, or other third-party/reference content. InkFlow does not bundle those materials; the 100x importer reads a user-selected local library into that user's data directory.

Copyright (c) 2026 柴郡Cheshire. Upstream project: 100x-learning.

## Direct software dependencies

Python runtime dependencies:

- Alembic — MIT
- FastAPI — MIT
- keyring — MIT
- platformdirs — MIT
- Uvicorn — BSD-3-Clause
- Pydantic — MIT
- HTTPX — BSD-3-Clause
- SQLAlchemy — MIT
- Typer — MIT
- python-dotenv — BSD-3-Clause

Frontend runtime dependencies:

- React and React DOM — MIT
- Lucide React — ISC

Frontend build and development dependencies include Vite (MIT), TypeScript (Apache-2.0), ESLint and its listed plugins (MIT), and the React type packages (MIT). Transitive dependency names and exact installed versions are recorded by `frontend/package-lock.json`; Python dependency constraints are recorded by `pyproject.toml`. Their package distributions contain the authoritative license texts and copyright notices.
