For preservation of history, here is my initial project brief.
Claude has added and changed some details as we refined the spec, but it reflects the original idea. 

Purpose of this project in short: 
 - For ergonomic reasons I recommend using the CapsLock and LSGT keys for Shift and AltGr and I do it in this order, but the reverse also works and is muscle-memory compatible with an ANSI keyboard. (LSGT is also known as  ISO key, 102nd, or Non-US Backslash.)
 - Most of the required mappings are already offered as 'options' in xkb, but they are dispersed in various option groups in Gnome Tweaks. The UI is also inconsistent: the 'caps' group ensures that only one behavior for the CapsLock key can be selected from that group, but other behaviors (such as CapsLock as AltGr) can be selected in other groups.
 - One of the very attractive options, namely CapsLock acting as a plain Shift (momentary modifier) is not offered in stock xkb at all. It is the *only* mapping this project needs that stock xkb is missing: LSGT as Shift is `lv2:lsgt_switch`, LSGT as AltGr is `lv3:lsgt_switch`, CapsLock as AltGr is `lv3:caps_switch`. Everything else this project does is about selecting existing options *consistently*.
 
How this project makes configuring the CapsLock and LSGT behavior easier:
 - adds the missing option 'caps:shift_modifier'. This is already present in `./config/xkb/`, whose layout mirrors `$XDG_CONFIG_HOME/xkb/` (usually `~/.config/xkb/`).
 - provides a small terminal UI (or graphical UI, if we can keep installation size small and ideally only deliver an inspectable script, not a compiled binary) for selecting options consistently:
   + one exclusive choice for CapsLock behavior: disabled (`caps:none`), as Shift, as AltGr, or as CapsLock (no option set, because this is the default).
   + one exclusive choice for LSGT behavior: as Shift, as AltGr, or whatever is the layout default (usually a character key).
   + one yes/no choice if other Shift keys should also act as CapsLock on their Shift layer. (This behavior is automatic for the CapsLock key when used as Shift.) It is recommended whenever CapsLock is assigned something other than its default behavior, and the menu says so — but the preselection is always the value that is actually set, never a recommendation. Preselecting a value the user does not have would break the rule that re-running is a no-op, and would make `--set` and the menu disagree about the same state.

The script is `xkb-caps-options.py` in the repo and is installed to `~/.local/bin` as `xkb-caps-options`. If it's a GUI, a .desktop file for it should also be created in the right place in the user's home dir.

### Supported environments

**Wayland only.** `~/.config/xkb/` is a libxkbcommon feature, so a Wayland compositor reads it, while an X11 session compiles its keymap with the X server's own `xkbcomp`, whose include path is `/usr/share/X11/xkb` and which never looks in the home directory. Supporting X11 would mean a system-wide install needing root, and that is out of scope. The tool should detect an X11 session and say so plainly instead of offering a choice that cannot take effect.

**Gnome only, for now.** Gnome keeps the option list in gsettings, under `org.gnome.desktop.input-sources xkb-options`. KDE keeps its own list in `kxkbrc` and may be added later, so reading and writing the option list should sit behind a small interface rather than being spread through the code.

**Python 3 has to be there already.** It is a prerequisite rather than something the tool can install, since installing is itself the tool's job and it is written in Python. Every Gnome system has it. The remaining dependencies are listed in `tech-specs.md`.

### Requirements the UI has to meet

 - **Never lose settings it does not manage.** The GNOME key `org.gnome.desktop.input-sources xkb-options` (and its equivalent elsewhere) routinely already holds entries this project has no opinion about: `grp:*` for layout switching, `compose:*`, `terminate:*`, `nbsp:*`, `numpad:*`. The tool must read the current list, replace only the entries belonging to the choices above, and write the rest back untouched.
 - **Never silently discard a CapsLock behavior the user already picked.** Esc and Ctrl are by far the most popular CapsLock remappings, and neither is in the four-way choice above. If the current setting is outside the offered list, show it as the selected value rather than dropping it — otherwise the tool damages exactly the users it is meant to help. Decided: the short list plus a "keep `<current>`" entry, labelled with that option's own description from the xkb registry. Offering all ~30 competing behaviors would turn the menu into a worse copy of Gnome Tweaks, which is a non-goal below.
 - **Show what is set now, and what changed.** Print the resulting option list with a one-line description each. It makes the tool self-documenting and makes bug reports usable.
 - **Be idempotent and reversible.** Re-running must be a no-op; there must be a way back to the default.
 - **Offer a non-interactive mode** (`--get`, `--set`, `--dry-run`) next to the menu. It costs almost nothing, makes the tool usable from dotfiles, and is what makes it testable without driving a UI.

