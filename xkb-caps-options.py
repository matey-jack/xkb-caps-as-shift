#!/usr/bin/env python3
"""One consistent choice per key for Caps Lock and the <> key.

This is the whole product: a single file, standard library only, no network
access at runtime.  Read it before you run it.

    python3 xkb-caps-options --install    put it in ~/.local/bin
    xkb-caps-options                      the menu
    xkb-caps-options --help               everything else
"""

import sys

MIN_PYTHON = (3, 10)
if sys.version_info < MIN_PYTHON:
    sys.stderr.write(
        "xkb-caps-options needs Python %d.%d or newer; this is %d.%d.\n"
        % (MIN_PYTHON + sys.version_info[:2])
    )
    raise SystemExit(1)

import argparse
import ast
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ElementTree
from typing import Dict, List, Optional, Sequence, Tuple

VERSION = "1.0.0"

OUR_OPTION = "caps:shift_modifier"
OUR_OPTION_DESCRIPTION = (
    "Make Caps Lock an additional Shift, but Shift + Caps Lock is the regular Caps Lock"
)


# ---------------------------------------------------------------------------
# The slot tables
#
# A slot is one exclusive choice plus every option id that competes for it.
# `claims` is what gets cleared when the slot is written; `choices` is what the
# menu offers.  An id in `claims` but not in `choices` is a setting we do not
# recommend but must never silently drop -- it shows up as the current value.
#
# The lists are literal data on purpose: xkeyboard-config grows options, and
# adding one here should be a one-line diff.  Checked against 2.41.
# ---------------------------------------------------------------------------


class Choice:
    def __init__(self, key: str, option: Optional[str], label: str, needs_config: bool = False):
        self.key = key
        self.option = option
        self.label = label
        self.needs_config = needs_config


class Slot:
    def __init__(self, key: str, title: str, claims: Sequence[str], choices: Sequence[Choice]):
        self.key = key
        self.title = title
        self.claims = list(claims)
        self.choices = list(choices)

    def choice_for_option(self, option: Optional[str]) -> Optional[Choice]:
        for choice in self.choices:
            if choice.option == option:
                return choice
        return None

    def choice_by_key(self, key: str) -> Optional[Choice]:
        for choice in self.choices:
            if choice.key == key:
                return choice
        return None


CAPS_CLAIMS = [
    # The caps: group, as spelled in rules/evdev.  That is one more than the
    # Gnome UI shows: caps:escape_shifted_compose has no registry entry, so it
    # is settable through gsettings while being invisible in Tweaks.
    "caps:backspace",
    "caps:capslock",
    "caps:ctrl_modifier",
    "caps:escape",
    "caps:escape_shifted_capslock",
    "caps:escape_shifted_compose",
    "caps:hyper",
    "caps:internal",
    "caps:internal_nocancel",
    "caps:menu",
    "caps:none",
    "caps:numlock",
    "caps:shift",
    "caps:shift_nocancel",
    "caps:shiftlock",
    "caps:super",
    "caps:swapescape",
    OUR_OPTION,
    # And the six other groups that claim the same key without the caps: group
    # ever being consulted.  ctrl:nocaps belongs here above all: it is the most
    # common Caps Lock remapping there is.
    "ctrl:nocaps",
    "ctrl:swapcaps",
    "ctrl:hyper_capscontrol",
    "lv3:caps_switch",
    "lv3:caps_switch_latch",
    "lv5:caps_switch",
    "grp:caps_toggle",
    "grp:caps_switch",
    "grp:caps_select",
    "grp:shift_caps_toggle",
    "grp:shift_caps_switch",
    "grp:alt_caps_toggle",
    "compose:caps",
    "compose:caps-altgr",
    # grp_led:caps is deliberately absent: it claims the Caps Lock LED, not the
    # key, and works alongside every choice here.
]

LSGT_CLAIMS = [
    "lv2:lsgt_switch",
    "lv3:lsgt_switch",
    "lv3:lsgt_switch_latch",
    "lv5:lsgt_switch",
    "lv5:lsgt_switch_lock",
    "lv5:lsgt_switch_lock_cancel",
]

BOTH_SHIFT_CLAIMS = [
    "shift:both_capslock",
    "shift:both_capslock_cancel",
    "shift:lshift_both_capslock",
    "shift:lshift_both_capslock_cancel",
    "shift:rshift_both_capslock",
    "shift:rshift_both_capslock_cancel",
    # The shift:*_both_shiftlock family is a different behaviour (Shift Lock,
    # not Caps Lock) and shift:breaks_caps is unrelated, so neither is claimed.
]

