#!/usr/bin/env python3
"""nada - deterministic structured music recipe -> Standard MIDI File.

Reads a small JSON recipe (tempo, tracks, notes) and emits a valid
format-1 .mid file. No composition, no network, no randomness: the same
recipe always produces byte-identical output. Python 3.8+ standard
library only.
"""

import argparse
import json
import re
import struct
import sys

VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Limits (deterministic bounds so a broken recipe fails loudly, not hugely)

TICKS_PER_BEAT_DEFAULT = 480
MAX_TRACKS = 64
MAX_NOTES_PER_TRACK = 100_000
MAX_TOTAL_TICKS = 10_000_000
MIN_TEMPO_BPM = 10
MAX_TEMPO_BPM = 600
MAX_NAME_LEN = 128
DRUM_CHANNEL = 9  # General MIDI percussion channel (channel 10, 0-indexed 9)

NOTE_RE = re.compile(r"^([A-Ga-g])(#|b)?(-?\d+)$")
NOTE_BASE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# General MIDI program names, 0-indexed (program change values).
GM_INSTRUMENTS = [
    "Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano",
    "Honky-tonk Piano", "Electric Piano 1", "Electric Piano 2",
    "Harpsichord", "Clavinet", "Celesta", "Glockenspiel", "Music Box",
    "Vibraphone", "Marimba", "Xylophone", "Tubular Bells", "Dulcimer",
    "Drawbar Organ", "Percussive Organ", "Rock Organ", "Church Organ",
    "Reed Organ", "Accordion", "Harmonica", "Tango Accordion",
    "Acoustic Guitar (nylon)", "Acoustic Guitar (steel)",
    "Electric Guitar (jazz)", "Electric Guitar (clean)",
    "Electric Guitar (muted)", "Overdriven Guitar", "Distortion Guitar",
    "Guitar harmonics", "Acoustic Bass", "Electric Bass (finger)",
    "Electric Bass (pick)", "Fretless Bass", "Slap Bass 1", "Slap Bass 2",
    "Synth Bass 1", "Synth Bass 2", "Violin", "Viola", "Cello",
    "Contrabass", "Tremolo Strings", "Pizzicato Strings",
    "Orchestral Harp", "Timpani", "String Ensemble 1", "String Ensemble 2",
    "Synth Strings 1", "Synth Strings 2", "Choir Aahs", "Voice Oohs",
    "Synth Voice", "Orchestra Hit", "Trumpet", "Trombone", "Tuba",
    "Muted Trumpet", "French Horn", "Brass Section", "Synth Brass 1",
    "Synth Brass 2", "Soprano Saxophone", "Alto Saxophone",
    "Tenor Saxophone", "Baritone Saxophone", "Oboe", "English Horn",
    "Bassoon", "Clarinet", "Piccolo", "Flute", "Recorder", "Pan Flute",
    "Blown Bottle", "Shakuhachi", "Whistle", "Ocarina", "Square Lead",
    "Sawtooth Lead", "Calliope Lead", "Chiff Lead", "Charang Lead",
    "Voice Lead", "Fifths Lead", "Bass and Lead", "Synth Pad (new age)",
    "Synth Pad (warm)", "Synth Pad (polysynth)", "Synth Pad (choir)",
    "Synth Pad (bowed)", "Synth Pad (metallic)", "Synth Pad (halo)",
    "Synth Pad (sweep)", "FX (rain)", "FX (soundtrack)", "FX (crystal)",
    "FX (atmosphere)", "FX (brightness)", "FX (goblins)", "FX (echoes)",
    "FX (sci-fi)", "Sitar", "Banjo", "Shamisen", "Koto", "Kalimba",
    "Bagpipe", "Fiddle", "Shanai", "Tinkle Bell", "Agogo", "Steel Drums",
    "Woodblock", "Taiko Drum", "Melodic Tom", "Synth Drum",
    "Reverse Cymbal", "Guitar Fret Noise", "Breath Noise", "Seashore",
    "Bird Tweet", "Telephone Ring", "Helicopter", "Applause", "Gunshot",
]
GM_BY_NAME = {name.lower(): i for i, name in enumerate(GM_INSTRUMENTS)}

# Common drum kit note names (channel 10), a useful subset.
DRUM_NAMES = {
    "kick": 36, "bass drum": 36, "snare": 38, "clap": 39,
    "closed hihat": 42, "open hihat": 46, "crash": 49, "ride": 51,
    "high tom": 50, "mid tom": 47, "low tom": 43, "rimshot": 37,
    "cowbell": 56, "tambourine": 54, "pedal hihat": 44,
}


