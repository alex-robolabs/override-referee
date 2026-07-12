# Facilitator key: Override Referee lab (Thursday, ~25 min)

For Iniya. Everything here was verified live at build time on the real manual, the real embedding model, and the real search code. The two-line launch pitch:

> "Monday your agent could check a battery. Today it reads the 139-page rulebook that no AI on Earth has ever seen, and by the end you will have measured, not argued, that it works."

## Timing (25 min)

| Act | Minutes | Beat to land |
|---|---|---|
| Setup | 3 | key from projector, or Enter for replay mode |
| Act 0 | 2 | the model lies about yellow pins, manual proves it |
| Act 1 | 4 | keyword search works, then whiffs on "how tall" |
| Act 2 | 5 | the same question finds <SG3>; Tuesday's map, working |
| Act 3 | 7 | the agent searches TWICE for the midfield question |
| Act 4 | 4 | the table: keyword 3/8, semantic 8/8 |

Wrap and QR reveal ride on the closing slide. Running long: skip Act 1's warmup cell (go straight to break-it). Challenges are never run live from the front.

## Before students arrive

- Run the whole notebook once yourself with the class key. Confirm `gemini-flash-latest` still resolves (it is pinned in the Setup cell; swap there if Google renamed it).
- Class key on the projector, same flow as Monday (aistudio.google.com, billing enabled, budget alert, delete Friday).
- The `sentence-transformers` install takes about 40 s on a fresh Colab runtime and the embedding model is a ~90 MB one-time download per runtime. Narrate over it: "the model that draws the meaning map is downloading; it will embed the whole rulebook in seconds."
- Colab requires personal Google accounts (school accounts sometimes block it), same as Monday.

## Replay mode is a feature

No key, dead wifi, or a 429 storm: re-run Setup and press Enter at the key prompt. Acts 0 and 3 print runs recorded earlier from the real model, clearly labeled. Acts 1, 2 and 4 never touch the API; the eval always runs live. Every teaching beat survives offline except the thrill of a live agent.

If the API rate-limits mid-class (429s): have tables run one at a time for a minute; it clears fast.

## Checkpoints to call from the front

1. "Everyone seen the model lie about yellow pins?" (Act 0)
2. "Everyone broken keyword search?" (Act 1)
3. "Everyone seen SG3 come back?" (Act 2)
4. "Everyone watched it search twice?" (Act 3)
5. "Everyone's table shows 3 versus 8?" (Act 4)

## Expected numbers (verified live at build time, 2026-07-11)

- Eval: keyword **3/8**, semantic **8/8**, hit-at-top-3.
- Yellow pin = 10 points (owned), alliance pin = 5, autonomous bonus = 12, robot in midfield = 8. Scoring table, manual p. 25.
- Break-it question "How tall can my robot get during a match?": keyword returns GG3/GG15/R2 (all wrong), semantic returns <SG3> first at ~0.66 similarity. The rule: 50 inch limit, manual p. 31.
- Act 0, tested 9 times across 3 questions on `gemini-flash-latest`: 9/9 failures. Asked about SG6 it denies Override exists, decides you mean Over Under (2023-2024), and recites a fabricated rule about goals and Triballs, with penalties. That exact recorded answer ships as the replay.
- Act 3 star question ("leaning over the midfield at the buzzer"): verified 3 runs out of 3 with EXACTLY two search_rules calls, both phrased as natural questions, final answer citing <SC6> and the 8 point value. The persona forces one search per sub-question; the tool description asks for natural-question queries (keyword-soup queries retrieve worse and cause extra searches).

## Two gotchas found live (read before reusing Monday's code)

1. **Gemini now signs tool calls.** Current `gemini-flash-latest` returns a `thought_signature` inside each tool call and 400-errors if your next request echoes the assistant message without it. Monday's notebook rebuilt that message dict by hand, which strips the signature: that pattern now BREAKS mid-loop. Thursday's loop does `messages.append(msg)` (hand the model's message straight back). If you reuse Monday's agent cell anywhere, apply the same fix.
2. **Thinking latency.** Each agent call can take 15-40 s because the model reasons before acting. The Act 3 star run takes about 1-2 minutes live. Narrate the PLAN/ACT/OBSERVE lines as they stream; the wait is the demo.

## Challenge answer key

**⭐ C1 (fool keyword search), verified examples:**
- "Can I pull scoring objects out of the other alliance's goal?" (governing rule <SG9>, keyword misses)
- "Does my robot's code have to use the competition template?" (<R9>, keyword misses)
- Not valid: "Our robot tipped over, can a person reach into the field to fix it?" (keyword finds <GG4>: "field" and "match" overlap enough).

**⭐⭐ C2 (fool semantic search), verified examples:**
- "Is it legal to hold an opposing robot in place all match?": top hit is the Head-to-Head Match definition. Why: embeddings average the sentence; *match* is the loudest noun, and short definition chunks sit very close to short questions.
- "How long is the autonomous period?": the Autonomous Period definition outranks the Match Timing chunk that actually contains 0:15. Same disease: the definition IS the query's noun phrase, so it wins.

**⭐⭐ C4 (hard citations):** append to `REFEREE_PERSONA`:
> "If your draft answer contains no rule ID in angle brackets, do not send it: search again with different words, and if two searches still do not answer, reply exactly 'not covered by the manual'."
Walkie talkie test: should end at <R18> Prohibited Items or "not covered by the manual". Either is a win; discuss which is better.

**⭐⭐⭐ C5 (eval-driven development), verified:** adding `("Are points counted the moment the match ends?", ["SC1"])` drops semantic to 8/9. Fixing SC1's title to "When points are counted: scores are evaluated the moment the Match ends, after everything settles" and re-running the Act 2 embed cell then the eval brings it to 9/9. If asked why re-embedding is needed: the map does not move until you re-place the point.

## Common snags

- Key pasted with a trailing space: re-run Setup.
- Student edited a search function and got NameError: Runtime → Run all.
- A pair stuck on challenges: they are optional, say so out loud.
- Fresh-runtime Run All measured at well under 3 minutes including installs, model download, and rules fetch.

## Fast-finisher easter egg (metadata filtering in one beat)

Setup filtered out 39 VEX U chunks. Have fast pairs set `CHUNKS = ALL_CHUNKS`, re-run the embed cell, and ask "how long is the autonomous period?": a VEX U answer (<VUT4>/<VUT5>, 0:30 and 1:30) can pollute the V5RC answer (0:15 and 1:45). Then put the filter back. That is metadata filtering, the thing every production retrieval system does.

---

Game Manual text © 2026 VEX Robotics, Inc. Used with permission for educational purposes at Robolabs Summer Academy.
