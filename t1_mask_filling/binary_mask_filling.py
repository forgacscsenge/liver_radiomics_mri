import numpy as np
import nibabel as nib
from scipy.ndimage import binary_fill_holes, binary_closing
import sys

def mask_filling(inputpath, outputpath, structuresize=15):

    nii = nib.load(inputpath)
    mask = nii.get_fdata()
    mask = (mask > 0).astype(np.uint8)  #all non-0 voxel values are set to 1, while all zero values remain unchanged

    structure = np.ones((structuresize, structuresize, structuresize))
    filled = binary_closing(mask, structure=structure).astype(np.uint8)

    filled_nii = nib.Nifti1Image(filled, affine=nii.affine, header=nii.header)
    nib.save(filled_nii, outputpath)

if __name__ == "__main__":

    inputpath = sys.argv[1]
    outputpath = sys.argv[2]
    mask_filling(inputpath, outputpath)