class RecipeError(ValueError):
    """The recipe is invalid; message names the offending field."""


class ParseError(ValueError):
    """A .mid file is malformed."""


# ---------------------------------------------------------------------------
# Validation

def _err(path, msg):
    raise RecipeError(f"{path}: {msg}")


def _require(cond, path, msg):
    if not cond:
        _err(path, msg)


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check_keys(obj, allowed, path):
    for k in obj:
        if k not in allowed:
            _err(path, f"unknown key {k!r} (allowed: {', '.join(sorted(allowed))})")


def note_to_pitch(value, path):
    """Resolve a note name like C4 / F#3 / Bb5 to a MIDI pitch 0-127 (C4=60)."""
    if isinstance(value, bool):
        _err(path, "must be a note name or integer pitch")
    if isinstance(value, int):
        _require(0 <= value <= 127, path, f"pitch {value} out of range 0-127")
        return value
    if isinstance(value, str):
        m = NOTE_RE.match(value.strip())
        if m:
            letter, accidental, octave = m.group(1).upper(), m.group(2), int(m.group(3))
            pitch = NOTE_BASE[letter] + (1 if accidental == "#" else -1 if accidental == "b" else 0) \
                + 12 * (octave + 1)
            _require(0 <= pitch <= 127, path, f"note {value!r} out of range C-1..G9")
            return pitch
        low = value.strip().lower()
        if low in DRUM_NAMES:
            return DRUM_NAMES[low]
        _err(path, f"unrecognized note {value!r} (use e.g. C4, F#3, Bb5, or 0-127)")
    _err(path, "must be a note name or integer pitch")


def _beats_to_ticks(value, tpb, path):
    _require(_is_number(value), path, "must be a number of beats")
    _require(value >= 0, path, "must be >= 0 beats")
    ticks = value * tpb
    rounded = round(ticks)
    _require(abs(ticks - rounded) < 1e-6, path,
             f"{value} beats is not a whole tick at {tpb} ticks/beat")
    return rounded


