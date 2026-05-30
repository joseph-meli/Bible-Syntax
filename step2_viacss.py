"""
step2_generate_html.py
======================
Generates two offline HTML files:
  OT_syntax.html  -- Hebrew Bible  (BHSA/ETCBC)
  NT_syntax.html  -- Greek NT      (Nestle 1904 / N1904)

Each word box shows:
  - Original text (Hebrew / Greek)
  - Transliteration
  - English gloss
  - Morphology tag
  - Strong's number

Run AFTER step1_download_data.py.  No internet required.

Usage:
    python step2_generate_html.py
    python step2_generate_html.py --ot-only
    python step2_generate_html.py --nt-only

FIXES (v2):
  - BUG 1: Book accordions now wrapped in .bk-wrap so the ~ sibling CSS
    selector is scoped per-book; previously opening one book would cause
    all subsequent books to open too.
  - BUG 2: OT books with numeric prefixes (1_Samuel, 2_Kings, etc.) were
    displaying malformed verse references like "Samuel 5:1.2". Fixed by
    building the display name lookup table keyed on the raw BHSA book ID
    string returned by T.sectionFromNode(), and falling back gracefully.
"""

import sys
import os
import csv
import glob
import argparse
from collections import defaultdict

try:
    from tf.fabric import Fabric
except ImportError:
    print("Text-Fabric not found.  Run:  pip install text-fabric")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR   = os.path.join(os.path.expanduser("~"), "bible_syntax_data")
BHSA_DIR   = os.path.join(BASE_DIR, "bhsa")
N1904_DIR  = os.path.join(BASE_DIR, "n1904")
STRONG_CSV = os.path.join(BASE_DIR, "strong", "BHS-with-Strong-no-extended.csv")


