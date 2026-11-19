# nada

Deterministic MIDI generation: a small structured recipe in, a valid
`.mid` file out. No composition, no randomness, no network. The same
recipe always produces byte-identical output.

nada exists so that something that cannot write code (a person describing
a song, or a chatbot like [Daya](https://github.com/irvan-putra/daya))
can still produce real music files: it writes a small JSON recipe, and
nada validates it and compiles it to a Standard MIDI File. The recipe is
the interface; the code is nada's problem.

Status: early prototype. Python 3.8+ standard library only.

## Usage

```sh
python3 nada.py build examples/twinkle.json -o twinkle.mid
python3 nada.py inspect twinkle.mid
python3 nada.py instruments        # list General MIDI instrument names
```

Play the result in any MIDI player or open it in
[Tengok](https://github.com/irvan-putra/tengok) to look at the notes.

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
recipe's author (human or chatbot) can fix it and retry. Limits keep a
broken recipe from producing a huge or absurd file (64 tracks, 100k
notes per track, 10M ticks total).

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

## License

GNU Affero General Public License v3.0. See LICENSE.