SLOTS = [
    Slot(
        key="caps",
        title="Caps Lock",
        claims=CAPS_CLAIMS,
        choices=[
            Choice("default", None, "Caps Lock, unchanged"),
            Choice("shift", OUR_OPTION, "a Shift key; Shift + Caps Lock is the regular Caps Lock", needs_config=True),
            Choice("altgr", "lv3:caps_switch", "AltGr (chooses the 3rd level)"),
            Choice("none", "caps:none", "disabled"),
        ],
    ),
    Slot(
        key="lsgt",
        title='The "< >" key (left of Z on ISO keyboards)',
        claims=LSGT_CLAIMS,
        choices=[
            Choice("default", None, "whatever the layout says, usually < and >"),
            Choice("shift", "lv2:lsgt_switch", "a Shift key"),
            Choice("altgr", "lv3:lsgt_switch", "AltGr (chooses the 3rd level)"),
        ],
    ),
    Slot(
        key="both-shift-caps",
        title="Both Shift keys together toggle Caps Lock",
        claims=BOTH_SHIFT_CLAIMS,
        choices=[
            Choice("no", None, "no"),
            Choice("yes", "shift:both_capslock_cancel", "yes, and one Shift alone switches it back off"),
        ],
    ),
]


# --- BEGIN EMBEDDED CONFIG (generated from config/xkb/ by --regen-embedded) ---
EMBEDDED_CONFIG = {
    "rules/evdev": """
// On the left side of this rule the 'caps:' prefix is a UI grouping convention,
// not a file name.
//
// The right side 'capslock_shift' is the file's name in the ../symbols folder
// and 'shift_modifier' is the section in that file.
! option = symbols
caps:shift_modifier = +capslock_shift(shift_modifier)

// Since the rules reader stops searching file paths at the first one found,
// we explicitly need to import the system rules.  Keeping the include last also
// applies our symbols before all stock ones, so a stock option that claims
// <CAPS> as well wins over caps:shift_modifier, in any option order.
! include %S/evdev
""",
    "rules/evdev.xml": """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xkbConfigRegistry SYSTEM "xkb.dtd">
<!--
  Registration file for GNOME's UI.  It is read by libxkbregistry, which merges
  ~/.config/xkb/rules/evdev.xml with /etc/xkb/ and /usr/share/X11/xkb/ instead of
  replacing them, so only the additions belong here.  
-->
<xkbConfigRegistry version="1.1">

  <!--
    Option groups merge the same way variant lists do, so this adds a 17th entry
    to the stock 'caps' group rather than creating a group of its own.  
    
    The stock 'caps' group is set as allowMultipleSelection="false", which makes
    perfect sense since using CapsLock as Shift is exclusive to the other options from that group
    (using CapsLock as Escape, Ctrl, disabling it, etc).

    The name is 'shift_modifier' and not the obvious 'shift' because caps:shift
    is already taken upstream: it means "Caps Lock acts as Shift *with locking*"
    and is a types rule (+caps(shift)).  caps:shift_modifier is the exact analog
    of the stock caps:ctrl_modifier, "Make Caps Lock an additional Ctrl".
  -->
  <optionList>
    <group allowMultipleSelection="false">
      <configItem>
        <name>caps</name>
      </configItem>
      <option>
        <configItem>
          <name>caps:shift_modifier</name>
          <description>Make Caps Lock an additional Shift, but Shift + Caps Lock is the regular Caps Lock</description>
        </configItem>
      </option>
    </group>
  </optionList>

</xkbConfigRegistry>
""",
    "symbols/capslock_shift": """// Caps Lock behaves as an additional (momentary) Shift key.
// Shift then Caps Lock keys pressed together activates the actual classic CapsLock.
//
// Selected as the option caps:shift_modifier, registered into the stock 'caps'
// group so the UI makes it exclusive with caps:none and the rest.  The section
// name matches the option's suffix by convention only; ../rules/evdev is what
// actually ties the two together.
//
// The file name has to be unique across the xkb include path: symbols files are
// located by search and the first match wins, so a file named like a stock one
// hides that one instead of adding to it.
//
// The mapping is the same construct stock shift(lshift_both_capslock) uses for
// <LFSH>: the standard compat rules turn level 1 into SetMods(Shift) and level 2
// into LockMods(Lock).  <CAPS> also stays in modifier_map Lock, through the
// Caps_Lock keysym bound in symbols/pc, and that is what keeps the LED working.
hidden partial modifier_keys
xkb_symbols "shift_modifier" {
    key <CAPS> { [  Shift_L,  Caps_Lock  ], type[group1]="ALPHABETIC" };
    modifier_map Shift { <CAPS> };
};
""",
}
# --- END EMBEDDED CONFIG ---

CONFIG_FILES = ("symbols/capslock_shift", "rules/evdev", "rules/evdev.xml")

OUR_RULE_LINE = "caps:shift_modifier = +capslock_shift(shift_modifier)"
INCLUDE_RE = re.compile(r"^!\s*include\s+%S/evdev\s*$")
OPTION_HEADER_RE = re.compile(r"^!\s*option\s*=\s*symbols\s*$")


