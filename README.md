# xkb-caps-as-shift

Makes the Caps Lock key work as a plain Shift key on Linux — the momentary kind that
shifts while you hold it, not the locking kind — while keeping the real Caps Lock
available on Shift + Caps Lock.

## Why

Caps Lock sits on the home row, right under your little finger, and does almost nothing.
The keys you actually reach for constantly are Shift and AltGr. So move them there: Caps
Lock becomes Shift, and the key left of Z on ISO keyboards — `LSGT`, also known as the ISO
key, 102nd, or Non-US Backslash — becomes AltGr. The other way round works too, and has
the advantage of matching the muscle memory of an ANSI keyboard, where the key in that
position *is* a Shift.

Most of these mappings already exist in xkb. The problem is getting at them:

- they are scattered across four different option groups, so nothing shows you the
  behavior of one key in one place;
- the groups do not agree with each other. Gnome's UI lets you pick only one entry from
  the "Caps Lock behavior" group, but you can happily select "Caps Lock chooses the 3rd
  level" from another group at the same time — and then that one silently wins;
- and the one mapping that would be most useful, Caps Lock as a plain Shift, is not in
  stock xkb at all.

This project fills in that missing option, and is growing a small tool to make the
selection consistent.

## What you get

`caps:shift_modifier`, a new entry in the standard "Caps Lock behavior" group:

- **Hold Caps Lock** — it shifts, exactly like a Shift key.
- **Shift + Caps Lock** — the classic Caps Lock, toggled on and off.
- **While Caps Lock is on**, pressing Caps Lock switches it back off rather than shifting.
- The Caps Lock **LED keeps working**.
- The two real Shift keys are left alone. Pressing both together does *not* toggle Caps
  Lock unless you also enable the stock option `shift:both_capslock`.

## Requirements

- **A Wayland session.** The option is installed into your home directory, and only
  libxkbcommon — which is what Wayland compositors use — reads keyboard config from there.
  An X11 session compiles its keymap with the X server's own `xkbcomp`, which never looks
  in your home directory, so this will not work there.
- **Gnome**, for the settings part. The keymap files themselves work under any Wayland
  compositor; only the "how to select the option" instructions below are Gnome-specific.

## Installing

There is no installer yet — see [Status](#status). For now, copy the three files by hand:

```sh
git clone https://github.com/matey-jack/xkb-caps-as-shift.git
cd xkb-caps-as-shift
mkdir -p ~/.config/xkb/rules ~/.config/xkb/symbols
cp config/xkb/symbols/capslock_shift ~/.config/xkb/symbols/
cp config/xkb/rules/evdev ~/.config/xkb/rules/
cp config/xkb/rules/evdev.xml ~/.config/xkb/rules/
```

⚠️ **If `~/.config/xkb/rules/evdev` or `evdev.xml` already exists, do not copy over it.**
Those files are yours, not the system's, and overwriting them loses whatever you had.
Merge instead: add the `caps:shift_modifier` line to your `evdev` while keeping exactly
one `! include %S/evdev` at the end, and add the `<option>` block into the `caps` group of
your `evdev.xml`.

Then select the option, either in the UI or from the command line.

**Gnome Tweaks** → Keyboard & Mouse → Additional Layout Options → Caps Lock behavior →
*"Make Caps Lock an additional Shift, but Shift + Caps Lock is the regular Caps Lock"*.

If the entry is not there yet, restart Tweaks — it reads the list of available options
once at startup. Gnome Settings caches it the same way.

**Or with `gsettings`**, which is worth doing carefully, because the key holds a list and
setting it replaces the whole thing:

```sh
gsettings get org.gnome.desktop.input-sources xkb-options
gsettings set org.gnome.desktop.input-sources xkb-options "['caps:shift_modifier']"
```

Whatever the first command printed — layout switching, compose key, and so on — belongs in
the list you set with the second one. Dropping those is the most common way to break
something while installing this.

The mapping takes effect immediately; no logout needed.

## Checking that it worked

Beyond just typing a capital letter:

```sh
xkbcli compile-keymap --options caps:shift_modifier | grep -A3 'key <CAPS>'
```

should print

```
	key <CAPS>               {
		type= "ALPHABETIC",
		symbols[Group1]= [         Shift_L,       Caps_Lock ]
	};
```

`xkbcli` comes from `libxkbcommon-tools` on Debian and Ubuntu.

## Options that go with it

All of these are stock xkb, selectable in the same Gnome dialog or the same gsettings
list:

| option | effect |
|---|---|
| `lv3:lsgt_switch` | the `LSGT` key becomes AltGr |
| `lv2:lsgt_switch` | the `LSGT` key becomes another Shift |
| `shift:both_capslock` | the two real Shift keys together toggle Caps Lock |
| `shift:both_capslock_cancel` | the same, and one Shift alone switches Caps Lock back off |

⚠️ Do not combine `caps:shift_modifier` with another option that also claims the Caps Lock
key — `lv3:caps_switch`, `grp:caps_toggle` and friends. Nothing stops you, and nothing
warns you: the other option simply wins, whichever order they appear in. Sorting this out
is what the tool below is for.

## Uninstalling

Remove the option from the list, and delete the files if you want them gone:

```sh
gsettings reset org.gnome.desktop.input-sources xkb-options
rm ~/.config/xkb/symbols/capslock_shift
```

`~/.config/xkb/rules/evdev` and `evdev.xml` can go too, unless you have put anything else
of your own in them.

## Status

The xkb option works and is what the instructions above install.

The selector tool — one exclusive choice per key, across all the groups that compete for
it, with your unrelated settings left alone — is specified but not written yet. See
[`scope.md`](scope.md) for what it should do and [`tech-specs.md`](tech-specs.md) for how.

## License

MIT — see [LICENSE](LICENSE).
