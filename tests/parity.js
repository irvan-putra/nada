// Parity check: web/nada.js must produce byte-identical .mid output to
// nada.py for every fixture in examples/. Run: node tests/parity.js
"use strict";
const fs = require("fs");
const path = require("path");
const nada = require(path.join(__dirname, "..", "web", "nada.js"));

let failed = false;
const dir = path.join(__dirname, "..", "examples");
for (const f of fs.readdirSync(dir).filter(f => f.endsWith(".json")).sort()) {
  const text = fs.readFileSync(path.join(dir, f), "utf8");
  const recipe = nada.validateRecipe(JSON.parse(text));
  const bytes = Buffer.from(nada.buildMidi(recipe));
  const out = path.join("/tmp", f.replace(/\.json$/, ".js.mid"));
  fs.writeFileSync(out, bytes);
  console.log("wrote", out, bytes.length, "bytes");
}
process.exit(failed ? 1 : 0);
