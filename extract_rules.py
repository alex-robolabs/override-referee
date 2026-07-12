"""Build-time extractor: parses the VEX V5RC Override Game Manual PDF into rules.json.

Run once at build time. The lab notebook and the web app never parse the PDF;
they consume rules.json.

Usage:  python extract_rules.py [path-to-manual.pdf]

Output: rules.json, a list of chunks:
  {id, family, section, title, text, page, program}

How rules are detected (the manual's typography makes this reliable):
- A rule starts on a LINE that begins with a BOLD <ID> marker, e.g. <SG3>.
  Plain cross references like "See <T16>" are regular weight.
- Two extra guards kill bold false positives (some callout notes are fully
  bold and can wrap so a line starts with a bold <ID>): the family must be
  one that lives in the current manual section, and the rule number must be
  exactly the next number for that family (rules appear in order).
- The rule title is the bold run that follows the marker (it may wrap onto
  following lines); the body is everything until the next rule starts.
- Page furniture (copyright header), section headings, and figure captions
  are dropped.
- Diagram label fragments are dropped by geometry: text inside or just below
  a cluster of large images is figure annotation, and narrow left-margin
  blocks are kept only when they continue a kept block right above them.
  Every dropped block is printed in an audit log for eyeball review.

Game definitions ship as family "DEF": the Appendix B glossary, the VURC
definitions (program VEXU), and one hand-transcribed chunk for the Scoring
table on page 25, which lives outside any numbered rule in the manual.

`page` is the 1-based PDF page number (what a PDF viewer's go-to-page uses).
Typography is normalized for retrieval: soft hyphens joined, list glyphs
standardized to "-", em and en dashes transcribed as " - " or "-".

Game Manual text (c) 2026 VEX Robotics, Inc. Used with permission for
educational purposes at Robolabs Summer Academy.
"""

import json
import re
import sys
from collections import Counter

import fitz  # PyMuPDF

_args = [a for a in sys.argv[1:] if not a.startswith("-")]
PDF_PATH = _args[0] if _args else "v5rc-override-1.0.pdf"
OUT_PATH = "rules.json"

# 1-based inclusive PDF page ranges (from the manual's table of contents),
# with the rule families that live in each section.
RULE_SECTIONS = [
    ((25, 29), "Scoring", {"SC"}),
    ((30, 36), "Specific Game Rules", {"SG"}),
    ((37, 37), "Safety Rules", {"S"}),
    ((38, 43), "General Rules", {"G"}),
    ((44, 52), "General Game Rules", {"GG"}),
    ((53, 57), "Robot Skills Challenge Rules", {"RSC"}),
    ((58, 71), "Inspection Rules", {"R"}),
    ((72, 85), "Tournament Rules", {"T"}),
    ((86, 102), "VEX U", {"VUR", "VUG", "VURS", "VUT"}),
]
GLOSSARY_PAGES = (120, 131)  # Appendix B - Glossary of Terms

VU_FAMILIES = {"VUR", "VUG", "VURS", "VUT"}

RULE_START = re.compile(r"^<([A-Z]{1,4})(\d{1,2})>")
TERM_DASH = re.compile(r"^(.{2,60}?) - \S")
FURNITURE_PREFIXES = (
    "VEX V5 Robotics Competition Override - Game Manual",
    "Copyright 2026, Innovation First",
    "Version 1.0 - Released",
    "Unauthorized copying",
    "Unauthorized use",
    "Appendix B - Glossary of Terms",
)
BOLD_FLAG = 16


def normalize(text):
    """Typographic cleanup so chunks embed and display well."""
    text = text.replace("­", "")     # stray soft hyphens
    text = text.replace("—", " - ")  # em dash, transcribed
    text = text.replace("–", "-")    # en dash, transcribed
    for glyph in ("●", "०", "॰", "▪", "•"):
        text = text.replace(glyph, "-")
    text = re.sub(r"[ \t ]+", " ", text)
    return text.strip()


def join_wrapped(acc, line_text):
    """Append a wrapped line, healing soft-hyphen and hyphen breaks."""
    if not acc:
        return line_text
    if acc.endswith("­"):
        return acc[:-1] + line_text
    if acc.endswith("-") and line_text[:1].islower():
        return acc + line_text
    return acc + " " + line_text


