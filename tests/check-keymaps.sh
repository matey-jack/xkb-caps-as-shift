#!/bin/sh
# Compile keymaps against config/xkb/ and assert on the result.
#
# This catches the class of bug that otherwise only surfaces as "my keyboard is
# weird now": a symbols file that shadows a stock one, a rules line that does
# not resolve, a registry entry the desktop cannot see.
#
# Needs libxkbcommon-tools (xkbcli) and x11-xkb-utils (xkbcomp).
set -eu

repo=$(cd "$(dirname "$0")/.." && pwd)
XDG_CONFIG_HOME="$repo/config"
export XDG_CONFIG_HOME
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

failures=0

check() {
    description=$1
    expected=$2
    actual=$3
    if printf '%s' "$actual" | grep -qF "$expected"; then
        echo "ok       $description"
    else
        echo "FAILED   $description"
        echo "         expected to find: $expected"
        echo "         got: $actual"
        failures=$((failures + 1))
    fi
}

caps_line() {
    # The <CAPS> binding out of a compiled keymap, on one line.
    sed -n '/key <CAPS>/,/};/p' | tr -s ' \t\n' ' '
}

echo "--- libxkbcommon (what a Wayland compositor uses) ---"

check "caps:shift_modifier makes <CAPS> a Shift" \
    "symbols[Group1]= [ Shift_L, Caps_Lock ]" \
    "$(xkbcli compile-keymap --layout us --options caps:shift_modifier | caps_line)"

check "caps:escape is not shadowed by our symbols file" \
    "symbols[Group1]= [ Escape ]" \
    "$(xkbcli compile-keymap --layout us --options caps:escape | caps_line)"

check "the stock layout still compiles with no options" \
    "key <CAPS> { [ Caps_Lock ] };" \
    "$(xkbcli compile-keymap --layout us | caps_line)"

check "the registry merge is visible to libxkbregistry" \
    "caps:shift_modifier" \
    "$(xkbcli list 2>/dev/null | grep shift_modifier || true)"

echo "--- xkbcomp (stricter about include-path shadowing) ---"

cat > "$work/ours.xkb" <<'EOF'
xkb_keymap {
  xkb_keycodes { include "evdev+aliases(qwerty)" };
  xkb_types    { include "complete" };
  xkb_compat   { include "complete" };
  xkb_symbols  { include "pc+us+capslock_shift(shift_modifier)" };
};
EOF

cat > "$work/stock.xkb" <<'EOF'
xkb_keymap {
  xkb_keycodes { include "evdev+aliases(qwerty)" };
  xkb_types    { include "complete" };
  xkb_compat   { include "complete" };
  xkb_symbols  { include "pc+us+capslock(escape)" };
};
EOF

compile() {
    xkbcomp -I -I"$repo/config/xkb" -I/usr/share/X11/xkb -xkb "$1" - 2>"$work/err" || {
        echo "FAILED   xkbcomp could not compile $1"
        cat "$work/err"
        exit 1
    }
}

check "capslock_shift(shift_modifier) resolves and compiles" \
    "symbols[Group1]= [ Shift_L, Caps_Lock ]" \
    "$(compile "$work/ours.xkb" | caps_line)"

check "our include path does not hide the stock capslock symbols" \
    "symbols[Group1]= [ Escape ]" \
    "$(compile "$work/stock.xkb" | caps_line)"

echo
if [ "$failures" -eq 0 ]; then
    echo "All keymap checks passed."
else
    echo "$failures keymap check(s) failed."
    exit 1
fi
