import os
import json
import glob
import argparse
import numpy as np
import pandas as pd
import ants
from radiomics import featureextractor


#At this stage, it converts numerical data received from multiple sources into floating-point format; where there is no data, it returns “none.”
def to_float(x):
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() in {"na", "nan", "none"}:
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

#consolidates SESIDs coming from multiple sources (removes the “SES” prefix or leaves it unchanged if it is not present)
def norm_session_id(s: str) -> str:
    s = str(s).strip()
    if s.startswith("ses-"):
        s = s[4:]
    return s

#It's a test to see if the two sesid are the same
def session_ids_equivalent(a: str, b: str) -> bool:
    a = norm_session_id(a)
    b = norm_session_id(b)

    if a == b:
        return True

#It goes through the methods listed below to ensure that the sesids are equal
    if a.replace("I", ".") == b:
        return True
    if a == b.replace("I", "."):
        return True
    if a.replace(".", "I") == b:
        return True
    if a == b.replace(".", "I"):
        return True

    return False

#finds the first column in the DataFrame that I want to filter by (regardless of whether it contains lowercase, uppercase, or misspelled words)
def pick_col_case_insensitive(df: pd.DataFrame, wanted: list[str]):
    cols = list(df.columns)
    lower_map = {c.lower(): c for c in cols}
    for w in wanted:
        if w.lower() in lower_map:
            return lower_map[w.lower()]
    return None

#It reads the weight and height from the session.tsv file based on the session ID associated with a specific patient, and then calculates the BMI.
def read_sessions_meta(rawdata_root: str, taj: str, sesid: str) -> dict:
    sesid = norm_session_id(sesid)
#The default output is “out,” even if there is no data
    out = {"Patient_Weight_kg": None, "Patient_Size_m": None, "BMI": None}

#Check for session.tsv; if it does not exist, return “NONE”
    sessions_tsv = os.path.join(rawdata_root, f"sub-{taj}", "sessions.tsv")
    if not os.path.isfile(sessions_tsv):
        return out

    #Reading a TSV file using flexible delimiters (; tab, comma+space)
    df = pd.read_csv(
        sessions_tsv,
        sep=r"\t|;|\s*,\s*",
        engine="python",
        dtype=str,
        skipinitialspace=True,
    )
    df.columns = [c.strip() for c in df.columns] #veletlen/felesleges szokozok leszedese
#Search for the “sesid” column based on the possibilities listed below
    sid_col = pick_col_case_insensitive(df, ["session-id", "session_id", "session", "sesid", "ses"])
    if sid_col is None:
        return out
#Finding the “size” and “weight” columns
    w_col = pick_col_case_insensitive(df, ["weight", "patient_weight", "Patient_Weight", "testsuly"])
    s_col = pick_col_case_insensitive(df, ["size", "patient_size", "Patient_Size", "magassag"])

    #Find the row associated with “sesid” (if there are multiple, keep the last row)
    hit = None
    for _, row in df.iterrows():
        sid_val = (row.get(sid_col, "") or "").strip()
        if session_ids_equivalent(sid_val, sesid):
            hit = row

    #weight: only from the current session
    w = None
    if hit is not None and w_col:
        w = to_float(hit.get(w_col))

    #size: primarily from the row associated with the current session
    s = None
    if hit is not None and s_col:
        s = to_float(hit.get(s_col))

    #If it's in centimeters, convert it to meters
    if isinstance(s, float) and s > 3.0:
        s = s / 100.0

    #If “size” isn't in the current session, it checks to see if it's in another one and selects the most recent occurrence.
    if (s is None or not isinstance(s, float) or s <= 0) and s_col:
        fallback_s = None
        for _, row in df.iterrows():
            cand = to_float(row.get(s_col))
            if isinstance(cand, float) and cand > 0:
                # cm -> m
                if cand > 3.0:
                    cand = cand / 100.0
                fallback_s = cand
        s = fallback_s

    out["Patient_Weight_kg"] = w
    out["Patient_Size_m"] = s

#BMI counting
    if isinstance(w, float) and isinstance(s, float) and s > 0:
        out["BMI"] = w / (s ** 2)

    return out

#It searches for .json files in the folder under the specified sub-taj/ses-sesid and reads the Station/Institution/Manufacturer model names.
def read_ses_json_meta(rawdata_root: str, taj: str, sesid: str) -> dict:
    sesid = norm_session_id(sesid)
#The default output is “out”
    out = {
        "Station_Name": None,
        "Institution_Name": None,
        "Manufacturers_Model_Name": None,
    }

#Definition of “session library”
    ses_dir = os.path.join(rawdata_root, f"sub-{taj}", f"ses-{sesid}")
    if not os.path.isdir(ses_dir):
        return out