class Line:
    """One rendered line: its text plus span-level bold info."""

    def __init__(self, spans):
        self.spans = [(s["text"], bool(s["flags"] & BOLD_FLAG)) for s in spans]
        self.text = "".join(s["text"] for s in spans)
        self.max_size = max((s["size"] for s in spans), default=0)

    def leading_bold(self):
        """Text of the bold run at the start of the line."""
        parts = []
        for text, bold in self.spans:
            if bold or (text.strip() == "" and parts):
                parts.append(text)
            else:
                break
        return "".join(parts)

    def starts_bold(self):
        for text, bold in self.spans:
            if text.strip():
                return bold
        return False


DROPPED = []  # audit log: (page_no, reason, text)


def image_clusters(page):
    """Bounding rects of large-image groups (figures with their diagrams)."""
    rects = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") == 1:
            x0, y0, x1, y1 = block["bbox"]
            if x1 - x0 >= 120 and y1 - y0 >= 80:
                rects.append([x0, y0, x1, y1])
    # merge rects that overlap vertically (side-by-side figure rows)
    merged = True
    while merged:
        merged = False
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, b = rects[i], rects[j]
                if a[1] <= b[3] and b[1] <= a[3]:  # y ranges overlap
                    rects[i] = [min(a[0], b[0]), min(a[1], b[1]),
                                max(a[2], b[2]), max(a[3], b[3])]
                    del rects[j]
                    merged = True
                    break
            if merged:
                break
    return rects


def in_figure_zone(bbox, clusters):
    """Inside a figure cluster's span, or in the label band under it."""
    x0, y0, x1, y1 = bbox
    for cx0, cy0, cx1, cy1 in clusters:
        if (x0 >= cx0 - 15 and x1 <= cx1 + 15
                and y0 >= cy0 - 5 and y0 <= cy1 + 45):
            return True
    return False


def page_blocks(page, page_no, chunk_open):
    """Text blocks as lists of Lines, with furniture, captions, and figure
    annotations removed. `chunk_open`: a rule/definition is mid-accumulation
    when the page starts, so a narrow continuation at the page top is real.
    """
    clusters = image_clusters(page)
    kept_bottom = 95 if chunk_open else None  # y1 of the last kept block
    # NOTE: keep the PDF's natural content-stream order. It is correct
    # reading order for body text (rules arrive strictly in sequence), and
    # floats (captions, boxes) trail behind, where the downward-only chain
    # test below rejects them.
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        lines = [Line(line["spans"]) for line in block["lines"]]
        lines = [l for l in lines if l.text.strip()]
        if not lines:
            continue
        first = normalize(lines[0].text)
        if first.startswith(FURNITURE_PREFIXES):
            continue
        if re.fullmatch(r"[A-D]?\d{1,3}", first):  # printed page numbers
            continue
        if first.startswith("Figure "):            # captions reference images
            DROPPED.append((page_no, "caption", first[:70]))
            continue

        x0, y0, x1, y1 = block["bbox"]
        width = x1 - x0
        # A rule can start mid-block (blocks merge across paragraph breaks),
        # so scan every line for a bold marker before geometry can drop it.
        anchor = bool(TERM_DASH.match(first) and lines[0].starts_bold())
        if not anchor:
            anchor = any(RULE_START.match(l.leading_bold().lstrip())
                         for l in lines)
        if not anchor:
            if in_figure_zone(block["bbox"], clusters):
                DROPPED.append((page_no, "figure-zone", first[:70]))
                continue
            # Block boxes overlap ~20pt vertically (generous line leading),
            # so in-flow continuations sit at delta -25..40 from the last
            # kept block; floats (captions, labels) jump much further back.
            wide = width > 380
            chained = (kept_bottom is not None
                       and -25 <= y0 - kept_bottom < 40)
            if not (x0 <= 100 and (wide or chained)):
                DROPPED.append((page_no, "floating", first[:70]))
                continue
        kept_bottom = y1
        yield lines


