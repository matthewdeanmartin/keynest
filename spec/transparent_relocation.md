# Spec: Transparent Repo Relocation

Status: implemented (R1–R4)
Audience: keynest maintainers
Relates to: [`spec.md`](./spec.md) §3 (core model), §4 (backends), §6 (CLI), §11 (search)

## 1. The idea in one sentence

When keynest is launched from inside a git repository, it should
**transparently default its folder to that repo's identity** — derived from the
GitHub/GitLab remote when present, otherwise the local repo — so a developer
working in `~/code/acme-api` sees and creates secrets under
`/acme-api` (or `/github.com/acme/acme-api`) without ever choosing a folder.

The developer's *workflow location* (their checkout) becomes the secret's
*namespace*, automatically. This is the same instinct as `direnv`, `aws-vault`'s
per-profile scoping, and `chamber`'s per-service namespacing: the tool meets the
developer where they already are.

## 2. Why

Today (`spec.md` §3) every secret lands in `/default` unless the user manually
picks a folder. In practice developers think *per project*: "the secrets for
acme-api", "the secrets for my mastodon bot". Asking them to name and re-select a
folder every time is friction that pushes them back to `.env` files sitting next
to the code — exactly what keynest exists to prevent.

If keynest can notice "you are in the acme-api repo" the same way `git` itself
does, it can make the *project-scoped path the easiest path*, consistent with the
product opinion (`spec.md` §18): the safe path should be the path of least
resistance from inside the developer's actual workflow.

## 3. Critical constraint: "relocation" is about *namespacing*, not moving bytes

This must be stated up front because the feature name is slightly misleading.

OS keyring secrets are stored **per OS user**, globally, under one service name
(`spec.md` §4). They are not physically stored "in" a repo, and they must never
be. Putting secret material inside a working tree is the precise failure mode
keynest prevents.

Therefore **transparent relocation changes only:**

1. the **default folder** keynest selects when launched, and
2. the **filtered view** keynest shows (which maps it surfaces first), and
3. the **identity** used to name new folders.

It does **not**:

- write any secret value into the repo,
- write any file into the repo by default (see §8 for an opt-in, non-secret
  marker file),
- move or copy existing secrets between folders implicitly.

"Relocation" = "the app relocates *its attention* to your current repo." The
secrets stay in the OS keyring / AWS exactly as before.

## 4. Repo identity resolution

When keynest starts (CLI or GUI), it resolves a **RepoContext** by walking up
from the current working directory.

### 4.1 Detection order

1. **Find the repo root.** Walk parents looking for a `.git` directory/file.
   (A `.git` *file* indicates a worktree or submodule; follow its `gitdir:`
   pointer.) If none is found before the filesystem root or `$HOME`, there is no
   repo context — fall back to `/default` exactly as today.

2. **Read the remote.** Prefer `origin`, else the first remote, by parsing
   `.git/config` directly (no `git` subprocess required; std-lib `configparser`
   per `spec.md` §14). Extract the remote URL.

3. **Classify the host.** Normalize the remote URL (both SSH and HTTPS forms):

   | Remote URL                                   | host         | owner   | repo       |
   |----------------------------------------------|--------------|---------|------------|
   | `git@github.com:acme/acme-api.git`           | github.com   | acme    | acme-api   |
   | `https://github.com/acme/acme-api.git`       | github.com   | acme    | acme-api   |
   | `git@gitlab.com:acme/group/acme-api.git`     | gitlab.com   | acme/group | acme-api |
   | `https://ghe.corp.example/acme/x.git`        | ghe.corp…    | acme    | x          |
   | (no remote)                                  | —            | —       | (dir name) |

   GitLab subgroups (`owner/group/subgroup/repo`) must be preserved in the owner
   segment. Strip a trailing `.git`. Lowercase the host; preserve case elsewhere.

4. **Derive the folder.** See §5 for the naming scheme and its trade-offs.

### 4.2 RepoContext shape

```python
@dataclass(frozen=True)
class RepoContext:
    root: Path                 # repo working-tree root
    host: str | None           # "github.com", "gitlab.com", "ghe.corp...", or None
    owner: str | None          # "acme" or "acme/group" (GitLab subgroups), or None
    repo: str | None           # "acme-api", or None
    remote_url: str | None     # raw remote URL as found, or None
    source: Literal["remote", "local-dir"]  # how identity was derived

    @property
    def is_repo(self) -> bool: ...
    @property
    def default_folder(self) -> str: ...   # the folder keynest should select
```

`RepoContext` holds **no secret material** and is cheap to compute. It is the
single object passed into the GUI/CLI to drive defaulting.

### 4.3 Where it lives

