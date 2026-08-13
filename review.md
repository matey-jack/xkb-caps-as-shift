# Project review: scope, configuration, and implementation options

Review of `scope.md`, `config/xkb/**` and the repository as a whole.

Everything marked **verified** below was checked by compiling real keymaps in a container
that happens to carry exactly the target versions: `xkb-data 2.41-2ubuntu1.1` and
`libxkbcommon 1.6.0` — i.e. Ubuntu 24.04's own packages. Tools used: `xkbcli
compile-keymap` / `xkbcli list` (the libxkbcommon path, which is what a Wayland session
uses) and `xkbcomp` (the X11 path).

---

## 1. `scope.md` — inconsistencies, errors, and gaps

### 1.1 Factual errors

**Wrong option names.** None of the three option ids listed at the bottom of `scope.md`
exist. xkeyboard-config uses `lv`, not `lvl`, and every one of these options carries a
`_switch` suffix:

| `scope.md` says | actual id (verified in `rules/evdev`) | meaning |
|---|---|---|
| `lvl3:caps` | `lv3:caps_switch` | CapsLock chooses 3rd level (AltGr) |
| `lvl3:lsgt` | `lv3:lsgt_switch` | LSGT chooses 3rd level (AltGr) |
| `lvl2:lsgt` | `lv2:lsgt_switch` | LSGT is a plain Shift |
| `shift:both_capslock` | `shift:both_capslock` | correct |
| `caps:none` | `caps:none` | correct |

This matters more than a typo: these strings are the tool's entire data model, and a
wrong id fails silently — `gsettings` accepts any string, and the keymap simply compiles
without it.

**"LSGT as Shift" is not a missing feature.** `lv2:lsgt_switch` already does exactly
that — verified, it compiles to `key <LSGT> { [ Shift_L ], type = "ONE_LEVEL" }` plus
`modifier_map Shift { <LSGT> }`. The scope reads as if it might be missing. It is worth
stating explicitly that **the only mapping stock xkb lacks is CapsLock-as-momentary-Shift**;
everything else the tool offers already exists and the tool's value is purely
*consistent, conflict-free selection*. That framing sharpens the whole project.

**Claim "not offered in stock xkb at all" — confirmed.** The stock `caps` group has
exactly 16 options (verified via `xkbcli list`), none of which is a momentary Shift;
`caps:shift` and `caps:shift_nocancel` are *locking* variants (they are `types` rules,
`+caps(shift)`), so the name `caps:shift_modifier` is the right choice and free of
collisions (verified: no `shift_modifier` anywhere in stock `rules/evdev`).

**The screenshot is mislabelled.** The commit message says "OOTB xkb options as of Ubuntu
24-04", but the image shows *"Make Caps Lock an additional Shift; any two Shift keys
toggle Caps Lock"* present **and selected** — that is this project's own option, so the
screenshot is post-install, not stock. If it is meant to document the problem (options
scattered across groups), fine — but say so in the README, or the reader will conclude
the option already exists upstream. Also: the filename contains spaces, which is awkward
for anything scripted; consider `docs/gnome-tweaks-caps-and-3rd-level.png`.

### 1.2 Missing information — the ones that will actually bite

1. **Target environment is never stated, and it decides the whole design.**
   `~/.config/xkb/` is a *libxkbcommon* feature. A Wayland session (mutter, KWin, sway)
   reads it. The X server compiles its keymap with its own `xkbcomp`, whose include path
   is `/usr/share/X11/xkb` only — verified: `xkbcomp` finds nothing in the home directory
   unless you pass `-I`. So on GNOME **X11**, everything in `config/xkb/` is inert, and
   the tool would show a "CapsLock as Shift" choice that silently does nothing.
   The scope must decide: Wayland-only v1 (detect `XDG_SESSION_TYPE` and say so plainly),
   or a root install into `/usr/share/X11/xkb` for X11 users. See D1.

2. **How the selection is persisted and applied is only mentioned in passing**
   (one parenthesis about `gsettings` inside the installer bullet). This is the single
   biggest technical decision in the project and deserves its own section: GNOME's
   `org.gnome.desktop.input-sources xkb-options` vs KDE's `kxkbrc` vs `localectl` vs
   `setxkbmap`. See D1.

3. **Preserving unrelated options is not mentioned at all.** `xkb-options` routinely
   already holds `grp:*` (layout switching), `compose:*`, `terminate:*`, `numpad:*`,
   `nbsp:*`. The tool must read-modify-write and touch *only* the keys it manages. A
   blind `gsettings set` would silently destroy a user's layout-switch shortcut. This
   belongs in the scope as a hard requirement.

4. **Which `shift:both_capslock` variant?** There are six:
   `shift:both_capslock`, `both_capslock_cancel`, and the `lshift_`/`rshift_` variants
   of each. The scope says "one yes/no choice" without saying what "yes" writes.
   (`both_capslock` = two Shifts enable Caps Lock; `_cancel` = additionally, one Shift
   alone disables it again. The `_cancel` variant pairs better with this project's
   ergonomics, because you will hit Shift far more often than you want Caps Lock.)

5. **No behaviour contract for `caps:shift_modifier`.** Users need to know, and the
   README needs to state (all verified by compiling):
   - Tap/hold CapsLock → momentary Shift.
   - Shift+CapsLock → toggles the real Caps Lock.
   - **While Caps Lock is on, pressing CapsLock turns it off** rather than acting as
     Shift (the key is at level 2 whenever `Lock` is active). Sensible, but surprising
     if undocumented.
   - The Caps LED still works, because `<CAPS>` stays bound to the `Lock` modifier.

6. **Install/uninstall/upgrade mechanics.** The scope names an installer but not:
   what happens when `~/.config/xkb/rules/evdev` **already exists** (many people already
   have a custom layout there — clobbering it is data loss; the installer must merge or
   at minimum back up and refuse), that `XDG_CONFIG_HOME` must be honoured rather than
   hardcoding `~/.config`, that there must be an uninstall path, and that re-running must
   be idempotent.

7. **Reload semantics.** Changing `xkb-options` re-triggers the keymap compile, so the
   mapping applies immediately — but `gnome-control-center` / GNOME Tweaks cache the
   option *registry*, so a freshly installed `evdev.xml` shows up only after those apps
   restart (worst case, after logout). Without this in the docs, the first bug report
   will be "it doesn't appear in Tweaks".

8. **No non-interactive interface.** `xkb-caps-options --get` / `--set caps=shift lsgt=altgr`
   / `--dry-run` costs almost nothing, makes the tool scriptable and dotfile-friendly,
   and — importantly — makes it testable in CI without driving a UI.

9. **Repo hygiene not in scope:** no LICENSE (blocking if you ever upstream), no README
   (already listed as a to-do), no CI, no tests. A CI job that compiles the keymap is
   cheap and would have caught the issues in §2 — see D6.

10. **Naming drift.** Repo `xkb-caps-as-shift`, script `xkb-caps-options`, option
    `caps:shift_modifier`. That is fine, but pick one name for the *product* and use it
    consistently in the README and installer output.

11. **No non-goals section.** Worth adding: not a general keyboard remapper, not a
    replacement for GNOME Settings, no per-layout options, no Xorg-wide/system install
    (if that is the decision), no support for non-libxkbcommon setups.

### 1.3 Scope changes that would serve users better

- **Do not narrow the CapsLock choice to four entries.** The scope offers
  *disabled / Shift / AltGr / CapsLock*. But the caps group has 17 members now, and
  **Esc and Ctrl are by far the most common CapsLock remaps** — a user who already has
  `caps:escape` set would open this tool, see four options none of which is theirs, pick
  one, and lose their setting. Minimum requirement: show the currently-set option even
  if it is outside the curated list, and never discard it silently. Better: list the
  whole exclusive set, with the four ergonomic recommendations marked as such. The tool's
  selling point is *consistency*, and a curated subset that quietly drops settings is the
  opposite.

- **Widen the conflict model beyond `caps:` and `lv3:`.** Verified, these stock options
  also claim `<CAPS>` and will silently override `caps:shift_modifier`:
  `grp:caps_toggle`, `grp:caps_switch`, `grp:caps_select`, `grp:shift_caps_toggle`,
  `grp:alt_caps_toggle`, plus `lv3:caps_switch_latch`. For `<LSGT>`:
  `lv2:lsgt_switch`, `lv3:lsgt_switch`, `lv3:lsgt_switch_latch`, `lv5:lsgt_switch`,
  `lv5:lsgt_switch_lock`, `lv5:lsgt_switch_lock_cancel`.
  The scope's "one exclusive choice per key" is the right idea, but the exclusion set is
  *every option that touches that keycode*, not just two groups.

  Concretely verified: with both `caps:shift_modifier` and `lv3:caps_switch` set,
  `<CAPS>` compiles to `ISO_Level3_Shift` — **`lv3` wins, regardless of the order in
  `xkb-options`**, because rule-file order decides, not user order. Exactly the silent
  failure the tool exists to prevent, and a good example for the README.

- **State the "explain what changed" requirement.** Print the resulting option list and
  a one-line description of each. It makes the tool self-documenting and makes bug
  reports usable.

- **Add "upstream it" as an explicit goal.** `caps:shift_modifier` is a five-line patch
  to `xkeyboard-config` (`symbols/capslock` + `rules/*.part` + `rules/base.xml.in`), and
  the implementation is already an exact copy of an idiom upstream uses elsewhere (§2).
  If it lands, the entire install mechanism becomes unnecessary for future distro
  releases and the tool shrinks to just the selector. That is the highest-leverage item
  in this project and it is currently not in the scope at all.

---

## 2. Configuration review

**Verdict: the mapping itself is correct and idiomatic — verified working end to end.**
Two issues worth fixing (one user-visible, one latent), plus minor notes. Notably, one of
the two is a comment that states the opposite of what actually happens.

### 2.1 What is right

- `symbols/capslock` uses precisely the upstream idiom. Compare with stock
  `symbols/shift`:
  ```
  xkb_symbols "lshift_both_capslock" {
      key <LFSH> {[  Shift_L,  Caps_Lock  ], type[group1]="ALPHABETIC" };
  };
  ```
  That is character-for-character the same construct as `shift_modifier`, applied to
  `<LFSH>` instead of `<CAPS>`. So the "Shift+Caps = real Caps Lock" behaviour is not a
  clever trick, it is the mechanism `shift:both_capslock` itself is built on. Good.
- Verified with `XDG_CONFIG_HOME` pointing at the repo's `config/`:
  `xkbcli compile-keymap --options caps:shift_modifier` yields
  `key <CAPS> { type = "ALPHABETIC", symbols[Group1] = [ Shift_L, Caps_Lock ] }` with no
  warnings, and `xkbcli list` shows the option merged into the stock `caps` group.
  The rules file, the symbols file and the registry XML all work together as intended.
- The `! include %S/evdev` at the end of `rules/evdev`, and the comment explaining it,
  are correct — the rules file is *not* merged, so re-including the system rules is
  mandatory.
- `evdev.xml`'s comments are accurate: libxkbregistry does merge, `allowMultipleSelection="false"`
  matches the stock `caps` group, and the count is right — stock has 16 caps options
  (verified), so this is the 17th. The reasoning for not calling it `caps:shift` is
  correct too.
- No DTD warning despite `xkb.dtd` not existing next to the user's `evdev.xml`
  (verified: `xkbcli list` runs clean).

### 2.2 Issue 1 — the option description promises behaviour it does not deliver

`evdev.xml` says:

> Make Caps Lock an additional Shift; **any two Shift keys toggle Caps Lock**

Verified: with only `caps:shift_modifier` set, `<LFSH>` and `<RTSH>` are untouched, so
LeftShift+RightShift does nothing. What actually works is CapsLock + *either* Shift.
"Any two Shift keys" only becomes true if `shift:both_capslock` is also set — which is
precisely the separate yes/no choice the scope describes, so the description is
overpromising by exactly one option.

This is user-visible: it is the string GNOME shows in the UI (it is the label in the
screenshot). Two ways out:

- **(a) Fix the wording** — mirror upstream's phrasing for the analogous
  `caps:escape_shifted_capslock` ("Make Caps Lock an additional Esc, but Shift + Caps
  Lock is the regular Caps Lock"):
  > `Make Caps Lock an additional Shift; Shift + Caps Lock is the regular Caps Lock`
- **(b) Make the description true** by adding `include "shift(both_capslock)"` to the
  symbols section.

Recommend **(a)**. Option (b) would make one entry in the `caps` group silently rewrite
the Shift keys, which fights the tool's own separate yes/no choice for that behaviour and
would surprise anyone selecting it from GNOME's UI.

### 2.3 Issue 2 — the file name shadows the stock `symbols/capslock`, and the comment says the opposite

The header comment in `config/xkb/symbols/capslock` says the name was chosen so ours
"slots in beside" the stock options. It does not — symbol files are found by *path
search*, not merged, so a user file named `capslock` is found first and the stock file
holding the other 13 sections may never be read.

Verified, with the user directory first in the include path:

```
$ xkbcomp -I<userdir> -I/usr/share/X11/xkb  ... "pc+us+capslock(escape)"
Error: No Symbols named "escape" in the include file "capslock"
       Exiting
```

Two mitigating facts, which is why this has not been noticed:

- libxkbcommon 1.6 **falls through to the next include path** when the named section is
  not in the first matching file, so on Wayland `caps:escape` still resolves correctly
  today (verified: it compiles to `[ Escape ]`). That is an implementation detail, not a
  documented guarantee.
- The X server's `xkbcomp` — the one that *does* hard-fail — never looks in
  `~/.config/xkb` in the first place, so it only bites people who pass `-I` manually
  (a widely circulated X11 workaround) or who install these files system-wide (which is
  exactly the X11 install path discussed in D1).

So: works today, breaks tomorrow, and breaks specifically in the scenario the project is
likely to add next. The fix is free — rename the file and update the one rule line:

```
config/xkb/symbols/capslock  →  config/xkb/symbols/capslock_shift
caps:shift_modifier = +capslock(shift_modifier)
                    → +capslock_shift(shift_modifier)
```

Verified: after the rename, `capslock_shift(shift_modifier)` and `capslock(escape)`
compile together in one keymap with no errors, under `xkbcomp` as well. The comment
should then be corrected to say the opposite of what it says now: a unique file name is
required *because* user symbol files shadow rather than merge — unlike `rules/evdev.xml`,
which genuinely does merge.

### 2.4 Minor notes

- **`hidden` flag.** Every stock section in `symbols/capslock` is declared
  `hidden partial modifier_keys`; ours is `partial modifier_keys`. `hidden` keeps the
  section out of the map lists that tools enumerate. Harmless either way, but matching
  upstream costs one word.
- **`modifier_map Shift { <CAPS> }` is redundant.** `symbols/pc` already contains
  `modifier_map Shift { Shift_L, Shift_R }`, which binds by *keysym*, so `<CAPS>` gets
  the Shift modifier from its level-1 `Shift_L` regardless. Verified in the compiled
  keymap. Keeping it as explicit documentation is defensible — upstream's
  `capslock(super)`/`(hyper)` do the same — but the comment could say so.
- **`<CAPS>` also stays in `modifier_map Lock`** (verified in the compiled map), because
  `symbols/pc` binds the `Caps_Lock` keysym to `Lock` and our level 2 still carries that
  keysym. This is not a bug — stock `caps:escape_shifted_capslock` has exactly the same
  property — and it is what keeps the Caps LED working. Worth a line in the comment so
  it is not "fixed" later by someone who thinks it is a leak.
- **Ordering consequence worth documenting in `rules/evdev`:** because our rule line sits
  *before* `! include %S/evdev`, our symbols are applied before all stock ones, so any
  stock option touching `<CAPS>` overrides ours (verified with `lv3:caps_switch`). Moving
  the include to the top would invert that. Neither is a substitute for the tool
  enforcing exclusivity, but the current order is the safer default: it fails toward
  stock behaviour rather than overriding what the user explicitly picked elsewhere.
- **Stray apostrophe** in `rules/evdev`: ``the files name in the ../symbols folder'``.
- **Where do these files install to?** The repo layout `config/xkb/...` mirrors
  `$XDG_CONFIG_HOME/xkb/...`, but nothing says so. One line in the README (or a
  `config/README`) removes the guesswork for anyone installing manually.

---

## 3. Implementing the missing functionality — decisions and options

The unbuilt part is: a selector tool, an installer, and a README. Six decisions actually
matter; the rest follows from them.

Criteria used throughout, in priority order:
**(C1) reach** — works on an unmodified target machine with nothing extra installed;
**(C2) inspectability** — a `curl | bash` audience must be able to read what runs;
**(C3) correctness/safety** — never destroys existing settings, always reversible;
**(C4) maintenance cost** for a one-person project;
**(C5) UX**.

### D1 — Target platform and settings backend

| Option | Reach | Notes |
|---|---|---|
| **A. GNOME + Wayland only**, via `gsettings org.gnome.desktop.input-sources xkb-options` | Ubuntu 24.04 default session; Fedora Workstation; most GNOME distros | `~/.config/xkb` works (verified); `gsettings` CLI always present with GNOME; per-user, no root |
| B. + GNOME on X11 | adds X11 sessions | `gsettings` works, but `~/.config/xkb` does **not** — needs the files in `/usr/share/X11/xkb` (root, and fights package updates) or a login-time `xkbcomp $DISPLAY` hack |
| C. + KDE | adds KDE | different store (`kxkbrc` `[Layout] Options` + a D-Bus reload); Wayland KWin reads `~/.config/xkb` fine |
| D. `localectl set-x11-keymap` | system-wide | root; ignored by GNOME/KDE session settings; wrong layer for a per-user preference |
| E. `setxkbmap -option` | X11 only | not persistent; useful only as a "try it now" preview |

**Recommendation: A for v1**, with a *backend* abstraction (one function to read the
option list, one to write it) so KDE is a later addition rather than a rewrite. Detect
`XDG_SESSION_TYPE=x11` and, rather than failing, tell the user precisely why the custom
option cannot load and offer the root install as an opt-in second step. The one thing to
avoid is silently offering a choice that does nothing — which is the current state on X11.

### D2 — Language and UI toolkit

| Option | C1 reach | C2 inspectable | Notes |
|---|---|---|---|
| **Python 3, stdlib only, text menu** | Python 3 is present on every GNOME distro (GNOME's own tooling depends on it) | yes, single readable file | `curses` is stdlib if a fuller TUI is ever wanted; trivially unit-testable |
| bash + `whiptail` | `whiptail` (newt) is on Debian/Ubuntu, **not** default on Fedora/Arch | yes | list/state juggling in bash is where the bugs will live |
| bash + `dialog` | not installed by default anywhere | yes | worst reach |
| bash/Python + `zenity` (GUI) | present on Ubuntu/Fedora GNOME | yes | one dialog per question; clunky for 3 linked choices + conflict explanations |
| Python + PyGObject/GTK3 | `python3-gi` ships on Ubuntu/Fedora GNOME | yes | real GUI, needs the `.desktop` file; GTK4/libadwaita availability varies |
| compiled (Rust/Go/C) | needs a binary download | **no** | rejected by the scope's own "inspectable script" criterion |

**Recommendation: a single stdlib-only Python 3 file** implementing the logic plus a
plain interactive menu *and* the non-interactive CLI (§1.2 item 8). Talk to `gsettings`
via `subprocess` rather than importing `gi`, so the script has literally no import beyond
the standard library — that keeps the installer's dependency check down to "is there a
`python3` and a `gsettings`", both of which are answerable in two lines.

Add the GTK UI later, as an optional second entry point in the same file
(`try: import gi` → GUI, else text menu). Then the `.desktop` file becomes meaningful.
Do not start with the GUI: the text mode is what makes the tool testable in CI and usable
over SSH, and the scope already says the GUI need not be pretty.

### D3 — Distribution and installer

The `curl | bash` installer should:

1. install the script to **`~/.local/bin`**, not `~/bin` as the scope says —
   `~/.local/bin` is the XDG location and is already on `PATH` on Ubuntu 22.04+ and
   Fedora, whereas `~/bin` is only added by Debian/Ubuntu's `.profile` *if it exists at
   login*, i.e. it needs a logout to work. (Fall back to `~/bin` if it exists and is on
   `PATH`.)
2. install the xkb files under `${XDG_CONFIG_HOME:-$HOME/.config}/xkb/`, **merging**:
   if `rules/evdev` exists, append the option line only when absent and make sure exactly
   one `! include %S/evdev` remains last; if `rules/evdev.xml` exists, insert the
   `<option>` into the existing `caps` group. Back up anything it modifies. If it cannot
   merge confidently, stop and say what to do by hand — never overwrite.
3. self-verify: if `xkbcli` is available, run
   `xkbcli compile-keymap --options caps:shift_modifier | grep '<CAPS>'` and confirm
   `Shift_L, Caps_Lock`. That is a genuine end-to-end check, and it is the same command
   CI should run.
4. print what to do next (restart GNOME Settings/Tweaks before the entry appears).
5. support `--uninstall` and be idempotent.

A neat simplification: make the installer a thin fetch-and-run wrapper around
`xkb-caps-options --install`, so install/uninstall/merge logic lives in the same
inspectable Python file rather than being duplicated in shell.

Packaging (deb/rpm/AUR) is a later concern; Flatpak is a poor fit since the whole point
is writing to `~/.config/xkb`.

### D4 — The core data model

Model the domain as **slots**, not as individual options:

```
slot "caps"  → exclusive over: all caps:*  ∪ {lv3:caps_switch, lv3:caps_switch_latch,
                                              grp:caps_toggle, grp:caps_switch,
                                              grp:caps_select, grp:shift_caps_toggle,
                                              grp:alt_caps_toggle}
slot "lsgt"  → exclusive over: {lv2:lsgt_switch, lv3:lsgt_switch, lv3:lsgt_switch_latch,
                                lv5:lsgt_switch, lv5:lsgt_switch_lock,
                                lv5:lsgt_switch_lock_cancel}
slot "both_shift_caps" → {shift:both_capslock | shift:both_capslock_cancel | unset}
```

Read the current `xkb-options`, bucket each entry into a slot or into "not ours",
present one choice per slot with the current value preselected, then write back
`untouched_options + chosen_options`. That single rule gives you conflict-freedom,
preservation of unrelated options (§1.2 item 3), and the "show what's currently set"
behaviour (§1.3), and it is about thirty lines of code. Keep the tables as literal data
at the top of the file so they are easy to audit and extend.

### D5 — File naming

Covered in §2.3: rename to a unique file name. Decide it now, before anyone has the
current layout installed, because changing it later means the installer has to clean up
the old `symbols/capslock`.

Related, and worth a deliberate decision: **keep the `caps:` prefix** for the option id
even though libxkbcommon's docs suggest a `custom:` prefix for user-defined options.
`caps:` is what puts the entry inside GNOME's exclusive `caps` radio group — the entire
UX benefit — and `custom:` would forfeit it. The cost is a small collision risk if
upstream ever adds the same id, which is acceptable, and which upstreaming (D7) would
resolve outright.

### D6 — Verification and CI

A GitHub Actions job on `ubuntu-24.04` that does
`apt-get install -y libxkbcommon-tools xkb-data`, points `XDG_CONFIG_HOME` at the repo's
`config/`, and asserts on compiled keymaps is cheap and would have caught both issues in
§2:

- `xkbcli compile-keymap --layout us --options caps:shift_modifier` contains
  `symbols[Group1]= [ Shift_L, Caps_Lock ]` for `<CAPS>`;
- `xkbcli list` contains `caps:shift_modifier` (registry merge still works);
- `xkbcli compile-keymap --options caps:escape` still yields `Escape` (no shadowing
  regression);
- the same two via `xkbcomp -I` — this is the check that fails today and passes after
  the rename;
- once the tool exists: `--dry-run` assertions over a set of starting `xkb-options`
  values, especially "unrelated options survive".

### D7 — Upstreaming

Worth doing in parallel with everything above, not after: a patch to `xkeyboard-config`
adding `caps:shift_modifier` (symbols section + `rules/*.part` + `rules/base.xml.in`).
The implementation already matches upstream's own idiom, the naming rationale is already
written down in `evdev.xml`, and the gap it fills is obvious once pointed out. If it
lands, D1's X11 problem and D3's whole install-and-merge apparatus become legacy
concerns, and this project reduces to the selector tool — which is the part with lasting
value. Requires a LICENSE on this repo (MIT or the MIT-ish terms xkeyboard-config uses).

---

## 4. Suggested order of work

1. Rename the symbols file and fix the two comments and the option description (§2.2,
   §2.3) — small, and everything else builds on it.
2. Fix the option ids in `scope.md`, add the target-environment and
   preserve-unrelated-options requirements (§1.1, §1.2).
3. CI keymap test (D6) — it is a dozen lines and locks in step 1.
4. `xkb-caps-options` with the slot model and the non-interactive CLI (D2, D4), text UI
   first.
5. Installer + README (D3), including the X11 caveat.
6. Submit upstream (D7).