# ---------------------------------------------------------------------------
# Strong's number loader for OT
# ---------------------------------------------------------------------------
def load_ot_strongs():
    if not os.path.exists(STRONG_CSV):
        print("  WARNING: Strong's CSV not found at " + STRONG_CSV)
        print("  Run step1_download_data.py to download it.")
        print("  OT Strong's numbers will be omitted.")
        return {}

    mapping = {}
    print("  Loading OT Strong's from " + STRONG_CSV + "...")
    with open(STRONG_CSV, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            sort_val = row.get("BHSsort", "").strip()
            sn       = row.get("extendedStrongNumber", "").strip()
            if sort_val and sn:
                try:
                    mapping[int(sort_val)] = sn
                except ValueError:
                    pass

    print("  Loaded " + str(len(mapping)) + " Strong's entries for OT")
    return mapping


# ---------------------------------------------------------------------------
# BHSA -> readable transliteration converter
# ---------------------------------------------------------------------------
def bhsa_to_translit(g_word):
    CONS = {
        ">": "\u02bc",
        "B": "b",
        "G": "g",
        "D": "d",
        "H": "h",
        "W": "w",
        "Z": "z",
        "X": "\u1e25",
        "V": "\u1e6d",
        "J": "y",
        "K": "k",
        "k": "k",
        "L": "l",
        "M": "m",
        "m": "m",
        "N": "n",
        "n": "n",
        "S": "s",
        "<": "\u02bf",
        "P": "p",
        "p": "p",
        "Y": "\u1e63",
        "y": "\u1e63",
        "Q": "q",
        "R": "r",
        "C": "\u0161",
        "F": "\u015b",
        "#": "\u0161",
        "T": "t",
    }
    VOWELS = {
        "A":  "a",
        ":A": "\u1d43",
        "@":  "\u0101",
        ":@": "\u1d52",
        "E":  "e",
        ":E": "\u1d49",
        ";":  "\u00ea",
        "I":  "\u00ee",
        "O":  "\u00f4",
        "U":  "u",
        ":":  "\u1d49",
    }
    TWO_CHAR_VOWELS = {":A", ":@", ":E"}

    result = []
    i = 0
    s = g_word
    n = len(s)

    while i < n:
        c = s[i]

        if c.isdigit() and i + 1 < n and s[i+1].isdigit():
            i += 2
            continue

        if c == ".":
            if i + 1 < n and s[i+1] in ("c", "f"):
                i += 2
            else:
                i += 1
            continue

        if c in (",", "&", "_", "'", "*"):
            i += 1
            continue

        if c == "0" and i + 1 < n and s[i+1] in ("0", "5"):
            i += 2
            continue

        if c == ":" and i + 1 < n:
            two = ":" + s[i+1]
            if two in TWO_CHAR_VOWELS:
                result.append(VOWELS[two])
                i += 2
                continue
            else:
                result.append(VOWELS[":"])
                i += 1
                continue

        if c in VOWELS:
            result.append(VOWELS[c])
            i += 1
            continue

        if c in CONS:
            result.append(CONS[c])
            i += 1
            continue

        i += 1

    return "".join(result)


# ---------------------------------------------------------------------------
# Label maps
# ---------------------------------------------------------------------------
OT_BOOK_NAMES = {
    "Genesis": "Genesis", "Exodus": "Exodus", "Leviticus": "Leviticus",
    "Numbers": "Numbers", "Deuteronomy": "Deuteronomy", "Joshua": "Joshua",
    "Judges": "Judges", "Ruth": "Ruth",
    "1_Samuel": "1 Samuel", "2_Samuel": "2 Samuel",
    "1_Kings": "1 Kings", "2_Kings": "2 Kings",
    "1_Chronicles": "1 Chronicles", "2_Chronicles": "2 Chronicles",
    "Ezra": "Ezra", "Nehemiah": "Nehemiah", "Esther": "Esther",
    "Job": "Job", "Psalms": "Psalms", "Proverbs": "Proverbs",
    "Ecclesiastes": "Ecclesiastes", "Song_of_songs": "Song of Songs",
    "Isaiah": "Isaiah", "Jeremiah": "Jeremiah",
    "Lamentations": "Lamentations", "Ezekiel": "Ezekiel", "Daniel": "Daniel",
    "Hosea": "Hosea", "Joel": "Joel", "Amos": "Amos",
    "Obadiah": "Obadiah", "Jonah": "Jonah", "Micah": "Micah",
    "Nahum": "Nahum", "Habakkuk": "Habakkuk", "Zephaniah": "Zephaniah",
    "Haggai": "Haggai", "Zechariah": "Zechariah", "Malachi": "Malachi",
}

# ---------------------------------------------------------------------------
# BUG 2 FIX: BHSA sometimes returns book IDs without underscores or with
# different capitalisation. Build a normalised lookup that handles both the
# canonical key ("1_Samuel") AND the raw string BHSA actually returns at
# runtime (e.g. "1Samuel", "Samuel", etc.).  We also build a reverse map
# from every plausible variant to the display name so sectionFromNode()
# output always resolves correctly.
# ---------------------------------------------------------------------------
def _build_ot_name_lookup():
    """
    Returns a dict that maps any plausible BHSA book-ID variant -> display name.
    Keys include: canonical ("1_Samuel"), no-underscore ("1Samuel"),
    lower-case, and plain name ("Samuel") as fallback.
    """
    lookup = {}
    for k, v in OT_BOOK_NAMES.items():
        lookup[k] = v                          # "1_Samuel" -> "1 Samuel"
        lookup[k.replace("_", "")] = v         # "1Samuel"  -> "1 Samuel"
        lookup[k.lower()] = v                  # "1_samuel" -> "1 Samuel"
        lookup[k.replace("_", "").lower()] = v # "1samuel"  -> "1 Samuel"
    return lookup

OT_NAME_LOOKUP = _build_ot_name_lookup()

def ot_book_display(raw_id):
    """Return the display name for a raw BHSA book ID, with graceful fallback."""
    if raw_id in OT_NAME_LOOKUP:
        return OT_NAME_LOOKUP[raw_id]
    # Try stripping leading digits that sometimes get separated
    stripped = raw_id.lstrip("0123456789")
    if stripped in OT_NAME_LOOKUP:
        return OT_NAME_LOOKUP[stripped]
    # Last resort: replace underscores with spaces
    return raw_id.replace("_", " ")

OT_BOOK_ORDER = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "1_Samuel", "2_Samuel",
    "1_Kings", "2_Kings", "1_Chronicles", "2_Chronicles",
    "Ezra", "Nehemiah", "Esther", "Job", "Psalms", "Proverbs",
    "Ecclesiastes", "Song_of_songs", "Isaiah", "Jeremiah", "Lamentations",
    "Ezekiel", "Daniel", "Hosea", "Joel", "Amos", "Obadiah",
    "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah",
    "Haggai", "Zechariah", "Malachi",
]

NT_BOOK_NAMES = {
    "Matthew": "Matthew", "Mark": "Mark", "Luke": "Luke", "John": "John",
    "Acts": "Acts", "Romans": "Romans",
    "I_Corinthians": "1 Corinthians", "II_Corinthians": "2 Corinthians",
    "Galatians": "Galatians", "Ephesians": "Ephesians",
    "Philippians": "Philippians", "Colossians": "Colossians",
    "I_Thessalonians": "1 Thessalonians", "II_Thessalonians": "2 Thessalonians",
    "I_Timothy": "1 Timothy", "II_Timothy": "2 Timothy",
    "Titus": "Titus", "Philemon": "Philemon", "Hebrews": "Hebrews",
    "James": "James", "I_Peter": "1 Peter", "II_Peter": "2 Peter",
    "I_John": "1 John", "II_John": "2 John", "III_John": "3 John",
    "Jude": "Jude", "Revelation": "Revelation",
}