class Problem(Exception):
    """Something the user has to decide about.  Printed without a traceback."""


# ---------------------------------------------------------------------------
# Where things live
# ---------------------------------------------------------------------------


def config_home() -> str:
    return os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")


def xkb_dir() -> str:
    return os.path.join(config_home(), "xkb")


def bin_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".local", "bin")


def installed_path() -> str:
    return os.path.join(bin_dir(), "xkb-caps-options")


def source_config_dir() -> Optional[str]:
    """The repo's config/xkb next to this script, when run from a checkout.

    Development then never goes through the embedded copy.
    """
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except NameError:  # read from stdin
        return None
    candidate = os.path.join(here, "config", "xkb")
    if all(os.path.exists(os.path.join(candidate, name)) for name in CONFIG_FILES):
        return candidate
    return None


def config_content(name: str) -> str:
    source = source_config_dir()
    if source:
        with open(os.path.join(source, name), encoding="utf-8") as handle:
            return handle.read()
    return EMBEDDED_CONFIG[name]


# ---------------------------------------------------------------------------
# Option descriptions, read from the registry the desktop itself uses
# ---------------------------------------------------------------------------


def registry_paths() -> List[str]:
    paths = [
        os.path.join(xkb_dir(), "rules", "evdev.xml"),
        "/etc/xkb/rules/evdev.xml",
        "/usr/share/X11/xkb/rules/evdev.xml",
    ]
    return [path for path in paths if os.path.exists(path)]


_descriptions: Optional[Dict[str, str]] = None


def descriptions() -> Dict[str, str]:
    global _descriptions
    if _descriptions is not None:
        return _descriptions
    found: Dict[str, str] = {OUR_OPTION: OUR_OPTION_DESCRIPTION}
    for path in registry_paths():
        try:
            root = ElementTree.parse(path).getroot()
        except (ElementTree.ParseError, OSError):
            continue
        for option in root.iter("option"):
            name = option.find("configItem/name")
            description = option.find("configItem/description")
            if name is not None and name.text and description is not None and description.text:
                found.setdefault(name.text.strip(), description.text.strip())
    _descriptions = found
    return found


def describe(option: str) -> str:
    return descriptions().get(option, "no description in the xkb registry")


# ---------------------------------------------------------------------------
# The settings backend.  Gnome today, kxkbrc later -- hence the interface.
# ---------------------------------------------------------------------------


class SettingsBackend:
    name = "none"

    def available(self) -> bool:
        raise NotImplementedError

    def read(self) -> List[str]:
        raise NotImplementedError

    def write(self, options: Sequence[str]) -> None:
        raise NotImplementedError


class GnomeBackend(SettingsBackend):
    name = "GNOME (gsettings)"
    SCHEMA = "org.gnome.desktop.input-sources"
    KEY = "xkb-options"

    def available(self) -> bool:
        return shutil.which("gsettings") is not None

    def read(self) -> List[str]:
        raw = run(["gsettings", "get", self.SCHEMA, self.KEY]).strip()
        if raw.startswith("@as "):
            raw = raw[4:].strip()
        if not raw or raw == "[]":
            return []
        try:
            value = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            raise Problem("could not parse the current option list from gsettings: %r" % raw)
        return [str(item) for item in value]

    def write(self, options: Sequence[str]) -> None:
        literal = "[" + ", ".join("'%s'" % option for option in options) + "]"
        run(["gsettings", "set", self.SCHEMA, self.KEY, literal])


def run(command: Sequence[str], env: Optional[Dict[str, str]] = None) -> str:
    try:
        result = subprocess.run(
            list(command), capture_output=True, text=True, env=env, check=False
        )
    except FileNotFoundError:
        raise Problem("%s is not installed." % command[0])
    if result.returncode != 0:
        raise Problem(
            "%s failed (exit %d):\n%s"
            % (" ".join(command), result.returncode, (result.stderr or result.stdout).strip())
        )
    return result.stdout


def get_backend() -> SettingsBackend:
    backend = GnomeBackend()
    if not backend.available():
        raise Problem(
            "gsettings was not found, so the option list cannot be read or written.\n"
            "That means this is not a GNOME session; KDE support is not written yet."
        )
    return backend


# ---------------------------------------------------------------------------
# Session checks
# ---------------------------------------------------------------------------


