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

    def test_a_flat_preset_from_an_older_moonlight_is_refused_with_the_conversion(self):
        flat = '{"captures": "Effects", "Effects.0.type": "Layer", "Effects.enabled": true}'
        e = gallery.parse(BODY.replace('{"Drivers": {"palette": "Ocean", "brightness": 40}}', flat))
        self.assertTrue(any("flat format" in p and "restore" in p for p in gallery.problems(e)))

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


class Voting(unittest.TestCase):
    def test_a_vote_is_a_liking_reaction_on_the_entrys_issue(self):
        issues = [{"number": 7, "reactions": {"+1": 3, "heart": 2, "hooray": 1, "rocket": 1, "-1": 4, "confused": 1, "laugh": 1, "eyes": 1}},
                  {"number": 9, "reactions": {}}, {"number": 11, "pull_request": {}, "reactions": {"+1": 5}}]
        self.assertEqual(gallery.votes_from(issues), {7: 8, 9: 0})

    def test_an_entry_accepted_with_a_heart_starts_with_one_vote(self):
        self.assertEqual(gallery.likes({"heart": 1, "url": "https://api.github.com/x", "total_count": 1}), 1)
        self.assertEqual(gallery.likes(None), 0)

    def test_the_index_changes_only_when_a_count_does(self):
        index = [{"issue": 7, "votes": 3}, {"issue": 9}]
        self.assertTrue(gallery.apply_votes(index, {7: 3, 9: 2}))
        self.assertEqual(index, [{"issue": 7, "votes": 3}, {"issue": 9, "votes": 2}])
        self.assertFalse(gallery.apply_votes(index, {7: 3, 9: 2}))

    def test_an_accepted_entry_starts_with_its_votes_so_far(self):
        with tempfile.TemporaryDirectory() as d:
            gallery.accept(gallery.parse(BODY), 7, "someone", "", Path(d), votes=4)
            self.assertEqual(json.loads((Path(d) / "index.json").read_text())[0]["votes"], 4)



class Thumbnails(unittest.TestCase):
    def test_a_youtube_link_takes_its_own_still_and_anything_else_is_read_as_it_is(self):
        self.assertEqual(gallery.thumb_source("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3"), "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg")
        self.assertEqual(gallery.thumb_source("https://youtu.be/dQw4w9WgXcQ"), "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg")
        self.assertEqual(gallery.thumb_source("https://github.com/user-attachments/assets/1234-abcd"), "https://github.com/user-attachments/assets/1234-abcd")

    def test_every_entry_without_a_thumbnail_gets_one_by_its_issue_and_an_unreadable_one_keeps_none(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "thumbs").mkdir()
            (root / "thumbs" / "0001.webp").write_bytes(b"old")
            index = [{"issue": 1, "media": "https://x/1.gif", "thumb": "thumbs/0001.webp"},
                     {"issue": 2, "media": "https://x/2.mp4"},
                     {"issue": 3, "media": "https://x/broken"}]
            fetched = []
            def fetch(url, dest):
                if url.endswith("broken"):
                    raise OSError("404")
                fetched.append(url)
                dest.write_bytes(b"media")
            def still(src, dest):
                dest.write_bytes(b"webp")
            self.assertTrue(gallery.make_thumbs(index, root, fetch, still))
            self.assertEqual(fetched, ["https://x/2.mp4"])   # the one that has a thumbnail is not fetched again
            self.assertEqual(index[1]["thumb"], "thumbs/0002.webp")
            self.assertTrue((root / "thumbs" / "0002.webp").exists())
            self.assertNotIn("thumb", index[2])
            self.assertFalse(gallery.make_thumbs(index[:2], root, fetch, still))

    def test_re_accepting_an_issue_drops_its_thumbnail_so_a_new_picture_gets_a_new_one(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            gallery.accept(gallery.parse(BODY), 7, "a", "u", root)
            index = json.loads((root / "index.json").read_text())
            (root / "thumbs").mkdir()
            (root / "thumbs" / "0007.webp").write_bytes(b"old")
            index[0]["thumb"] = "thumbs/0007.webp"
            (root / "index.json").write_text(json.dumps(index))
            gallery.accept(gallery.parse(BODY), 7, "a", "u", root)
            self.assertFalse((root / "thumbs" / "0007.webp").exists())
            self.assertNotIn("thumb", json.loads((root / "index.json").read_text())[0])


if __name__ == "__main__":
    unittest.main()