NT_BOOK_ORDER = [
    "Matthew", "Mark", "Luke", "John", "Acts", "Romans",
    "I_Corinthians", "II_Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "I_Thessalonians", "II_Thessalonians",
    "I_Timothy", "II_Timothy", "Titus", "Philemon", "Hebrews",
    "James", "I_Peter", "II_Peter", "I_John", "II_John", "III_John",
    "Jude", "Revelation",
]

OT_FUNC = {
    "Pred": "Predicate", "Subj": "Subject", "Objc": "Object",
    "Cmpl": "Complement", "Adju": "Adjunct", "Time": "Time reference",
    "Loca": "Location", "Mnr": "Manner", "Rela": "Relation",
    "Conj": "Conjunction", "Frnt": "Front", "Intj": "Interjection",
    "Nega": "Negation", "Voct": "Vocative", "PrAd": "Predicative adj.",
    "NA": "",
}
OT_TYP = {
    "NP": "Nominal phrase", "PP": "Prepositional phrase",
    "VP": "Verbal phrase", "AdjP": "Adjectival phrase",
    "AdvP": "Adverbial phrase", "PrNP": "Proper noun phrase",
    "NmCl": "Nominal clause", "AjCl": "Adjectival clause",
    "WayX": "Wayyiqtol clause", "XQtl": "x-Qatal clause",
    "WXQt": "We-x-Qatal clause", "WQt": "We-Qatal clause",
    "XIm": "x-Yiqtol clause", "InfA": "Infinitive absolute",
    "InfC": "Infinitive construct", "Ptcp": "Participial phrase",
    "CP": "Compound phrase", "": "",
}
NT_ROLE = {
    "s": "Subject", "o": "Object", "v": "Predicate (verb)",
    "p": "Predicate", "adv": "Adverbial", "io": "Indirect object",
    "vc": "Verbal copula", "apposition": "Apposition",
    "aux": "Auxiliary", "o2": "Second object", "": "",
}
NT_CLS = {
    "np": "Nominal phrase", "pp": "Prepositional phrase",
    "vp": "Verbal phrase", "adjp": "Adjectival phrase",
    "advp": "Adverbial phrase", "cl": "Clause",
    "conj": "Conjunction", "nump": "Numeral phrase",
    "noun": "Noun", "verb": "Verb", "det": "Determiner",
    "pron": "Pronoun", "adj": "Adjective", "adv": "Adverb",
    "prep": "Preposition", "ptcl": "Particle", "": "",
}