def validate_recipe(data):
    """Check a parsed JSON recipe; return a normalized copy."""
    _require(isinstance(data, dict), "recipe", "top level must be a JSON object")
    _check_keys(data, {"title", "tempo", "time_signature", "ticks_per_beat", "tracks"},
                "recipe")
    _require("tracks" in data, "recipe.tracks", "required")
    _require(isinstance(data["tracks"], list) and 1 <= len(data["tracks"]) <= MAX_TRACKS,
             "recipe.tracks", f"must be a list of 1-{MAX_TRACKS} tracks")

    tempo = data.get("tempo", 120)
    _require(_is_number(tempo) and MIN_TEMPO_BPM <= tempo <= MAX_TEMPO_BPM,
             "recipe.tempo", f"must be {MIN_TEMPO_BPM}-{MAX_TEMPO_BPM} bpm")

    sig = data.get("time_signature", [4, 4])
    _require(isinstance(sig, list) and len(sig) == 2
             and isinstance(sig[0], int) and isinstance(sig[1], int),
             "recipe.time_signature", "must be [numerator, denominator]")
    _require(1 <= sig[0] <= 32, "recipe.time_signature[0]", "must be 1-32")
    _require(sig[1] in (1, 2, 4, 8, 16, 32), "recipe.time_signature[1]",
             "denominator must be a power of two (1-32)")

    tpb = data.get("ticks_per_beat", TICKS_PER_BEAT_DEFAULT)
    _require(isinstance(tpb, int) and 24 <= tpb <= 960, "recipe.ticks_per_beat",
             "must be an integer 24-960")

    title = data.get("title", "untitled")
    _require(isinstance(title, str) and 0 < len(title) <= MAX_NAME_LEN,
             "recipe.title", f"must be a string of at most {MAX_NAME_LEN} characters")

    used_channels = {}
    tracks = []
    for i, t in enumerate(data["tracks"]):
        path = f"recipe.tracks[{i}]"
        _require(isinstance(t, dict), path, "must be an object")
        _check_keys(t, {"name", "instrument", "channel", "drums", "notes"}, path)
        _require("notes" in t, f"{path}.notes", "required")
        _require(isinstance(t["notes"], list)
                 and 0 < len(t["notes"]) <= MAX_NOTES_PER_TRACK,
                 f"{path}.notes", f"must be a list of 1-{MAX_NOTES_PER_TRACK} notes")

        drums = t.get("drums", False)
        _require(isinstance(drums, bool), f"{path}.drums", "must be true or false")

        name = t.get("name", f"track {i + 1}")
        _require(isinstance(name, str) and 0 < len(name) <= MAX_NAME_LEN,
                 f"{path}.name", f"must be a string of at most {MAX_NAME_LEN} characters")

        instrument = t.get("instrument", 0)
        if isinstance(instrument, str):
            key = instrument.strip().lower()
            _require(key in GM_BY_NAME, f"{path}.instrument",
                     f"unknown instrument {instrument!r} (see 'nada instruments')")
            instrument = GM_BY_NAME[key]
        else:
            _require(isinstance(instrument, int) and not isinstance(instrument, bool)
                     and 0 <= instrument <= 127,
                     f"{path}.instrument", "must be a General MIDI program 0-127")

        if drums:
            _require("channel" not in t or t["channel"] == DRUM_CHANNEL,
                     f"{path}.channel", f"drums use channel {DRUM_CHANNEL} (omit 'channel')")
            channel = DRUM_CHANNEL
        else:
            channel = t.get("channel")
            if channel is None:
                for c in range(16):
                    if c != DRUM_CHANNEL and c not in used_channels:
                        channel = c
                        break
                else:
                    _err(path, "no free MIDI channel left")
            _require(isinstance(channel, int) and not isinstance(channel, bool)
                     and 0 <= channel <= 15, f"{path}.channel", "must be 0-15")
            _require(channel != DRUM_CHANNEL, f"{path}.channel",
                     f"channel {DRUM_CHANNEL} is reserved for drums")
        if channel in used_channels:
            _err(f"{path}.channel",
                 f"channel {channel} already used by track {used_channels[channel]!r}")
        used_channels[channel] = name

        notes = []
        total_ticks = 0
        for j, n in enumerate(t["notes"]):
            np_ = f"{path}.notes[{j}]"
            _require(isinstance(n, dict), np_, "must be an object")
            _check_keys(n, {"note", "chord", "pitch", "start", "duration", "velocity"}, np_)
            _require("start" in n, f"{np_}.start", "required (beats from song start)")
            _require("duration" in n, f"{np_}.duration", "required (beats)")
            start = _beats_to_ticks(n["start"], tpb, f"{np_}.start")
            dur = _beats_to_ticks(n["duration"], tpb, f"{np_}.duration")
            _require(dur > 0, f"{np_}.duration", "must be > 0 beats")

            velocity = n.get("velocity", 96)
            _require(isinstance(velocity, int) and not isinstance(velocity, bool)
                     and 1 <= velocity <= 127, f"{np_}.velocity", "must be 1-127")

            given = [k for k in ("note", "chord", "pitch") if k in n]
            _require(len(given) == 1, np_, "give exactly one of 'note', 'chord' or 'pitch'")
            pitches = []
            if "chord" in n:
                _require(isinstance(n["chord"], list) and 1 <= len(n["chord"]) <= 16,
                         f"{np_}.chord", "must be a list of 1-16 notes")
                for k, c in enumerate(n["chord"]):
                    pitches.append(note_to_pitch(c, f"{np_}.chord[{k}]"))
            elif "note" in n:
                pitches.append(note_to_pitch(n["note"], f"{np_}.note"))
            else:
                pitches.append(note_to_pitch(n["pitch"], f"{np_}.pitch"))

            notes.append({"pitches": pitches, "start": start, "duration": dur,
                          "velocity": velocity})
            total_ticks = max(total_ticks, start + dur)
        _require(total_ticks <= MAX_TOTAL_TICKS, path,
                 f"song too long (max {MAX_TOTAL_TICKS} ticks)")
        tracks.append({"name": name, "instrument": instrument, "channel": channel,
                       "drums": drums, "notes": notes})
    return {"title": title, "tempo": tempo, "time_signature": sig,
            "ticks_per_beat": tpb, "tracks": tracks}


# ---------------------------------------------------------------------------
# Standard MIDI File writing (format 1)

def vlq(n):
    """Encode a 28-bit integer as a MIDI variable-length quantity."""
    if not 0 <= n <= 0x0FFFFFFF:
        raise ValueError(f"VLQ out of range: {n}")
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)


def _meta(delta, mtype, payload):
    return vlq(delta) + bytes([0xFF, mtype]) + vlq(len(payload)) + payload


