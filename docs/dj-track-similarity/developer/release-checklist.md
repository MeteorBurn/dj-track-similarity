# Release checklist

> Audience: Maintainers doing a final audit.
> Goal: Check safety, contracts, builds, and public wording before publishing.
> Type: how-to

## Checklist

- No examples expose private paths, usernames, real track names, secrets, or local database locations.
- CLI docs use the unified `dj-sim analyze` command.
- API docs mention active endpoints only.
- Frontend and docs builds ran when touched.
- Focused tests cover touched behavior.
- Generated reports, SQLite files, logs, node_modules, and local model artifacts are not staged.
- SONARA upstream version/schema, project feature revision, default profile, and signature example agree with `sonara_contract.py` and `sonara_features.py`.
- A SONARA semantic change also reviews classifier invalidation, manifest compatibility, the prepare/reset/reanalysis workflow, and focused SONARA tests.
- Sidebar entries and local links include every new documentation page.

## Safety audit

Review any code path that writes audio tags or deletes audio. Also check relocation, analysis reset, and database clear paths.
