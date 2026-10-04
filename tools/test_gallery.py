"""What the gallery tool reads from an issue, what it refuses, and what it files."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gallery  # noqa: E402

# An issue body as GitHub renders the contribution form.
BODY = """### Kind

Preset

### Name

Ocean Drift

### What it does

A slow blue noise field.

### Picture or video

![drift](https://github.com/user-attachments/assets/1234-abcd)

### MoonLight version

6.1.0

### File

```text
{"Drivers": {"palette": "Ocean", "brightness": 40}}
```

### License

- [X] I dedicate this file to the public domain under CC0 1.0
"""


class ReadingAnIssue(unittest.TestCase):
    def test_every_field_is_read_from_its_section(self):
        e = gallery.parse(BODY)
        self.assertEqual(e["kind"], "Preset")
        self.assertEqual(e["name"], "Ocean Drift")
        self.assertEqual(e["media"], "https://github.com/user-attachments/assets/1234-abcd")
        self.assertEqual(e["firmware"], "6.1.0")
        self.assertEqual(json.loads(e["file"]), {"Drivers": {"palette": "Ocean", "brightness": 40}})
        self.assertTrue(e["licensed"])

    def test_a_complete_contribution_has_nothing_to_fix(self):
        self.assertEqual(gallery.problems(gallery.parse(BODY)), [])

    def test_an_empty_field_reads_as_empty_not_as_githubs_placeholder(self):
        e = gallery.parse(BODY.replace("6.1.0", "_No response_"))
        self.assertEqual(e["firmware"], "")
        self.assertTrue(any(p.startswith("MoonLight version") for p in gallery.problems(e)))


class Refusing(unittest.TestCase):
    def test_a_preset_that_is_not_json_says_where(self):
        e = gallery.parse(BODY.replace('"brightness": 40}}', '"brightness": 40'))
        self.assertTrue(any("not valid JSON" in p for p in gallery.problems(e)))

    def test_a_preset_must_name_modules(self):
        e = gallery.parse(BODY.replace('{"Drivers": {"palette": "Ocean", "brightness": 40}}', "[1, 2]"))
        self.assertTrue(any("JSON object" in p for p in gallery.problems(e)))

    def test_no_picture_and_no_license_are_both_named(self):
        e = gallery.parse(BODY.replace("![drift](https://github.com/user-attachments/assets/1234-abcd)", "").replace("- [X]", "- [ ]"))
        found = gallery.problems(e)
        self.assertTrue(any(p.startswith("Picture or video") for p in found))
        self.assertTrue(any(p.startswith("License") for p in found))

    def test_an_unknown_kind_is_refused(self):
        self.assertTrue(any(p.startswith("Kind") for p in gallery.problems(gallery.parse(BODY.replace("\nPreset\n", "\nSomething\n")))))


class Filing(unittest.TestCase):
    def test_an_accepted_issue_lands_as_a_file_and_an_index_entry(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = gallery.accept(gallery.parse(BODY), 7, "someone", "https://example/7", root)
            self.assertEqual(path.relative_to(root).as_posix(), "presets/0007-ocean-drift.json")
            index = json.loads((root / "index.json").read_text())
            self.assertEqual([(e["issue"], e["file"], e["author"]) for e in index], [(7, "presets/0007-ocean-drift.json", "someone")])

    def test_re_accepting_an_issue_replaces_its_file_even_under_a_new_name(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            gallery.accept(gallery.parse(BODY), 7, "someone", "", root)
            gallery.accept(gallery.parse(BODY.replace("Ocean Drift", "Deep Ocean")), 7, "someone", "", root)
            self.assertFalse((root / "presets/0007-ocean-drift.json").exists())
            self.assertTrue((root / "presets/0007-deep-ocean.json").exists())
            self.assertEqual(len(json.loads((root / "index.json").read_text())), 1)

    def test_a_script_goes_to_scripts_with_its_kinds_extension(self):
        body = BODY.replace("\nPreset\n", "\nEffect script\n").replace('{"Drivers": {"palette": "Ocean", "brightness": 40}}', "void loop() {}")
        with tempfile.TemporaryDirectory() as d:
            path = gallery.accept(gallery.parse(body), 12, "someone", "", Path(d))
            self.assertEqual(path.name, "0012-ocean-drift.mle")
            self.assertEqual(path.parent.name, "scripts")


if __name__ == "__main__":
    unittest.main()
