"""
step1_download_data.py
======================
Downloads all datasets needed for offline Bible syntax HTML generation:

  1. BHSA        -- Hebrew Bible, ETCBC linguistic annotations (Text-Fabric)
  2. N1904        -- Greek NT, Nestle 1904 Lowfat syntax trees (Text-Fabric)
  3. BHS-Strong   -- Strong's number mapping for every Hebrew word (single CSV zip)

Run this ONCE while online on ethernet.  After this, step2 runs fully offline.

Usage:
    python step1_download_data.py
    python step1_download_data.py --skip-bhsa    (if BHSA already downloaded)
    python step1_download_data.py --skip-n1904
    python step1_download_data.py --skip-strong

Requirements:
    pip install text-fabric requests tqdm
"""

import sys
import os
import zipfile
import shutil
import argparse

try:
    import requests
    from tqdm import tqdm
except ImportError:
    print("Missing dependencies. Run:")
    print("  pip install text-fabric requests tqdm")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR      = os.path.join(os.path.expanduser("~"), "bible_syntax_data")
BHSA_DIR      = os.path.join(BASE_DIR, "bhsa")
N1904_DIR     = os.path.join(BASE_DIR, "n1904")
STRONG_DIR    = os.path.join(BASE_DIR, "strong")

for d in [BHSA_DIR, N1904_DIR, STRONG_DIR]:
    os.makedirs(d, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def download_file(url, dest_path, label):
    print("\nDownloading " + label + "...")
    print("  URL: " + url)
    print("  -> " + dest_path)
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))
    with open(dest_path, "wb") as f, tqdm(
        total=total, unit="B", unit_scale=True, unit_divisor=1024, desc=label[:30]
    ) as bar:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
            bar.update(len(chunk))
    print("  Downloaded (" + str(round(os.path.getsize(dest_path) / 1e6, 1)) + " MB)")


