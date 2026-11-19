#!/usr/bin/env python3
"""Tests for nada. Run: python3 -m unittest discover -s tests -v

Covers: VLQ encoding, note-name parsing, recipe validation (including
corrupt and out-of-bounds input), exact output bytes for a golden recipe,
roundtrip parsing of generated files, and a cross-check with the `mido`
library when it is installed.
"""

import json
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import nada  # noqa: E402

try:
    import mido
    HAVE_MIDO = True
except ImportError:
    HAVE_MIDO = False


def recipe(**overrides):
    base = {
        "title": "test song",
        "tempo": 120,
        "tracks": [
            {"name": "melody", "instrument": 0,
             "notes": [{"note": "C4", "start": 0, "duration": 1}]},
        ],
    }
    base.update(overrides)
    return base


class TestVlq(unittest.TestCase):
    def test_known_values(self):
        cases = [
            (0x00000000, bytes([0x00])),
            (0x0000007F, bytes([0x7F])),
            (0x00000080, bytes([0x81, 0x00])),
            (0x00002000, bytes([0xC0, 0x00])),
            (0x001FFFFF, bytes([0xFF, 0xFF, 0x7F])),
            (0x0FFFFFFF, bytes([0xFF, 0xFF, 0xFF, 0x7F])),
        ]
        for value, expected in cases:
            self.assertEqual(nada.vlq(value), expected, hex(value))

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            nada.vlq(-1)
        with self.assertRaises(ValueError):
            nada.vlq(0x10000000)


class TestNoteNames(unittest.TestCase):
    def test_valid(self):
        cases = [("C4", 60), ("A4", 69), ("C#4", 61), ("Db4", 61),
                 ("C-1", 0), ("G9", 127), ("e2", 40), ("kick", 36),
                 ("closed hihat", 42)]
        for name, pitch in cases:
            self.assertEqual(nada.note_to_pitch(name, "x"), pitch, name)

    def test_invalid(self):
        for bad in ["H4", "C10", "C-2", "", "middle c", 3.5, True, 128, -1]:
            with self.assertRaises(nada.RecipeError, msg=repr(bad)):
                nada.note_to_pitch(bad, "x")


