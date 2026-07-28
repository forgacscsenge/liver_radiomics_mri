# Makefile for liver segmentation

SHELL       := /bin/bash
#arra valo, hogy a makefile egy shellben fusson vegig
.ONESHELL:
#ha valami hibas, a session elbukik, nem lesz "felig" feldolgozott ses.
.SHELLFLAGS := -euo pipefail -c

#inputok a process.shbol
Gender  ?=
T1Nifti ?=
ADC     ?=
SESID   ?=

#hibauzenetek, ha valamelyik bemenetek nem jon
ifeq ($(strip $(Gender)),)
$(error Gender is not set. Use: make target Gender=F)
endif

ifeq ($(strip $(T1Nifti)),)
$(error T1Nifti is not set. Use: make target T1Nifti=...)
endif

ifeq ($(strip $(ADC)),)
$(error ADC is not set. Use: make target ADC=...)
endif
ifeq ($(strip $(SESID)),)
    $(error SESID is not set. Use: make all SESID=01)
endif

#taj kinyerese a t1 file nevebol
TAJ := $(shell basename "$(T1Nifti)" | sed -E 's/.*sub-([0-9]{9}).*/\1/')

ifeq ($(strip $(TAJ)),)
$(error Could not extract TAJ from T1Nifti: $(T1Nifti))
endif

#dinamikus mappak
BASEWD    = 
WD        = $(BASEWD)/$(TAJ)
#ScriptDir = $(BASEWD)/steps
ScriptDir = 
#gender specific atlas
ifeq ($(Gender),F)
liverAtlas = $(ScriptDir)/average_atlas/female_liver_average_trh05.nii.gz
else
liverAtlas = $(ScriptDir)/average_atlas/male_liver_average_trh05.nii.gz
endif

#outputs
TSOutput          = $(WD)/t1/$(TAJ)_$(SESID)_liver
FilledT1LiverMask = $(WD)/t1/$(TAJ)_$(SESID)_filled_liver_mask.nii.gz
TFMT1Liver2Atlas  = $(WD)/t1/$(TAJ)_$(SESID)_t12atlas.tfm
T1Liver2Atlas     = $(WD)/t1/$(TAJ)_$(SESID)_t1_in_atlas.nii.gz
ADCLiver2T1       = $(WD)/adc/$(TAJ)_$(SESID)_adc_in_t1.nii.gz
TFMADCLiver2T1    = $(WD)/adc/$(TAJ)_$(SESID)_adc2t1.tfm
ADCLiver2Atlas    = $(WD)/adc/$(TAJ)_$(SESID)_adc_in_atlas.nii.gz
LiverMaskInAtlas  = $(WD)/qc/$(TAJ)_$(SESID)_liver_mask_in_atlas.nii.gz
QC_MASTER_CSV     = $(BASEWD)/qc_metrics.csv

PatientMaskInAtlas ?= $(T1Liver2Atlas)

#scriptek listaja
liverSegm        = segment_liver.py
binaryMaskFill   = $(ScriptDir)/t1_mask_filling/binary_mask_filling.py
t12atlas         = $(ScriptDir)/t12atlas/euler/t12atlas_euler.py
adc2t1           = $(ScriptDir)/adc2t1/euler/adc2t1.py
adc2atlas        = $(ScriptDir)/adc2atlas/adc2atlas.py
QCDir            = steps/qc/
jaccard_script   = $(QCDir)/jaccard.py
hausdorff_script = $(QCDir)/hausdorff.py


#default target
all: $(ADCLiver2Atlas) qc

# Liver segmentation from T1
$(TSOutput): $(T1Nifti)
	@mkdir -p $(WD)/t1
	@echo "Liver segmentation..."
	@source totalsegm/totalsegm_env_310/bin/activate
	@python $(liverSegm) "$(T1Nifti)" "$(TSOutput)"

# Fill segmented liver mask
$(FilledT1LiverMask): $(TSOutput)
	@echo "Liver mask filling..."
	@source totalsegm/totalsegm_env_310/bin/activate
	@python $(binaryMaskFill) "$(TSOutput)/liver.nii.gz" "$(FilledT1LiverMask)"

# Transform T1 to atlas space
$(TFMT1Liver2Atlas) $(T1Liver2Atlas): $(T1Nifti) $(FilledT1LiverMask) $(liverAtlas)
	@echo "Transforming T1 to UK Biobank atlas..."
	@source totalsegm/totalsegm_env_310/bin/activate
	@python $(t12atlas) \
	"$(T1Nifti)" \
	"$(FilledT1LiverMask)" \
	"$(liverAtlas)" \
	"$(TFMT1Liver2Atlas)" \
	"$(T1Liver2Atlas)"

# Transform ADC to T1
$(TFMADCLiver2T1) $(ADCLiver2T1): $(T1Nifti) $(ADC) $(FilledT1LiverMask)
	@mkdir -p $(WD)/adc
	@echo "Transforming ADC to T1..."
	@source totalsegm/totalsegm_env_310/bin/activate
	@python $(adc2t1) \
	"$(T1Nifti)" \
	"$(ADC)" \
	"$(FilledT1LiverMask)" \
	"$(ADCLiver2T1)" \
	"$(TFMADCLiver2T1)"

# Transform ADC to atlas
$(ADCLiver2Atlas): $(ADC) $(TFMADCLiver2T1) $(TFMT1Liver2Atlas) $(liverAtlas)
	@echo "Transforming ADC to UK Biobank atlas..."
	@source totalsegm/totalsegm_env_310/bin/activate
	@python $(adc2atlas) \
	"$(ADC)" \
	"$(TFMADCLiver2T1)" \
	"$(TFMT1Liver2Atlas)" \
	"$(liverAtlas)" \
	"$(ADCLiver2Atlas)"

#Jaccard index es Hausdorff distance szamolasa
qc: $(T1Liver2Atlas)
	@mkdir -p "$(BASEWD)"
	@source totalsegm/totalsegm_env_310/bin/activate
	@J=$$(python "$(QCDir)/jaccard.py" "$(liverAtlas)" "$(T1Liver2Atlas)"); \
	D=$$(python -c 'import sys; j=float(sys.argv[1]); print(0.0 if j<0 else (2*j/(1.0+j)))' "$$J"); \
	H=$$(python "$(QCDir)/hausdorff.py" "$(liverAtlas)" "$(T1Liver2Atlas)"); \
	if [[ ! -f "$(QC_MASTER_CSV)" ]]; then \
	echo "TAJ,SESID,Gender,Jaccard,Dice,Hausdorff_mm" > "$(QC_MASTER_CSV)"; \
	fi; \
	echo "$(TAJ),$(SESID),$(Gender),$$J,$$D,$$H" >> "$(QC_MASTER_CSV)"; \
	echo "QC: J=$$J Dice=$$D H=$$H"

# segedfeladatok: teszt es torles
test:
	@echo "TAJ = $(TAJ)"
	@echo "Gender = $(Gender)"
	@echo "T1Nifti = $(T1Nifti)"
	@echo "ADC = $(ADC)"
	@echo "WD = $(WD)"
	@echo "liverAtlas = $(liverAtlas)"

clean:
	@rm -rf \
	"$(TSOutput)" \
	"$(FilledT1LiverMask)" \
	"$(TFMT1Liver2Atlas)" \
	"$(T1Liver2Atlas)" \
	"$(ADCLiver2T1)" \
	"$(TFMADCLiver2T1)" \
	"$(ADCLiver2Atlas)"

