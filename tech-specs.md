# Technical specifications

The decisions on language and target environment are in `scope.md`. This file covers how
the tool is installed, how it models the options, and how it is tested.

## Installation and distribution

The tool ships as a single Python file. The question this section settles is the *shape*
of the installation: a separate installer script that fetches and places everything, or
one self-installing file that does it itself. The duties either shape has to fulfil —
honour `XDG_CONFIG_HOME`, merge instead of overwrite, back up, verify, support
uninstalling — are listed in `scope.md`; the question here is only which shape carries
them better. Shape B won, and is what is built.

### Shape A — separate install script

The familiar `curl … | bash` pattern. `install.sh` lives next to the tool in the repo and
is the thing the README tells people to run:

1. check preconditions: Wayland session, Gnome, `python3`, `gsettings`;
2. fetch the payload — `xkb-caps-options` plus the three files under `config/xkb/` — which
   means either four raw URLs or a tarball of the repo;
3. merge the xkb files into `$XDG_CONFIG_HOME/xkb/`, backing up whatever is already there;
4. install `xkb-caps-options` into `~/.local/bin` and make it executable;
5. warn if `~/.local/bin` is not on `PATH`;
6. verify: compile a keymap with the new option and check that `<CAPS>` came out as
   `Shift_L, Caps_Lock`;
7. print what to do next, and offer to start the tool.

### Shape B — the tool installs itself

The README tells people to download one file, read it, and run it:

```
curl -fsSLO https://raw.githubusercontent.com/matey-jack/xkb-caps-as-shift/main/xkb-caps-options
less xkb-caps-options          # this is the whole product, not a bootstrap
python3 xkb-caps-options --install
```

Explicit `python3` on that last line, because a file arriving over HTTP has no execute
bit. It is needed exactly once: `--install` copies the script to `~/.local/bin` with mode
0755, so every later run is just `xkb-caps-options`, which is what the `#!/usr/bin/env
python3` shebang is there for.

`--install` runs steps 1, 4, 5 and 7 of that list. Fetching is gone, and so are the two
steps that belong to the xkb config: writing it (see below) and verifying it, which
cannot run before it has been written. When everything is already in place it is a no-op
that re-checks, so it doubles as the update and repair path. Running the tool without
arguments goes straight to the menu, and `--uninstall` undoes everything from the same
file.

Undoing is surgical rather than a restore from backup: by the time someone uninstalls,
the backups can be months old and the files may have been edited since, so putting one
back would itself be data loss. `--uninstall` removes exactly the lines the tool added,
deletes a file only when nothing but those lines was left in it, and says so plainly when
it finds a shape it did not write.

### Which is better for the user

| | Shape A: install script | Shape B: self-installing tool |
|---|---|---|
| what the user can inspect before running | the bootstrap only; the actual tool arrives afterwards | the entire product, in one file |
| network requests | 2–5 (installer plus payload) | 1 |
| half-installed state possible | yes, if a payload fetch fails midway | no, the file is either there or not |
| where the merge/backup/verify logic lives | in `install.sh`, duplicated in an uninstaller | once, in the tool |
| updating | re-fetch and re-run the installer | `xkb-caps-options --install` |
| uninstalling offline | needs the installer again | already on disk |
| xkb config files exist in the repo… | once, under `config/xkb/` | twice: as files and as constants |

**Shape B is the better deal for the user**, and the trust argument is the one that
settles it. The whole objection to `curl … | bash` is that you are asked to trust code you
have not seen; Shape A does not actually answer it, because reading `install.sh` tells you
nothing about the tool it will fetch a moment later. Shape B hands over exactly one file,
which is both the thing you inspect and the thing you keep. Everything else follows from
there: one fetch instead of several, no half-installed state, and uninstall that still
works when the repo has moved or you are offline.

### The xkb config is installed on demand

The tool is useful without the xkb config. Every choice it offers except CapsLock-as-Shift
is a stock xkb option, and the value it adds — one exclusive choice per key, across option
groups that no existing UI keeps consistent — needs nothing installed at all. So
`--install` places the script and stops there, and the config under
`$XDG_CONFIG_HOME/xkb/` is written the first time the user actually selects
CapsLock-as-Shift.