# ---------------------------------------------------------------------------
# HTML page builder
# ---------------------------------------------------------------------------
def page_head(lang, direction, title):
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"" + lang + "\" dir=\"" + direction + "\">\n"
        "<head>\n"
        "<meta charset=\"UTF-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,user-scalable=yes\">\n"
        "<title>" + title + "</title>\n"
        "<style>\n"
        ":root {\n"
        "  --bg: #0f0f14; --surface: #1a1a24; --border: #2e2e40;\n"
        "  --gold: #e8c96a; --teal: #5ecfb0; --violet: #b57ff5;\n"
        "  --orange: #f0965a; --text: #ddd8cc; --muted: #6a6a7a;\n"
        "  --cl-bg: #1a1a2e; --cl-bdr: #6a4aaa;\n"
        "  --ph-bg: #1a2035; --ph-bdr: #2a5a8a;\n"
        "  --wd-bg: #0d0d18; --wd-bdr: #2a2a50;\n"
        "  --r: 6px;\n"
        "}\n"
        "* { box-sizing: border-box; margin: 0; padding: 0; }\n"
        "body { background: var(--bg); color: var(--text); font-family: Georgia, serif; line-height: 1.5; }\n"

        # BUG 1 FIX: .bk-wrap scopes the ~ sibling selector so only the
        # correct .bk-body opens when a .bk-toggle is checked.
        ".bk-wrap { display: block; }\n"
        ".bk-toggle { display: none; }\n"
        ".bk-lbl {\n"
        "  display: flex; align-items: center; gap: 8px; padding: 10px 14px;\n"
        "  cursor: pointer; user-select: none; background: var(--surface);\n"
        "  border-bottom: 1px solid var(--border);\n"
        "}\n"
        ".bk-lbl:hover { background: #22223a; }\n"
        ".bk-name { color: var(--gold); font-size: 0.95rem; font-weight: bold; flex: 1; }\n"
        ".bk-arrow { color: var(--muted); font-size: 0.75rem; transition: transform 0.18s; display: inline-block; }\n"
        ".bk-body { display: none; padding-bottom: 8px; }\n"
        # Scoped to .bk-wrap so siblings in other book wrappers are not affected
        ".bk-wrap .bk-toggle:checked ~ .bk-body { display: block; }\n"
        ".bk-wrap .bk-toggle:checked ~ .bk-lbl .bk-arrow { transform: rotate(90deg); }\n"

        ".ch-toggle { display: none; }\n"
        ".ch { margin: 5px 10px; border: 1px solid var(--border); border-radius: var(--r); overflow: hidden; }\n"
        ".ch-lbl {\n"
        "  display: flex; align-items: center; gap: 8px; padding: 6px 10px;\n"
        "  cursor: pointer; background: #161622; user-select: none;\n"
        "}\n"
        ".ch-lbl:hover { background: #1e1e32; }\n"
        ".ch-num { color: var(--teal); font-size: 0.8rem; font-weight: bold; flex: 1; }\n"
        ".ch-arrow { color: var(--muted); font-size: 0.7rem; display: inline-block; transition: transform 0.18s; }\n"
        ".ch-body { display: none; padding: 6px; }\n"
        # .ch already acts as the scoping wrapper for chapters so these are fine
        ".ch .ch-toggle:checked ~ .ch-body { display: block; }\n"
        ".ch .ch-toggle:checked ~ .ch-lbl .ch-arrow { transform: rotate(90deg); }\n"

        ".vs { margin: 5px 0; padding: 6px 8px; border-left: 2px solid var(--border); border-radius: 0 var(--r) var(--r) 0; }\n"
        ".vs-ref { font-size: 0.68rem; color: var(--muted); margin-bottom: 5px; font-family: monospace; }\n"
        ".vs-clauses { display: flex; flex-direction: column; gap: 5px; }\n"
        ".clause { border: 1px solid var(--cl-bdr); border-radius: var(--r); background: var(--cl-bg); overflow: hidden; }\n"
        ".cl-head {\n"
        "  display: flex; align-items: baseline; gap: 6px;\n"
        "  padding: 3px 8px; background: #180f2a; border-bottom: 1px solid var(--cl-bdr);\n"
        "}\n"
        ".cl-func { font-size: 0.72rem; color: var(--teal); font-weight: bold; }\n"
        ".cl-type { font-size: 0.62rem; color: var(--violet); font-style: italic; font-family: monospace; }\n"
        ".cl-body { display: flex; flex-wrap: wrap; gap: 6px; padding: 6px 8px; align-items: flex-start; }\n"
        ".phrase {\n"
        "  border: 1px solid var(--ph-bdr); border-radius: var(--r);\n"
        "  background: var(--ph-bg); display: inline-flex; flex-direction: column;\n"
        "  gap: 3px; padding: 4px 6px;\n"
        "}\n"
        ".ph-head {\n"
        "  display: flex; flex-direction: column; align-items: center; gap: 1px;\n"
        "  border-bottom: 1px solid var(--ph-bdr); padding-bottom: 3px; margin-bottom: 2px;\n"
        "}\n"
        ".ph-func { font-size: 0.68rem; color: var(--orange); font-weight: bold; text-align: center; }\n"
        ".ph-type { font-size: 0.6rem; color: var(--teal); font-style: italic; font-family: monospace; text-align: center; }\n"
        ".ph-words { display: flex; flex-wrap: wrap; gap: 3px; justify-content: center; }\n"
        ".word {\n"
        "  display: inline-flex; flex-direction: column; align-items: center;\n"
        "  background: var(--wd-bg); border: 1px solid var(--wd-bdr);\n"
        "  border-radius: var(--r); padding: 4px 6px; min-width: 44px;\n"
        "  cursor: default;\n"
        "}\n"
        ".wd-txt  { font-size: 1.3rem; color: #fff; line-height: 1.2; text-align: center; }\n"
        ".wd-tlit { font-size: 0.62rem; color: var(--teal); text-align: center; font-style: italic; }\n"
        ".wd-gl   { font-size: 0.58rem; color: var(--muted); text-align: center; max-width: 80px; word-break: break-word; }\n"
        ".wd-mp   { font-size: 0.5rem; color: #44445a; font-family: monospace; text-align: center; }\n"
        ".wd-sn   { font-size: 0.5rem; color: #7a6a3a; font-family: monospace; text-align: center; }\n"
        "[dir=rtl] .cl-body { flex-direction: row-reverse; }\n"
        "[dir=rtl] .ph-words { flex-direction: row-reverse; }\n"
        "header {\n"
        "  position: sticky; top: 0; z-index: 200;\n"
        "  background: #08080f; border-bottom: 1px solid var(--border);\n"
        "  padding: 8px 14px;\n"
        "}\n"
        "header h1 { color: var(--gold); font-size: 1rem; margin-bottom: 2px; }\n"
        "footer { text-align: center; padding: 20px; color: var(--muted); font-size: 0.68rem; border-top: 1px solid var(--border); margin-top: 14px; }\n"
        "@media (max-width: 480px) {\n"
        "  .wd-txt { font-size: 1.1rem; }\n"
        "  header h1 { font-size: 0.88rem; }\n"
        "}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        "<header><h1>" + title + "</h1></header>\n"
        "<main>\n"
    )