A new pure function module, e.g. `keynest/services/repo_context.py`, sitting
beside the existing `repo_tools.py`. It depends only on `pathlib`,
`configparser`, and `re` — no new third-party deps, no `git` binary requirement
(detection must work even when `git` is not on `PATH`). If a `git` binary *is*
present it may be used as a fallback/confirmation, but never as the sole path.

## 5. Folder naming scheme

There is a real trade-off between **short and friendly** vs **globally
unambiguous**. Two repos named `api` under different owners must not collide.

### 5.1 Options considered

| Scheme            | Example folder                  | Pros                          | Cons                                  |
|-------------------|---------------------------------|-------------------------------|---------------------------------------|
| A. repo only      | `/acme-api`                     | shortest, matches mental model| collisions across owners/forks        |
| B. owner/repo     | `/acme/acme-api`                | disambiguates forks           | one collision case left (host)        |
| C. host/owner/repo| `/github.com/acme/acme-api`     | globally unique               | verbose; deep nesting (spec discourages) |
| D. local dir name | `/acme-api` (from folder name)  | works with no remote          | brittle if dirs renamed/duplicated    |

### 5.2 Recommendation

**Default to B (`owner/repo`) when a remote is known, D (directory name) when it
is not.** Make the scheme a single configurable setting (`relocation.scheme =
repo | owner-repo | host-owner-repo`) so power users can opt into C for maximum
disambiguation.

Rationale: `owner/repo` is what developers say out loud ("acme/acme-api"),
matches the GitHub/GitLab URL slug, and resolves the common fork-collision case.
`spec.md` §824 explicitly discourages *deeply* nested JSON but folders are a
flat-ish namespace; `owner/repo` is two segments, which the existing
`normalize_folder` / `parse_path` model already tolerates (folders are arbitrary
strings; `/` inside a folder is just part of the name).

> Implementation note: today `parse_path` splits on the *first* `/` into
> `(folder, name)`. A two-segment folder like `acme/acme-api` plus a map name
> `dev` would be the logical path `/acme/acme-api/dev`, which the current parser
> would read as folder=`acme`, name=`acme-api/dev`. **This is the main code
> change the feature requires** and §9 calls it out as a decision point: either
> (a) keep folders single-segment and join owner+repo with a separator that is
> not `/` (e.g. `acme.acme-api`), or (b) extend the path model to support
> multi-segment folders. Pick one before building.

### 5.3 Sanitization

Folder segments must be normalized to safe, display-friendly tokens: trim
whitespace, collapse internal whitespace, and forbid characters that break the
keyring username convention. Reuse/extend `normalize_folder`. Never silently map
two distinct repos to the same folder; if sanitization would collide, fall back
to a more-qualified scheme and tell the user.

## 6. Behavior: GUI

On launch, after computing `RepoContext`:

1. If `ctx.is_repo`, **pre-select** the derived folder in the left panel and show
   a non-modal banner/status:

   > 📂 Detected repo **acme/acme-api** (github.com). New secrets default here.
   > [Use /default instead] [Pin this choice]

2. New maps (`New map`, `Quick add`, `Paste .env`) default their folder to
   `ctx.default_folder` instead of `default`.

3. The folder is **a default, never a jail.** All other folders remain visible
   and selectable. The user can always switch to `/default` or any other folder;
   relocation only changes what is *pre-selected*.

4. If no repo is detected, behavior is identical to today (defaults to
   `/default`). The feature is invisible when irrelevant.

The detection result should be surfaced in **Diagnostics** (`spec.md` references
a diagnostics view) so a confused user can see "why is my default acme-api?"

## 7. Behavior: CLI

The CLI gains an implicit, overridable repo default.

```bash
# Inside ~/code/acme-api (origin = github.com/acme/acme-api):

keynest list                 # lists maps under the detected folder first
keynest set dev DATABASE_URL "postgres://..."   # -> /acme/acme-api/dev
keynest run dev -- python app.py                # resolves /acme/acme-api/dev
```

Rules:

- A **bare name** with no folder (e.g. `dev`) resolves against the detected repo
  folder instead of `/default`, *when a repo is detected*. This is the heart of
  "transparent."
- An **explicit path** (`other-proj/dev`, `/default/x`) always wins. Detection
  never overrides an explicit folder.
- A global flag disables it for one invocation: `--no-repo` (or env
  `KEYNEST_NO_REPO=1`).
- `keynest list` without `--folder` may show the detected folder's maps first,
  then a separator, then everything else — so the user still discovers other
  secrets but sees the relevant ones immediately.

This mirrors `aws-vault exec <profile>` / `chamber exec <service>` ergonomics,
except the "profile/service" is inferred from the checkout.