This is worth doing for its own sake, not just to save a step. The merge into an existing
`rules/evdev` and `rules/evdev.xml` is the only part of the installation that can damage
something the user already had, and on demand it runs only for the people who need it,
at a moment where the tool can say what it is about to write and why. Everyone else never
has files appear under `~/.config/xkb` — and `--uninstall` is symmetric: it removes what
was actually installed.

### The config is embedded, not fetched

The three files total about 3 KB, so the script carries them as string constants rather
than downloading them when the moment comes.

Fetching on demand would re-open the hole that this whole shape exists to close: the file
the user inspected would quietly pull content they did not. An embedded SHA-256 per file,
checked after download, would close it again — but then the script carries the hashes
*and* a network dependency, where embedding carries neither. On demand sharpens the point:
the fetch would land while the user sits in the menu having just made their choice, which
is the worst moment for a captive portal to turn a keyboard setting into an error message.
Embedded, "on demand" is instant and works offline.

The price is that the config then exists twice, as files under `config/xkb/` and as
constants in the script. The files stay the source of truth and the constants are
generated from them, which makes the duplication mechanical instead of something anyone
has to maintain by hand:

- `--regen-embedded` rewrites the block between two markers in the script's own source
  from `config/xkb/`, and `--check-embedded` fails if the two have drifted, which is what
  CI runs. Both are hidden from `--help`: they are development commands, and the file a
  user downloads has no `config/xkb/` next to it for them to work on;
- when the tool finds a `config/xkb/` next to itself — i.e. when it runs from a git
  checkout — it uses those files rather than its constants, so development never goes
  through the copy.

Deleting `config/xkb/` and keeping only the constants would remove the duplication
outright, but the files earn their place several times over: they are what CI compiles,
what someone who does not want the tool can copy by hand, what an X11 user would install
system-wide, and what a patch to xkeyboard-config would consist of. xkb syntax nested in
a Python string literal is none of those, and it cannot be reviewed in a diff.

### A note on piping

If a pipe is wanted anyway, `curl -fsSL … | python3 - --install` works, with one wrinkle:
a script read from stdin has no `__file__` to copy from, so `--install` would have to
write itself out from its own embedded source or re-download. That is solvable, but it
gives up the inspection step that is the main reason to prefer this shape, so the README
should lead with download-then-run.

Distribution beyond this — .deb, .rpm, AUR — is a later concern, and Shape B suits it
better too: a package installs the single file and the config directly, and `--install`
simply never runs. Flatpak is a poor fit either way, since the whole job is writing into
`~/.config/xkb`.

## Dependencies

Short list, and two of the three are already on any machine that can run the tool at all.
Nothing comes from PyPI: the standard library covers everything, and the config is
embedded, so there is no download at runtime either.

| dependency | needed for | typically present | Debian/Ubuntu package |
|---|---|---|---|
| `python3` | everything | always, on Gnome | `python3` |
| `gsettings` | reading and writing the option list | always, on Gnome | `libglib2.0-bin` |
| `xkbcli` | verifying the compiled keymap | often not | `libxkbcommon-tools` |

**`python3`** is a prerequisite, not a dependency the tool can resolve — see `scope.md`.
The floor is **3.10**, what Ubuntu 22.04 LTS ships and below anything newer still in
support. It is checked in a prelude before the other imports, and the whole file is
written in syntax an older interpreter can still parse, because a `SyntaxError` happens
at parse time and would beat any check to it.

**`gsettings`** comes with glib. If it is genuinely missing, the machine is not running
Gnome, which the tool has already detected by then, so this is a check that should never
fire in practice.

**`xkbcli`** is the only one likely to be missing, because it lives in a tools package
that a desktop install does not pull in — libxkbcommon itself is always there, since the
compositor links against it. It is needed only for the verification step before an option
is set. So: offer to install it, and if the user declines, carry on and say plainly that
the setting is being written unverified. Refusing to work without it would be out of
proportion to what it does.