class TestValidation(unittest.TestCase):
    def test_minimal_recipe_defaults(self):
        r = nada.validate_recipe({"tracks": [{"notes": [
            {"note": "C4", "start": 0, "duration": 1}]}]})
        self.assertEqual(r["tempo"], 120)
        self.assertEqual(r["time_signature"], [4, 4])
        self.assertEqual(r["ticks_per_beat"], 480)
        self.assertEqual(r["tracks"][0]["channel"], 0)
        self.assertEqual(r["tracks"][0]["notes"][0]["velocity"], 96)

    def test_corrupt_shapes(self):
        bad = [
            None, [], "song", 42,
            {},                                  # no tracks
            {"tracks": []},                      # empty track list
            {"tracks": [{"notes": []}]},         # empty notes
            {"tracks": [{"notes": [{"start": 0, "duration": 1}]}]},  # no note
            {"tracks": [{"notes": [{"note": "C4", "duration": 1}]}]},  # no start
            {"tracks": [{"notes": [{"note": "C4", "start": 0}]}]},  # no duration
            {"tempo": "fast", "tracks": [{"notes": [{"note": "C4",
                                                     "start": 0, "duration": 1}]}]},
        ]
        for b in bad:
            with self.assertRaises(nada.RecipeError, msg=repr(b)[:60]):
                nada.validate_recipe(b)

    def test_bounds(self):
        def with_note(**kw):
            n = {"note": "C4", "start": 0, "duration": 1}
            n.update(kw)
            return recipe(tracks=[{"notes": [n]}])

        for bad in [{"velocity": 0}, {"velocity": 128}, {"velocity": 96.5},
                    {"start": -1}, {"duration": 0}, {"duration": 1 / 7},
                    {"note": "C4", "chord": ["E4"]}]:
            with self.assertRaises(nada.RecipeError, msg=repr(bad)):
                nada.validate_recipe(with_note(**bad))
        for bad_tempo in [0, 9, 601, "fast"]:
            with self.assertRaises(nada.RecipeError):
                nada.validate_recipe(recipe(tempo=bad_tempo))
        with self.assertRaises(nada.RecipeError):
            nada.validate_recipe(recipe(unknown_key=1))
        with self.assertRaises(nada.RecipeError):
            nada.validate_recipe(recipe(tracks=[{"notes": [
                {"note": "C4", "start": 0, "duration": 1,
                 "mystery": True}]}]))

    def test_channel_conflict(self):
        r = recipe(tracks=[
            {"notes": [{"note": "C4", "start": 0, "duration": 1}],
             "channel": 3},
            {"notes": [{"note": "E4", "start": 0, "duration": 1}],
             "channel": 3},
        ])
        with self.assertRaises(nada.RecipeError):
            nada.validate_recipe(r)

    def test_drum_rules(self):
        r = nada.validate_recipe(recipe(tracks=[
            {"drums": True, "notes": [{"note": "kick", "start": 0, "duration": 1}]},
        ]))
        self.assertEqual(r["tracks"][0]["channel"], 9)
        with self.assertRaises(nada.RecipeError):
            nada.validate_recipe(recipe(tracks=[
                {"drums": True, "channel": 2,
                 "notes": [{"note": "kick", "start": 0, "duration": 1}]},
            ]))
        with self.assertRaises(nada.RecipeError):
            nada.validate_recipe(recipe(tracks=[
                {"channel": 9,
                 "notes": [{"note": "C4", "start": 0, "duration": 1}]},
            ]))

    def test_fractional_beats(self):
        r = nada.validate_recipe(recipe(tracks=[{"notes": [
            {"note": "C4", "start": 0.5, "duration": 0.25}]}]))
        self.assertEqual(r["tracks"][0]["notes"][0]["start"], 240)
        self.assertEqual(r["tracks"][0]["notes"][0]["duration"], 120)