def extract_zip_stripped(zip_path, dest_dir, strip_prefix):
    """Extract zip, stripping the top-level folder."""
    print("  Extracting to " + dest_dir + "...")
    with zipfile.ZipFile(zip_path, "r") as z:
        members = z.namelist()
        for member in tqdm(members, desc="Extracting"):
            if member.startswith(strip_prefix + "/"):
                rel = member[len(strip_prefix) + 1:]
            else:
                rel = member
            if not rel:
                continue
            target = os.path.join(dest_dir, rel)
            if member.endswith("/"):
                os.makedirs(target, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    print("  Extracted")


def extract_zip_flat(zip_path, dest_dir):
    """Extract all files from zip directly into dest_dir (no subfolder stripping)."""
    print("  Extracting to " + dest_dir + "...")
    with zipfile.ZipFile(zip_path, "r") as z:
        # find the single CSV inside (may be nested)
        for member in z.namelist():
            if member.endswith(".csv") and "BHS-with-Strong" in member:
                # extract just this file flat into dest_dir
                data = z.read(member)
                out_path = os.path.join(dest_dir, "BHS-with-Strong-no-extended.csv")
                with open(out_path, "wb") as f:
                    f.write(data)
                print("  Extracted: " + out_path
                      + " (" + str(round(len(data) / 1e6, 1)) + " MB)")
                return
        # fallback: extract everything
        z.extractall(dest_dir)
    print("  Extracted (fallback)")


def already_done(dest_zip, dest_dir, marker_file):
    """Return True if zip is present and marker file exists in dest_dir."""
    return (
        os.path.exists(dest_zip)
        and os.path.getsize(dest_zip) > 100_000
        and os.path.exists(os.path.join(dest_dir, marker_file))
    )


# ---------------------------------------------------------------------------
# Dataset 1: BHSA
# ---------------------------------------------------------------------------
def download_bhsa():
    print("\n" + "=" * 40)
    print("DATASET 1: BHSA (Hebrew Bible, ETCBC)")
    print("=" * 40)

    zip_path = os.path.join(BASE_DIR, "bhsa.zip")
    marker   = os.path.join(BHSA_DIR, "tf")   # directory marker

    if os.path.exists(zip_path) and os.path.getsize(zip_path) > 1_000_000 and os.path.isdir(marker):
        print("  Already downloaded and extracted. Skipping.")
        return

    url = "https://github.com/ETCBC/bhsa/archive/refs/heads/master.zip"
    download_file(url, zip_path, "BHSA")

    if os.path.exists(BHSA_DIR):
        shutil.rmtree(BHSA_DIR)
    os.makedirs(BHSA_DIR, exist_ok=True)
    extract_zip_stripped(zip_path, BHSA_DIR, "bhsa-master")
    print("  BHSA done -> " + BHSA_DIR)


# ---------------------------------------------------------------------------
# Dataset 2: N1904
# ---------------------------------------------------------------------------
def download_n1904():
    print("\n" + "=" * 40)
    print("DATASET 2: N1904 (Greek NT, Nestle 1904)")
    print("=" * 40)

    zip_path = os.path.join(BASE_DIR, "n1904.zip")
    marker   = os.path.join(N1904_DIR, "tf")

    if os.path.exists(zip_path) and os.path.getsize(zip_path) > 1_000_000 and os.path.isdir(marker):
        print("  Already downloaded and extracted. Skipping.")
        return

    url = "https://github.com/CenterBLC/N1904/archive/refs/heads/main.zip"
    download_file(url, zip_path, "N1904")

    if os.path.exists(N1904_DIR):
        shutil.rmtree(N1904_DIR)
    os.makedirs(N1904_DIR, exist_ok=True)
    extract_zip_stripped(zip_path, N1904_DIR, "N1904-main")
    print("  N1904 done -> " + N1904_DIR)


# ---------------------------------------------------------------------------
# Dataset 3: BHS-Strong-no (single CSV zip, ~3 MB)
# ---------------------------------------------------------------------------
def download_strong():
    print("\n" + "=" * 40)
    print("DATASET 3: BHS Strong's numbers + KJV versification mapping")
    print("=" * 40)

    zip_path  = os.path.join(BASE_DIR, "bhs_strong.zip")
    csv_path  = os.path.join(STRONG_DIR, "BHS-with-Strong-no-extended.csv")
    kjv_dir   = os.path.join(BASE_DIR, "bhs_kjv_map")

    # Strong's CSV
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 100_000:
        print("  Strong's CSV already downloaded. Skipping.")
    else:
        url = "https://github.com/eliranwong/BHS-Strong-no/raw/master/BHS-with-Strong-no-extended.csv.zip"
        download_file(url, zip_path, "BHS-Strong-no")
        if os.path.exists(STRONG_DIR):
            shutil.rmtree(STRONG_DIR)
        os.makedirs(STRONG_DIR, exist_ok=True)
        extract_zip_flat(zip_path, STRONG_DIR)
        print("  Strong's done -> " + STRONG_DIR)

    # KJV versification mapping from OpenHebrewBible 008-BHS-mapping-KJV
    os.makedirs(kjv_dir, exist_ok=True)
    kjv_csvs = [f for f in os.listdir(kjv_dir) if f.endswith(".csv")]
    if kjv_csvs:
        print("  KJV mapping already downloaded (" + str(len(kjv_csvs)) + " files). Skipping.")
    else:
        print("  Downloading KJV versification mapping (OpenHebrewBible 008)...")
        full_zip = os.path.join(BASE_DIR, "ohb_full.zip")
        url = "https://github.com/eliranwong/OpenHebrewBible/archive/refs/heads/master.zip"
        download_file(url, full_zip, "OpenHebrewBible")
        extracted = 0
        with zipfile.ZipFile(full_zip, "r") as z:
            for member in z.namelist():
                if "008-BHS-mapping-KJV" in member and member.endswith(".csv"):
                    data = z.read(member)
                    fname = os.path.basename(member)
                    with open(os.path.join(kjv_dir, fname), "wb") as f:
                        f.write(data)
                    print("  Extracted: " + fname + " (" + str(len(data)//1000) + " KB)")
                    extracted += 1
        if os.path.exists(full_zip):
            os.remove(full_zip)
        print("  KJV mapping done: " + str(extracted) + " files -> " + kjv_dir)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Download Bible syntax datasets")
    parser.add_argument("--skip-bhsa",   action="store_true")
    parser.add_argument("--skip-n1904",  action="store_true")
    parser.add_argument("--skip-strong", action="store_true")
    args = parser.parse_args()

    print("Bible Syntax Data Downloader")
    print("=" * 40)
    print("Data directory: " + BASE_DIR)
    print("Estimated download: ~1.5 GB total (BHSA ~600 MB, N1904 ~200 MB, Strong's ~3 MB)")
    print("Make sure you are on ethernet.\n")

    if not args.skip_bhsa:
        download_bhsa()
    else:
        print("\n[SKIP] BHSA")

    if not args.skip_n1904:
        download_n1904()
    else:
        print("\n[SKIP] N1904")

    if not args.skip_strong:
        download_strong()
    else:
        print("\n[SKIP] Strong's")

    print("\n" + "=" * 40)
    print("All downloads complete.")
    print("Now run:  python step2_generate_html.py")


if __name__ == "__main__":
    main()
