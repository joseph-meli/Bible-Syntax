"""
step3_build_esword.py
=====================
Generates two e-Sword commentary files (.cmti) from the BHSA and N1904
Text-Fabric datasets.  Each verse entry contains the full clause/phrase/word
syntactic analysis as static HTML -- no JavaScript required.

Output:
  BHS_Syntax.cmti   -- Hebrew Bible syntactic analysis
  GNT_Syntax.cmti   -- Greek NT syntactic analysis

Place the .cmti files in your e-Sword installation folder
(e.g. C:\\Program Files (x86)\\e-Sword\\) and they will appear in
the Commentary window, synced verse-by-verse to your Bible text.

Usage:
    python step3_build_esword.py
    python step3_build_esword.py --ot-only
    python step3_build_esword.py --nt-only

Requirements:
    pip install text-fabric  (already installed from step1)
"""

import sys
import os
import csv
import glob
import sqlite3
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
# e-Sword book number maps
# e-Sword numbers OT 1-39, NT 40-66 (standard Logos/e-Sword canonical order)
# ---------------------------------------------------------------------------
OT_BOOK_NUMBERS = {
    "Genesis": 1, "Exodus": 2, "Leviticus": 3, "Numbers": 4,
    "Deuteronomy": 5, "Joshua": 6, "Judges": 7, "Ruth": 8,
    "1_Samuel": 9, "2_Samuel": 10, "1_Kings": 11, "2_Kings": 12,
    "1_Chronicles": 13, "2_Chronicles": 14, "Ezra": 15, "Nehemiah": 16,
    "Esther": 17, "Job": 18, "Psalms": 19, "Proverbs": 20,
    "Ecclesiastes": 21, "Song_of_songs": 22, "Isaiah": 23,
    "Jeremiah": 24, "Lamentations": 25, "Ezekiel": 26, "Daniel": 27,
    "Hosea": 28, "Joel": 29, "Amos": 30, "Obadiah": 31, "Jonah": 32,
    "Micah": 33, "Nahum": 34, "Habakkuk": 35, "Zephaniah": 36,
    "Haggai": 37, "Zechariah": 38, "Malachi": 39,
}

# Display names -- BHSA 2021 uses English names with underscores for spaces
OT_BOOK_NAMES = {k: k.replace("_", " ") for k in OT_BOOK_NUMBERS}

NT_BOOK_NUMBERS = {
    "Matthew": 40, "Mark": 41, "Luke": 42, "John": 43, "Acts": 44,
    "Romans": 45, "I_Corinthians": 46, "II_Corinthians": 47,
    "Galatians": 48, "Ephesians": 49, "Philippians": 50,
    "Colossians": 51, "I_Thessalonians": 52, "II_Thessalonians": 53,
    "I_Timothy": 54, "II_Timothy": 55, "Titus": 56, "Philemon": 57,
    "Hebrews": 58, "James": 59, "I_Peter": 60, "II_Peter": 61,
    "I_John": 62, "II_John": 63, "III_John": 64, "Jude": 65,
    "Revelation": 66,
}

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

# OT discourse domain labels (from BHSA 'domain' feature on clause nodes)
OT_DOMAIN = {
    "N": "Narrative",
    "D": "Discursive",
    "Q": "Quotation",
    "?": "",
}
# txt is a stack like "?NQ" -- last char is the current clause level
# We show the last meaningful character
def ot_discourse_label(txt):
    if not txt:
        return ""
    for ch in reversed(txt):
        label = OT_DOMAIN.get(ch, "")
        if label:
            return label
    return ""

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
# CSS for verse HTML -- embedded in each verse entry.
# e-Sword renders this per-entry so we include it inline once via a shared
# stylesheet approach: we put the CSS in the Details.Comments field and
# e-Sword injects it.  In practice, the safest approach is to include a
# <style> block in every verse entry -- e-Sword deduplicates rendering.
# We use a compact inline-style approach for word boxes to avoid bloat,
# and a small <style> block for layout.
# ---------------------------------------------------------------------------
VERSE_CSS = ""  # No stylesheet -- all styling is inline for e-Sword compatibility



# Table-based layout -- guaranteed to work in any HTML renderer including e-Sword




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


# ---------------------------------------------------------------------------
# Morphology expanders -- human-readable parse tag descriptions
# ---------------------------------------------------------------------------

# OT (BHSA): sp / vs / vt values
OT_SP = {
    "subs": "Noun", "verb": "Verb", "prep": "Prep.",
    "conj": "Conj.", "nmpr": "Proper noun", "art": "Article",
    "adjv": "Adjective", "nega": "Negation", "prps": "Pers. pronoun",
    "advb": "Adverb", "prde": "Dem. pronoun", "intj": "Interjection",
    "inrg": "Interrog.", "prin": "Rel. pronoun",
}
OT_VS = {
    "qal": "Qal", "hif": "Hiphil", "piel": "Piel", "nif": "Niphal",
    "hit": "Hithpael", "pual": "Pual", "hof": "Hophal", "peal": "Peal",
    "hsht": "Hishtaphel", "haf": "Hafel", "pael": "Pael", "htpe": "Hithpeel",
    "peil": "Peil", "htpa": "Hithpaal", "shaf": "Shafel", "hotp": "Hotpaal",
    "etpa": "Etpaal", "pasq": "Pasq", "poel": "Poel", "tif": "Tiphel",
    "afel": "Afel", "nit": "Nitpael", "poal": "Poal", "htpo": "Hithpoel",
    "etpe": "Etpeel",
}
OT_VT = {
    "perf": "Perfect", "impf": "Imperfect", "wayq": "Wayyiqtol",
    "ptca": "Participle act.", "infc": "Inf. construct",
    "impv": "Imperative", "ptcp": "Participle pass.",
    "infa": "Inf. absolute",
}
OT_GN = {
    "m": "Masc.", "f": "Fem.",
}
OT_NU = {
    "sg": "Sg.", "pl": "Pl.", "du": "Du.",
}
OT_PS = {
    "p1": "1st", "p2": "2nd", "p3": "3rd",
}
OT_ST = {
    "a": "Abs.", "c": "Constr.", "e": "Emph.",
}

