#!/usr/bin/env python3
import sys
import numpy as np
import SimpleITK as sitk


def load_and_binarize(path: str):
    img = sitk.ReadImage(path)

    #If it's in 4D, let's cut it down to 3D (rare, but it happens)
    if img.GetDimension() == 4:
        full = list(img.GetSize())
        size3d = [full[0], full[1], full[2], 0]
        idx = [0, 0, 0, 0]
        img = sitk.Extract(img, size3d, idx)

    arr = sitk.GetArrayFromImage(img)
    return img, (arr > 0)


def resample_to_ref(moving_img: sitk.Image, ref_img: sitk.Image) -> sitk.Image:
    resampler = sitk.ResampleImageFilter()
    resampler.SetReferenceImage(ref_img)
    resampler.SetInterpolator(sitk.sitkNearestNeighbor)
    resampler.SetDefaultPixelValue(0)
    return resampler.Execute(moving_img)


def jaccard_index(ref_path: str, moving_path: str) -> float:
    ref_img, ref_mask = load_and_binarize(ref_path)
    mov_img, _ = load_and_binarize(moving_path)

    # moving -> ref space (NN)
    mov_rs = resample_to_ref(mov_img, ref_img)
    mov_mask = sitk.GetArrayFromImage(mov_rs) > 0

    inter = np.logical_and(ref_mask, mov_mask).sum()
    uni = np.logical_or(ref_mask, mov_mask).sum()

    if uni == 0:
        return 1.0 if inter == 0 else 0.0
    return float(inter / uni)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python jaccard.py <ref_mask.nii.gz> <moving_mask.nii.gz>", file=sys.stderr)
        sys.exit(2)

    ref_mask_path = sys.argv[1]
    moving_mask_path = sys.argv[2]
    print(jaccard_index(ref_mask_path, moving_mask_path))
