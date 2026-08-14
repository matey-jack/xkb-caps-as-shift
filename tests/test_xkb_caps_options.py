"""Tests for xkb-caps-options.

Run with:  python3 -m unittest discover -s tests -v

The merge tests are the ones that matter most: merging into a `rules/evdev`
and `rules/evdev.xml` the user already had is the only part of this tool that
can destroy something.  The end-to-end tests drive the real script through a
fake `gsettings` or `kwriteconfig6` on PATH, which is what makes "unrelated
options survive" testable without a desktop session, on either desktop.
"""

import ast
import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from importlib.machinery import SourceFileLoader
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "xkb-caps-options.py")


def load_module():
    loader = SourceFileLoader("xkb_caps_options", SCRIPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


tool = load_module()


class MergeRulesTests(unittest.TestCase):
    def assert_well_formed(self, merged):
        lines = [line for line in merged.splitlines() if line.strip()]
        includes = [line for line in lines if tool.INCLUDE_RE.match(line.strip())]
        self.assertEqual(len(includes), 1, "exactly one include")
        self.assertEqual(lines[-1].strip(), "! include %S/evdev", "include comes last")
        self.assertEqual(
            [line.strip() for line in lines].count(tool.OUR_RULE_LINE), 1, "our line, once"
        )

    def test_adds_to_a_file_that_only_has_the_include(self):
        merged = tool.merge_rules("! include %S/evdev\n")
        self.assert_well_formed(merged)

    def test_keeps_the_users_own_rules(self):
        existing = (
            "! option = symbols\n"
            "mine:thing = +mine(thing)\n"
            "! include %S/evdev\n"
            "\n"
            "! option = types\n"
            "mine:other = +other\n"
        )
        merged = tool.merge_rules(existing)
        self.assert_well_formed(merged)
        self.assertIn("mine:thing = +mine(thing)", merged)
        self.assertIn("mine:other = +other", merged)

    def test_our_line_goes_under_an_existing_symbols_header(self):
        merged = tool.merge_rules("! option = symbols\nmine:thing = +mine(thing)\n")
        body = [line.strip() for line in merged.splitlines() if line.strip()]
        self.assertEqual(body.index(tool.OUR_RULE_LINE), body.index("! option = symbols") + 1)
        self.assert_well_formed(merged)

    def test_adds_a_symbols_header_when_there_is_none(self):
        merged = tool.merge_rules("! option = types\nmine:other = +other\n")
        self.assertIn("! option = symbols", merged)
        self.assert_well_formed(merged)

    def test_is_idempotent(self):
        once = tool.merge_rules("! include %S/evdev\n")
        self.assertEqual(tool.merge_rules(once), once)

    def test_refuses_to_guess_with_two_includes(self):
        with self.assertRaises(tool.Problem):
            tool.merge_rules("! include %S/evdev\n! include %S/evdev\n")


USER_REGISTRY = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xkbConfigRegistry SYSTEM "xkb.dtd">
<xkbConfigRegistry version="1.1">
  <!-- a comment the user wrote and would be upset to lose -->
  <optionList>
    <group allowMultipleSelection="false">
      <configItem>
        <name>caps</name>
      </configItem>
      <option>
        <configItem>
          <name>caps:mine</name>
          <description>Something of my own</description>
        </configItem>
      </option>
    </group>
  </optionList>
</xkbConfigRegistry>
"""

NO_CAPS_GROUP = """<?xml version="1.0" encoding="UTF-8"?>
<xkbConfigRegistry version="1.1">
  <optionList>
    <group allowMultipleSelection="true">
      <configItem>
        <name>grp</name>
      </configItem>
    </group>
  </optionList>
</xkbConfigRegistry>
"""


class MergeRegistryTests(unittest.TestCase):
    def caps_group_options(self, text):
        root = ElementTree.fromstring(text)
        for group in root.iter("group"):
            name = group.find("configItem/name")
            if name is not None and name.text.strip() == "caps":
                return [option.find("configItem/name").text.strip() for option in group.findall("option")]
        return None

    def test_inserts_into_the_existing_caps_group(self):
        merged = tool.merge_registry(USER_REGISTRY)
        self.assertEqual(self.caps_group_options(merged), ["caps:mine", tool.OUR_OPTION])

    def test_keeps_comments_and_the_doctype(self):
        merged = tool.merge_registry(USER_REGISTRY)
        self.assertIn("a comment the user wrote", merged)
        self.assertIn("<!DOCTYPE xkbConfigRegistry", merged)

    def test_creates_a_caps_group_when_there_is_none(self):
        merged = tool.merge_registry(NO_CAPS_GROUP)
        self.assertEqual(self.caps_group_options(merged), [tool.OUR_OPTION])
        self.assertIsNotNone(ElementTree.fromstring(merged))

    def test_is_idempotent(self):
        once = tool.merge_registry(USER_REGISTRY)
        self.assertEqual(tool.merge_registry(once), once)

    def test_refuses_invalid_xml(self):
        with self.assertRaises(tool.Problem):
            tool.merge_registry("<xkbConfigRegistry>")

    def test_strip_puts_it_back_the_way_it_was(self):
        merged = tool.merge_registry(USER_REGISTRY)
        self.assertEqual(tool.strip_our_option(merged), USER_REGISTRY)

    def test_strip_removes_a_group_it_emptied(self):
        merged = tool.merge_registry(NO_CAPS_GROUP)
        self.assertIsNone(self.caps_group_options(tool.strip_our_option(merged)))


class UninstallConfigTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        self.rules_dir = os.path.join(tmp, "xkb", "rules")
        os.makedirs(self.rules_dir)
        self.registry = os.path.join(self.rules_dir, "evdev.xml")
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp})
        patcher.start()
        self.addCleanup(patcher.stop)

    def uninstall(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            tool.uninstall_config()
        return out.getvalue()

    def test_a_registry_it_cannot_recognise_is_left_untouched(self):
        merged = tool.merge_registry(USER_REGISTRY)
        doubled = merged.replace(tool.OUR_OPTION_BLOCK, tool.OUR_OPTION_BLOCK * 2)
        with open(self.registry, "w", encoding="utf-8") as handle:
            handle.write(doubled)

        output = self.uninstall()

        self.assertIn("left", output)
        with open(self.registry, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), doubled)
        self.assertEqual(os.listdir(self.rules_dir), ["evdev.xml"], "no backup of an untouched file")

    def test_a_registry_it_wrote_loses_our_option_and_is_backed_up(self):
        with open(self.registry, "w", encoding="utf-8") as handle:
            handle.write(tool.merge_registry(USER_REGISTRY))

        self.uninstall()

        with open(self.registry, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), USER_REGISTRY)
        self.assertEqual(len(os.listdir(self.rules_dir)), 2, "the file it edited is backed up")


class SlotTests(unittest.TestCase):
    def test_unrelated_options_are_not_claimed(self):
        options = ["grp:alt_shift_toggle", "compose:ralt", "terminate:ctrl_alt_bksp", "caps:escape"]
        _, untouched = tool.read_state(options)
        self.assertEqual(untouched, ["grp:alt_shift_toggle", "compose:ralt", "terminate:ctrl_alt_bksp"])

    def test_unrelated_options_survive_a_write(self):
        options = ["grp:alt_shift_toggle", "caps:escape"]
        _, untouched = tool.read_state(options)
        result = tool.compose(untouched, {"caps": tool.OUR_OPTION, "lsgt": "lv3:lsgt_switch"})
        self.assertIn("grp:alt_shift_toggle", result)
        self.assertNotIn("caps:escape", result)

    def test_a_caps_mapping_we_do_not_offer_is_kept_not_dropped(self):
        states, _ = tool.read_state(["ctrl:nocaps"])
        keeps = tool.keep_choices(states["caps"])
        self.assertEqual([keep.option for keep in keeps], ["ctrl:nocaps"])

    def test_a_caps_mapping_we_do_offer_needs_no_keep_entry(self):
        states, _ = tool.read_state(["caps:none"])
        self.assertEqual(tool.keep_choices(states["caps"]), [])

    def test_competing_options_show_up_as_a_conflict(self):
        states, _ = tool.read_state([tool.OUR_OPTION, "lv3:caps_switch"])
        self.assertTrue(states["caps"].conflicted)
        self.assertIn("conflict", states["caps"].label())

    def test_a_conflict_offers_every_unoffered_option_on_its_own(self):
        # Which of the two is in effect is decided by rule order, so neither
        # may be presented as the current setting.
        states, _ = tool.read_state(["ctrl:nocaps", "caps:escape"])
        keeps = tool.keep_choices(states["caps"])
        self.assertEqual([keep.option for keep in keeps], ["ctrl:nocaps", "caps:escape"])
        self.assertIn("drop caps:escape", keeps[0].label)
        self.assertIn("drop ctrl:nocaps", keeps[1].label)

    def test_a_conflict_between_offered_options_needs_no_keep_entry(self):
        states, _ = tool.read_state([tool.OUR_OPTION, "lv3:caps_switch"])
        self.assertEqual(tool.keep_choices(states["caps"]), [])

    def test_every_claimed_option_is_a_real_xkb_option(self):
        rules = "/usr/share/X11/xkb/rules/evdev"
        if not os.path.exists(rules):
            self.skipTest("no xkeyboard-config on this machine")
        with open(rules, encoding="utf-8") as handle:
            known = {
                line.split("=", 1)[0].strip()
                for line in handle
                if "=" in line and not line.strip().startswith("//")
            }
        for slot in tool.SLOTS:
            for option in slot.claims:
                if option == tool.OUR_OPTION:
                    continue
                self.assertIn(option, known, "%s is not in %s" % (option, rules))

    def test_slots_do_not_overlap(self):
        seen = set()
        for slot in tool.SLOTS:
            overlap = seen & set(slot.claims)
            self.assertEqual(overlap, set(), "an option cannot be in two slots")
            seen |= set(slot.claims)

    def test_every_choice_is_claimed_by_its_own_slot(self):
        for slot in tool.SLOTS:
            for choice in slot.choices:
                if choice.option is not None:
                    self.assertIn(choice.option, slot.claims)


class EmbeddedConfigTests(unittest.TestCase):
    def test_matches_the_files_it_was_generated_from(self):
        for name in tool.CONFIG_FILES:
            with open(os.path.join(REPO, "config", "xkb", name), encoding="utf-8") as handle:
                self.assertEqual(handle.read(), tool.EMBEDDED_CONFIG[name], name)

    def test_a_checkout_reads_the_files_not_the_constants(self):
        self.assertEqual(tool.source_config_dir(), os.path.join(REPO, "config", "xkb"))


class PromptTests(unittest.TestCase):
    def test_enter_takes_the_default(self):
        with mock.patch("builtins.input", side_effect=[""]):
            self.assertEqual(tool.prompt_index(4, 3), 3)

    def test_a_conflicted_slot_asks_until_it_gets_an_answer(self):
        with mock.patch("builtins.input", side_effect=["", "2"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.prompt_index(4, None), 2)


class BackendChoiceTests(unittest.TestCase):
    """Which backend a session gets.  Availability alone is not the answer:
    gsettings ships with glib and is on plenty of KDE systems."""

    def choose(self, desktop, installed):
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": desktop}), mock.patch.object(
            tool.shutil, "which", lambda name: name if name in installed else None
        ):
            return tool.get_backend()

    def test_kde_session_with_gsettings_installed_still_gets_kde(self):
        backend = self.choose("KDE", ["gsettings", "kreadconfig6", "kwriteconfig6"])
        self.assertIsInstance(backend, tool.KdeBackend)

    def test_gnome_session_gets_gnome(self):
        backend = self.choose("ubuntu:GNOME", ["gsettings", "kreadconfig6", "kwriteconfig6"])
        self.assertIsInstance(backend, tool.GnomeBackend)

    def test_an_unknown_desktop_falls_back_to_what_is_installed(self):
        backend = self.choose("sway", ["kreadconfig6", "kwriteconfig6"])
        self.assertIsInstance(backend, tool.KdeBackend)

    def test_plasma_5_is_used_when_6_is_absent(self):
        backend = self.choose("KDE", ["kreadconfig5", "kwriteconfig5"])
        self.assertEqual(backend.name, "KDE (kwriteconfig5)")

    def test_neither_backend_is_a_problem_not_a_crash(self):
        with self.assertRaises(tool.Problem):
            self.choose("sway", [])


FAKE_GSETTINGS = """#!/bin/sh
# Enough of gsettings for the tests: one key, kept in a file.
state="$XKB_TEST_STATE"
case "$1" in
  get) cat "$state" ;;
  set) shift 3; printf '%s\\n' "$1" > "$state" ;;
