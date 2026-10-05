#!/usr/bin/env python3
"""Read a contribution issue, check it, and file an accepted one into the gallery.

A contribution is an issue opened with the form in .github/ISSUE_TEMPLATE/contribution.yml.
GitHub renders each form field as a `### Label` section of the issue body, so the body is the record.
The workflows call this script, with the issue's fields in environment variables rather than in the command line, so nothing a contributor types reaches a shell.

    python tools/gallery.py check    # ISSUE_BODY; prints what to fix, exit 1 when anything is
    python tools/gallery.py accept   # ISSUE_BODY, ISSUE_NUMBER, ISSUE_AUTHOR, ISSUE_URL, ISSUE_VOTES; writes the file and index.json
    python tools/gallery.py votes    # GITHUB_REPOSITORY, GH_TOKEN; refreshes each entry's 👍 count in index.json
    python tools/gallery.py thumbs   # makes the still thumbnail of every entry that has none, with ffmpeg
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.json"

# The form's kinds, each with the folder and extension MoonLight reads it by.
KINDS = {
    "Preset": ("presets", ".json"),
    "Effect script": ("scripts", ".mle"),
    "Layout script": ("scripts", ".mll"),
    "Modifier script": ("scripts", ".mlm"),
    "Service script": ("scripts", ".mls"),
    "Palette script": ("scripts", ".mlp"),
}
MAX_FILE_BYTES = 64 * 1024   # far past any real preset or script; a larger paste is a mistake
NO_RESPONSE = "_No response_"   # what GitHub writes for an empty optional field
THUMB_SIZE = 240   # a square tile in the browsing grid, about 15 KB as WebP, so a page of twelve costs less than one GIF
MAX_MEDIA_BYTES = 100 * 1024 * 1024   # GitHub's own upload limit for a video


def sections(body: str) -> dict:
    """The issue body's `### Label` sections, as label to text."""
    out, label, lines = {}, None, []
    for line in (body or "").replace("\r\n", "\n").split("\n"):
        if line.startswith("### "):
            if label is not None:
                out[label] = "\n".join(lines).strip()
            label, lines = line[4:].strip(), []
        elif label is not None:
            lines.append(line)
    if label is not None:
        out[label] = "\n".join(lines).strip()
    return {k: ("" if v == NO_RESPONSE else v) for k, v in out.items()}


