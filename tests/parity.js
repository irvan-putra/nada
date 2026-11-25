// Parity check: web/nada.js must produce byte-identical .mid output to
// nada.py for every fixture in examples/. Run: node tests/parity.js
"use strict";
const fs = require("fs");
const path = require("path");
const os = require("os");
const { execFileSync } = require("child_process");
const nada = require(path.join(__dirname, "..", "web", "nada.js"));

const repoRoot = path.join(__dirname, "..");
const pythonCmd = process.platform === "win32" ? "python" : "python3";

let failed = false;
const dir = path.join(__dirname, "..", "examples");
const fixtures = fs.readdirSync(dir).filter(f => f.endsWith(".json")).sort();
for (const f of fixtures) {
  const text = fs.readFileSync(path.join(dir, f), "utf8");
  const recipe = nada.validateRecipe(JSON.parse(text));
  const jsBytes = Buffer.from(nada.buildMidi(recipe));

  const tmpOut = path.join(os.tmpdir(), f.replace(/\.json$/, "") + ".py.mid");
  try {
    execFileSync(pythonCmd, ["nada.py", "build", path.join("examples", f), "-o", tmpOut], {
      cwd: repoRoot,
    });
    const pyBytes = fs.readFileSync(tmpOut);
    fs.unlinkSync(tmpOut);

    if (!jsBytes.equals(pyBytes)) {
      failed = true;
      const offset = jsBytes.findIndex((b, i) => b !== pyBytes[i]);
      console.log(`parity mismatch ${f}: first diff at byte offset ${offset}`);
    } else {
      console.log(`parity ok ${f} ${jsBytes.length} bytes`);
    }
  } catch (err) {
    failed = true;
    console.log(`parity error ${f}: ${err.message}`);
  }
}

console.log(failed ? "PARITY FAILED" : "PARITY OK");
process.exit(failed ? 1 : 0);
