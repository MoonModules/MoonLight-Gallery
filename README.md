# MoonLight Gallery

Presets and MoonLive scripts for [MoonLight](https://github.com/MoonModules/MoonLight), shared by the people who made them.

Every entry starts as an issue with a picture or video of what it does, so you can see it before you install it.
The discussion stays on that issue, and the file itself lives here once it is accepted.

## What is here

| Folder | What | Installed on a device as |
|---|---|---|
| `presets/` | presets: part of a device's state as one JSON document, from a palette alone to a whole effects stack | a file in `/.config/presets`, or the body of `PATCH /api/state` |
| `scripts/` | MoonLive scripts: effects (`.mle`), layouts (`.mll`), modifiers (`.mlm`), services (`.mls`) and palettes (`.mlp`) | a file in `/moonlive`, or pasted into the MoonLive editor |

[`index.json`](index.json) lists every entry with its name, kind, file, picture or video, author, the MoonLight version it was made on, the issue where it was discussed, and its votes.

## Installing an entry

Open the entry's issue first: it shows what the entry does and anything it needs, such as a panel size or a microphone.

- **A preset**: in the File Manager, turn on hidden files and upload it into `/.config/presets`, and it appears as a pad on the Control card. Or send it straight to the device with `curl -X PATCH --data @preset.json http://<device>/api/state`.
- **A script**: upload it into `/moonlive` with the File Manager, or paste it into the MoonLive editor, and pick it as you pick any effect, layout or modifier.

An entry made on a newer MoonLight than yours may use something your device does not have yet; update first.

## Voting

Like an entry? Give its issue a 👍: that is the vote, open or closed.
The counts go into `index.json` once a day, so the gallery can show what people like most.

## Sharing your own

1. Open a new issue and choose **Share a preset or script**.
2. Fill in every field: the kind, a name, what it does, a picture or video, the MoonLight version, and the file's contents.
3. Tick the CC0 box, which lets anyone use it.

A check runs as soon as you submit and on every edit, and says in the issue what is still missing.
Once it passes, the issue is marked `ready`.
People can comment, and you can edit the issue to improve the file.
When a maintainer adds the `accepted` label, the file is added to the gallery, linked from the issue, and the issue closes.
To update an accepted entry, reopen its issue, edit the file, and ask for it to be accepted again: the new file replaces the old one.

## License

Everything in this gallery is dedicated to the public domain under [CC0 1.0](LICENSE).
Contributors agree to that when they share, so a preset or script can be used anywhere, MoonLight included, with nothing to keep track of.

## For maintainers

The labels: `contribution` (set by the form), `ready` and `needs-fix` (set by the check), and `accepted` (set by you).
Accepting is adding `accepted`: [`accept.yml`](.github/workflows/accept.yml) runs the same check, commits the file under `presets/` or `scripts/` as `<issue>-<name>`, updates `index.json`, comments the link, and closes the issue.
A contribution that no longer passes the check is not added; the issue says why and loses the label.
[`check.yml`](.github/workflows/check.yml) runs on every submission and edit, and [`votes.yml`](.github/workflows/votes.yml) counts the 👍 on accepted issues once a day.
Both use [`tools/gallery.py`](tools/gallery.py), whose tests run on every change to it.