> Backwards-compat caution: making a bare `dev` mean a different folder depending
> on `cwd` is powerful but surprising. The CLI must **echo the resolved path** on
> mutating commands (`set`, `run`, `import-env`) — e.g.
> `→ /acme/acme-api/dev` — so the user always sees where a secret went. Silence
> here would be a footgun.

## 8. Optional: the `.keynest` repo marker (opt-in, non-secret)

Some teams will want the repo→folder mapping to be **explicit and shareable**
rather than inferred. Support an optional, committed, **secret-free** file at the
repo root:

```toml
# .keynest  (safe to commit; contains NO secret values)
folder = "acme/acme-api"
# optional: default map name when only a folder is given
default_map = "dev"
```

Rules:

- If `.keynest` exists, it **overrides** inferred identity (explicit beats
  magic).
- keynest must **refuse to write secret values** into this file, ever, and the
  file schema has no field that could hold one. A linter/check rejects unknown
  fields to prevent abuse.
- The import flow (`spec.md` §8) may *offer* to create `.keynest` and to add the
  keynest index dir to `.gitignore` (`repo_tools.GITIGNORE_SUGGESTIONS` already
  lists `.devsecrets/`).

This gives the "in-repo" experience the user asked for — a file you can see in
the repo — **without** the danger of secrets in the tree. The repo carries the
*pointer*, never the payload.

## 9. Open decisions (resolve before building)

1. **Folder path model (the big one).** Adopt multi-segment folders (extend
   `parse_path`/`normalize_folder`) or keep single-segment and encode
   `owner/repo` with a non-`/` separator? This dictates the data model and every
   path-parsing call site. *Recommendation: pick single-segment with a `.`
   join (`acme.acme-api`) for v1 to avoid touching `parse_path` semantics; revisit
   multi-segment later.*
2. **Default scheme:** `owner-repo` (recommended) vs `repo` vs `host-owner-repo`.
3. **Migration:** existing users have secrets under `/default` and hand-named
   folders. Detection must never strand them — they stay listed. Do we offer a
   one-click "move these `/default` maps into the detected folder"? *Recommend:
   offer, never automatic.*
4. **Monorepo / nested repos:** which root wins when nested? *Recommend: the
   nearest `.git` going up; document it.*
5. **Worktrees & submodules:** confirm `.git`-file following resolves to the
   intended identity (a submodule's remote ≠ the superproject's).
6. **Privacy:** the remote URL can embed a username or token
   (`https://user:token@host/...`). When recording `remote_url` in diagnostics or
   `.keynest`, **strip credentials** from the URL first.

## 10. Security & honesty notes

Consistent with `spec.md` §16's "say it plainly":

- This feature stores **no new secret material anywhere**; it only changes
  defaulting and views. The threat model is unchanged.
- `.git/config` and the optional `.keynest` file are **non-secret** inputs.
  keynest reads them; it does not trust them with secret values.
- Inferring identity from `cwd` means the *same command* can target different
  folders in different directories. The CLI mitigates this by echoing the
  resolved path on every mutation (§7).
- Detection must be **fail-safe**: any error parsing `.git/config` degrades to
  "no repo detected → `/default`", never to a crash or a wrong-folder write.
- Never execute hooks or arbitrary `git` config aliases during detection; parse
  config as data only.

## 11. Suggested phasing

- **Phase R1 — detection, read-only.** `repo_context.py` + diagnostics line
  showing the detected identity. No defaulting yet. Pure function, fully unit
  testable with fixture `.git/config` files (SSH/HTTPS/GitLab-subgroup/no-remote).
- **Phase R2 — GUI default + banner.** Pre-select folder, "use /default instead"
  escape hatch. Strictly additive; off when no repo.
- **Phase R3 — CLI bare-name resolution** with `--no-repo`, path echoing, and
  `list` ordering.
- **Phase R4 — `.keynest` marker** (opt-in, schema-validated, secret-free) and
  the import-flow offer to create it.

Each phase is shippable alone and reversible; R1 is risk-free (read-only,
informational).

## 12. Test sketch

- `repo_context`: table-driven over remote URL forms (SSH, HTTPS, `.git` suffix,
  GitLab subgroups, credential-bearing URLs that must be scrubbed, GHE hosts,
  no-remote dir-name fallback, no-repo → `None`).
- `.git`-file following for worktrees/submodules via tmp fixtures.
- path-model decision (§9.1): tests proving `owner/repo`-derived folders round-trip
  through `parse_path`/`logical_path` without misclassifying the map name.
- CLI: bare name resolves to detected folder; explicit path overrides; `--no-repo`
  disables; mutations echo the resolved path.
- Fail-safe: malformed `.git/config` → `/default`, no exception.
- Security: credential-bearing remote URL never appears verbatim in diagnostics
  or `.keynest`.
```