def expand_ot_morph(parse_tag):
    """
    Expand BHSA morphology tag to readable string.
    Tag format: sp[.vs.vt[.gn.nu.ps]] for verbs
                sp[.gn.nu.st]         for nominals
    All six features are passed as a dot-joined string.
    """
    if not parse_tag:
        return ""

    # Tag is always sp.vs.vt.gn.nu.ps.st (fixed positions, empty string if absent)
    parts = parse_tag.split(".")
    def _p(i): return parts[i] if len(parts) > i else ""
    sp = _p(0); vs = _p(1); vt = _p(2)
    gn = _p(3); nu = _p(4); ps = _p(5); st = _p(6)

    result = []

    # Part of speech
    sp_label = OT_SP.get(sp, sp)
    if sp_label:
        result.append(sp_label)

    if sp == "verb":
        # Verbal stem and tense
        if vs and vs not in ("NA", ""):
            result.append(OT_VS.get(vs, vs))
        if vt and vt not in ("NA", ""):
            result.append(OT_VT.get(vt, vt))
        # Subject agreement (person/gender/number encoded on verb)
        if ps and ps not in ("NA", "unknown", ""):
            result.append(OT_PS.get(ps, ps))
        if gn and gn not in ("NA", "unknown", ""):
            result.append(OT_GN.get(gn, gn))
        if nu and nu not in ("NA", "unknown", ""):
            result.append(OT_NU.get(nu, nu))
    elif sp in ("prps", "prin", "prde"):
        # Pronouns: person, gender, number
        if ps and ps not in ("NA", "unknown", ""):
            result.append(OT_PS.get(ps, ps))
        if gn and gn not in ("NA", "unknown", ""):
            result.append(OT_GN.get(gn, gn))
        if nu and nu not in ("NA", "unknown", ""):
            result.append(OT_NU.get(nu, nu))
    elif sp in ("subs", "adjv", "nmpr"):
        # Nominals: gender, number, state
        if gn and gn not in ("NA", "unknown", ""):
            result.append(OT_GN.get(gn, gn))
        if nu and nu not in ("NA", "unknown", ""):
            result.append(OT_NU.get(nu, nu))
        if st and st not in ("NA", "unknown", ""):
            result.append(OT_ST.get(st, st))

    return " · ".join(result)


# NT (RMAC): maps for each position in the code
RMAC_POS = {
    "N": "Noun", "V": "Verb", "T": "Article", "A": "Adjective",
    "R": "Rel. pronoun", "C": "Recip. pronoun", "D": "Demonstrative",
    "K": "Correlative", "I": "Interrogative", "X": "Indefinite pronoun",
    "Q": "Correlative/indef.", "F": "Reflexive pronoun",
    "S": "Poss. pronoun", "P": "Personal pronoun",
    "CONJ": "Conjunction", "PREP": "Preposition", "ADV": "Adverb",
    "PRT": "Particle", "PRT-N": "Neg. particle", "INJ": "Interjection",
    "ARAM": "Aramaic", "HEB": "Hebrew",
}
RMAC_CASE = {
    "N": "Nom.", "G": "Gen.", "D": "Dat.", "A": "Acc.", "V": "Voc.",
}
RMAC_NUMBER = {
    "S": "Sg.", "P": "Pl.",
}
RMAC_GENDER = {
    "M": "Masc.", "F": "Fem.", "N": "Neut.",
}
RMAC_TENSE = {
    "P": "Pres.", "I": "Impf.", "F": "Fut.", "A": "Aor.",
    "R": "Perf.", "L": "Plup.", "2A": "2nd Aor.", "2R": "2nd Perf.",
    "2L": "2nd Plup.", "2F": "2nd Fut.",
}
RMAC_VOICE = {
    "A": "Act.", "M": "Mid.", "P": "Pass.", "D": "Mid./Pass.",
    "O": "Mid. deponent", "N": "Pass. deponent", "Q": "Mid./Pass. dep.",
    "E": "Either mid./pass.",
}
RMAC_MOOD = {
    "I": "Ind.", "S": "Subj.", "O": "Opt.", "M": "Impv.",
    "N": "Inf.", "P": "Part.", "R": "Part.",
}
RMAC_PERSON = {
    "1": "1st", "2": "2nd", "3": "3rd",
}
RMAC_DEGREE = {
    "C": "Comp.", "S": "Superl.",
}