class TestBuildAndRoundtrip(unittest.TestCase):
    def test_golden_header(self):
        midi = nada.build_midi(nada.validate_recipe(recipe()))
        self.assertEqual(midi[:14],
                         b"MThd" + struct.pack(">IHHH", 6, 1, 2, 480))
        self.assertEqual(midi.count(b"MTrk"), 2)

    def test_tempo_track(self):
        midi = nada.build_midi(nada.validate_recipe(recipe(tempo=120)))
        smf = nada.parse_midi(midi)
        tempo_track = smf["tracks"][0]["events"]
        tempos = [e for e in tempo_track
                  if e["type"] == "meta" and e["meta_type"] == 0x51]
        self.assertEqual(len(tempos), 1)
        self.assertEqual(tempos[0]["bpm"], 120.0)
        sigs = [e for e in tempo_track
                if e["type"] == "meta" and e["meta_type"] == 0x58]
        self.assertEqual(sigs[0]["data"], bytes([4, 2, 24, 8]))

    def test_roundtrip_events(self):
        src = recipe(tracks=[
            {"name": "melody", "instrument": 40,
             "notes": [
                 {"note": "C4", "start": 0, "duration": 1, "velocity": 100},
                 {"chord": ["E4", "G4"], "start": 1, "duration": 0.5},
             ]},
            {"name": "drums", "drums": True,
             "notes": [{"note": "kick", "start": 0, "duration": 0.25}]},
        ])
        midi = nada.build_midi(nada.validate_recipe(src))
        smf = nada.parse_midi(midi)
        self.assertEqual(smf["format"], 1)
        self.assertEqual(len(smf["tracks"]), 3)

        mel = [e for e in smf["tracks"][1]["events"]
               if e["type"] in ("note_on", "note_off", "program_change")]
        pc = [e for e in mel if e["type"] == "program_change"]
        self.assertEqual((pc[0]["channel"], pc[0]["program"]), (0, 40))
        ons = [(e["tick"], e["pitch"], e["velocity"])
               for e in mel if e["type"] == "note_on"]
        self.assertEqual(ons, [(0, 60, 100), (480, 64, 96), (480, 67, 96)])
        offs = [(e["tick"], e["pitch"]) for e in mel if e["type"] == "note_off"]
        self.assertEqual(offs, [(480, 60), (720, 64), (720, 67)])

        drm = [e for e in smf["tracks"][2]["events"]
               if e["type"] in ("note_on", "note_off", "program_change")]
        self.assertFalse(any(e["type"] == "program_change" for e in drm))
        self.assertEqual([(e["tick"], e["channel"], e["pitch"])
                          for e in drm if e["type"] == "note_on"],
                         [(0, 9, 36)])

    def test_note_off_before_note_on_at_same_tick(self):
        src = recipe(tracks=[{"notes": [
            {"note": "C4", "start": 0, "duration": 1},
            {"note": "C4", "start": 1, "duration": 1}]}])
        midi = nada.build_midi(nada.validate_recipe(src))
        events = [e for e in nada.parse_midi(midi)["tracks"][1]["events"]
                  if e["type"] in ("note_on", "note_off")]
        at_480 = [e["type"] for e in events if e["tick"] == 480]
        self.assertEqual(at_480, ["note_off", "note_on"])

    def test_deterministic_bytes(self):
        src = nada.validate_recipe(recipe())
        self.assertEqual(nada.build_midi(src), nada.build_midi(src))

    def test_parse_corrupt(self):
        for bad in [b"", b"not midi", b"MThd\x00\x00",
                    b"MThd" + struct.pack(">IHHH", 6, 1, 1, 480) + b"MTrk\x00",
                    b"MThd" + struct.pack(">IHHH", 5, 1, 1, 480)]:
            with self.assertRaises(nada.ParseError, msg=repr(bad)[:40]):
                nada.parse_midi(bad)

    @unittest.skipUnless(HAVE_MIDO, "mido not installed")
    def test_mido_crosscheck(self):
        src = nada.validate_recipe(recipe(tracks=[
            {"name": "melody", "instrument": 40,
             "notes": [{"chord": ["C4", "E4"], "start": 0, "duration": 2}]},
            {"name": "drums", "drums": True,
             "notes": [{"note": "kick", "start": 0, "duration": 0.25}]},
        ]))
        midi_bytes = nada.build_midi(src)
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            f.write(midi_bytes)
            path = f.name
        try:
            mf = mido.MidiFile(path)
            self.assertEqual(mf.ticks_per_beat, 480)
            notes = [m for m in mf.tracks[1]
                     if m.type == "note_on" and m.velocity > 0]
            self.assertEqual(sorted(m.note for m in notes), [60, 64])
            tempo = [m for m in mf.tracks[0] if m.type == "set_tempo"]
            self.assertEqual(mido.tempo2bpm(tempo[0].tempo), 120.0)
        finally:
            os.unlink(path)


class TestCli(unittest.TestCase):
    def test_build_and_inspect(self):
        with tempfile.TemporaryDirectory() as d:
            recipe_path = os.path.join(d, "song.json")
            with open(recipe_path, "w", encoding="utf-8") as f:
                json.dump(recipe(), f)
            out = os.path.join(d, "song.mid")
            self.assertEqual(nada.main(["build", recipe_path, "-o", out]), 0)
            self.assertTrue(os.path.getsize(out) > 20)
            self.assertEqual(nada.main(["inspect", out]), 0)

    def test_cli_rejects_bad_recipe(self):
        with tempfile.TemporaryDirectory() as d:
            bad_path = os.path.join(d, "bad.json")
            with open(bad_path, "w", encoding="utf-8") as f:
                f.write("{not json")
            self.assertEqual(nada.main(["build", bad_path]), 2)
            with open(bad_path, "w", encoding="utf-8") as f:
                json.dump({"tracks": [{"notes": [{"note": "C4"}]}]}, f)
            self.assertEqual(nada.main(["build", bad_path]), 2)


if __name__ == "__main__":
    unittest.main()
