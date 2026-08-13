   
Purpose of this project in short: 
 - For ergonomic reasons I recommend using the CapsLock and LSGT keys for Shift and AltGr and I do it in this order, but the reverse also works and is muscle-memory compatible with an ANSI keyboard. (LSGT is also known as  ISO key, 102nd, or Non-US Backslash.)
 - Most of the required mappings are already offered as 'options' in xkb, but they are dispersed in various option groups in Gnome Tweaks. The UI is also inconsistent: the 'caps' group ensures that only one behavior for the CapsLock key can be selected from that group, but other behaviors (such as CapsLock as AltGr) can be selected in other groups.
 - One of the very attractive options, namely CapsLock acting as a plain Shift (momentary modifier) is not offered in stock xkb at all.
 
How this project makes configuring the CapsLock and LSGT behavior easier:
 - adds the missing option 'caps:shift_modifier'. This is already present in `./config/xkb/`.
 - provides a small terminal UI (or graphical UI, if we can keep installation size small and ideally only deliver an inspectable script, not a compiled binary) for selecting options consistently:
   + one exclusive choice for CapsLock behavior: none, as Shift, as AltGr, or as CapsLock (no option set, because this is the default).
   + one exclusive choice for LSGT behavior: as Shift, as AltGr, or whatever is the layout default (usually a character key).
   + one yes/no choice if other Shift keys should also act as CapsLock on their Shift layer. (This behavior is automatic for the CapsLock key when used as Shift; this option will automatically pre-selected if CapsLock is assigned anything other than the default CapsLock behavior and unselected otherwise. The user can override this preselection.)

This script could be named `xkb-caps-options` and be installed to `~/bin`. If it's a GUI, a .desktop file for it should also be created in the right place in the user's home dir.

Other things the project needs:
 - an installation script of the pipe-curl-to-bash kind which installs all of the above.

 - a ReadMe.md explaining the motivation and how to use it
 
names of some of the relevant existing xkb options:
+ 'shift:both_capslock' 
+ 'caps:none' and others in the caps:* group
+ 'lvl3:caps' which is also exclusive with all the caps:* settings, but this is not enforced by the existing Gnome Tweaks UI.
+ 'lvl3:lsgt' and 'lvl2:lsgt' which are also mutually exclusive.
   