def expand_nt_morph(morph):
    """
    Expand RMAC morph code to readable string.
    RMAC format:
      Nominal: POS-CGN        e.g. N-NSF  -> parts=["N","NSF"]  CGN = case+number+gender
      Verbal:  V-TVM-pn       e.g. V-PAI-3S -> parts=["V","PAI","3S"]  TVM concatenated
      Participle: V-TVM-CGN   e.g. V-PAP-NSM -> parts=["V","PAP","NSM"]
    """
    if not morph:
        return ""
    if morph == "PRT-N":
        return "Neg. particle"
    if morph in RMAC_POS:
        return RMAC_POS[morph]
    if "-" not in morph:
        return RMAC_POS.get(morph, morph)

    parts = morph.split("-")
    result = []
    pos_raw = parts[0]
    pos = RMAC_POS.get(pos_raw, pos_raw)
    result.append(pos)

    if pos_raw == "V" and len(parts) >= 2:
        tvm = parts[1]  # e.g. "PAI", "PAP", "2AAI"
        # Tense: may be 2-char prefix (2A, 2R, 2F, 2L)
        if len(tvm) >= 2 and tvm[0] == "2":
            tense_key = tvm[:2]
            tvm_rest  = tvm[2:]
        else:
            tense_key = tvm[0:1]
            tvm_rest  = tvm[1:]
        result.append(RMAC_TENSE.get(tense_key, tense_key))
        if len(tvm_rest) >= 1:
            result.append(RMAC_VOICE.get(tvm_rest[0], tvm_rest[0]))
        if len(tvm_rest) >= 2:
            result.append(RMAC_MOOD.get(tvm_rest[1], tvm_rest[1]))

        if len(parts) >= 3:
            pn = parts[2]  # "3S", "1P" or "NSM", "GSF" etc.
            if len(pn) >= 1 and pn[0] in RMAC_PERSON:
                # finite verb: person + number
                result.append(RMAC_PERSON.get(pn[0], pn[0]))
                if len(pn) >= 2:
                    result.append(RMAC_NUMBER.get(pn[1], pn[1]))
            elif len(pn) >= 3:
                # participle: case + number + gender
                result.append(RMAC_CASE.get(pn[0], pn[0]))
                result.append(RMAC_NUMBER.get(pn[1], pn[1]))
                result.append(RMAC_GENDER.get(pn[2], pn[2]))
    elif len(parts) >= 2:
        # Nominal: parts[1] = CGN (3 chars), parts[2] = degree
        cgn = parts[1]
        if len(cgn) >= 1:
            result.append(RMAC_CASE.get(cgn[0], cgn[0]))
        if len(cgn) >= 2:
            result.append(RMAC_NUMBER.get(cgn[1], cgn[1]))
        if len(cgn) >= 3:
            result.append(RMAC_GENDER.get(cgn[2], cgn[2]))
        if len(parts) >= 3:
            result.append(RMAC_DEGREE.get(parts[2], parts[2]))

    return " \u00b7 ".join(result)


def expand_morph(parse_tag, lang):
    """Dispatch to OT or NT expander based on language."""
    if lang == "heb":
        return expand_ot_morph(parse_tag)
    else:
        return expand_nt_morph(parse_tag)



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
    return candidates[0][1]


