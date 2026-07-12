// Build-time: embed every V5RC chunk of rules.json with the SAME quantized
// model the web app runs in the browser (transformers.js, q8), so shipped
// vectors and live query vectors come from one model.
//
//   npm install
//   node build_embeddings.mjs        -> writes embeddings.json
//
// Game Manual text (c) 2026 VEX Robotics, Inc. Used with permission for
// educational purposes at Robolabs Summer Academy.

import { pipeline } from "@huggingface/transformers";
import { readFileSync, writeFileSync } from "node:fs";

const MODEL = "Xenova/all-MiniLM-L6-v2";
const DTYPE = "q8"; // must match the dtype used in index.html

const rules = JSON.parse(readFileSync("rules.json", "utf8"));
const chunks = rules.filter((c) => c.program === "V5RC");
const texts = chunks.map((c) => `${c.id}: ${c.title} ${c.text}`);

console.log(`Embedding ${chunks.length} V5RC chunks with ${MODEL} (${DTYPE})`);
const embed = await pipeline("feature-extraction", MODEL, { dtype: DTYPE });

const vectors = [];
for (let i = 0; i < texts.length; i++) {
  const out = await embed(texts[i], { pooling: "mean", normalize: true });
  vectors.push(Array.from(out.data).map((x) => Math.round(x * 1e5) / 1e5));
  if ((i + 1) % 50 === 0) console.log(`  ${i + 1}/${texts.length}`);
}

const payload = {
  model: MODEL,
  dtype: DTYPE,
  dim: vectors[0].length,
  ids: chunks.map((c) => c.id),
  vectors,
};
writeFileSync("embeddings.json", JSON.stringify(payload));
console.log(`Wrote embeddings.json (${vectors.length} x ${payload.dim})`);
