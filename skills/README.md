# Local Skills

The bridge discovers local, declarative skills from `skills/<name>/skill.yaml`
and the matching `SKILL.md`. It does not implement a marketplace, download
code, or grant permissions automatically. `enable_skill` and `disable_skill`
only change the in-memory enabled state; declared tools remain subject to the
normal registry and permission checks.

Skills can be added in their own directories, for example:

```text
skills/windows-assistant/SKILL.md
skills/windows-assistant/skill.yaml
```

Available built-ins are `coding`, `embedded`, and `windows`. The embedded
skill is intentionally read/search/build/analyze oriented; it does not flash
hardware or access serial credentials.