On other distributions the split differs — `xkbcli` may sit in the main libxkbcommon
package rather than a separate one — so the package name has to be looked up per
distribution family rather than assumed to be `libxkbcommon-tools` everywhere.

A graphical UI would add PyGObject (`python3-gi`) and GTK, but that is a later iteration
and does not belong in the first install.

## The core data model

Model the domain as **slots**, not as individual options. A slot is one exclusive choice
together with the full set of option ids that compete for it — for `<CAPS>` and `<LSGT>`
those sets are listed in `scope.md`, and they span four different option groups:

```
slot "caps"            → every option that claims <CAPS>
slot "lsgt"            → every option that claims <LSGT>
slot "both-shift-caps" → all six shift:*_both_capslock spellings
```

A slot carries two lists: everything it *claims*, which is what gets cleared when the
slot is written, and the shorter list of *choices* it offers. The two differ on purpose —
an option that is claimed but not offered is one this project does not recommend and must
still never drop, which is what produces the "keep `<current>`" entry from `scope.md`.

The whole algorithm is then: read the current option list, bucket each entry into a slot
or into "not ours", show one choice per slot with the current value preselected, and write
back `untouched_options + chosen_options`.

That single rule delivers conflict-freedom, preservation of unrelated options, and the
"show what is set now" behaviour all at once, in about thirty lines. Keep the slot tables
as literal data at the top of the file, so they are easy to audit and easy to extend when
xkeyboard-config adds an option.

The non-interactive interface is the same model spelled out: `--set caps=shift,lsgt=altgr`
takes `slot=value` pairs where the values are the choice names (`default`, `shift`,
`altgr`, `none`, `yes`, `no`) plus `keep`. A slot nobody mentions keeps what it has, which
is what makes the command idempotent and safe in a dotfile.

Descriptions are not embedded. The tool reads them out of the xkb registry the desktop
itself uses — `$XDG_CONFIG_HOME/xkb/rules/evdev.xml`, then `/etc/xkb`, then
`/usr/share/X11/xkb` — so every option prints with its real one-line description,
including the ones this project has never heard of, and a table of ~120 strings does not
have to be maintained against xkeyboard-config releases.

## Verification and testing

A Github Actions job on `ubuntu-24.04` that installs `libxkbcommon-tools` and
`x11-xkb-utils`, points `XDG_CONFIG_HOME` at the repo's `config/`, and asserts on
compiled keymaps. The assertions live in `tests/check-keymaps.sh` and
`tests/test_xkb_caps_options.py` rather than in the workflow file, so they can be run
by hand on the machine where something is actually broken. Together they catch the class
of bug that otherwise only surfaces as "my keyboard is weird now":

- `xkbcli compile-keymap --layout us --options caps:shift_modifier` gives
  `symbols[Group1]= [ Shift_L, Caps_Lock ]` for `<CAPS>`;
- `xkbcli list` contains `caps:shift_modifier`, so the registry merge still works;
- `xkbcli compile-keymap --options caps:escape` still gives `Escape`, so no stock caps
  option has been shadowed;
- the same two checks through `xkbcomp -I`, which is stricter than libxkbcommon about
  include-path shadowing and will fail where libxkbcommon quietly recovers;
- assertions over a set of starting option lists, above all "unrelated options survive"
  and "an existing caps option is not silently dropped". These drive the real script with
  a fake `gsettings` on `PATH` and `XDG_CONFIG_HOME` in a temporary directory, so the
  parsing, the merge and the write are all exercised without a desktop session;
- the merges into a `rules/evdev` and `rules/evdev.xml` the user already had, which is the
  only part of this tool that can destroy something: comments and DOCTYPE survive, the
  result is still valid XML, running twice changes nothing, and `--uninstall` returns the
  file to exactly what it was;
- that every option id in the slot tables is a real one, by checking it against the
  installed `rules/evdev` — the tables are hand-maintained, and a typo in them would
  silently stop clearing a conflicting option;
- and the check that the embedded config matches `config/xkb/`.
