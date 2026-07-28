import ants
import sys


def register_t1_to_atlas_syn(t1_path, mask_path, atlas_path, out_tfm, out_mask):

    t1 = ants.image_read(t1_path)          #moving
    t1_mask = ants.image_read(mask_path)   #moving mask
    atlas = ants.image_read(atlas_path)    #fixed

    #reorient everything to lpi
    t1_lpi = ants.reorient_image2(t1, "LPI")
    t1_mask_lpi = ants.reorient_image2(t1_mask, "LPI")
    atlas_lpi = ants.reorient_image2(atlas, "LPI")

    fixed = atlas_lpi
    moving = t1_lpi
    fixed_mask = fixed > 0
    moving_mask = t1_mask_lpi > 0

    #registration
    tx = ants.registration(
        fixed=fixed,
        moving=moving,
        type_of_transform="SyNRA",
        mask_image=fixed_mask,
        moving_mask=moving_mask,
        reg_iterations=(200, 100, 50, 20),
        verbose=False,
    )

    for f in tx["fwdtransforms"]:
        print("  ", f)

    #saving
    with open(out_tfm, "w") as f:
        for fname in tx["fwdtransforms"]:
            f.write(fname + "\n")

    #t1 mask deform to atlas
    warped_mask = ants.apply_transforms(
        fixed=fixed,
        moving=t1_mask_lpi,
        transformlist=tx["fwdtransforms"],
        interpolator="nearestNeighbor",
    )

    ants.image_write(warped_mask, out_mask)

if __name__ == "__main__":
    _, t1, mask, atlas, out_tfm, out_mask = sys.argv
    register_t1_to_atlas_syn(t1, mask, atlas, out_tfm, out_mask)
