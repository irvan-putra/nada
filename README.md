# nada

Deterministic MIDI generation: a small structured recipe in, a valid
`.mid` file out. No composition, no randomness, no network. The same
recipe always produces byte-identical output.

nada exists so that something that cannot write code (a person describing
a song, or a chatbot such as the Daya project)
can still produce real music files: it writes a small JSON recipe, and
nada validates it and compiles it to a Standard MIDI File. The recipe is
the interface; the code is nada's problem.

Status: early prototype. Python 3.8+ standard library only.

Try it: the [web version](https://vanipy.com/nada/) runs in any browser;
signed Android APKs are on the
[releases page](https://github.com/irvan-putra/nada/releases), also listed
in the [kaji gallery](https://vanipy.com/kaji/apk/).

Project boundary (per the owner): nada stays a precise recipe-to-MIDI
generator. The conversational composing workshop is a separate project,
Denting; nada does not grow chat or free-form composition features.

## Usage

```sh
python3 nada.py build examples/twinkle.json -o twinkle.mid
python3 nada.py inspect twinkle.mid
python3 nada.py instruments        # list General MIDI instrument names
```

## Web version

`web/` is a dependency-free browser version of the same tool: open
`web/index.html` (or serve the folder statically) to edit a recipe,
validate it, play an approximate synth preview and download the `.mid`.
`web/nada.js` mirrors `nada.py` validation and writing; the fixtures in
`examples/` are the cross-runtime contract, and `tests/parity.js`
(node) proves both implementations produce byte-identical files for
them. Everything runs locally; nothing is uploaded.

## Android

`android/` wraps the same `web/` assets in an offline WebView app, so
the music logic stays a single shared implementation (the web JS core
plus the Python CLI, kept honest by the parity fixtures) instead of a
third copy.

Play the result in any MIDI player, or open it in the Tengok viewer
project to look at the notes.

## Recipe format

```json
{
  "title": "my song",
  "tempo": 120,
  "time_signature": [4, 4],
  "tracks": [
    {
      "name": "melody",
      "instrument": "Music Box",
      "notes": [
        {"note": "C4", "start": 0, "duration": 1},
        {"chord": ["E4", "G4"], "start": 1, "duration": 0.5, "velocity": 100}
      ]
    },
    {
      "name": "drums",
      "drums": true,
      "notes": [
        {"note": "kick", "start": 0, "duration": 0.25}
      ]
    }
  ]
}
```

- `tempo`: beats per minute, 10-600 (default 120).
- `time_signature`: `[numerator, denominator]`, denominator a power of
  two (default `[4, 4]`).
- `ticks_per_beat`: timing resolution 24-960 (default 480).
- `instrument`: a General MIDI program number 0-127, or its name from
  `nada instruments`. `"drums": true` puts the track on the percussion
  channel and takes drum names like `kick`, `snare`, `closed hihat`.
- Notes use names like `C4`, `F#3`, `Bb5` (C4 = middle C) or a raw pitch
  0-127. `start` and `duration` are in beats; they must land on whole
  ticks. `chord` plays up to 16 notes together. `velocity` is 1-127
  (default 96).
- Each track gets its own MIDI channel; reusing one is an error.

Validation is strict on purpose: unknown keys, out-of-range values and
impossible timings fail with a specific message naming the field, so the
recipe's author (human or chatbot) can fix it and retry. Bounds keep a
broken or hostile recipe from producing a huge or slow build: 4 MiB of
JSON, 64 tracks, 100k notes per track and 200k total, 1M pitched events,
10M ticks.

## What nada does not do

- It does not compose. A recipe with valid notes that sound bad is a
  valid recipe. Taste still belongs to whoever writes the recipe; use a
  player or Tengok to preview before sharing.
- It does not render audio. `.mid` is instructions for instruments, not
  sound; how it sounds depends on the player's sound bank.
- Round-tripping through other editors can lose things: this writer
  emits notes, program changes, tempo and time signature only. Pitch
  bend, sustain pedal and other controller data from imported files are
  not preserved, and any import feature added later must say so
  explicitly.

## Development

```sh
python3 -m unittest discover -s tests -v
```

Tests cover the binary format against hand-computed bytes, the recipe
validator with corrupt and out-of-bounds input, a self-reader round
trip, and (when the optional `mido` package is installed, dev only)
cross-checking the output with an independent MIDI library. Never
a runtime dependency.

## Known limitations (Android)

- Verified on an emulator only so far: page load, recipe build, and saving
  through MediaStore.Audio to Music/nada pass in CI, including with the
  signed release APK. It has not yet run on a physical phone; treat first
  on-device installs as unverified.
- MediaStore lifecycle: saving a file and then uninstalling the app leaves
  provider-side state for that package's entries. A subsequent same-package
  save on the same device can be invisible to MediaStore.Files queries for
  a while even though the insert and write succeeded. Fresh first installs
  are unaffected; reinstall-over-itself cycles during testing may show this.
- The production app carries no test hooks or automation extras.

## License

GNU Affero General Public License v3.0. See LICENSE.

---

Built with AI assistance (Instinct and others). Not everything has been reviewed by Irvan.
