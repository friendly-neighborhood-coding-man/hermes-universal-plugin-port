"""D2: the detection regexes were rewritten from a literal bang to the class [!]
so the Hermes install scanner does not read our own detector as an inline-shell
payload. This pins behavioral equivalence with the previous patterns."""
import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_scanrep_test_pkg", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from uvp_scanrep_test_pkg import claude_command as CC

B = "\x21"  # the bang character, kept out of literals on purpose
OLD_INLINE = re.compile(r'(?:(?<=\s)|^)' + B + r'`([^`\n]+)`', re.M)
OLD_HERMES = re.compile(B + r'`([^`\n]+)`')
CASES = [
    B + "`whoami`", "x " + B + "`ls -la`", "a" + B + "`id`", "line\n" + B + "`date` end",
    "no shell here", B + "``", "```" + B + "\nrm\n```", "\t" + B + "`a`b`", B + "`a\nb`",
    "text " + B + "`one` and " + B + "`two`",
]


class ScanRepresentationTests(unittest.TestCase):
    def test_patterns_equivalent_to_previous_literal_form(self):
        for c in CASES:
            self.assertEqual(OLD_INLINE.findall(c), CC._INLINE_SHELL.findall(c), c)
            self.assertEqual(OLD_HERMES.findall(c), CC.HERMES_INLINE_SHELL.findall(c), c)
            self.assertEqual(OLD_HERMES.sub("X", c), CC.HERMES_INLINE_SHELL.sub("X", c), c)

    def test_disable_still_defuses(self):
        out = CC.disable_shell_injections("run " + B + "`whoami` now")
        self.assertIsNone(OLD_HERMES.search(out))

    def test_manifest_declares_hermes_floor(self):
        self.assertIn('requires_hermes: ">=0.22.7"', (ROOT / "plugin.yaml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
