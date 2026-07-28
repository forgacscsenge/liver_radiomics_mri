import ants
import sys

def register_adc_to_t1_syn(t1_path, dwi_path, mask_path, out_mask_path, out_tfm_path):

    t1 = ants.image_read(t1_path)          #fixed
    dwi = ants.image_read(dwi_path)        #moving
    t1_mask = ants.image_read(mask_path)   #fixed mask

    #reorient everything to lpi
    t1_lpi = ants.reorient_image2(t1, "LPI")
    dwi_lpi = ants.reorient_image2(dwi, "LPI")
    t1_mask_lpi = ants.reorient_image2(t1_mask, "LPI")

    fixed = t1_lpi
    moving = dwi_lpi
    fixed_mask = t1_mask_lpi > 0

    #registration
    tx = ants.registration(
        fixed=fixed,
        moving=moving,
        type_of_transform="SyN",
        mask_image=fixed_mask,
        reg_iterations=(200, 100, 50, 20),
        verbose=False,
    )

    for f in tx["fwdtransforms"]:
        print("  ", f)

    for f in tx["invtransforms"]:
        print("  ", f)

    #saving tfm
    with open(out_tfm_path, "w") as f:
        for fname in tx["fwdtransforms"]:
            f.write(fname + "\n")

    #t1 liver mask in adc space
    mask_in_dwi = ants.apply_transforms(
        fixed=dwi_lpi,
        moving=t1_mask_lpi,
        transformlist=tx["invtransforms"],   #T12DWI
        interpolator="nearestNeighbor",
    )

    ants.image_write(mask_in_dwi, out_mask_path)

if __name__ == "__main__":
    _, t1, dwi, mask, out_mask, out_tfm = sys.argv
    register_adc_to_t1_syn(t1, dwi, mask, out_mask, out_tfm)
