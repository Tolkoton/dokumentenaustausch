# Memory Management

How feature-implementer reads and writes MEMORY.md files at task boundaries. Implements the per-technology + per-project memory pattern.

## Storage layout

```
~/.claude/memory/                       # User-level, cross-project, per-technology
├── datev/MEMORY.md
├── python-fastapi/MEMORY.md
├── pydantic-v2/MEMORY.md
├── postgres/MEMORY.md
├── sqlalchemy/MEMORY.md
├── hypothesis/MEMORY.md
├── argon2/MEMORY.md
└── ...

<project_root>/.architecture/MEMORY.md  # Per-project, codebase-specific
```

## Tech detection algorithm

Run at Phase A (intake) AND Phase F (handoff). Outputs ranked list of relevant technologies for this task.

```python
def detect_technologies(task) -> list[str]:
    candidates = {}  # tech_name → weight

    # Source 1: pyproject.toml dependencies (weight 1 each)
    pyproject = parse_pyproject_toml(project_root / "pyproject.toml")
    for dep in pyproject.get("dependencies", []):
        name = normalize_dep_name(dep)
        candidates[name] = candidates.get(name, 0) + 1

    # Source 2: imports in files this task touches (weight 3 each per import)
    for f in task.files_to_modify + task.files_to_create:
        if (project_root / f).exists():
            for imp in parse_imports(project_root / f):
                tech = imp_to_tech(imp)
                if tech:
                    candidates[tech] = candidates.get(tech, 0) + 3

    # Source 3: tasks.yaml explicit tags (weight 5 each)
    for tech in task.get("technologies", []):
        candidates[tech] = candidates.get(tech, 0) + 5

    # Source 4: Phase 2 ADR-referenced libraries (weight 2 each)
    for adr_ref in task.references.get("adrs", []):
        for lib in get_libs_from_adr(adr_ref):
            candidates[lib] = candidates.get(lib, 0) + 2

    # Take top 5 by weight
    ranked = sorted(candidates.items(), key=lambda x: -x[1])
    return [tech for tech, weight in ranked[:5]]


def normalize_dep_name(dep: str) -> str:
    """
    Normalize package names to memory-file convention.
    - lowercase
    - strip version constraints (`fastapi>=0.100` → `fastapi`)
    - strip extras (`pydantic[email]` → `pydantic`)
    - map common aliases (`sqlalchemy` → same, `psycopg2` → `postgres`, etc.)
    """
    name = re.split(r"[><=!~\[]", dep)[0].strip().lower()
    ALIAS = {
        "psycopg2": "postgres",
        "psycopg2-binary": "postgres",
        "psycopg": "postgres",
        "pg8000": "postgres",
        "asyncpg": "postgres",
        "sqlmodel": "sqlalchemy",
        "pydantic-settings": "pydantic-v2",
        "fastapi-users": "fastapi",
        "argon2-cffi": "argon2",
        "passlib": "argon2",  # if using argon2 backend
    }
    return ALIAS.get(name, name)


def imp_to_tech(import_str: str) -> str | None:
    """
    Map a Python import to a tech name. Returns None for stdlib / unknown.
    """
    root = import_str.split(".")[0]
    STDLIB = {"os", "sys", "re", "json", ...}  # full list elsewhere
    if root in STDLIB:
        return None
    return normalize_dep_name(root)
```

Output: 5 most-relevant technologies. Examples:

For a task touching `src/users/service.py` (FastAPI app with Pydantic, Postgres, argon2):
```
[
    "fastapi",         # imports + dep
    "pydantic-v2",     # imports + dep
    "postgres",        # imports + dep
    "argon2",          # imports + dep
    "sqlalchemy",      # imports + dep
]
```

For a task touching `src/billing/datev_export.py`:
```
[
    "datev",           # path + tag
    "pydantic-v2",     # imports
    "decimal",         # imports
    "csv",             # imports (stdlib but financial relevance)
    "postgres",        # dep
]
```

## Read protocol (Phase A)

```python
def load_memory(task) -> str:
    """
    Read all relevant MEMORY.md files. Inject into Claude's context.
    Cap at ~5000 tokens.
    """
    techs = detect_technologies(task)
    chunks = []

    # Per-tech files
    for tech in techs:
        path = Path.home() / ".claude" / "memory" / tech / "MEMORY.md"
        if path.exists():
            chunks.append(("tech:" + tech, read_top_lessons(path, max_count=20)))

    # Per-project file
    proj_path = project_root / ".architecture" / "MEMORY.md"
    if proj_path.exists():
        chunks.append(("project", read_top_lessons(proj_path, max_count=20)))

    # Concatenate with headers, cap at 5K tokens
    output = ""
    token_budget = 5000
    for label, content in chunks:
        section = f"\n## Memory: {label}\n\n{content}\n"
        if approx_token_count(output + section) > token_budget:
            break
        output += section

    return output


def read_top_lessons(path: Path, max_count: int = 20) -> str:
    """
    Read the most recent N lessons from a MEMORY.md file.
    MEMORY.md format: chronological, newest at top.
    """
    text = path.read_text()
    lessons = text.split("\n## ")  # split on lesson headers
    return "\n## ".join(lessons[:max_count])
```

The output is injected as a background block in Claude's context. NOT shown to the user (it's internal context).

## Write protocol (Phase F session-dreaming)