def _track_chunk(events):
    """events: list of (tick, priority, bytes). Adds End of Track."""
    events = sorted(events, key=lambda e: (e[0], e[1]))
    body = bytearray()
    last = 0
    for tick, _prio, raw in events:
        body += vlq(tick - last)
        body += raw
        last = tick
    body += _meta(0, 0x2F, b"")  # End of Track
    return b"MTrk" + struct.pack(">I", len(body)) + bytes(body)


def build_midi(recipe):
    """Build format-1 SMF bytes from a validated recipe."""
    tpb = recipe["ticks_per_beat"]
    num, den = recipe["time_signature"]
    den_pow = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4, 32: 5}[den]
    us_per_quarter = round(60_000_000 / recipe["tempo"])

    title_b = recipe["title"].encode("utf-8")
    tempo_events = [
        (0, 0, bytes([0xFF, 0x03]) + vlq(len(title_b)) + title_b),
        (0, 1, bytes([0xFF, 0x58, 0x04, num, den_pow, 24, 8])),
        (0, 2, bytes([0xFF, 0x51, 0x03]) + us_per_quarter.to_bytes(3, "big")),
    ]

    chunks = [_track_chunk(tempo_events)]
    for t in recipe["tracks"]:
        name_b = t["name"].encode("utf-8")
        events = [(0, 0, bytes([0xFF, 0x03]) + vlq(len(name_b)) + name_b)]
        if not t["drums"]:
            events.append((0, 1, bytes([0xC0 | t["channel"], t["instrument"]])))
        for n in t["notes"]:
            for p in n["pitches"]:
                events.append((n["start"], 3,
                               bytes([0x90 | t["channel"], p, n["velocity"]])))
                events.append((n["start"] + n["duration"], 2,
                               bytes([0x80 | t["channel"], p, 64])))
        chunks.append(_track_chunk(events))

    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), tpb)
    return header + b"".join(chunks)


# ---------------------------------------------------------------------------
# Minimal SMF reader (for `inspect` and tests)

def parse_midi(data):
    """Parse SMF bytes; return {format, ticks_per_beat, tracks:[{events:[...]}]}.

    Each event: {tick, type, ...}. Supports running status, meta and SysEx.
    Raises ParseError on malformed input.
    """
    def fail(msg):
        raise ParseError(msg)

    if len(data) < 14 or data[:4] != b"MThd":
        fail("missing MThd header")
    hlen, fmt, ntracks, division = struct.unpack(">IHHH", data[4:14])
    if hlen < 6:
        fail("bad MThd length")
    if division & 0x8000:
        fail("SMPTE time division not supported")
    pos = 8 + hlen
    tracks = []
    for _ in range(ntracks):
        if pos + 8 > len(data) or data[pos:pos + 4] != b"MTrk":
            fail("missing MTrk chunk")
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + length]
        if len(body) != length:
            fail("truncated MTrk chunk")
        pos += 8 + length
        tracks.append(_parse_track(body))
    return {"format": fmt, "ticks_per_beat": division, "tracks": tracks}


def _parse_track(body):
    def fail(msg):
        raise ParseError(msg)

    events = []
    tick = 0
    i = 0
    status = None

    def read_vlq():
        nonlocal i
        value = 0
        for _ in range(4):
            if i >= len(body):
                fail("truncated VLQ")
            b = body[i]
            i += 1
            value = (value << 7) | (b & 0x7F)
            if not b & 0x80:
                return value
        fail("VLQ too long")

    CH_SIZES = {0x8: 2, 0x9: 2, 0xA: 2, 0xB: 2, 0xC: 1, 0xD: 1}
    while i < len(body):
        tick += read_vlq()
        if i >= len(body):
            fail("truncated event")
        b = body[i]
        if b & 0x80:
            status = b
            i += 1
        elif status is None:
            fail("running status without status byte")
        if status == 0xFF:
            if i >= len(body):
                fail("truncated meta event")
            mtype = body[i]
            i += 1
            mlen = read_vlq()
            payload = body[i:i + mlen]
            if len(payload) != mlen:
                fail("truncated meta payload")
            i += mlen
            ev = {"tick": tick, "type": "meta", "meta_type": mtype, "data": payload}
            if mtype == 0x51 and mlen == 3:
                ev["bpm"] = round(60_000_000 / int.from_bytes(payload, "big"), 3)
            if mtype == 0x03:
                ev["name"] = payload.decode("utf-8", "replace")
            events.append(ev)
            if mtype == 0x2F:
                break
        elif status in (0xF0, 0xF7):
            slen = read_vlq()
            if i + slen > len(body):
                fail("truncated sysex")
            events.append({"tick": tick, "type": "sysex", "data": body[i:i + slen]})
            i += slen
        else:
            kind = status >> 4
            if kind not in CH_SIZES:
                fail(f"unsupported status byte 0x{status:02X}")
            need = CH_SIZES[kind]
            if i + need > len(body):
                fail("truncated channel event")
            vals = body[i:i + need]
            i += need
            names = {0x8: "note_off", 0x9: "note_on", 0xA: "poly_aftertouch",
                     0xB: "control_change", 0xC: "program_change",
                     0xD: "channel_aftertouch"}
            ev = {"tick": tick, "type": names[kind], "channel": status & 0x0F}
            if kind in (0x8, 0x9):
                ev.update({"pitch": vals[0], "velocity": vals[1]})
            elif kind == 0xB:
                ev.update({"control": vals[0], "value": vals[1]})
            elif kind == 0xC:
                ev["program"] = vals[0]
            else:
                ev["value"] = vals[0]
            events.append(ev)
    return {"events": events}


