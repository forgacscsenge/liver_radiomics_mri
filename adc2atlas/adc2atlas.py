import ants
import sys

def load_transform_list(path):
    with open(path, "r") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    return lines

def adc_to_atlas_syn(adc_path, adc2t1_tfm_txt, t12atlas_tfm_txt, atlas_path, out_adc_path):

    adc = ants.image_read(adc_path)
    atlas = ants.image_read(atlas_path)

    #reorient everything to lpi
    adc_lpi = ants.reorient_image2(adc, "LPI")
    atlas_lpi = ants.reorient_image2(atlas, "LPI")

    #read tfm
    adc2t1_fwd = load_transform_list(adc2t1_tfm_txt)    #adc2t1
    t12atlas_fwd = load_transform_list(t12atlas_tfm_txt)  #t12atlas

    for t in adc2t1_fwd:
        print("   ", t)

    for t in t12atlas_fwd:
        print("   ", t)

    #compose: first t12atlas then adc2t1
    composed_forward = t12atlas_fwd + adc2t1_fwd

    for t in composed_forward:
        print("   ", t)

    #apply transform
    adc_in_atlas = ants.apply_transforms(
        fixed=atlas_lpi,
        moving=adc_lpi,
        transformlist=composed_forward,
        interpolator="linear",
    )

    ants.image_write(adc_in_atlas, out_adc_path)

if __name__ == "__main__":
    _, adc, adc2t1_tfm, t1atlas_tfm, atlas, out_adc = sys.argv
    adc_to_atlas_syn(adc, adc2t1_tfm, t1atlas_tfm, atlas, out_adc)
