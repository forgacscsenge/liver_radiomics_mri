#!/usr/bin/env python3
import sys
import numpy as np
import SimpleITK as sitk


def load_3d(path: str) -> sitk.Image:
    img = sitk.ReadImage(path)
    if img.GetDimension() == 4:
        full = list(img.GetSize())
        img = sitk.Extract(img, [full[0], full[1], full[2], 0], [0, 0, 0, 0])
    return img


def resample_to_ref(moving: sitk.Image, ref: sitk.Image) -> sitk.Image:
    r = sitk.ResampleImageFilter()
    r.SetReferenceImage(ref)
    r.SetInterpolator(sitk.sitkNearestNeighbor)
    r.SetDefaultPixelValue(0)
    return r.Execute(moving)


def hd95_mm(ref_path: str, mov_path: str) -> float:
    ref = load_3d(ref_path)
    mov = load_3d(mov_path)
    mov = resample_to_ref(mov, ref)

    ref = sitk.Cast(ref > 0, sitk.sitkUInt8)
    mov = sitk.Cast(mov > 0, sitk.sitkUInt8)

    # surface distance map (mm)
    dist_ref = sitk.Abs(sitk.SignedMaurerDistanceMap(ref, squaredDistance=False, useImageSpacing=True))
    dist_mov = sitk.Abs(sitk.SignedMaurerDistanceMap(mov, squaredDistance=False, useImageSpacing=True))

    # surface voxels
    ref_surf = sitk.LabelContour(ref)
    mov_surf = sitk.LabelContour(mov)

    d1 = sitk.GetArrayFromImage(dist_mov)[sitk.GetArrayFromImage(ref_surf) > 0]  # ref surface -> mov
    d2 = sitk.GetArrayFromImage(dist_ref)[sitk.GetArrayFromImage(mov_surf) > 0]  # mov surface -> ref

    if d1.size == 0 and d2.size == 0:
        return 0.0
    all_d = np.concatenate([d1, d2]) if d1.size and d2.size else (d1 if d1.size else d2)
    return float(np.percentile(all_d, 95))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python hausdorff.py <ref_mask.nii.gz> <moving_mask.nii.gz>", file=sys.stderr)
        sys.exit(2)
    print(hd95_mm(sys.argv[1], sys.argv[2]))