esac
"""

FAKE_KREADCONFIG = """#!/bin/sh
# Enough of kreadconfig6 for the tests: one key, kept in a file.
while [ $# -gt 0 ]; do
  case "$1" in
    --key) key="$2"; shift 2 ;;
    *) shift ;;
  esac
done
if [ "$key" = Options ] && [ -f "$XKB_TEST_STATE" ]; then cat "$XKB_TEST_STATE"; fi
"""

FAKE_KWRITECONFIG = """#!/bin/sh
# The mirror of it.  Keys other than Options are accepted and dropped.
value=""
while [ $# -gt 0 ]; do
  case "$1" in
    --file|--group) shift 2 ;;
    --key) key="$2"; shift 2 ;;
    --notify) shift ;;
    *) value="$1"; shift ;;
  esac
done
[ "$key" = Options ] && printf '%s\\n' "$value" > "$XKB_TEST_STATE"
exit 0
"""

FAKE_DBUS_SEND = """#!/bin/sh
exit 0
"""


class EndToEndCases:
    """Drives the real script, with the desktop and the config dir faked out.

    Not a TestCase itself; the two subclasses below say which desktop, which
    fake commands to put on PATH, and how that desktop spells an option list.
    """

    desktop = ""
    fakes = {}

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = os.path.join(self.tmp, "state")
        bin_dir = os.path.join(self.tmp, "bin")
        os.makedirs(bin_dir)
        for name, script in self.fakes.items():
            fake = os.path.join(bin_dir, name)
            with open(fake, "w", encoding="utf-8") as handle:
                handle.write(script)
            os.chmod(fake, 0o755)
        self.config_home = os.path.join(self.tmp, "config")
        self.env = dict(
            os.environ,
            PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""),
            XKB_TEST_STATE=self.state,
            XDG_CONFIG_HOME=self.config_home,
            XDG_CURRENT_DESKTOP=self.desktop,
        )
        self.env.pop("XDG_SESSION_TYPE", None)
        self.env.pop("WAYLAND_DISPLAY", None)

    def set_options(self, options):
        with open(self.state, "w", encoding="utf-8") as handle:
            handle.write(self.encode(options) + "\n")

    def get_options(self):
        with open(self.state, encoding="utf-8") as handle:
            return self.decode(handle.read().strip())

    def run_tool(self, *args, **kwargs):
        result = subprocess.run(
            [sys.executable, SCRIPT] + list(args),
            capture_output=True,
            text=True,
            env=self.env,
            input="",
        )
        if kwargs.get("expect_failure"):
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_get_reports_each_slot(self):
        self.set_options(["grp:alt_shift_toggle", "caps:escape"])
        output = self.run_tool("--get")
        self.assertIn("caps:", output)
        self.assertIn("caps:escape", output)
        self.assertIn("Make Caps Lock an additional Esc", output)
        self.assertIn("not managed by this tool", output)

    def test_get_handles_an_empty_list(self):
        self.set_options([])
        self.assertIn("empty", self.run_tool("--get"))

    def test_dry_run_writes_nothing(self):
        self.set_options(["grp:alt_shift_toggle"])
        output = self.run_tool("--set", "caps=shift", "--dry-run")
        self.assertIn("nothing was written", output)
        self.assertEqual(self.get_options(), ["grp:alt_shift_toggle"])
        self.assertFalse(os.path.exists(os.path.join(self.config_home, "xkb")))

    def test_set_keeps_options_it_does_not_manage(self):
        self.set_options(["grp:alt_shift_toggle", "compose:ralt", "caps:escape"])
        self.run_tool("--set", "caps=altgr")
        written = self.get_options()
        self.assertIn("grp:alt_shift_toggle", written)
        self.assertIn("compose:ralt", written)
        self.assertIn("lv3:caps_switch", written)
        self.assertNotIn("caps:escape", written)

    def test_set_leaves_untouched_slots_alone(self):
        self.set_options(["ctrl:nocaps", "lv3:lsgt_switch"])
        self.run_tool("--set", "lsgt=shift")
        written = self.get_options()
        self.assertIn("ctrl:nocaps", written, "an unoffered caps mapping must survive")
        self.assertIn("lv2:lsgt_switch", written)
        self.assertNotIn("lv3:lsgt_switch", written)

    def test_setting_caps_as_shift_writes_the_xkb_config(self):
        self.set_options([])
        self.run_tool("--set", "caps=shift")
        xkb = os.path.join(self.config_home, "xkb")
        with open(os.path.join(xkb, "rules", "evdev"), encoding="utf-8") as handle:
            self.assertIn(tool.OUR_RULE_LINE, handle.read())
        self.assertTrue(os.path.exists(os.path.join(xkb, "symbols", "capslock_shift")))
        self.assertIn(tool.OUR_OPTION, self.get_options())

    def test_rerunning_is_a_no_op(self):
        self.set_options(["grp:alt_shift_toggle"])
        self.run_tool("--set", "caps=shift,lsgt=altgr,both-shift-caps=yes")
        first = self.get_options()
        output = self.run_tool("--set", "caps=shift,lsgt=altgr,both-shift-caps=yes")
        self.assertIn("Nothing to change", output)
        self.assertEqual(self.get_options(), first)

    def test_uninstall_takes_ours_out_and_leaves_the_rest(self):
        self.set_options(["grp:alt_shift_toggle"])
        self.run_tool("--set", "caps=shift")
        self.run_tool("--uninstall")
        self.assertEqual(self.get_options(), ["grp:alt_shift_toggle"])
        xkb = os.path.join(self.config_home, "xkb")
        self.assertFalse(os.path.exists(os.path.join(xkb, "symbols", "capslock_shift")))

    def test_rejects_an_unknown_slot_or_value(self):
        self.set_options([])
        self.assertIn("unknown slot", self.run_tool("--set", "nope=1", expect_failure=True))
        self.assertIn("unknown value", self.run_tool("--set", "caps=nope", expect_failure=True))

    def test_refuses_an_x11_session(self):
        self.set_options([])
        self.env["XDG_SESSION_TYPE"] = "x11"
        self.assertIn("X11", self.run_tool("--set", "caps=shift", expect_failure=True))

    def test_the_desktop_it_picked_raises_no_warning(self):
        self.set_options([])
        self.assertNotIn("does not look like", self.run_tool("--get"))


class GnomeEndToEndTests(EndToEndCases, unittest.TestCase):
    desktop = "GNOME"
    fakes = {"gsettings": FAKE_GSETTINGS}

    def encode(self, options):
        if not options:
            return "@as []"  # what gsettings really prints for an empty list
        return "[" + ", ".join("'%s'" % option for option in options) + "]"

    def decode(self, raw):
        return list(ast.literal_eval(raw[4:] if raw.startswith("@as ") else raw))


class KdeEndToEndTests(EndToEndCases, unittest.TestCase):
    desktop = "KDE"
    fakes = {
        "kreadconfig6": FAKE_KREADCONFIG,
        "kwriteconfig6": FAKE_KWRITECONFIG,
        "dbus-send": FAKE_DBUS_SEND,
    }

    def encode(self, options):
        return ",".join(options)

    def decode(self, raw):
        return [option for option in (part.strip() for part in raw.split(",")) if option]


if __name__ == "__main__":
    unittest.main()
