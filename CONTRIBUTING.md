# Contributing

Keep contributions focused on portable resource-management workflows.

- Do not add organization-specific categories or project structures.
- Add reusable behavior as parameters, references, or scripts.
- Keep `.skills/SKILLS.md` synchronized with every skill directory.
- Prefer small composable skills over broad orchestration.
- Document new backend assumptions in `GOVERNANCE.md`.
- Run relevant local checks, including `python3 -m py_compile` for changed
  Python helpers and `git diff --check` before proposing changes.
