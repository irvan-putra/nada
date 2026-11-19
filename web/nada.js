/* nada - deterministic structured music recipe -> Standard MIDI File.
 * Browser/Node port of nada.py. Same recipe schema, byte-identical output.
 * No dependencies. */
"use strict";
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.nada = factory();
})(typeof self !== "undefined" ? self : this, function () {

  const VERSION = "0.1.0";
  const TICKS_PER_BEAT_DEFAULT = 480;
  const MAX_TRACKS = 64;
  const MAX_NOTES_PER_TRACK = 100000;
  const MAX_TOTAL_NOTES = 200000;    // across all tracks
  const MAX_PITCH_EVENTS = 1000000;  // notes x chord pitches, bounds CPU and output size
  const MAX_RECIPE_BYTES = 4 * 1024 * 1024;  // JSON input size
  const MAX_TOTAL_TICKS = 10000000;
  const MIN_TEMPO_BPM = 10;
  const MAX_TEMPO_BPM = 600;
  const MAX_NAME_LEN = 128;
  const DRUM_CHANNEL = 9;

  const NOTE_RE = /^([A-Ga-g])(#|b)?(-?\d+)$/;
  const NOTE_BASE = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

  const GM_INSTRUMENTS = [
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
  ];
  const GM_BY_NAME = {};
  GM_INSTRUMENTS.forEach((n, i) => { GM_BY_NAME[n.toLowerCase()] = i; });

  const DRUM_NAMES = {
    "kick": 36, "bass drum": 36, "snare": 38, "clap": 39,
    "closed hihat": 42, "open hihat": 46, "crash": 49, "ride": 51,
    "high tom": 50, "mid tom": 47, "low tom": 43, "rimshot": 37,
    "cowbell": 56, "tambourine": 54, "pedal hihat": 44,
  };

  class RecipeError extends Error {}

  function err(path, msg) { throw new RecipeError(`${path}: ${msg}`); }
  function require_(cond, path, msg) { if (!cond) err(path, msg); }
  function isNumber(x) { return typeof x === "number" && !Number.isNaN(x); }

  function checkKeys(obj, allowed, path) {
    for (const k of Object.keys(obj)) {
      if (!allowed.includes(k)) {
        err(path, `unknown key '${k}' (allowed: ${allowed.slice().sort().join(", ")})`);
      }
    }
  }

  function noteToPitch(value, path) {
    if (typeof value === "boolean") err(path, "must be a note name or integer pitch");
    if (Number.isInteger(value)) {
      require_(value >= 0 && value <= 127, path, `pitch ${value} out of range 0-127`);
      return value;
    }
    if (typeof value === "string") {
      const m = NOTE_RE.exec(value.trim());
      if (m) {
        const letter = m[1].toUpperCase();
        const acc = m[2];
        const octave = parseInt(m[3], 10);
        const pitch = NOTE_BASE[letter] + (acc === "#" ? 1 : acc === "b" ? -1 : 0)
          + 12 * (octave + 1);
        require_(pitch >= 0 && pitch <= 127, path, `note '${value}' out of range C-1..G9`);
        return pitch;
      }
      const low = value.trim().toLowerCase();
      if (low in DRUM_NAMES) return DRUM_NAMES[low];
      err(path, `unrecognized note '${value}' (use e.g. C4, F#3, Bb5, or 0-127)`);
    }
    err(path, "must be a note name or integer pitch");
  }

  function beatsToTicks(value, tpb, path) {
    require_(isNumber(value), path, "must be a number of beats");
    require_(value >= 0, path, "must be >= 0 beats");
    const ticks = value * tpb;
    const rounded = Math.round(ticks);
    require_(Math.abs(ticks - rounded) < 1e-6, path,
      `${value} beats is not a whole tick at ${tpb} ticks/beat`);
    return rounded;
  }

  function validateRecipe(data) {
    require_(data !== null && typeof data === "object" && !Array.isArray(data),
      "recipe", "top level must be a JSON object");
    checkKeys(data, ["title", "tempo", "time_signature", "ticks_per_beat", "tracks"],
      "recipe");
    require_("tracks" in data, "recipe.tracks", "required");
    require_(Array.isArray(data.tracks) && data.tracks.length >= 1
      && data.tracks.length <= MAX_TRACKS,
      "recipe.tracks", `must be a list of 1-${MAX_TRACKS} tracks`);

    const tempo = data.tempo === undefined ? 120 : data.tempo;
    require_(isNumber(tempo) && tempo >= MIN_TEMPO_BPM && tempo <= MAX_TEMPO_BPM,
      "recipe.tempo", `must be ${MIN_TEMPO_BPM}-${MAX_TEMPO_BPM} bpm`);

    const sig = data.time_signature === undefined ? [4, 4] : data.time_signature;
    require_(Array.isArray(sig) && sig.length === 2
      && Number.isInteger(sig[0]) && Number.isInteger(sig[1]),
      "recipe.time_signature", "must be [numerator, denominator]");
    require_(sig[0] >= 1 && sig[0] <= 32, "recipe.time_signature[0]", "must be 1-32");
    require_([1, 2, 4, 8, 16, 32].includes(sig[1]), "recipe.time_signature[1]",
      "denominator must be a power of two (1-32)");

    const tpb = data.ticks_per_beat === undefined
      ? TICKS_PER_BEAT_DEFAULT : data.ticks_per_beat;
    require_(Number.isInteger(tpb) && tpb >= 24 && tpb <= 960,
      "recipe.ticks_per_beat", "must be an integer 24-960");

    const title = data.title === undefined ? "untitled" : data.title;
    require_(typeof title === "string" && title.length > 0
      && title.length <= MAX_NAME_LEN,
      "recipe.title", `must be a string of at most ${MAX_NAME_LEN} characters`);

    const usedChannels = {};
    const tracks = [];
    let totalNotesAll = 0;
    let totalPitchEvents = 0;
    data.tracks.forEach((t, i) => {
      const path = `recipe.tracks[${i}]`;
      require_(t !== null && typeof t === "object" && !Array.isArray(t),
        path, "must be an object");
      checkKeys(t, ["name", "instrument", "channel", "drums", "notes"], path);
      require_("notes" in t, `${path}.notes`, "required");
      require_(Array.isArray(t.notes) && t.notes.length >= 1
        && t.notes.length <= MAX_NOTES_PER_TRACK,
        `${path}.notes`, `must be a list of 1-${MAX_NOTES_PER_TRACK} notes`);

      const drums = t.drums === undefined ? false : t.drums;
      require_(typeof drums === "boolean", `${path}.drums`, "must be true or false");

      const name = t.name === undefined ? `track ${i + 1}` : t.name;
      require_(typeof name === "string" && name.length > 0
        && name.length <= MAX_NAME_LEN,
        `${path}.name`, `must be a string of at most ${MAX_NAME_LEN} characters`);

      let instrument = t.instrument === undefined ? 0 : t.instrument;
      if (typeof instrument === "string") {
        const key = instrument.trim().toLowerCase();
        require_(key in GM_BY_NAME, `${path}.instrument`,
          `unknown instrument '${instrument}' (see instrument list)`);
        instrument = GM_BY_NAME[key];
      } else {
        require_(Number.isInteger(instrument) && instrument >= 0 && instrument <= 127,
          `${path}.instrument`, "must be a General MIDI program 0-127");
      }

      let channel;
      if (drums) {
        require_(t.channel === undefined || t.channel === DRUM_CHANNEL,
          `${path}.channel`, `drums use channel ${DRUM_CHANNEL} (omit 'channel')`);
        channel = DRUM_CHANNEL;
      } else {
        channel = t.channel === undefined ? null : t.channel;
        if (channel === null) {
          for (let c = 0; c < 16; c++) {
            if (c !== DRUM_CHANNEL && !(c in usedChannels)) { channel = c; break; }
          }
          if (channel === null) err(path, "no free MIDI channel left");
        }
        require_(Number.isInteger(channel) && channel >= 0 && channel <= 15,
          `${path}.channel`, "must be 0-15");
        require_(channel !== DRUM_CHANNEL, `${path}.channel`,
          `channel ${DRUM_CHANNEL} is reserved for drums`);
      }
      if (channel in usedChannels) {
        err(`${path}.channel`,
          `channel ${channel} already used by track '${usedChannels[channel]}'`);
      }
      usedChannels[channel] = name;

      const notes = [];
      let totalTicks = 0;
      t.notes.forEach((n, j) => {
        const np = `${path}.notes[${j}]`;
        require_(n !== null && typeof n === "object" && !Array.isArray(n),
          np, "must be an object");
        checkKeys(n, ["note", "chord", "pitch", "start", "duration", "velocity"], np);
        require_("start" in n, `${np}.start`, "required (beats from song start)");
        require_("duration" in n, `${np}.duration`, "required (beats)");
        const start = beatsToTicks(n.start, tpb, `${np}.start`);
        const dur = beatsToTicks(n.duration, tpb, `${np}.duration`);
        require_(dur > 0, `${np}.duration`, "must be > 0 beats");

        const velocity = n.velocity === undefined ? 96 : n.velocity;
        require_(Number.isInteger(velocity) && velocity >= 1 && velocity <= 127,
          `${np}.velocity`, "must be 1-127");

        const given = ["note", "chord", "pitch"].filter(k => k in n);
        require_(given.length === 1, np, "give exactly one of 'note', 'chord' or 'pitch'");
        const pitches = [];
        if ("chord" in n) {
          require_(Array.isArray(n.chord) && n.chord.length >= 1 && n.chord.length <= 16,
            `${np}.chord`, "must be a list of 1-16 notes");
          n.chord.forEach((c, k) => pitches.push(noteToPitch(c, `${np}.chord[${k}]`)));
        } else if ("note" in n) {
          pitches.push(noteToPitch(n.note, `${np}.note`));
        } else {
          pitches.push(noteToPitch(n.pitch, `${np}.pitch`));
        }
        notes.push({ pitches, start, duration: dur, velocity });
        totalTicks = Math.max(totalTicks, start + dur);
      });
      require_(totalTicks <= MAX_TOTAL_TICKS, path,
        `song too long (max ${MAX_TOTAL_TICKS} ticks)`);
      totalNotesAll += notes.length;
      require_(totalNotesAll <= MAX_TOTAL_NOTES, path,
        `too many notes in total (max ${MAX_TOTAL_NOTES})`);
      totalPitchEvents += notes.reduce((s, n) => s + n.pitches.length, 0);
      require_(totalPitchEvents <= MAX_PITCH_EVENTS, path,
        `too many pitched events in total (max ${MAX_PITCH_EVENTS})`);
      tracks.push({ name, instrument, channel, drums, notes });
    });
    return { title, tempo, time_signature: sig, ticks_per_beat: tpb, tracks };
  }

  // --- SMF writer ---

  function vlq(n) {
    if (!Number.isInteger(n) || n < 0 || n > 0x0FFFFFFF) {
      throw new Error(`VLQ out of range: ${n}`);
    }
    const out = [n & 0x7F];
    n = Math.floor(n / 128);
    while (n) {
      out.unshift((n & 0x7F) | 0x80);
      n = Math.floor(n / 128);
    }
    return out;
  }

  function trackChunk(events) {
    events.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const body = [];
    let last = 0;
    for (const [tick, , raw] of events) {
      body.push(...vlq(tick - last), ...raw);
      last = tick;
    }
    body.push(0x00, 0xFF, 0x2F, 0x00); // End of Track
    const chunk = [0x4D, 0x54, 0x72, 0x6B, // "MTrk"
      (body.length >>> 24) & 0xFF, (body.length >>> 16) & 0xFF,
      (body.length >>> 8) & 0xFF, body.length & 0xFF, ...body];
    return chunk;
  }

  function textMeta(type, text) {
    const bytes = Array.from(new TextEncoder().encode(text));
    return [0xFF, type, ...vlq(bytes.length), ...bytes];
  }

  function buildMidi(recipe) {
    const tpb = recipe.ticks_per_beat;
    const [num, den] = recipe.time_signature;
    const denPow = { 1: 0, 2: 1, 4: 2, 8: 3, 16: 4, 32: 5 }[den];
    const usPerQuarter = Math.round(60000000 / recipe.tempo);

    const tempoEvents = [
      [0, 0, textMeta(0x03, recipe.title)],
      [0, 1, [0xFF, 0x58, 0x04, num, denPow, 24, 8]],
      [0, 2, [0xFF, 0x51, 0x03,
        (usPerQuarter >>> 16) & 0xFF, (usPerQuarter >>> 8) & 0xFF,
        usPerQuarter & 0xFF]],
    ];

    const chunks = [trackChunk(tempoEvents)];
    for (const t of recipe.tracks) {
      const events = [[0, 0, textMeta(0x03, t.name)]];
      if (!t.drums) events.push([0, 1, [0xC0 | t.channel, t.instrument]]);
      for (const n of t.notes) {
        for (const p of n.pitches) {
          events.push([n.start, 3, [0x90 | t.channel, p, n.velocity]]);
          events.push([n.start + n.duration, 2, [0x80 | t.channel, p, 64]]);
        }
      }
      chunks.push(trackChunk(events));
    }

    const ntracks = chunks.length;
    return new Uint8Array([
      0x4D, 0x54, 0x68, 0x64, // "MThd"
      0, 0, 0, 6,
      0, 1, // format 1
      (ntracks >>> 8) & 0xFF, ntracks & 0xFF,
      (tpb >>> 8) & 0xFF, tpb & 0xFF,
      ...chunks.flat(),
    ]);
  }

  return { VERSION, GM_INSTRUMENTS, DRUM_NAMES, RecipeError,
    validateRecipe, buildMidi, vlq, noteToPitch, MAX_RECIPE_BYTES };
});
