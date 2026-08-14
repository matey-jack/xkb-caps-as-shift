# Implementation notes

## The core data model

Model the domain as **slots**, not as individual options. A slot is one exclusive choice
together with the full set of option ids that compete for it — for `<CAPS>` and `<LSGT>`
those sets are listed in `scope.md`, and they span option groups the UI keeps apart:

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
`x11-xkb-utils` and asserts on compiled keymaps. The assertions live in
`tests/check-keymaps.sh`, which points `XDG_CONFIG_HOME` at the repo's `config/`, and
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