def code_block(text: str) -> str:
    """The content of the first fenced block, which the form's file field is rendered as; the text itself when there is none."""
    m = re.search(r"^```[^\n]*\n(.*?)\n?^```", text, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else text


def parse(body: str) -> dict:
    """The contribution's fields, read from the form's sections."""
    s = sections(body)
    media = re.findall(r"https?://\S+?(?=[\s)\]>\"]|$)", s.get("Picture or video", ""))
    return {
        "kind": s.get("Kind", ""),
        "name": s.get("Name", ""),
        "description": s.get("What it does", ""),
        "media": media[0] if media else "",
        "firmware": s.get("MoonLight version", ""),
        "file": code_block(s.get("File", "")),
        "licensed": "- [x]" in s.get("License", "").lower(),
    }


def problems(entry: dict) -> list:
    """What keeps the contribution from being accepted, in words a contributor can act on; empty when nothing does."""
    found = []
    if entry["kind"] not in KINDS:
        found.append(f"Kind: pick one of {', '.join(KINDS)}.")
    if not entry["name"]:
        found.append("Name: give it a name.")
    if not entry["description"]:
        found.append("What it does: say what it shows or does.")
    if not entry["media"]:
        found.append("Picture or video: add one, so people can see it before installing it.")
    if not entry["firmware"]:
        found.append("MoonLight version: name the version you made it on.")
    if not entry["licensed"]:
        found.append("License: tick the CC0 box, or the file cannot be shared here.")
    text = entry["file"]
    if not text.strip():
        found.append("File: paste the file's contents.")
    elif len(text.encode("utf-8")) > MAX_FILE_BYTES:
        found.append(f"File: larger than {MAX_FILE_BYTES // 1024} KB, which is more than a preset or script needs.")
    elif entry["kind"] == "Preset":
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as e:
            found.append(f"File: not valid JSON ({e.msg} at line {e.lineno}).")
        else:
            if not isinstance(doc, dict) or not doc:
                found.append("File: a preset is a JSON object naming the modules it sets, such as {\"Drivers\": {\"brightness\": 40}}.")
            elif "captures" in doc or any("." in k for k in doc):
                found.append("File: this is the flat format an older MoonLight saved presets in; back up and restore the device holding it, which converts it, then paste the file again.")
    return found


def slug(name: str) -> str:
    """A file-name-safe form of the name."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:48] or "untitled"


def votes_from(issues: list) -> dict:
    """Each issue's 👍 count, by issue number, from the GitHub API's issue list."""
    return {i["number"]: int(i.get("reactions", {}).get("+1", 0)) for i in issues if "pull_request" not in i}


def apply_votes(index: list, votes: dict) -> bool:
    """Set each entry's votes from the counts; True when any changed, so an unchanged index is not rewritten."""
    changed = False
    for e in index:
        n = votes.get(e["issue"], e.get("votes", 0))
        if e.get("votes") != n:
            e["votes"] = n
            changed = True
    return changed


def fetch_votes(repo: str, token: str) -> dict:
    """The 👍 counts of every accepted issue, page by page."""
    votes, page = {}, 1
    while True:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/issues?labels=accepted&state=all&per_page=100&page={page}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            issues = json.loads(r.read())
        votes.update(votes_from(issues))
        if len(issues) < 100:
            return votes
        page += 1


def accept(entry: dict, number: int, author: str, url: str, root: Path = ROOT, votes: int = 0) -> Path:
    """Write the contribution's file and its index entry, replacing an earlier acceptance of the same issue; return the file's path."""
    folder, ext = KINDS[entry["kind"]]
    index_path = root / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    # One file per issue: a re-accepted issue replaces its file, even under a new name, and its thumbnail, since the picture may have changed.
    for old in [e for e in index if e.get("issue") == number]:
        (root / old["file"]).unlink(missing_ok=True)
        if old.get("thumb"):
            (root / old["thumb"]).unlink(missing_ok=True)
    index = [e for e in index if e.get("issue") != number]
    rel = f"{folder}/{number:04d}-{slug(entry['name'])}{ext}"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    text = entry["file"]
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    index.append({
        "issue": number,
        "kind": entry["kind"],
        "name": entry["name"],
        "file": rel,
        "description": entry["description"],
        "media": entry["media"],
        "firmware": entry["firmware"],
        "author": author,
        "url": url,
        "votes": votes,
    })
    index.sort(key=lambda e: e["issue"])
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def thumb_source(media: str) -> str:
    """Where a thumbnail's frame comes from: a YouTube link's own still, any other picture or video as it is."""
    m = re.search(r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([\w-]{11})", media)
    return f"https://img.youtube.com/vi/{m.group(1)}/hqdefault.jpg" if m else media


def download(url: str, dest: Path) -> None:
    """Fetch a picture or video, following GitHub's redirect for an uploaded one, refusing one larger than an upload can be."""
    with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
        size = 0
        while chunk := r.read(1 << 16):
            size += len(chunk)
            if size > MAX_MEDIA_BYTES:
                raise ValueError("larger than an upload can be")
            f.write(chunk)


def frame(src: Path, dest: Path) -> None:
    """One square still as WebP: a second in, past a fade from black, or the first frame of something shorter."""
    scale = f"scale={THUMB_SIZE}:{THUMB_SIZE}:force_original_aspect_ratio=increase,crop={THUMB_SIZE}:{THUMB_SIZE}"
    for seek in (["-ss", "1"], []):
        dest.unlink(missing_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *seek, "-i", str(src), "-frames:v", "1", "-vf", scale, "-q:v", "70", str(dest)],
                       capture_output=True, timeout=120)
        if dest.exists() and dest.stat().st_size:
            return
    raise ValueError("ffmpeg made no frame")


def make_thumbs(index: list, root: Path = ROOT, fetch=download, still=frame) -> bool:
    """Give every entry without a thumbnail one under thumbs/, named by its issue; True when any was made. An entry whose picture cannot be read keeps none, and the gallery shows its kind instead."""
    made = False
    for e in index:
        if e.get("thumb") and (root / e["thumb"]).exists():
            continue
        rel = f"thumbs/{e['issue']:04d}.webp"
        (root / "thumbs").mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory() as td:
                src = Path(td) / "media"
                fetch(thumb_source(e.get("media", "")), src)
                still(src, root / rel)
        except Exception as err:   # one unreadable picture leaves that entry without a thumbnail, not the rest
            print(f"#{e['issue']}: no thumbnail ({err})", file=sys.stderr)
            continue
        e["thumb"] = rel
        made = True
    return made


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "votes":
        index = json.loads(INDEX.read_text(encoding="utf-8"))
        if apply_votes(index, fetch_votes(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"])):
            INDEX.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print("votes changed")
        return 0
    if command == "thumbs":
        index = json.loads(INDEX.read_text(encoding="utf-8"))
        if make_thumbs(index):
            INDEX.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 0
    entry = parse(os.environ.get("ISSUE_BODY", ""))
    found = problems(entry)
    if command == "check":
        print("\n".join(f"- {p}" for p in found))
        return 1 if found else 0
    if command == "accept":
        if found:
            print("\n".join(f"- {p}" for p in found))
            return 1
        path = accept(entry, int(os.environ["ISSUE_NUMBER"]), os.environ.get("ISSUE_AUTHOR", ""),
                      os.environ.get("ISSUE_URL", ""), votes=int(os.environ.get("ISSUE_VOTES") or 0))
        print(path.relative_to(ROOT).as_posix())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
