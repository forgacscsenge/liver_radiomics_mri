from totalsegmentator.python_api import totalsegmentator
import sys
import os
from pathlib import Path

ROI_SUBSET = ["liver"]
DEVICE = "cpu"

def liversegment(inputpath,outputfolder):

    os.makedirs(outputfolder, exist_ok=True)

    #totalsegmentator futtatasa
    totalsegmentator(
        inputpath,
        outputfolder,
        roi_subset=ROI_SUBSET,
        device=DEVICE
    )

    print("liver segmentation done")


if __name__ == "__main__":
    INPUT_PATH = Path(sys.argv[1])   #input nii file
    OUTPUT_FOLDER = Path(sys.argv[2])     #output folder

    liversegment(INPUT_PATH, OUTPUT_FOLDER)


