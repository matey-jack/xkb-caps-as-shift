# Technical specifications

The decisions on language and target environment are in `scope.md`. This file covers how
the tool is installed, how it models the options, and how it is tested.

## Installation and distribution

The tool ships as a single Python file. What is still open is the *shape* of the
installation: a separate installer script that fetches and places everything, or one
self-installing file that does it itself. The duties either shape has to fulfil — honour
`XDG_CONFIG_HOME`, merge instead of overwrite, back up, verify, support uninstalling —
are listed in `scope.md`; the question here is only which shape carries them better.

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

`--install` runs the same seven steps as above, except that step 2 disappears: the xkb
files are string constants inside the script, and step 4 is the script copying itself to
`~/.local/bin`. When the installation is already in place, `--install` is a no-op that
just re-verifies, so it doubles as the update and repair path. Running the tool without
arguments goes straight to the menu, and `--uninstall` undoes everything from the same
file.

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

The cost is the one entry in the last row: the xkb config would exist both as files under
`config/xkb/` and as string constants in the script, and those two can drift apart. Two
ways to keep them honest, and doing both is cheap:

- when the script finds a `config/xkb/` next to itself — i.e. when it runs from a git
  checkout — it uses those files rather than its constants, so development never goes
  through the copy;
- CI asserts that the constants and the files are identical, which is a three-line test.

If a pipe is wanted anyway, `curl -fsSL … | python3 - --install` works, with one wrinkle:
a script read from stdin has no `__file__` to copy from, so `--install` would have to
write itself out from its own embedded source or re-download. That is solvable, but it
gives up the inspection step that is the main reason to prefer this shape, so the README
should lead with download-then-run.

Distribution beyond this — .deb, .rpm, AUR — is a later concern, and Shape B suits it
better too: a package installs the single file and the config directly, and `--install`
simply never runs. Flatpak is a poor fit either way, since the whole job is writing into
`~/.config/xkb`.

## The core data model

Model the domain as **slots**, not as individual options. A slot is one exclusive choice
together with the full set of option ids that compete for it — for `<CAPS>` and `<LSGT>`
those sets are listed in `scope.md`, and they span four different option groups:

```
slot "caps"            → every option that claims <CAPS>
slot "lsgt"            → every option that claims <LSGT>
slot "both_shift_caps" → shift:both_capslock | shift:both_capslock_cancel | unset
```

The whole algorithm is then: read the current option list, bucket each entry into a slot
or into "not ours", show one choice per slot with the current value preselected, and write
back `untouched_options + chosen_options`.

That single rule delivers conflict-freedom, preservation of unrelated options, and the
"show what is set now" behaviour all at once, in about thirty lines. Keep the slot tables
as literal data at the top of the file, so they are easy to audit and easy to extend when
xkeyboard-config adds an option.

## Verification and testing

A Github Actions job on `ubuntu-24.04` that installs `libxkbcommon-tools`, points
`XDG_CONFIG_HOME` at the repo's `config/`, and asserts on compiled keymaps. It is a dozen
lines and it catches the class of bug that otherwise only surfaces as "my keyboard is
weird now":

- `xkbcli compile-keymap --layout us --options caps:shift_modifier` gives
  `symbols[Group1]= [ Shift_L, Caps_Lock ]` for `<CAPS>`;
- `xkbcli list` contains `caps:shift_modifier`, so the registry merge still works;
- `xkbcli compile-keymap --options caps:escape` still gives `Escape`, so no stock caps
  option has been shadowed;
- the same two checks through `xkbcomp -I`, which is stricter than libxkbcommon about
  include-path shadowing and will fail where libxkbcommon quietly recovers;
- once the tool exists: `--dry-run` assertions over a set of starting option lists, above
  all "unrelated options survive" and "an existing caps option is not silently dropped";
- and the check that the embedded config matches `config/xkb/`.