def parse_rules(doc):
    """Walk the rule sections line by line."""
    rules = []
    current = None       # rule being accumulated
    collecting_title = False
    next_number = {}     # family -> expected next rule number

    def finalize():
        nonlocal current, collecting_title
        if current is not None:
            current["title"] = normalize(current["title"])
            current["text"] = normalize(current["text"])
            if not current["text"]:      # a rule that is all bold title
                current["text"] = current["title"]
            if len(current["title"]) < 10:
                # A few rules (SC3, SC7, SC8) have no bold title in the
                # manual: use the first sentence of the rule text.
                text = current["text"]
                cut = min((i for i in (text.find(". ", 20), text.find(": ", 20))
                           if i != -1), default=-1)
                sentence = text[:cut + 1] if cut != -1 else text
                if len(sentence) > 140:
                    sentence = sentence[:120].rsplit(" ", 1)[0] + "..."
                current["title"] = sentence
                if cut != -1 and cut + 2 < len(text) and len(text) > 180:
                    current["text"] = text[cut + 2:]
            rules.append(current)
        current, collecting_title = None, False

    for (start, end), section, families in RULE_SECTIONS:
        for page_no in range(start, end + 1):
            for lines in page_blocks(doc[page_no - 1], page_no,
                                     current is not None):
                for line in lines:
                    if line.max_size >= 14:  # section headings
                        finalize()
                        continue
                    stripped = line.text.lstrip()
                    bold_run = line.leading_bold().lstrip()
                    marker = RULE_START.match(stripped)
                    if (marker and RULE_START.match(bold_run)
                            and marker.group(1) in families
                            and int(marker.group(2))
                                == next_number.get(marker.group(1), 1)):
                        finalize()
                        family = marker.group(1)
                        next_number[family] = int(marker.group(2)) + 1
                        current = {
                            "id": f"{family}{marker.group(2)}",
                            "family": family,
                            "section": section,
                            "title": bold_run[marker.end():],
                            "text": "",
                            "page": page_no,
                            "program": "VEXU" if family in VU_FAMILIES
                                       else "V5RC",
                        }
                        rest = stripped[len(bold_run):]
                        collecting_title = rest.strip() == ""
                        current["text"] = rest.strip()
                        continue
                    if current is None:
                        continue  # section preamble prose
                    if collecting_title and line.starts_bold():
                        # a long bold title wrapped onto this line
                        run = line.leading_bold()
                        current["title"] = join_wrapped(current["title"], run)
                        rest = line.text[len(run):].strip()
                        if rest:
                            current["text"] = rest
                            collecting_title = False
                        continue
                    collecting_title = False
                    current["text"] = join_wrapped(current["text"], line.text)
        finalize()
    return rules


def parse_definitions(doc, pages, section, program, multiblock):
    """Glossary-style term blocks: bold Term, ' - ', definition."""
    defs = []
    current = None

    def finalize():
        nonlocal current
        if current is not None:
            current["text"] = normalize(current["text"])
            defs.append(current)
            current = None

    for page_no in range(pages[0], pages[1] + 1):
        for lines in page_blocks(doc[page_no - 1], page_no,
                                 current is not None):
            if lines[0].max_size >= 14:
                finalize()
                continue
            block_text = ""
            for line in lines:
                block_text = join_wrapped(block_text, line.text)
            text = normalize(block_text)
            if not text:
                continue
            term = TERM_DASH.match(text)
            if (term and lines[0].starts_bold()
                    and normalize(lines[0].leading_bold()) == term.group(1)):
                finalize()
                name = term.group(1)
                current = {
                    "id": name if program == "V5RC" else f"{name} (VEXU)",
                    "family": "DEF",
                    "section": section,
                    "title": name,
                    "text": text[term.end() - 1:].strip(),
                    "page": page_no,
                    "program": program,
                }
            elif current is not None and multiblock:
                current["text"] += "\n" + text
    finalize()
    return defs