def load_ot_strongs():
    """
    Build a map from (kjv_book_num, chapter, verse, word_position) -> strong_number.
    This is correct because BHSsort and BHSA word nodes use different sequential
    numbering but agree on word order within each verse.
    The KJVverseID column in the CSV gives (testament, book, chapter, verse).
    """
    if not os.path.exists(STRONG_CSV):
        print("  WARNING: Strong's CSV not found -- Strong's numbers will be omitted.")
        return {}

    import re as _re
    mapping = {}       # (book_num, ch, vs, position_0based) -> strong_number
    verse_counters = {}  # (book_num, ch, vs) -> current position count

    with open(STRONG_CSV, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            kjv = row.get("\u3014KJVverseID\uff5cbook\uff5cchapter\uff5cverse\u3015", "")
            sn  = row.get("extendedStrongNumber", "").strip()
            if not kjv or not sn:
                continue
            m = _re.search(r'\u3014(\d+)\uff5c(\d+)\uff5c(\d+)\uff5c(\d+)\u3015', kjv)
            if not m:
                continue
            bk, ch, vs = int(m.group(2)), int(m.group(3)), int(m.group(4))
            key = (bk, ch, vs)
            pos = verse_counters.get(key, 0)
            verse_counters[key] = pos + 1
            mapping[(bk, ch, vs, pos)] = sn

    print("  Loaded " + str(len(mapping)) + " OT Strong's entries (verse-position keyed)")
    return mapping


# KJV book number map for OT Strong's lookup
KJV_BOOK_NUMS = {
    "Genesis": 1, "Exodus": 2, "Leviticus": 3, "Numbers": 4,
    "Deuteronomy": 5, "Joshua": 6, "Judges": 7, "Ruth": 8,
    "1_Samuel": 9, "2_Samuel": 10, "1_Kings": 11, "2_Kings": 12,
    "1_Chronicles": 13, "2_Chronicles": 14, "Ezra": 15, "Nehemiah": 16,
    "Esther": 17, "Job": 18, "Psalms": 19, "Proverbs": 20,
    "Ecclesiastes": 21, "Song_of_songs": 22, "Isaiah": 23, "Jeremiah": 24,
    "Lamentations": 25, "Ezekiel": 26, "Daniel": 27, "Hosea": 28,
    "Joel": 29, "Amos": 30, "Obadiah": 31, "Jonah": 32, "Micah": 33,
    "Nahum": 34, "Habakkuk": 35, "Zephaniah": 36, "Haggai": 37,
    "Zechariah": 38, "Malachi": 39,
}


# ---------------------------------------------------------------------------
# BHSA ASCII -> readable transliteration
# ---------------------------------------------------------------------------
def bhsa_to_translit(g_word):
    CONS = {
        ">": "\u02bc", "B": "b", "G": "g", "D": "d", "H": "h",
        "W": "w", "Z": "z", "X": "\u1e25", "V": "\u1e6d", "J": "y",
        "K": "k", "k": "k", "L": "l", "M": "m", "m": "m",
        "N": "n", "n": "n", "S": "s", "<": "\u02bf", "P": "p",
        "p": "p", "Y": "\u1e63", "y": "\u1e63", "Q": "q", "R": "r",
        "C": "\u0161", "F": "\u015b", "#": "\u0161", "T": "t",
    }
    VOWELS = {
        "A": "a", ":A": "\u1d43", "@": "\u0101", ":@": "\u1d52",
        "E": "e", ":E": "\u1d49", ";": "\u00ea", "I": "\u00ee",
        "O": "\u00f4", "U": "u", ":": "\u1d49",
    }
    TWO = {":A", ":@", ":E"}
    result = []
    i = 0
    s = g_word
    n = len(s)
    while i < n:
        c = s[i]
        if c.isdigit() and i + 1 < n and s[i + 1].isdigit():
            i += 2
            continue
        if c == ".":
            i += 2 if i + 1 < n and s[i + 1] in ("c", "f") else i + 1
            i = i  # already incremented inside ternary logic -- rewrite:
        if c == ".":
            if i + 1 < n and s[i + 1] in ("c", "f"):
                i += 2
            else:
                i += 1
            continue
        if c in (",", "&", "_", "'", "*"):
            i += 1
            continue
        if c == "0" and i + 1 < n and s[i + 1] in ("0", "5"):
            i += 2
            continue
        if c == ":" and i + 1 < n:
            two = ":" + s[i + 1]
            if two in TWO:
                result.append(VOWELS[two])
                i += 2
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
# HTML fragment builders -- table-based layout for e-Sword compatibility
# Hebrew text uses <heb> tag, Greek uses <grk> tag (e-Sword font switching)
# Phrases sit side-by-side in a row; words sit side-by-side within phrases
# ---------------------------------------------------------------------------
def word_box(text, translit, gloss, parse_tag, strong, lang="grk"):
    """
    Word rendered as inline-block div matching OGNTi structure exactly.
    tvm and num tags must NOT be inside table cells -- e-Sword only
    intercepts them at the top level of the div content.
    """
    tag = "heb" if lang == "heb" else "grk"

    strong_num_tag = ""
    if strong:
        raw = str(strong).lstrip("HGhg")
        prefix = "H" if lang == "heb" else "G"
        strong_num_tag = "<num>" + prefix + raw + "</num>"

    morph_tvm_tag = ""
    if parse_tag and lang == "grk":
        morph_tvm_tag = "<tvm>" + parse_tag + "</tvm>"

    # Human-readable morphology expansion
    morph_expanded = expand_morph(parse_tag, lang) if parse_tag else ""

    h  = "<div style='display:inline-block;vertical-align:top;"
    h += "border:1px solid #444466;background-color:#0d0d18;"
    h += "padding:3px;margin:2px;text-align:center;'>"
    h += "<" + tag + "><font size='4' color='#ffffff'>" + esc(text) + "</font></" + tag + ">"
    if translit:
        h += "<br><font size='1' color='#5ecfb0'><i>" + esc(translit) + "</i></font>"
    h += "<br><font size='1' color='#8a8a9a'>" + esc(gloss) + "</font>"
    if parse_tag:
        if morph_tvm_tag:
            # tvm tag for clickability, expanded text as visible label
            h += "<br>" + morph_tvm_tag
            if morph_expanded and morph_expanded != parse_tag:
                h += "<br><font size='1' color='#555570'>" + esc(morph_expanded) + "</font>"
        else:
            # OT: no tvm, just show expanded form
            h += "<br><font size='1' color='#555570'>" + esc(morph_expanded or parse_tag) + "</font>"
    if strong_num_tag:
        h += "<br>" + strong_num_tag
    h += "</div>"
    return h


def phrase_box(func_lbl, type_lbl, word_list):
    """Phrase: header then word divs flowing inline inside one td."""
    short_type = type_lbl.split()[0] if type_lbl else ""
    h  = "<table border='1' cellpadding='3' cellspacing='0' width='100%' "
    h += "bgcolor='#1a2035' style='border-color:#2a5a8a;'>"
    if func_lbl or short_type:
        h += "<tr bgcolor='#162040'><td align='center'>"
        if func_lbl:
            h += "<b><font size='2' color='#f0965a'>" + esc(func_lbl) + "</font></b>"
        if func_lbl and short_type:
            h += "&nbsp;"
        if short_type:
            h += "<font size='1' color='#5ecfb0'><i>" + esc(short_type) + "</i></font>"
        h += "</td></tr>"
    # All word divs in one td -- they flow as inline-block, wrapping naturally
    h += "<tr><td>" + "".join(word_list) + "</td></tr>"
    h += "</table>"
    return h


def clause_box(func_lbl, type_lbl, inner_list):
    """Clause: header then phrases laid out 2 per row for mobile."""
    PHRASES_PER_ROW = 2
    h  = "<table border=\"1\" cellpadding=\"4\" cellspacing=\"0\" width=\"100%\" "
    h += "bgcolor=\"#1a1a2e\" style=\"border-color:#6a4aaa;margin-bottom:6px;\">"
    if func_lbl or type_lbl:
        h += "<tr bgcolor=\"#180f2a\"><td colspan=\"" + str(PHRASES_PER_ROW) + "\">"
        if func_lbl:
            h += "<b><font size=\"2\" color=\"#5ecfb0\">" + esc(func_lbl) + "</font></b>"
        if func_lbl and type_lbl:
            h += "&nbsp;&nbsp;"
        if type_lbl:
            h += "<font size=\"1\" color=\"#b57ff5\"><i>" + esc(type_lbl) + "</i></font>"
        h += "</td></tr>"
    for i in range(0, max(1, len(inner_list)), PHRASES_PER_ROW):
        chunk = inner_list[i:i + PHRASES_PER_ROW]
        h += "<tr>"
        for ph in chunk:
            h += "<td valign=\"top\" width=\"50%\">" + ph + "</td>"
        h += "</tr>"
    h += "</table>"
    return h


def wrap_verse(direction, clauses_html):
    # Always LTR for table layout so cells read TL->TR->BL->BR.
    # Hebrew text direction is handled by the <heb> tag inside each cell.
    return "<div dir=\"ltr\">" + "".join(clauses_html) + "</div>"



# ---------------------------------------------------------------------------
# SQLite .cmti builder
# ---------------------------------------------------------------------------
def create_cmti(filename, description, abbreviation):
    if os.path.exists(filename):
        os.remove(filename)
    conn = sqlite3.connect(filename)
    cur  = conn.cursor()
    # Correct schema matching real .cmti files (e.g. LGNTDF.cmti)
    cur.execute(
        "CREATE TABLE Details ("
        "Title NVARCHAR(255), "
        "Abbreviation NVARCHAR(50), "
        "Information TEXT, "
        "Version INT"
        ")"
    )
    cur.execute(
        "INSERT INTO Details VALUES (?, ?, ?, ?)",
        (description, abbreviation,
         "Generated from BHSA/ETCBC and N1904/MACULA datasets using Text-Fabric.",
         4)
    )
    cur.execute(
        "CREATE TABLE BookCommentary ("
        "Book INT, Comments TEXT"
        ")"
    )
    cur.execute(
        "CREATE TABLE ChapterCommentary ("
        "Book INT, Chapter INT, Comments TEXT"
        ")"
    )
    cur.execute(
        "CREATE TABLE VerseCommentary ("
        "Book INT, ChapterBegin INT, VerseBegin INT, "
        "ChapterEnd INT, VerseEnd INT, Comments TEXT"
        ")"
    )
    cur.execute(
        "CREATE INDEX VerseCommentaryIndex ON VerseCommentary "
        "(Book, ChapterBegin, VerseBegin)"
    )
    conn.commit()
    return conn


def insert_verse(conn, book_num, chapter, verse, html):
    conn.cursor().execute(
        "INSERT INTO VerseCommentary "
        "(Book, ChapterBegin, VerseBegin, ChapterEnd, VerseEnd, Comments) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (book_num, chapter, verse, chapter, verse, html)
    )


# ---------------------------------------------------------------------------
# OT generator
# ---------------------------------------------------------------------------
def generate_ot(conn=None):
    print("\n=== OLD TESTAMENT (BHSA/ETCBC) -> BHS_Syntax.cmti ===")

    strongs_map = load_ot_strongs()

    tf_dir = find_tf_dir(BHSA_DIR, ["tf/2021", "tf/2020", "tf/2019", "tf/2017", "tf/c", "tf"])
    if not tf_dir:
        print("ERROR: no BHSA .tf data under " + BHSA_DIR)
        sys.exit(1)
    print("  Data: " + tf_dir)

    TF  = Fabric(locations=tf_dir, silent=True)
    api = TF.load(
        "otype g_word_utf8 g_cons_utf8 g_word "
        "gloss sp vs vt gn nu st ps typ function domain txt book chapter verse "
        "mother",
        silent=True,
    )
    if api is False:
        print("ERROR: TF.load() failed.")
        sys.exit(1)

    F, L, T, E = api.F, api.L, api.T, api.E

    # Build word_node -> strong_number by matching verse position
    # strongs_map keys are (kjv_book_num, ch, vs, position_0based)
    print("  Building word->Strong's lookup by verse position...")
    word_strong = {}
    for bk_node in F.otype.s("book"):
        book_id  = T.sectionFromNode(bk_node)[0]
        book_num = KJV_BOOK_NUMS.get(book_id)
        if book_num is None:
            continue
        for ch_node in L.d(bk_node, "chapter"):
            ch_num = T.sectionFromNode(ch_node)[1]
            for v_node in L.d(ch_node, "verse"):
                v_num  = T.sectionFromNode(v_node)[2]
                v_words = L.d(v_node, "word")
                for pos, w_node in enumerate(v_words):
                    sn = strongs_map.get((book_num, ch_num, v_num, pos), "")
                    if sn:
                        word_strong[w_node] = sn
    print("  Mapped " + str(len(word_strong)) + " word nodes to Strong's numbers")

    # Build clause_node -> (book_en, ch, vs) for mother cross-reference resolution
    # Includes clause_atom nodes since some mothers point to those
    print("  Building clause reference map...")
    clause_ref = {}
    for cl in list(F.otype.s("clause")) + list(F.otype.s("clause_atom")):
        sec = T.sectionFromNode(cl)
        if sec and len(sec) >= 3:
            clause_ref[cl] = (
                OT_BOOK_NAMES.get(sec[0], sec[0]),
                sec[1], sec[2]
            )
    print("  Clause reference map: " + str(len(clause_ref)) + " entries")

    if conn is None:
        conn = create_cmti(
            "BHS_Syntax.cmti",
            "Hebrew Bible Syntactic Analysis (BHSA/ETCBC)",
            "BHS-Syntax"
        )
        standalone = True
    else:
        standalone = False

    total_verses = 0
    for bk_node in F.otype.s("book"):
        book_id = T.sectionFromNode(bk_node)[0]
        book_num = OT_BOOK_NUMBERS.get(book_id)
        if book_num is None:
            print("  SKIP (unknown book): " + repr(book_id))
            continue
        print("  " + book_id)

        for ch_node in L.d(bk_node, "chapter"):
            ch_num = T.sectionFromNode(ch_node)[1]

            for v_node in L.d(ch_node, "verse"):
                v_num = T.sectionFromNode(v_node)[2]

                clauses_html = []
                for cl_node in L.d(v_node, "clause"):
                    cl_func = OT_FUNC.get(sf(F, "function", cl_node), sf(F, "function", cl_node))
                    cl_typ  = OT_TYP.get(sf(F, "typ", cl_node), sf(F, "typ", cl_node))

                    # Discourse domain tag
                    cl_txt     = sf(F, "txt", cl_node)
                    cl_disc    = ot_discourse_label(cl_txt)

                    # Mother cross-reference
                    cl_mother_ref = ""
                    mothers = E.mother.f(cl_node)
                    if mothers:
                        m = mothers[0]
                        mref = clause_ref.get(m)
                        if mref:
                            m_bk, m_ch, m_vs = mref
                            this_vs = T.sectionFromNode(cl_node)
                            # Only show if mother is in a different verse
                            if not this_vs or m_vs != this_vs[2] or m_ch != this_vs[1]:
                                cl_mother_ref = m_bk + " " + str(m_ch) + ":" + str(m_vs)

                    # Append discourse and cross-ref to type label
                    extras = []
                    if cl_disc:
                        extras.append(cl_disc)
                    if cl_mother_ref:
                        extras.append("depends on " + cl_mother_ref)
                    if extras:
                        cl_typ = (cl_typ + " | " + " | ".join(extras)).strip(" |")

                    phrases_html = []
                    for ph_node in L.d(cl_node, "phrase"):
                        ph_func = OT_FUNC.get(sf(F, "function", ph_node), sf(F, "function", ph_node))
                        ph_typ  = OT_TYP.get(sf(F, "typ", ph_node), sf(F, "typ", ph_node))

                        words_html = []
                        for w_node in L.d(ph_node, "word"):
                            text     = sf(F, "g_word_utf8", w_node) or sf(F, "g_cons_utf8", w_node)
                            translit = bhsa_to_translit(sf(F, "g_word", w_node))
                            gloss    = sf(F, "gloss", w_node)
                            sp_v     = sf(F, "sp", w_node)
                            vs_v     = sf(F, "vs", w_node)
                            vt_v     = sf(F, "vt", w_node)
                            gn_v     = sf(F, "gn", w_node)
                            nu_v     = sf(F, "nu", w_node)
                            st_v     = sf(F, "st", w_node)
                            ps_v     = sf(F, "ps", w_node)
                            def _ok(v):
                                return v and v not in ("NA", "n/a", "absent", "none", "unknown", "")
                            # Always store in fixed order: sp.vs.vt.gn.nu.ps.st
                            parse_tag = ".".join([
                                sp_v if _ok(sp_v) else "",
                                vs_v if _ok(vs_v) else "",
                                vt_v if _ok(vt_v) else "",
                                gn_v if _ok(gn_v) else "",
                                nu_v if _ok(nu_v) else "",
                                ps_v if _ok(ps_v) else "",
                                st_v if _ok(st_v) else "",
                            ]).rstrip(".")
                            # Remove trailing empty segments
                            while parse_tag.endswith("."):
                                parse_tag = parse_tag[:-1]
                            strong    = word_strong.get(w_node, "")
                            words_html.append(word_box(text, translit, gloss, parse_tag, strong, lang="heb"))

                        phrases_html.append(phrase_box(ph_func, ph_typ, words_html))

                    clauses_html.append(clause_box(cl_func, cl_typ, phrases_html))

                if clauses_html:
                    html = wrap_verse("rtl", clauses_html)
                    insert_verse(conn, book_num, ch_num, v_num, html)
                    total_verses += 1

        conn.commit()

    # Book commentary: one entry per book with domain breakdown and clause stats
    print("  Building OT book commentary...")
    for bk_node in F.otype.s("book"):
        book_id  = T.sectionFromNode(bk_node)[0]
        book_num = OT_BOOK_NUMBERS.get(book_id)
        book_en  = OT_BOOK_NAMES.get(book_id, book_id)
        if book_num is None:
            continue
        # Count clauses by domain and type
        domain_counts = {"Narrative": 0, "Discursive": 0, "Quotation": 0, "Unknown": 0}
        type_counts = {}
        total_cls = 0
        for cl in L.d(bk_node, "clause"):
            total_cls += 1
            d = ot_discourse_label(sf(F, "txt", cl))
            if d:
                domain_counts[d] = domain_counts.get(d, 0) + 1
            else:
                domain_counts["Unknown"] += 1
            t = OT_TYP.get(sf(F, "typ", cl), sf(F, "typ", cl))
            if t:
                type_counts[t] = type_counts.get(t, 0) + 1
        # Build HTML
        h  = "<b><font size=\'3\'>" + book_en + " -- Syntactic Overview</font></b><br><br>"
        h += "<b>Total clauses:</b> " + str(total_cls) + "<br><br>"
        h += "<b>Discourse Domain Breakdown:</b><br>"
        for dom, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
            if count > 0:
                h += "&nbsp;&nbsp;" + dom + ": " + str(count) + "<br>"
        h += "<br><b>Top Clause Types:</b><br>"
        for typ, count in sorted(type_counts.items(), key=lambda x: -x[1])[:10]:
            h += "&nbsp;&nbsp;" + typ + ": " + str(count) + "<br>"
        cur = conn.cursor()
        cur.execute("INSERT INTO BookCommentary (Book, Comments) VALUES (?, ?)",
                    (book_num, h))
    conn.commit()

    if standalone:
        conn.close()
        size_mb = round(os.path.getsize("BHS_Syntax.cmti") / 1e6, 1)
        print("\n  Written: BHS_Syntax.cmti  (" + str(size_mb) + " MB)")
    print("  OT verses: " + str(total_verses))
    if not standalone:
        return conn


# ---------------------------------------------------------------------------
# NT generator
# ---------------------------------------------------------------------------
def generate_nt(conn=None):
    print("\n=== NEW TESTAMENT (N1904) -> GNT_Syntax.cmti ===")

    tf_dir = find_tf_dir_n1904(N1904_DIR)
    if not tf_dir:
        print("ERROR: no N1904 .tf data under " + N1904_DIR)
        sys.exit(1)
    print("  Data: " + tf_dir)

    TF = Fabric(locations=tf_dir, silent=True)
    api = TF.load(
        "otype unicode text normalized gloss lemma lemmatranslit "
        "cls role function sp morph case number gender tense mood voice "
        "book chapter verse strong",
        silent=True,
    )
    if api is False:
        print("ERROR: TF.load() failed.")
        sys.exit(1)

    F, L, T = api.F, api.L, api.T
    all_types  = set(F.otype.all)
    has_phrase = "phrase" in all_types

    # Build clause -> verse map.
    # Each clause is assigned to every verse its words touch (multi-verse mapping)
    # so no words are ever missing. For cross-boundary clauses, we track which
    # words belong to each verse so we only render those words under that verse,
    # preventing the crash from rendering 49-word clauses at a single verse entry.
    word_ref = {}
    for w in F.otype.s("word"):
        word_ref[w] = (F.book.v(w), F.chapter.v(w), F.verse.v(w))

    # Build word -> clause and word -> phrase lookups for fast bottom-up access
    word_to_clause = {}
    word_to_phrase = {}
    if "clause" in all_types:
        for cl in F.otype.s("clause"):
            for w in L.d(cl, "word"):
                word_to_clause[w] = cl
    if "phrase" in all_types:
        for ph in F.otype.s("phrase"):
            for w in L.d(ph, "word"):
                word_to_phrase[w] = ph

    # Build verse_words: all words per verse from verse container nodes
    verse_words = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for vn in F.otype.s("verse"):
        sec = T.sectionFromNode(vn)
        if sec and len(sec) >= 3:
            verse_words[sec[0]][sec[1]][sec[2]] = L.d(vn, "word")

    if conn is None:
        conn = create_cmti(
            "GNT_Syntax.cmti",
            "Greek NT Syntactic Analysis (Nestle 1904 / MACULA)",
            "GNT-Syntax"
        )
        standalone = True
    else:
        standalone = False

    def render_word_nt(w_node):
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
        return word_box(text, translit, gloss, morph, sn_str)

    total_verses = 0
    for book_id in NT_BOOK_ORDER:
        book_num = NT_BOOK_NUMBERS.get(book_id)
        if book_num is None:
            continue
        print("  " + NT_BOOK_NAMES.get(book_id, book_id))

        all_ch = sorted(verse_words[book_id].keys())

        for ch_num in all_ch:
            all_vs = sorted(verse_words[book_id][ch_num].keys())

            for vs_num in all_vs:
                vs_word_list = verse_words[book_id][ch_num].get(vs_num, [])
                if not vs_word_list:
                    continue

                # Group this verse's words by clause then by phrase
                # clause_node -> phrase_node (or None) -> [word_nodes]
                cl_ph_words = defaultdict(lambda: defaultdict(list))
                for w in vs_word_list:
                    cl = word_to_clause.get(w)
                    ph = word_to_phrase.get(w)
                    cl_ph_words[cl][ph].append(w)

                clauses_html = []

                for cl_node, ph_map in cl_ph_words.items():
                    # Clause label
                    if cl_node is not None:
                        cl_role = sf(F, "role", cl_node)
                        cl_cls  = sf(F, "cls",  cl_node)
                        cl_func = sf(F, "function", cl_node)
                        cl_func_lbl = NT_ROLE.get(cl_role, cl_role) or cl_func or ""
                        cl_type_lbl = NT_CLS.get(cl_cls, cl_cls)
                        # Continuation indicator
                        cl_all_words = L.d(cl_node, "word")
                        cl_verses = set(word_ref.get(w, ("", 0, 0))[2]
                                        for w in cl_all_words
                                        if word_ref.get(w, ("", 0, 0))[0] == book_id)
                        extras = []
                        if len(cl_verses) > 1:
                            other_vs = sorted(v for v in cl_verses if v != vs_num)
                            extras.append("cont. v." + "/".join(str(v) for v in other_vs))
                        # Parent clause cross-reference via containment
                        parent_clauses = L.u(cl_node, "clause")
                        if parent_clauses:
                            pc = parent_clauses[0]
                            pc_sec = T.sectionFromNode(pc)
                            if pc_sec and len(pc_sec) >= 3:
                                pc_vs = pc_sec[2]
                                pc_ch = pc_sec[1]
                                if pc_vs != vs_num or pc_ch != ch_num:
                                    pc_bk = NT_BOOK_NAMES.get(pc_sec[0], pc_sec[0])
                                    extras.append("depends on " + pc_bk + " " + str(pc_ch) + ":" + str(pc_vs))
                        if extras:
                            cl_type_lbl = (cl_type_lbl + " | " + " | ".join(extras)).strip(" |")
                        cl_func_lbl = (cl_func_lbl + "").strip()
                    else:
                        cl_func_lbl = ""
                        cl_type_lbl = ""
                        cont_str = ""

                    # If both labels empty but we have a cont indicator, put it in func
                    if not cl_func_lbl and not cl_type_lbl and cont_str:
                        cl_func_lbl = cont_str

                    phrases_html = []
                    for ph_node, w_list in ph_map.items():
                        if ph_node is not None:
                            ph_role = sf(F, "role", ph_node)
                            ph_cls  = sf(F, "cls",  ph_node)
                            ph_func = sf(F, "function", ph_node)
                            ph_func_lbl = NT_ROLE.get(ph_role, ph_role) or ph_func or ""
                            ph_type_lbl = NT_CLS.get(ph_cls, ph_cls)
                        else:
                            ph_func_lbl = ""
                            ph_type_lbl = ""
                        words_html = [render_word_nt(w) for w in w_list]
                        phrases_html.append(phrase_box(ph_func_lbl, ph_type_lbl, words_html))

                    clauses_html.append(clause_box(cl_func_lbl, cl_type_lbl, phrases_html))

                if clauses_html:
                    html = wrap_verse("ltr", clauses_html)
                    insert_verse(conn, book_num, ch_num, vs_num, html)
                    total_verses += 1

            conn.commit()

    # Book commentary for NT
    print("  Building NT book commentary...")
    for book_id in NT_BOOK_ORDER:
        book_num = NT_BOOK_NUMBERS.get(book_id)
        book_en  = NT_BOOK_NAMES.get(book_id, book_id)
        if book_num is None:
            continue
        # Count clauses by role and cls
        role_counts = {}
        total_cls = 0
        for cl in F.otype.s("clause"):
            words = L.d(cl, "word")
            if not words:
                continue
            if F.book.v(words[0]) != book_id:
                continue
            total_cls += 1
            role = NT_ROLE.get(sf(F, "role", cl), sf(F, "role", cl))
            if role:
                role_counts[role] = role_counts.get(role, 0) + 1
        if total_cls == 0:
            continue
        h  = "<b><font size=\'3\'>" + book_en + " -- Syntactic Overview</font></b><br><br>"
        h += "<b>Total clauses:</b> " + str(total_cls) + "<br><br>"
        h += "<b>Clause Role Breakdown:</b><br>"
        for role, count in sorted(role_counts.items(), key=lambda x: -x[1])[:12]:
            h += "&nbsp;&nbsp;" + (role or "unlabeled") + ": " + str(count) + "<br>"
        cur = conn.cursor()
        cur.execute("INSERT INTO BookCommentary (Book, Comments) VALUES (?, ?)",
                    (book_num, h))
    conn.commit()

    if standalone:
        conn.close()
        size_mb = round(os.path.getsize("GNT_Syntax.cmti") / 1e6, 1)
        print("\n  Written: GNT_Syntax.cmti  (" + str(size_mb) + " MB)")
    print("  NT verses: " + str(total_verses))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def generate_combined():
    """Generate a single Bible_Syntax.cmti with OT (1-39) and NT (40-66)."""
    print("\n=== COMBINED BIBLE SYNTAX -> Bible_Syntax.cmti ===")
    conn = create_cmti(
        "Bible_Syntax.cmti",
        "Bible Syntactic Analysis (BHSA/ETCBC + Nestle 1904 / MACULA)",
        "Bible-Syntax"
    )
    conn = generate_ot(conn=conn)
    generate_nt(conn=conn)
    conn.close()
    size_mb = round(os.path.getsize("Bible_Syntax.cmti") / 1e6, 1)
    print("\n  Written: Bible_Syntax.cmti  (" + str(size_mb) + " MB)")
    print("  Place in your e-Sword folder and restart e-Sword.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build e-Sword .cmti commentary files from TF datasets"
    )
    parser.add_argument("--ot-only",   action="store_true")
    parser.add_argument("--nt-only",   action="store_true")
    parser.add_argument("--combined",  action="store_true",
                        help="Single Bible_Syntax.cmti with OT+NT (default)")
    args = parser.parse_args()

    if not os.path.isdir(BASE_DIR):
        print("ERROR: " + BASE_DIR + " not found. Run step1_download_data.py first.")
        sys.exit(1)

    if args.ot_only:
        generate_ot()
    elif args.nt_only:
        generate_nt()
    else:
        # Default: combined
        generate_combined()

    print("\nDone.")