```python
def session_dreaming(task) -> None:
    """
    Distill lessons from this task and write to appropriate MEMORY files.
    """
    # 1. Identify lessons from PROGRESS.md and reflections.md
    candidates = identify_lessons(
        progress_md=read(f".architecture/tasks/{task.id}/PROGRESS.md"),
        reflections_md=read(f".architecture/tasks/{task.id}/reflections.md"),
    )

    # 2. Classify each lesson
    for lesson in candidates:
        scope = classify_lesson(lesson)
        # scope is "tech:<name>" or "project" or "both"

        if scope.startswith("tech:"):
            tech = scope.split(":")[1]
            append_to_memory(
                path=Path.home() / ".claude" / "memory" / tech / "MEMORY.md",
                lesson=lesson,
                source=f"t{task.id} / project: {project_name}",
            )
        elif scope == "project":
            append_to_memory(
                path=project_root / ".architecture" / "MEMORY.md",
                lesson=lesson,
                source=f"t{task.id}",
            )
        elif scope == "both":
            # Write to both per-tech AND per-project
            for tech in lesson.related_techs:
                append_to_memory(...)
            append_to_memory(project_md_path, ...)
```

### What is a "lesson"

From PROGRESS.md and reflections.md, identify:

1. **Concrete library/framework quirks**
   - "argon2-cffi's verify raises VerifyMismatchError, not returns False"
   - "Pydantic v2 Annotated[str, Field(min_length=8)] at function-level doesn't validate; only validates inside BaseModel"

2. **Patterns that worked unexpectedly well**
   - "Wrapping repo calls in a domain service decoupled tests nicely"

3. **Patterns that failed**
   - "Tried inheriting from Pydantic BaseModel for domain entity → mixed concerns, refactored to dataclass"

4. **Design choices and rationale**
   - "Chose explicit dataclass for User over Pydantic at domain level because of frozen + speed; documented in design.md"

5. **Errors that took >1 hour to debug**
   - "Test failed with `TypeError: 'list' object is not callable`; cause was a class attribute shadowing a method name. Took 45min to find."

NOT lessons (skip):
- Generic platitudes ("Pydantic is great")
- Things obvious to anyone in the domain
- Project-specific decisions already documented in ADRs
- Time spent (logging, not learning)

### Classification heuristic

For each candidate lesson:

```
Is this specific to one client / codebase decision?
  YES → project scope
  NO → continue

Is this about a specific library/framework's behavior?
  YES → tech scope (which tech: pick most relevant)
  NO → continue

Would this bite me in a different project using same stack?
  YES → tech scope
  NO → continue

Could be either?
  → both scopes (write to per-tech AND per-project)

Default if uncertain: BOTH (cheap, prevents loss)
```

Examples:

| Lesson | Classification |
|--------|---------------|
| "argon2-cffi verify raises exception" | tech:argon2 |
| "Our User entity uses CompositeKey(tenant_id, user_id)" | project |
| "Pydantic v2 doesn't allow `default=` in Annotated[Field]" | tech:pydantic-v2 |
| "We chose to wrap Stripe in stripe_adapter.py" | project |
| "DATEV invoice number must be sequential per Steuerberater" | tech:datev |
| "Hypothesis from_type for Annotated needs custom strategy" | tech:hypothesis + tech:pydantic-v2 (both) |
| "Postgres NUMERIC scale must match Decimal places" | tech:postgres |

### MEMORY.md append format

```markdown
## YYYY-MM-DD — t<id> — <one-line title>

<1-3 sentences, concrete>

Source task: t<id> / project: <project_name>
```

Append to TOP of file (newest at top).

Don't edit existing entries. Don't delete. Append only.

## Curation (user-driven, not automatic)

`MEMORY.md` files grow indefinitely. After ~50-100 lessons, manual curation is needed:

User reviews `MEMORY.md`, consolidates similar lessons, prunes outdated. The skill does NOT auto-prune.

To make curation easy, lessons:
- Have dates (sort by recency for relevance check)
- Have task references (can audit which tasks each lesson came from)
- Are atomic (one lesson = one paragraph)

Recommended curation triggers (user-initiated):
- Once per quarter
- When `MEMORY.md` exceeds ~10K tokens (skill cap when reading; rest gets dropped silently)
- When user notices repeated patterns (sign for consolidation)

## Memory hygiene rules

- **Append-only**: skill never deletes or rewrites existing entries
- **Atomic**: one lesson = one section
- **Concrete**: vague lessons get pruned in curation; better not to write them
- **Sourced**: every lesson has task ID for traceability
- **Bounded read**: skill reads top-20 per file (most recent); avoids context bloat
- **Project + tech**: ambiguous lessons go to both (cheap insurance)
- **No personal data**: lessons never contain user data, credentials, or project secrets

## Bootstrap (first project)

When `~/.claude/memory/` is empty (first ever task on this machine):
- `load_memory()` returns empty string
- That's fine — proceed without memory injection
- `session_dreaming` creates the appropriate directories on first write
- Over time, accumulation begins

## When NO tech is detected

Rare but possible: a task that's pure config/doc edits with no recognizable tech.
- `detect_technologies` returns empty list
- `load_memory()` reads only per-project MEMORY.md
- `session_dreaming` writes only to per-project MEMORY.md

That's correct behavior.

## Cross-machine sync (optional)

If the user wants memory shared across machines:
- `~/.claude/memory/` → symlink to cloud-synced folder (Dropbox, iCloud, syncthing)
- Or store in a private git repo, pull at session start

Skill doesn't need to know — it just reads/writes filesystem.

## Privacy concerns

Per-tech MEMORY.md crosses projects. Therefore:
- Never put client-identifying info in tech-scoped lessons (their company names, etc.)
- Project-scoped lessons can have project specifics (they don't leak)
- Default ambiguous → per-project (safer)