### The conflicts the UI has to enforce

The exclusive choice per key is not just "the caps group plus one AltGr option" — it is *every* option that claims that keycode, across four different groups:

 - `<CAPS>`: all 18 `caps:*` options (17 stock plus ours), `ctrl:nocaps`, `ctrl:swapcaps`, `ctrl:hyper_capscontrol`, `lv3:caps_switch`, `lv3:caps_switch_latch`, `lv5:caps_switch`, `grp:caps_toggle`, `grp:caps_switch`, `grp:caps_select`, `grp:shift_caps_toggle`, `grp:shift_caps_switch`, `grp:alt_caps_toggle`, `compose:caps`, `compose:caps-altgr`. That is seven groups, not four. `ctrl:nocaps` matters most of all: "CapsLock as Ctrl" is the single most common remapping of this key, and it is not in the `caps:*` group at all. `grp_led:caps` is deliberately not on the list — it claims the LED rather than the key, and works alongside every choice.
 - `<LSGT>`: `lv2:lsgt_switch`, `lv3:lsgt_switch`, `lv3:lsgt_switch_latch`, `lv5:lsgt_switch`, `lv5:lsgt_switch_lock`, `lv5:lsgt_switch_lock_cancel`.

Only the `caps:*` set is made exclusive by the Gnome Tweaks UI; the rest can be selected alongside it, and the result is decided silently by rule order rather than by the user. Verified: with `caps:shift_modifier` and `lv3:caps_switch` both set, `<CAPS>` compiles to `ISO_Level3_Shift` — `lv3` wins no matter which order the two appear in.

### What `caps:shift_modifier` actually does

Spelled out in the README, and it has to be spelled out in the UI's own description too, because most of it is surprising until seen — above all that Shift + CapsLock still gives the classic Caps Lock, and that two real Shift keys do *not*.

That last part is a separate choice with six stock spellings: `shift:both_capslock`, `shift:both_capslock_cancel`, and the `lshift_`/`rshift_` variant of each. "Yes" writes **`shift:both_capslock_cancel`**, because the `_cancel` ones additionally switch Caps Lock *off* when one Shift is pressed alone, which fits this project's ergonomics better — with CapsLock used as a Shift you will hit a Shift key far more often than you want Caps Lock. All six are recognised on the way in, so an existing setting is read correctly and replaced rather than duplicated.

### why not make a pull-request to include `caps:shift_modifier` in the official xkeyboard-config?

Yes, that would make everything much simpler. 
I am working on that. 
But the release interval there is a few months and distributions are even slower taking in the latest version.

So anyone wanting to improve their keyboard experience, better drop a small snippet of code into your local ~/.config/xkb than waiting for the upstream PR to land.


### Other things the project needs

 - the tool installs itself, in the shape worked out in `tech-specs.md`: the user downloads the single script, reads it, and runs it once as `python3 xkb-caps-options.py --install`, which puts it in `~/.local/bin`. That step checks the prerequisites that have to hold for the tool to work at all — the Python version, the session type, `gsettings`. `xkbcli` is checked where it is actually used, at the verification step, and offered through the distribution's package manager there; demanding it up front would block an installation that does not need it. (`gsettings` access can be via library or calling the CLI tool or whatever other way fits.)

 - the xkb config is *not* part of that step. It is written the first time the user actually selects CapsLock as Shift, since every other choice works with stock xkb. That is where these duties belong:
   + honour `XDG_CONFIG_HOME` instead of hardcoding `~/.config`;
   + **merge** rather than overwrite: plenty of people already have a `~/.config/xkb/rules/evdev` and `evdev.xml` of their own, and clobbering those is data loss. Append the option line only if absent, keep exactly one `! include %S/evdev` last, insert the `<option>` into an existing `caps` group. Back up anything it touches, and stop with instructions rather than guessing if it cannot merge confidently;
   + verify *before* setting the option: write the config, compile a keymap, check that `<CAPS>` came out as `Shift_L, Caps_Lock`, and only then put `caps:shift_modifier` into the option list. A failed write then cannot leave the user with a selected option that does nothing;
   + tell the user that Gnome Settings and Tweaks cache the option registry, so a newly written `evdev.xml` only shows up there after those apps restart (worst case, after logout). The keymap itself applies immediately;
   + be undoable, along with the rest of the installation.

### possible future improvements

* graphical UI
* KDE support

### Non-goals

 - a general-purpose keyboard remapper, or a replacement for GNOME Settings
 - per-layout or per-device options
 - support for setups that do not go through xkb at all