def check_session(strict: bool = True) -> List[str]:
    """Returns warnings; raises if the session cannot work at all."""
    warnings = []
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    on_wayland = session_type == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))
    if session_type == "x11" or (not on_wayland and session_type):
        if strict:
            raise Problem(
                "This is an X11 session, and there it cannot work.\n"
                "\n"
                "~/.config/xkb/ is a libxkbcommon feature, which is what Wayland\n"
                "compositors use.  X11 compiles its keymap with the X server's own\n"
                "xkbcomp, whose include path is /usr/share/X11/xkb and which never\n"
                "looks in your home directory.  Log into a Wayland session instead."
            )
        warnings.append("this looks like an X11 session, where the mapping will not take effect")
    elif not on_wayland:
        warnings.append("could not tell whether this is a Wayland session")

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    if "GNOME" not in desktop.upper():
        warnings.append(
            "this does not look like GNOME (XDG_CURRENT_DESKTOP=%r); the keymap files work\n"
            "  under any Wayland compositor, but the option list is read from GNOME's gsettings"
            % desktop
        )
    return warnings


# ---------------------------------------------------------------------------
# The whole algorithm: bucket the current list into slots, write back the rest
# ---------------------------------------------------------------------------


class SlotState:
    def __init__(self, slot: Slot, present: Sequence[str]):
        self.slot = slot
        self.present = list(present)

    @property
    def current(self) -> Optional[str]:
        return self.present[0] if self.present else None

    @property
    def conflicted(self) -> bool:
        return len(self.present) > 1

    def label(self) -> str:
        if not self.present:
            choice = self.slot.choice_for_option(None)
            return choice.label if choice else "unset"
        if self.conflicted:
            return "conflict: " + ", ".join(self.present)
        choice = self.slot.choice_for_option(self.current)
        if choice:
            return choice.label
        return "%s (%s)" % (self.current, describe(self.current))


def read_state(options: Sequence[str]) -> Tuple[Dict[str, SlotState], List[str]]:
    """Split the option list into one state per slot plus everything else."""
    states = {}
    claimed = set()
    for slot in SLOTS:
        present = [option for option in options if option in slot.claims]
        states[slot.key] = SlotState(slot, present)
        claimed.update(present)
    untouched = [option for option in options if option not in claimed]
    return states, untouched


def compose(untouched: Sequence[str], selection: Dict[str, Optional[str]]) -> List[str]:
    """untouched + the chosen options, in slot order, with no duplicates."""
    result = list(untouched)
    for slot in SLOTS:
        option = selection.get(slot.key)
        if option and option not in result:
            result.append(option)
    return result


def keep_choice(state: SlotState) -> Optional[Choice]:
    """The 'leave what is already there' entry, when it is not on the menu.

    Esc and Ctrl are the two most popular Caps Lock remappings and neither is
    among the four this project recommends.  Dropping them silently would
    damage exactly the people the tool is for.
    """
    if not state.present:
        return None
    if not state.conflicted and state.slot.choice_for_option(state.current):
        return None
    if state.conflicted:
        return Choice(
            "keep",
            state.current,
            "keep %s and drop the others (%s)"
            % (state.current, ", ".join(state.present[1:])),
        )
    return Choice("keep", state.current, "keep %s -- %s" % (state.current, describe(state.current)))


def menu_choices(state: SlotState) -> List[Choice]:
    extra = keep_choice(state)
    return ([extra] if extra else []) + state.slot.choices


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------


def print_options(options: Sequence[str]) -> None:
    if not options:
        print("  (empty -- every key does what the layout says)")
        return
    width = max(len(option) for option in options)
    for option in options:
        print("  %-*s  %s" % (width, option, describe(option)))


def print_diff(before: Sequence[str], after: Sequence[str]) -> bool:
    added = [option for option in after if option not in before]
    removed = [option for option in before if option not in after]
    if not added and not removed:
        print("Nothing to change.")
        return False
    for option in removed:
        print("  - %s  (%s)" % (option, describe(option)))
    for option in added:
        print("  + %s  (%s)" % (option, describe(option)))
    return True


# ---------------------------------------------------------------------------
# Installing the xkb config, on demand
# ---------------------------------------------------------------------------


def backup(path: str) -> str:
    target = "%s.backup-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, target)
    return target


def write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def merge_rules(existing: str) -> str:
    """Add our option line, and leave exactly one '! include %S/evdev' last."""
    lines = existing.splitlines()
    includes = [index for index, line in enumerate(lines) if INCLUDE_RE.match(line.strip())]
    if len(includes) > 1:
        raise Problem(
            "%s has more than one '! include %%S/evdev' line.\n"
            "Merging that automatically would be guessing, so nothing was written.\n"
            "Keep exactly one, at the end of the file, then run this again."
            % os.path.join(xkb_dir(), "rules", "evdev")
        )
    for index in reversed(includes):
        del lines[index]

    if not any(line.strip() == OUR_RULE_LINE for line in lines):
        header = None
        for index, line in enumerate(lines):
            if OPTION_HEADER_RE.match(line.strip()):
                header = index
                break
        if header is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append("! option = symbols")
            lines.append(OUR_RULE_LINE)
        else:
            lines.insert(header + 1, OUR_RULE_LINE)

    while lines and not lines[-1].strip():
        lines.pop()
    lines.append("")
    lines.append("! include %S/evdev")
    return "\n".join(lines) + "\n"