def parse():
    doc = fitz.open(PDF_PATH)
    chunks = parse_rules(doc)
    # VURC definitions live on the first two VEX U pages, before <VUR1>.
    chunks += parse_definitions(doc, (86, 87), "VEX U", "VEXU",
                                multiblock=False)
    chunks += parse_definitions(doc, GLOSSARY_PAGES, "Glossary", "V5RC",
                                multiblock=True)

    # Three facts in the manual live only in tables or primer prose, outside
    # any numbered rule, so the parser cannot reach them. They are the most
    # referee-relevant facts in the book. Hand-transcribed and spot-checked:
    chunks.append({
        "id": "Match Scoring Values",
        "family": "DEF",
        "section": "Scoring",
        "title": "Match Scoring Values (points table)",
        "text": ("How many points each scoring action is worth in a Match: "
                 "Autonomous Bonus: 12 points. Each Scored Alliance-colored "
                 "Pin (red or blue): 5 points. Each Scored yellow Pin: 10 "
                 "points, awarded to the Alliance that Owns it (see <SC4> "
                 "and <SC5>). Each Robot in the Midfield at the end of the "
                 "Match: 8 points. See rules <SC1> through <SC9> for how "
                 "each scoring status is evaluated."),
        "page": 25,
        "program": "V5RC",
    })
    chunks.append({
        "id": "Match Timing",
        "family": "DEF",
        "section": "Glossary",
        "title": "Match Timing (period lengths)",
        "text": ("How long each Match type lasts. A V5RC Head-to-Head Match "
                 "is two minutes total: a fifteen second (0:15) Autonomous "
                 "Period followed by a one minute and forty-five second "
                 "(1:45) Driver Controlled Period. A Driving Skills Match "
                 "is a one minute (1:00) Driver Controlled Period with no "
                 "Autonomous Period. An Autonomous Coding Skills Match is a "
                 "one minute (1:00) Autonomous Period with no Driver "
                 "Controlled Period. VEX U timing differs: see <VUT4> and "
                 "<VUT5>."),
        "page": 125,
        "program": "V5RC",
    })
    chunks.append({
        "id": "Robot Skills Scoring Values",
        "family": "DEF",
        "section": "Robot Skills Challenge Rules",
        "title": "Robot Skills Scoring Values (points table)",
        "text": ("How many points each scoring action is worth in a Robot "
                 "Skills Match: Each Scored red or blue Pin: 5 points. Each "
                 "Scored yellow Pin: 10 points. Each Robot in the Midfield: "
                 "8 points. There is no Autonomous Bonus in Robot Skills "
                 "Matches. See <RSC3> for how Pins are Scored and Owned in "
                 "Skills Matches."),
        "page": 54,
        "program": "V5RC",
    })
    return chunks


def sanity_report(chunks):
    counts = Counter(c["family"] for c in chunks)
    order = ["G", "GG", "SG", "SC", "RSC", "R", "S", "T",
             "VUR", "VUG", "VURS", "VUT", "DEF"]
    print(f"Total chunks: {len(chunks)}")
    rule_total = sum(v for k, v in counts.items() if k != "DEF")
    print(f"Rules: {rule_total}   Definitions: {counts['DEF']}")
    for fam in order:
        print(f"  {fam:5} {counts.get(fam, 0)}")
    extra = set(counts) - set(order)
    if extra:
        print("  UNEXPECTED FAMILIES:", extra)

    ids = [c["id"] for c in chunks]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    if dupes:
        print("DUPLICATE IDS:", dupes)

    # Numbering gaps catch parsing misses (a missing <G5> means we lost a rule).
    gaps = False
    for fam in order[:-1]:
        nums = sorted(int(c["id"][len(fam):]) for c in chunks
                      if c["family"] == fam)
        if nums:
            missing = sorted(set(range(1, max(nums) + 1)) - set(nums))
            if missing:
                print(f"  {fam}: MISSING NUMBERS {missing}")
                gaps = True
    if not gaps:
        print("No numbering gaps in any rule family.")

    short = [c for c in chunks if len(c["text"]) < 40]
    print(f"Chunks under 40 chars: {len(short)}")
    for c in short:
        print(f"  [{c['id']}] {c['title'][:50]!r} -> {c['text']!r}")


if __name__ == "__main__":
    chunks = parse()
    sanity_report(chunks)
    if "--audit" in sys.argv:
        print(f"\nDropped blocks ({len(DROPPED)}), for eyeball review:")
        for page_no, reason, text in DROPPED:
            print(f"  p{page_no:3} [{reason:11}] {text!r}")
    with open(OUT_PATH, "w") as f:
        json.dump(chunks, f, indent=1, ensure_ascii=False)
    print(f"Wrote {OUT_PATH}")