def page_foot(credit):
    return (
        "</main>\n"
        "<footer>" + credit + "</footer>\n"
        "</body>\n"
        "</html>\n"
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def esc(s):
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def sf(F, name, node):
    try:
        a = getattr(F, name, None)
        if a is None:
            return ""
        v = a.v(node)
        return v if v is not None else ""
    except Exception:
        return ""


def find_tf_dir(root, hints):
    for hint in hints:
        p = os.path.join(root, hint)
        if os.path.isdir(p) and glob.glob(os.path.join(p, "*.tf")):
            return p
    for dirpath, _, filenames in os.walk(root):
        if any(f.endswith(".tf") for f in filenames):
            return dirpath
    return None


def find_tf_dir_n1904(root):
    candidates = []
    for dirpath, _, filenames in os.walk(root):
        fset = set(filenames)
        if not any(f.endswith(".tf") for f in fset):
            continue
        score = 0
        if "otype.tf"   in fset: score += 10
        if "unicode.tf" in fset: score += 8
        if "role.tf"    in fset: score += 6
        if "cls.tf"     in fset: score += 5
        if "gloss.tf"   in fset: score += 4
        if "morph.tf"   in fset: score += 3
        lower = dirpath.lower()
        if "complement" in lower or "extra" in lower or "addon" in lower:
            score -= 25
        candidates.append((score, dirpath))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    print("  N1904 candidates (top 3):")
    for sc, d in candidates[:3]:
        print("    score=" + str(sc) + "  " + d)
    return candidates[0][1]


# ---------------------------------------------------------------------------
# HTML fragment builders
# ---------------------------------------------------------------------------
def word_box(text, translit, gloss, parse_tag, strong):
    h = "<div class=\"word\">"
    h += "<span class=\"wd-txt\">"  + esc(text)     + "</span>"
    if translit:
        h += "<span class=\"wd-tlit\">" + esc(translit) + "</span>"
    h += "<span class=\"wd-gl\">"   + esc(gloss)    + "</span>"
    if parse_tag:
        h += "<span class=\"wd-mp\">" + esc(parse_tag) + "</span>"
    if strong:
        h += "<span class=\"wd-sn\">" + esc(strong)    + "</span>"
    h += "</div>"
    return h


def phrase_box(func_lbl, type_lbl, word_list):
    h = "<div class=\"phrase\">"
    h += "<div class=\"ph-head\">"
    if func_lbl:
        h += "<span class=\"ph-func\">" + esc(func_lbl) + "</span>"
    if type_lbl:
        h += "<span class=\"ph-type\">" + esc(type_lbl) + "</span>"
    h += "</div>"
    h += "<div class=\"ph-words\">" + "".join(word_list) + "</div>"
    h += "</div>"
    return h


def clause_box(func_lbl, type_lbl, inner_list):
    h = "<div class=\"clause\">"
    h += "<div class=\"cl-head\">"
    if func_lbl:
        h += "<span class=\"cl-func\">" + esc(func_lbl) + "</span>"
    if type_lbl:
        h += "<span class=\"cl-type\">" + esc(type_lbl) + "</span>"
    h += "</div>"
    h += "<div class=\"cl-body\">" + "".join(inner_list) + "</div>"
    h += "</div>"
    return h


# ---------------------------------------------------------------------------
# OT generator  (BHSA/ETCBC)
# ---------------------------------------------------------------------------
def generate_ot():
    print("\n=== OLD TESTAMENT (BHSA/ETCBC) ===")

    strongs_map = load_ot_strongs()

    tf_dir = find_tf_dir(
        BHSA_DIR,
        ["tf/2021", "tf/2020", "tf/2019", "tf/2017", "tf/c", "tf"],
    )
    if not tf_dir:
        print("ERROR: no BHSA .tf data found under " + BHSA_DIR)
        sys.exit(1)
    print("  Data dir: " + tf_dir)

    TF  = Fabric(locations=tf_dir, silent=True)
    api = TF.load(
        "otype g_word_utf8 g_cons_utf8 g_word "
        "gloss sp vs vt typ function rela book chapter verse",
        silent=True,
    )
    if api is False:
        print("ERROR: TF.load() failed for BHSA.")
        sys.exit(1)

    F, L, T = api.F, api.L, api.T
    out = [page_head("he", "rtl", "Hebrew Bible -- Syntactic Analysis (BHSA/ETCBC)")]

    # Build a map from raw_book_id -> book_node
    # BUG 2 FIX: We store the raw string returned by sectionFromNode() as the
    # key, then resolve the display name through ot_book_display() which
    # handles all variant spellings (1Samuel, 1_Samuel, Samuel, etc.).
    book_node_map = {}
    for bk_node in F.otype.s("book"):
        raw_id = T.sectionFromNode(bk_node)[0]
        book_node_map[raw_id] = bk_node

    # Also build a mapping from canonical order key -> raw_id so we can
    # iterate in OT_BOOK_ORDER while still finding nodes stored under
    # variant spellings.
    canonical_to_raw = {}
    for raw_id in book_node_map:
        # Try exact match first
        if raw_id in OT_BOOK_ORDER:
            canonical_to_raw[raw_id] = raw_id
            continue
        # Try without underscores
        no_us = raw_id.replace("_", "")
        for canon in OT_BOOK_ORDER:
            if canon.replace("_", "") == no_us:
                canonical_to_raw[canon] = raw_id
                break

    total = len(OT_BOOK_ORDER)
    print("  Processing " + str(total) + " books in canonical order...")

    for bi, book_id in enumerate(OT_BOOK_ORDER):
        raw_id  = canonical_to_raw.get(book_id)
        if raw_id is None or raw_id not in book_node_map:
            continue
        bk_node = book_node_map[raw_id]

        # BUG 2 FIX: use ot_book_display() which handles all raw_id variants
        book_en = ot_book_display(raw_id)
        print("    [" + str(bi + 1) + "/" + str(total) + "] " + book_en
              + "  (raw_id=" + repr(raw_id) + ")")

        bk_cb_id = "bk-" + esc(book_id)

        # BUG 1 FIX: wrap each book in .bk-wrap so the CSS ~ selector is
        # scoped and only opens this book's .bk-body, not every subsequent one.
        out.append("<div class=\"bk-wrap\">")
        out.append("<input type=\"checkbox\" class=\"bk-toggle\" id=\"" + bk_cb_id + "\">")
        out.append(
            "<label class=\"bk-lbl\" for=\"" + bk_cb_id + "\">"
            "<span class=\"bk-name\">" + esc(book_en) + "</span>"
            "<span class=\"bk-arrow\">&#9658;</span>"
            "</label>"
        )
        out.append("<div class=\"bk-body\">")

        for ch_node in L.d(bk_node, "chapter"):
            ch_num = str(T.sectionFromNode(ch_node)[1])
            ch_cb_id = "ch-" + esc(book_id) + "-" + ch_num
            out.append("<div class=\"ch\">")
            out.append("<input type=\"checkbox\" class=\"ch-toggle\" id=\"" + ch_cb_id + "\">")
            out.append(
                "<label class=\"ch-lbl\" for=\"" + ch_cb_id + "\">"
                "<span class=\"ch-num\">Chapter " + ch_num + "</span>"
                "<span class=\"ch-arrow\">&#9658;</span>"
                "</label>"
            )
            out.append("<div class=\"ch-body\">")

            for v_node in L.d(ch_node, "verse"):
                v_num = str(T.sectionFromNode(v_node)[2])
                ref   = book_en + " " + ch_num + ":" + v_num
                out.append("<div class=\"vs\">")
                out.append("<div class=\"vs-ref\">" + esc(ref) + "</div>")
                out.append("<div class=\"vs-clauses\">")

                for cl_node in L.d(v_node, "clause"):
                    cl_func = OT_FUNC.get(sf(F, "function", cl_node), sf(F, "function", cl_node))
                    cl_typ  = OT_TYP.get(sf(F, "typ", cl_node), sf(F, "typ", cl_node))

                    phrases_html = []
                    for ph_node in L.d(cl_node, "phrase"):
                        ph_func = OT_FUNC.get(sf(F, "function", ph_node), sf(F, "function", ph_node))
                        ph_typ  = OT_TYP.get(sf(F, "typ", ph_node), sf(F, "typ", ph_node))

                        words_html = []
                        for w_node in L.d(ph_node, "word"):
                            text     = sf(F, "g_word_utf8", w_node) or sf(F, "g_cons_utf8", w_node)
                            translit = bhsa_to_translit(sf(F, "g_word", w_node))
                            gloss    = sf(F, "gloss", w_node)
                            sp       = sf(F, "sp", w_node)
                            vs       = sf(F, "vs", w_node)
                            vt       = sf(F, "vt", w_node)
                            ptags    = [x for x in [sp, vs, vt]
                                        if x and x not in ("NA", "n/a", "absent", "none")]
                            parse_tag = ".".join(ptags)
                            strong    = strongs_map.get(w_node, "")
                            words_html.append(word_box(text, translit, gloss, parse_tag, strong))

                        phrases_html.append(phrase_box(ph_func, ph_typ, words_html))

                    out.append(clause_box(cl_func, cl_typ, phrases_html))

                out.append("</div></div>")  # vs-clauses, vs

            out.append("</div></div>")  # ch-body, ch

        out.append("</div>")  # bk-body
        out.append("</div>")  # bk-wrap  <-- BUG 1 FIX closing tag

    out.append(page_foot(
        "Hebrew Bible: BHSA/ETCBC (Eep Talstra Centre, VU Amsterdam) | CC BY-NC 4.0 | "
        "Strong's: eliranwong/BHS-Strong-no | Text-Fabric"
    ))

    fname = "OT_syntax.html"
    with open(fname, "w", encoding="utf-8") as fh:
        fh.write("".join(out))
    print("  Written: " + fname + "  (" + str(round(os.path.getsize(fname) / 1e6, 1)) + " MB)")


# ---------------------------------------------------------------------------
# NT generator  (Nestle 1904 / N1904)
# ---------------------------------------------------------------------------
def generate_nt():
    print("\n=== NEW TESTAMENT (Nestle 1904 / N1904) ===")

    tf_dir = find_tf_dir_n1904(N1904_DIR)
    if not tf_dir:
        print("ERROR: no N1904 .tf data found under " + N1904_DIR)
        sys.exit(1)
    print("  Data dir: " + tf_dir)

    TF = Fabric(locations=tf_dir, silent=True)
    api = TF.load(
        "otype "
        "unicode text normalized "
        "gloss lemma lemmatranslit "
        "cls role function "
        "sp morph case number gender tense mood voice "
        "book chapter verse "
        "strong",
        silent=True,
    )
    if api is False:
        print("ERROR: TF.load() failed for N1904.")
        sys.exit(1)

    F, L, T = api.F, api.L, api.T
    all_types = set(F.otype.all)
    has_phrase = "phrase" in all_types

    word_ref = {}
    for w in F.otype.s("word"):
        word_ref[w] = (F.book.v(w), F.chapter.v(w), F.verse.v(w))

    bk_ch_vs_clauses = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    seen = set()

    if "clause" in all_types:
        for cl in F.otype.s("clause"):
            words = L.d(cl, "word")
            if not words:
                continue
            verses_touched = set()
            for w in words:
                ref = word_ref.get(w)
                if ref and ref[0]:
                    verses_touched.add(ref)
            for (bk, ch, vs) in sorted(verses_touched):
                key = (bk, ch, vs, cl)
                if key not in seen:
                    seen.add(key)
                    bk_ch_vs_clauses[bk][ch][vs].append(cl)

    out = [page_head("el", "ltr", "Greek New Testament -- Syntactic Analysis (Nestle 1904)")]

    for book_id in NT_BOOK_ORDER:
        if book_id not in bk_ch_vs_clauses:
            continue
        book_en = NT_BOOK_NAMES.get(book_id, book_id)
        print("  " + book_en)

        bk_cb_id = "bk-" + esc(book_id)

        # BUG 1 FIX: wrap each book in .bk-wrap (same fix as OT)
        out.append("<div class=\"bk-wrap\">")
        out.append("<input type=\"checkbox\" class=\"bk-toggle\" id=\"" + bk_cb_id + "\">")
        out.append(
            "<label class=\"bk-lbl\" for=\"" + bk_cb_id + "\">"
            "<span class=\"bk-name\">" + esc(book_en) + "</span>"
            "<span class=\"bk-arrow\">&#9658;</span>"
            "</label>"
        )
        out.append("<div class=\"bk-body\">")

        ch_map = bk_ch_vs_clauses[book_id]

        verse_words = defaultdict(lambda: defaultdict(list))
        for vn in F.otype.s("verse"):
            sec = T.sectionFromNode(vn)
            if sec and sec[0] == book_id:
                verse_words[sec[1]][sec[2]] = L.d(vn, "word")

        all_ch_nums = sorted(set(list(ch_map.keys()) + list(verse_words.keys())))

        for ch_num in all_ch_nums:
            ch_cb_id = "ch-" + esc(book_id) + "-" + str(ch_num)
            out.append("<div class=\"ch\">")
            out.append("<input type=\"checkbox\" class=\"ch-toggle\" id=\"" + ch_cb_id + "\">")
            out.append(
                "<label class=\"ch-lbl\" for=\"" + ch_cb_id + "\">"
                "<span class=\"ch-num\">Chapter " + str(ch_num) + "</span>"
                "<span class=\"ch-arrow\">&#9658;</span>"
                "</label>"
            )
            out.append("<div class=\"ch-body\">")

            vs_map = ch_map.get(ch_num, {})
            all_vs_nums = sorted(set(list(vs_map.keys()) + list(verse_words[ch_num].keys())))

            for vs_num in all_vs_nums:
                ref = book_en + " " + str(ch_num) + ":" + str(vs_num)
                out.append("<div class=\"vs\">")
                out.append("<div class=\"vs-ref\">" + esc(ref) + "</div>")
                out.append("<div class=\"vs-clauses\">")

                clause_nodes = vs_map.get(vs_num, [])

                if not clause_nodes:
                    wds = verse_words[ch_num].get(vs_num, [])
                    if wds:
                        whtml = []
                        for w_node in wds:
                            text     = sf(F, "unicode", w_node) or sf(F, "text", w_node)
                            translit = sf(F, "lemmatranslit", w_node)
                            gloss    = sf(F, "gloss", w_node) or sf(F, "lemma", w_node)
                            morph    = sf(F, "morph", w_node)
                            strong   = sf(F, "strong", w_node)
                            sn_str   = ("G" + str(strong)) if strong else ""
                            whtml.append(word_box(text, translit, gloss, morph, sn_str))
                        out.append(clause_box("Verse", "", [phrase_box("", "", whtml)]))
                    out.append("</div></div>")
                    continue

                for cl_node in clause_nodes:
                    cl_role = sf(F, "role", cl_node)
                    cl_cls  = sf(F, "cls",  cl_node)
                    cl_func = sf(F, "function", cl_node)
                    cl_func_lbl = NT_ROLE.get(cl_role, cl_role) or cl_func or ""
                    cl_type_lbl = NT_CLS.get(cl_cls, cl_cls)

                    phrases_html = []
                    ph_nodes = L.d(cl_node, "phrase") if has_phrase else []

                    if ph_nodes:
                        for ph_node in ph_nodes:
                            ph_role = sf(F, "role", ph_node)
                            ph_cls  = sf(F, "cls",  ph_node)
                            ph_func = sf(F, "function", ph_node)
                            ph_func_lbl = NT_ROLE.get(ph_role, ph_role) or ph_func or ""
                            ph_type_lbl = NT_CLS.get(ph_cls, ph_cls)

                            words_html = []
                            for w_node in L.d(ph_node, "word"):
                                text     = sf(F, "unicode", w_node) or sf(F, "text", w_node)
                                translit = sf(F, "lemmatranslit", w_node)
                                gloss    = sf(F, "gloss", w_node) or sf(F, "lemma", w_node)
                                morph    = sf(F, "morph", w_node)
                                if not morph:
                                    parts = [sf(F, x, w_node) for x in
                                             ["sp", "tense", "mood", "case", "number"]
                                             if sf(F, x, w_node) not in ("", "NA")]
                                    morph = ".".join(parts[:3])
                                strong = sf(F, "strong", w_node)
                                sn_str = ("G" + str(strong)) if strong else ""
                                words_html.append(word_box(text, translit, gloss, morph, sn_str))

                            phrases_html.append(phrase_box(ph_func_lbl, ph_type_lbl, words_html))
                    else:
                        words_html = []
                        for w_node in L.d(cl_node, "word"):
                            text     = sf(F, "unicode", w_node) or sf(F, "text", w_node)
                            translit = sf(F, "lemmatranslit", w_node)
                            gloss    = sf(F, "gloss", w_node) or sf(F, "lemma", w_node)
                            morph    = sf(F, "morph", w_node)
                            strong   = sf(F, "strong", w_node)
                            sn_str   = ("G" + str(strong)) if strong else ""
                            words_html.append(word_box(text, translit, gloss, morph, sn_str))
                        if words_html:
                            phrases_html.append(phrase_box("", "", words_html))

                    out.append(clause_box(cl_func_lbl, cl_type_lbl, phrases_html))

                out.append("</div></div>")  # vs-clauses, vs

            out.append("</div></div>")  # ch-body, ch

        out.append("</div>")  # bk-body
        out.append("</div>")  # bk-wrap  <-- BUG 1 FIX closing tag

    out.append(page_foot(
        "Greek NT: Nestle 1904 / MACULA Lowfat (Clear Bible / CenterBLC) | CC BY 4.0 | Text-Fabric"
    ))

    fname = "NT_syntax.html"
    with open(fname, "w", encoding="utf-8") as fh:
        fh.write("".join(out))
    print("  Written: " + fname + "  (" + str(round(os.path.getsize(fname) / 1e6, 1)) + " MB)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ot-only", action="store_true")
    parser.add_argument("--nt-only", action="store_true")
    args = parser.parse_args()

    if not os.path.isdir(BASE_DIR):
        print("ERROR: " + BASE_DIR + " not found. Run step1_download_data.py first.")
        sys.exit(1)

    if args.nt_only:
        generate_nt()
    elif args.ot_only:
        generate_ot()
    else:
        generate_ot()
        generate_nt()

    print("\nDone.")
    print("Copy OT_syntax.html / NT_syntax.html to your iCloud Drive folder.")