GROUP_RE = re.compile(r"<group\b.*?</group>", re.DOTALL)
CAPS_NAME_RE = re.compile(r"<name>\s*caps\s*</name>")

OUR_OPTION_BLOCK = """      <option>
        <configItem>
          <name>caps:shift_modifier</name>
          <description>%s</description>
        </configItem>
      </option>
""" % OUR_OPTION_DESCRIPTION

OUR_GROUP_BLOCK = """    <group allowMultipleSelection="false">
      <configItem>
        <name>caps</name>
      </configItem>
%s    </group>
""" % OUR_OPTION_BLOCK


def merge_registry(existing: str) -> str:
    """Insert our <option> into the caps group, keeping comments intact.

    Done as a text insertion rather than a parse-and-rewrite, because
    ElementTree would drop the DOCTYPE and every comment in the user's file.
    """
    path = os.path.join(xkb_dir(), "rules", "evdev.xml")
    if OUR_OPTION in existing:
        return existing
    try:
        ElementTree.fromstring(existing)
    except ElementTree.ParseError as error:
        raise Problem("%s is not valid XML (%s), so it was left alone." % (path, error))

    caps_groups = [match for match in GROUP_RE.finditer(existing) if CAPS_NAME_RE.search(match.group())]
    if len(caps_groups) > 1:
        raise Problem(
            "%s has more than one 'caps' option group, so nothing was written.\n"
            "Merge them into one and run this again." % path
        )

    def insert(block: str, at: int) -> str:
        # On its own lines, so that the closing tag keeps its indentation and
        # removing the block again is an exact reverse.
        line_start = existing.rfind("\n", 0, at) + 1
        return existing[:line_start] + block + existing[line_start:]

    if caps_groups:
        group = caps_groups[0]
        return insert(OUR_OPTION_BLOCK, group.start() + group.group().rindex("</group>"))

    if "</optionList>" in existing:
        return insert(OUR_GROUP_BLOCK, existing.rindex("</optionList>"))

    if "</xkbConfigRegistry>" in existing:
        block = "  <optionList>\n" + OUR_GROUP_BLOCK + "  </optionList>\n\n"
        return insert(block, existing.rindex("</xkbConfigRegistry>"))

    raise Problem(
        "%s has no </xkbConfigRegistry> element, so it was left alone.\n"
        "Add the caps:shift_modifier option block by hand, or move the file aside." % path
    )


def config_installed() -> bool:
    symbols = os.path.join(xkb_dir(), "symbols", "capslock_shift")
    rules = os.path.join(xkb_dir(), "rules", "evdev")
    if not os.path.exists(symbols) or not os.path.exists(rules):
        return False
    with open(rules, encoding="utf-8") as handle:
        return OUR_RULE_LINE in handle.read()


def install_config(dry_run: bool = False, quiet: bool = False) -> None:
    """Write the xkb files.  Called the first time Caps Lock as Shift is picked."""
    plan = []
    for name in CONFIG_FILES:
        path = os.path.join(xkb_dir(), name)
        content = config_content(name)
        if not os.path.exists(path):
            plan.append((path, content, "create"))
            continue
        with open(path, encoding="utf-8") as handle:
            existing = handle.read()
        if name == "symbols/capslock_shift":
            merged = content
        elif name == "rules/evdev":
            merged = merge_rules(existing)
        else:
            merged = merge_registry(existing)
        if merged != existing:
            plan.append((path, merged, "merge into"))

    if not plan:
        if not quiet:
            print("The xkb config is already in place.")
        return

    if not quiet:
        print("The Caps Lock as Shift mapping is not in stock xkb, so it has to be")
        print("written to disk first.  This will:")
        for path, _, action in plan:
            print("  %s %s" % (action, path))
        print("Anything that already exists is backed up next to itself first.")
    if dry_run:
        return

    for path, content, _ in plan:
        if os.path.exists(path):
            print("  backed up %s" % backup(path))
        write_file(path, content)
        print("  wrote %s" % path)