# ---------------------------------------------------------------------------
# CLI

def cmd_build(args):
    try:
        with open(args.recipe, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"nada: invalid JSON in {args.recipe}: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"nada: {e}", file=sys.stderr)
        return 2
    try:
        recipe = validate_recipe(data)
        midi = build_midi(recipe)
    except RecipeError as e:
        print(f"nada: invalid recipe: {e}", file=sys.stderr)
        return 2
    out = args.output or recipe["title"].replace(" ", "_") + ".mid"
    try:
        with open(out, "wb") as f:
            f.write(midi)
    except OSError as e:
        print(f"nada: {e}", file=sys.stderr)
        return 2
    note_count = sum(len(t["notes"]) for t in recipe["tracks"])
    total_ticks = max((n["start"] + n["duration"]
                       for t in recipe["tracks"] for n in t["notes"]), default=0)
    beats = total_ticks / recipe["ticks_per_beat"]
    seconds = beats * 60 / recipe["tempo"]
    print(f"nada: wrote {out} "
          f"({len(recipe['tracks'])} tracks, {note_count} notes, "
          f"{beats:g} beats, ~{seconds:.1f}s, {len(midi)} bytes)")
    return 0


def cmd_inspect(args):
    try:
        with open(args.midi_file, "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"nada: {e}", file=sys.stderr)
        return 2
    try:
        smf = parse_midi(data)
    except ParseError as e:
        print(f"nada: invalid MIDI file: {e}", file=sys.stderr)
        return 2
    print(f"format {smf['format']}, {smf['ticks_per_beat']} ticks/beat, "
          f"{len(smf['tracks'])} tracks")
    for ti, tr in enumerate(smf["tracks"]):
        print(f"track {ti}:")
        for ev in tr["events"]:
            desc = ev["type"]
            if ev["type"] == "meta":
                desc = f"meta 0x{ev['meta_type']:02X}"
                if "bpm" in ev:
                    desc += f" tempo={ev['bpm']:g}bpm"
                if "name" in ev:
                    desc += f" name={ev['name']!r}"
            elif ev["type"] in ("note_on", "note_off"):
                desc += f" ch={ev['channel']} pitch={ev['pitch']} vel={ev['velocity']}"
            elif ev["type"] == "program_change":
                desc += f" ch={ev['channel']} program={ev['program']}"
            elif ev["type"] in ("control_change",):
                desc += f" ch={ev['channel']} ctrl={ev['control']} val={ev['value']}"
            print(f"  tick {ev['tick']:>8}  {desc}")
    return 0


def cmd_instruments(_args):
    for i, name in enumerate(GM_INSTRUMENTS):
        print(f"{i:3d}  {name}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="nada",
        description="Deterministic structured music recipe -> Standard MIDI file.")
    parser.add_argument("--version", action="version", version=f"nada {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="build a .mid file from a JSON recipe")
    b.add_argument("recipe", help="path to the JSON recipe")
    b.add_argument("-o", "--output", help="output .mid path (default: <title>.mid)")
    b.set_defaults(func=cmd_build)
    i = sub.add_parser("inspect", help="print the events inside a .mid file")
    i.add_argument("midi_file")
    i.set_defaults(func=cmd_inspect)
    ins = sub.add_parser("instruments", help="list General MIDI instrument names")
    ins.set_defaults(func=cmd_instruments)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
