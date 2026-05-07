This repository contains portable SkillBag resource-management skills.

Preserve the SkillBag structure:

- `.skills/SKILLS.md` is the discovery catalog.
- each skill lives at `.skills/<name>/SKILL.md`.
- skill names are lowercase hyphenated identifiers.

Resource-root structure belongs in `resource-scaffold`; other skills should
depend on it instead of defining competing folder layouts.