#Recursive .json search, because the directory structure isn't always the same, so it searches every folder under the root directory
    for jp in sorted(glob.glob(os.path.join(ses_dir, "**", "*.json"), recursive=True)):
        try:
            with open(jp, "r", encoding="utf-8") as f:
                d = json.load(f)

#It reads each JSON file; if it finds a key in it, it writes the value only if the cell's value was previously None. If all three values are present, it exits.
#It searches for keys in JSON files in various ways
            if out["Manufacturers_Model_Name"] is None and "ManufacturersModelName" in d:
                v = str(d["ManufacturersModelName"]).strip()
                out["Manufacturers_Model_Name"] = v or None

            if out["Institution_Name"] is None and "InstitutionName" in d:
                v = str(d["InstitutionName"]).strip()
                out["Institution_Name"] = v or None

            if out["Station_Name"] is None:
                # előfordulhat több kulcsnév is
                for key in ["StationName", "Station", "Station_Name"]:
                    if key in d:
                        v = str(d[key]).strip()
                        if v:
                            out["Station_Name"] = v
                            break

#The output point, if the values of all three cells are known
            if all(out[k] is not None for k in out):
                break

#If the JSON is corrupted, radiomics won't shut down
        except Exception:
            continue

    return out


#radiomics
def main():
#arguments from process.sh
    ap = argparse.ArgumentParser()
    ap.add_argument("--adc_in_atlas", required=True)
    ap.add_argument("--taj", required=True)
    ap.add_argument("--sesid", required=True)
    ap.add_argument("--gender", required=True, help="M or F (pontosan)")
    ap.add_argument("--voi_male", required=True)
    ap.add_argument("--voi_female", required=True)
    ap.add_argument("--params", required=True)
    ap.add_argument("--rawdata", required=True)
    ap.add_argument("--out_csv", required=True)
    ap.add_argument("--out_masks_dir", required=True)
    args = ap.parse_args()

#Gender validation (only “M” and “F” are allowed; ‘male’ and “female” are not)
    if args.gender not in {"M", "F"}:
        raise ValueError("Gender must be exactly 'M' or 'F'.")
#Selection of Voi based on gender
    voi_path = args.voi_female if args.gender == "F" else args.voi_male
#Creating an output folder for the resampled VOIs and the CSV files
    os.makedirs(args.out_masks_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.out_csv), exist_ok=True)
#Initializing the Radiomics Extractor from params.yaml to specify which features to calculate
    extractor = featureextractor.RadiomicsFeatureExtractor(args.params)
#Extract the patient ID from the filename; this will be the column name in the CSV file
    adc_path = args.adc_in_atlas
    patient_id = os.path.basename(adc_path).replace("_adc_in_atlas.nii.gz", "")

    #reading adc file
    img = ants.image_read(adc_path)

    #A safety measure to ensure that the Voi mask is resampled to the ADC (if they are in different spaces)
    voi = ants.image_read(voi_path)
    voi_on_img = ants.resample_image_to_target(voi, img, interp_type="nearestNeighbor")
    #saving voi
    mask_path = os.path.join(args.out_masks_dir, f"{patient_id}_voi_on_adc.nii.gz")
    ants.image_write(voi_on_img, mask_path)

    #run radiomics
    feats = extractor.execute(adc_path, mask_path, label=1)

    #Compiling the output CSV file: first by weight/height, then by statname, etc.
    row = {}
    row.update(read_sessions_meta(args.rawdata, args.taj, args.sesid))
    row.update(read_ses_json_meta(args.rawdata, args.taj, args.sesid))

    #Add radiomic features, only those with the “original_” prefix
    for k, v in feats.items():
        if not k.startswith("original_"):
            continue
        try:
            row[k] = float(v)
        except Exception:
            row[k] = np.nan

#Create a column; the column name will be “taj_sesid”
    new_col = pd.Series(row, name=patient_id)

    #Fill in the matrix, or, generally, if there isn't one
    if os.path.isfile(args.out_csv):
        df = pd.read_csv(args.out_csv, index_col=0)
    else:
        df = pd.DataFrame()

    #If the column already exists, it overwrites it; if it does not exist, it adds it.
    df[new_col.name] = new_col

    #Meta-rows at the top, followed by the radiometric features
    meta_order = [
        "Patient_Weight_kg",
        "Patient_Size_m",
        "BMI",
        "Station_Name",
        "Institution_Name",
        "Manufacturers_Model_Name",
    ]
    meta_order = [m for m in meta_order if m in df.index]
    other = [f for f in df.index if f not in meta_order]
    df = df.loc[meta_order + other]

#Save and Print
    df.to_csv(args.out_csv)
    print(f"OK: {patient_id} -> {args.out_csv}")

if __name__ == "__main__":
    main()