def uninstall_config() -> None:
    """Undo install_config, surgically -- the user may have edited since."""
    symbols = os.path.join(xkb_dir(), "symbols", "capslock_shift")
    if os.path.exists(symbols):
        os.remove(symbols)
        print("  removed %s" % symbols)

    rules = os.path.join(xkb_dir(), "rules", "evdev")
    if os.path.exists(rules):
        with open(rules, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        kept = [line for line in lines if line.strip() != OUR_RULE_LINE]
        remaining = [line for line in kept if line.strip() and not line.strip().startswith("//")]
        if all(INCLUDE_RE.match(line.strip()) or OPTION_HEADER_RE.match(line.strip()) for line in remaining):
            os.remove(rules)
            print("  removed %s (nothing of yours was in it)" % rules)
        elif kept != lines:
            backup(rules)
            write_file(rules, "\n".join(kept) + "\n")
            print("  removed our line from %s" % rules)

    registry = os.path.join(xkb_dir(), "rules", "evdev.xml")
    if os.path.exists(registry):
        with open(registry, encoding="utf-8") as handle:
            existing = handle.read()
        if OUR_OPTION in existing:
            stripped = strip_our_option(existing)
            backup(registry)
            if stripped is None:
                print("  left %s alone: it holds options besides ours." % registry)
                print("  Remove the caps:shift_modifier <option> block by hand if you want it gone.")
            elif stripped.count("<option") == 0 and stripped.count("<group") == 0:
                os.remove(registry)
                print("  removed %s (nothing of yours was in it)" % registry)
            else:
                write_file(registry, stripped)
                print("  removed our option from %s" % registry)


def strip_our_option(existing: str) -> Optional[str]:
    """Cut our <option> block out.  None if the shape is not what we wrote."""
    pattern = re.compile(
        r"[ \t]*<option>\s*<configItem>\s*<name>\s*%s\s*</name>.*?</option>\n?" % re.escape(OUR_OPTION),
        re.DOTALL,
    )
    stripped, count = pattern.subn("", existing)
    if count != 1:
        return None
    empty_group = re.compile(
        r"[ \t]*<group[^>]*>\s*<configItem>\s*<name>\s*caps\s*</name>\s*</configItem>\s*</group>\n?",
        re.DOTALL,
    )
    stripped = empty_group.sub("", stripped)
    return stripped


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

PACKAGE_MANAGERS = [
    ("apt-get", ["sudo", "apt-get", "install", "-y", "libxkbcommon-tools"]),
    ("dnf", ["sudo", "dnf", "install", "-y", "libxkbcommon-tools"]),
    ("zypper", ["sudo", "zypper", "install", "-y", "libxkbcommon-tools"]),
    ("pacman", ["sudo", "pacman", "-S", "--needed", "libxkbcommon"]),
]


def offer_xkbcli(interactive: bool) -> bool:
    if shutil.which("xkbcli"):
        return True
    print()
    print("xkbcli is not installed.  It is used once, to check that the keymap really")
    print("compiles to Shift_L before the option is switched on.  Nothing else needs it.")
    if not interactive:
        return False
    for tool, command in PACKAGE_MANAGERS:
        if shutil.which(tool):
            if ask_yes_no("Install it now with '%s'?" % " ".join(command), default=True):
                try:
                    run(command)
                except Problem as error:
                    print("That did not work: %s" % error)
                    return False
                return shutil.which("xkbcli") is not None
            return False
    print("No known package manager found; on Debian and Ubuntu the package is")
    print("libxkbcommon-tools.")
    return False


def verify_keymap(options: Sequence[str]) -> Optional[bool]:
    """True/False if xkbcli could check it, None if xkbcli is missing."""
    if not shutil.which("xkbcli"):
        return None
    env = dict(os.environ, XDG_CONFIG_HOME=config_home())
    output = run(
        ["xkbcli", "compile-keymap", "--layout", "us", "--options", ",".join(options)], env=env
    )
    match = re.search(r"key\s+<CAPS>\s*\{(.*?)\};", output, re.DOTALL)
    if not match:
        return False
    return "Shift_L" in match.group(1) and "Caps_Lock" in match.group(1)


# ---------------------------------------------------------------------------
# Installing the tool itself
# ---------------------------------------------------------------------------


def install_self() -> int:
    try:
        source = os.path.abspath(__file__)
    except NameError:
        raise Problem(
            "This copy was read from stdin, so it has no file to install from.\n"
            "Download it first:\n"
            "  curl -fsSLO https://raw.githubusercontent.com/matey-jack/"
            "xkb-caps-as-shift/main/xkb-caps-options\n"
            "  python3 xkb-caps-options --install"
        )
    for warning in check_session(strict=False):
        print("Note: %s" % warning)
    get_backend()

    target = installed_path()
    os.makedirs(bin_dir(), exist_ok=True)
    if os.path.abspath(source) != target:
        shutil.copyfile(source, target)
    os.chmod(target, 0o755)
    print("Installed %s" % target)

    if not any(
        os.path.abspath(entry) == os.path.abspath(bin_dir())
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if entry
    ):
        print()
        print("%s is not on your PATH, so the command will not be found." % bin_dir())
        print("Add this to your shell's startup file:")
        print('  export PATH="$HOME/.local/bin:$PATH"')

    print()
    if config_installed():
        print("The xkb config is in place too.")
    else:
        print("The xkb config is not written yet, and does not need to be: every choice")
        print("except Caps Lock as Shift is a stock xkb option.  It gets written the first")
        print("time you pick that one.")
    print()
    print("Run 'xkb-caps-options' for the menu.")
    return 0


def uninstall_self(interactive: bool) -> int:
    backend = get_backend()
    before = backend.read()
    states, untouched = read_state(before)
    ours = [option for state in states.values() for option in state.present]
    if ours:
        print("These options are managed by this tool and will be removed:")
        print_options(ours)
        print("These are yours and will be kept:")
        print_options(untouched)
        if not interactive or ask_yes_no("Remove them?", default=True):
            backend.write(untouched)
            print("  option list is now %s" % (untouched or "empty"))

    uninstall_config()

    target = installed_path()
    if os.path.exists(target):
        os.remove(target)
        print("  removed %s" % target)
    print("Done.")
    return 0


# ---------------------------------------------------------------------------
# Applying a selection
# ---------------------------------------------------------------------------


def needs_config(selection: Dict[str, Optional[str]]) -> bool:
    for slot in SLOTS:
        choice = slot.choice_for_option(selection.get(slot.key))
        if choice is not None and choice.needs_config:
            return True
    return False


def apply(
    backend: SettingsBackend,
    selection: Dict[str, Optional[str]],
    dry_run: bool,
    interactive: bool,
) -> int:
    before = backend.read()
    _, untouched = read_state(before)
    after = compose(untouched, selection)

    wants_our_option = needs_config(selection)
    print()
    if not print_diff(before, after) and (not wants_our_option or config_installed()):
        print()
        print("Option list (%d):" % len(after))
        print_options(after)
        return 0

    if wants_our_option:
        print()
        install_config(dry_run=dry_run, quiet=False)

    if dry_run:
        print()
        print("--dry-run: nothing was written.  The list would become:")
        print_options(after)
        return 0

    if wants_our_option:
        if not offer_xkbcli(interactive):
            print()
            print("Continuing without verifying.  If Caps Lock does not shift, the keymap")
            print("did not compile the way it should -- see 'Checking that it worked' in the")
            print("README.")
        else:
            verdict = verify_keymap(after)
            if verdict is False:
                raise Problem(
                    "The keymap compiled, but <CAPS> did not come out as Shift_L, Caps_Lock.\n"
                    "The option list was left alone, so your keyboard is unchanged.\n"
                    "The files under %s were written and backed up; check them, or run\n"
                    "--uninstall to take them back out." % xkb_dir()
                )
            if verdict:
                print("  verified: <CAPS> compiles to Shift_L, Caps_Lock")

    backend.write(after)
    print()
    print("Option list is now (%d):" % len(after))
    print_options(after)
    print()
    print("The mapping applies immediately; no logout needed.")
    if wants_our_option:
        print("GNOME Settings and Tweaks read the list of available options once at startup,")
        print("so restart them before looking for the new entry in their menus.")
    return 0


# ---------------------------------------------------------------------------
# The menu
# ---------------------------------------------------------------------------


def ask_yes_no(question: str, default: bool) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        try:
            answer = input(question + suffix).strip().lower()
        except EOFError:
            return default
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


def menu(backend: SettingsBackend, dry_run: bool) -> int:
    options = backend.read()
    states, untouched = read_state(options)

    print("xkb-caps-options %s" % VERSION)
    print()
    if untouched:
        print("Options this tool does not manage, and will not touch:")
        print_options(untouched)
        print()

    selection: Dict[str, Optional[str]] = {}
    for slot in SLOTS:
        state = states[slot.key]
        choices = menu_choices(state)
        current = state.current

        print(slot.title)
        if slot.key == "caps":
            print("  (as a Shift key: hold it and it shifts; Shift + Caps Lock still gives")
            print("   you the classic Caps Lock, and the LED keeps working.)")
        default_index = 1
        for index, choice in enumerate(choices, start=1):
            marker = " "
            if choice.option == current or (choice.key == "keep" and state.present):
                marker = "*"
                default_index = index
            print("  %s %d) %s" % (marker, index, choice.label))
        if state.conflicted:
            print("  ! more than one option currently claims this key; picking any entry")
            print("    above resolves that.")

        chosen = prompt_index(len(choices), default_index)
        selection[slot.key] = choices[chosen - 1].option
        print()

    return apply(backend, selection, dry_run=dry_run, interactive=True)


def prompt_index(count: int, default: int) -> int:
    while True:
        try:
            answer = input("  choice [%d]: " % default).strip()
        except EOFError:
            return default
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= count:
            return int(answer)
        print("  enter a number between 1 and %d." % count)


# ---------------------------------------------------------------------------
# Non-interactive entry points
# ---------------------------------------------------------------------------


def do_get(backend: SettingsBackend) -> int:
    options = backend.read()
    states, untouched = read_state(options)
    for slot in SLOTS:
        print("%-16s %s" % (slot.key + ":", states[slot.key].label()))
    print()
    print("Option list (%d):" % len(options))
    print_options(options)
    if untouched:
        print()
        print("Of those, %d are not managed by this tool: %s" % (len(untouched), ", ".join(untouched)))
    return 0


def parse_set(argument: str, backend: SettingsBackend) -> Dict[str, Optional[str]]:
    options = backend.read()
    states, _ = read_state(options)
    selection: Dict[str, Optional[str]] = {}
    for slot in SLOTS:
        state = states[slot.key]
        keep = keep_choice(state)
        selection[slot.key] = keep.option if keep else state.current

    for pair in argument.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise Problem("--set takes slot=value pairs, for example --set caps=shift,lsgt=altgr")
        name, value = (part.strip() for part in pair.split("=", 1))
        slot = next((candidate for candidate in SLOTS if candidate.key == name), None)
        if slot is None:
            raise Problem(
                "unknown slot %r; the slots are %s" % (name, ", ".join(s.key for s in SLOTS))
            )
        if value == "keep":
            continue
        choice = slot.choice_by_key(value)
        if choice is None:
            raise Problem(
                "unknown value %r for %s; try one of %s, keep"
                % (value, name, ", ".join(c.key for c in slot.choices))
            )
        selection[name] = choice.option
    return selection


def regen_embedded() -> int:
    """Rewrite this file's embedded block from config/xkb/.  Development only."""
    source = source_config_dir()
    if not source:
        raise Problem("--regen-embedded only works from a checkout with config/xkb/ next to it.")
    path = os.path.abspath(__file__)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    begin = "# --- BEGIN EMBEDDED CONFIG (generated from config/xkb/ by --regen-embedded) ---\n"
    end = "# --- END EMBEDDED CONFIG ---\n"
    if begin not in text or end not in text:
        raise Problem("the embedded config markers are missing from %s" % path)

    body = ["EMBEDDED_CONFIG = {\n"]
    for name in sorted(CONFIG_FILES):
        with open(os.path.join(source, name), encoding="utf-8") as handle:
            content = handle.read()
        if '"""' in content or content.endswith("\\"):
            raise Problem("%s cannot be embedded as a triple-quoted string." % name)
        body.append('    "%s": """%s""",\n' % (name, content))
    body.append("}\n")

    start = text.index(begin) + len(begin)
    stop = text.index(end)
    updated = text[:start] + "".join(body) + text[stop:]
    if updated == text:
        print("The embedded config already matches config/xkb/.")
        return 0
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(updated)
    print("Regenerated the embedded config in %s from %s." % (path, source))
    return 0


def check_embedded() -> int:
    """Exit non-zero if the embedded copy has drifted.  Used by CI."""
    source = source_config_dir()
    if not source:
        raise Problem("--check-embedded only works from a checkout with config/xkb/ next to it.")
    drifted = []
    for name in CONFIG_FILES:
        with open(os.path.join(source, name), encoding="utf-8") as handle:
            if handle.read() != EMBEDDED_CONFIG[name]:
                drifted.append(name)
    if drifted:
        sys.stderr.write(
            "The embedded config no longer matches config/xkb/: %s\n"
            "Run './xkb-caps-options --regen-embedded' and commit the result.\n"
            % ", ".join(drifted)
        )
        return 1
    print("The embedded config matches config/xkb/.")
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xkb-caps-options",
        description="One consistent choice per key for Caps Lock and the <> key.",
        epilog="With no arguments, shows the menu.",
    )
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--get", action="store_true", help="print the current settings and exit")
    parser.add_argument(
        "--set",
        metavar="SLOT=VALUE,...",
        help="set slots without the menu, for example caps=shift,lsgt=altgr,both-shift-caps=yes",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would change, write nothing"
    )
    parser.add_argument("--install", action="store_true", help="copy this file to ~/.local/bin")
    parser.add_argument(
        "--uninstall", action="store_true", help="undo everything this tool installed"
    )
    parser.add_argument("--regen-embedded", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--check-embedded", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str]) -> int:
    args = build_parser().parse_args(list(argv))

    if args.regen_embedded:
        return regen_embedded()
    if args.check_embedded:
        return check_embedded()
    if args.install:
        return install_self()

    if args.uninstall:
        return uninstall_self(interactive=sys.stdin.isatty())

    for warning in check_session(strict=not (args.get or args.dry_run)):
        print("Note: %s" % warning)
        print()

    backend = get_backend()
    if args.get:
        return do_get(backend)
    if args.set:
        return apply(
            backend, parse_set(args.set, backend), dry_run=args.dry_run, interactive=False
        )
    return menu(backend, dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Problem as problem:
        sys.stderr.write("\n%s\n" % problem)
        raise SystemExit(1)
    except KeyboardInterrupt:
        sys.stderr.write("\nCancelled; nothing was written.\n")
        raise SystemExit(130)
