#!/usr/bin/env python
# coding: utf-8

# # SBG ISOFIT Application Notebook
# 

# In[4]:

import glob
import json
import os
import subprocess
import sys
import shutil

import numpy as np
from spectral.io import envi

from PIL import Image

import hytools_lite as ht
from isofit.utils import surface_model
import time


# stage_in packages
from unity_sds_client.resources.collection import Collection

# stage_out packages
from datetime import datetime, timezone
from unity_sds_client.resources.dataset import Dataset
from unity_sds_client.resources.data_file import DataFile


# ## Inputs and Configurations
# 
# In the original pre-process, inputs are supplied by a run_config file. This consists of 2 entries (a raw_data file, and a CRID). The system in reality needs 3 inputs files (an observation file, a radiance file, and the crid configurable.
# 
# In the Unity system, the data files required will be staged in for the applicaiton, and the crid is a config item that is passed in. To make this work in Unity, we will also pass in an "output collection" which is needed if we want to "persist" the output products in the data catalog.

# In[5]:


# The defaults used here generally relflect a local or jupyter environment; they are replaced with "runtime" values when run in the system.
input_stac_collection_file = '/unity/ads/input_collections/SBG-L1B-PRE/catalog.json' # type: stage-in
output_stac_catalog_dir    = '/unity/ads/outputs/SBG-L2A-RFL/process_results'                    # type: stage-out

# pre-process variables
output_collection="SBG-L2A-RFL"
crid = "001"
cores=8
segmentation_size=50
tmp_work = '/unity/ads/temp/'



# In[6]:


tmp_work = tmp_work.rstrip("/")


# # Import Files from STAC Item Collection
# 
# Load filenames from the stage_in STAC item collection file

# In[7]:


inp_collection = Collection.from_stac(input_stac_collection_file)
data_filenames = inp_collection.data_locations()

data_filenames


# ## Misc. function required by the preprocess command

# In[8]:


def get_rfl_basename(rdn_basename, crid):
    # Replace product type
    tmp_basename = rdn_basename.replace("L1B_RDN", "L2A_RFL")
    # Split, remove old CRID, and add new one
    tokens = tmp_basename.split("_")[:-1] + [str(crid)]
    return "_".join(tokens)


def generate_wavelengths(rdn_hdr_path, output_path):
    # Read in header file and get list of wavelengths and fwhm
    hdr = envi.read_envi_header(rdn_hdr_path)
    wl = hdr["wavelength"]
    fwhm = hdr["fwhm"]

    # Need to offset fwhm if its length is not the same as the wavelengths' length.  This is a known bug in
    # the AVIRIS-NG data.
    fwhm_offset = 0 if len(wl) == len(fwhm) else 23
    wl_arr = []
    for i in range(len(wl)):
        wl_arr.append([i, wl[i], fwhm[i + fwhm_offset]])

    # Save file
    np.savetxt(output_path, np.array(wl_arr, dtype=np.float32))


def generate_metadata(run_config,json_path,new_metadata):

    metadata= run_config['metadata']
    for key,value in new_metadata.items():
        metadata[key] = value

    with open(json_path, 'w') as out_obj:
        json.dump(metadata,out_obj,indent=3)

def generate_quicklook(rfl_img_path, output_path):
    # Generate a quicklook browse image
    img = ht.HyTools()
    img.read_file(rfl_img_path)

    if 'DESIS' in img.base_name:
        band3 = img.get_wave(560)
        band2 = img.get_wave(850)
        band1 = img.get_wave(660)
    else:
        band3 = img.get_wave(560)
        band2 = img.get_wave(850)
        band1 = img.get_wave(1660)

    rgb = np.stack([band1, band2, band3])
    rgb[rgb == img.no_data] = np.nan

    rgb = np.moveaxis(rgb,0,-1).astype(float)
    bottom = np.nanpercentile(rgb, 5, axis=(0, 1))
    top = np.nanpercentile(rgb, 95, axis=(0, 1))
    rgb = np.clip(rgb, bottom, top)
    rgb = (rgb - np.nanmin(rgb, axis=(0, 1))) / (np.nanmax(rgb, axis=(0, 1)) - np.nanmin(rgb, axis=(0, 1)))
    rgb = (rgb * 255).astype(np.uint8)

    im = Image.fromarray(rgb)
    im.save(output_path)

def update_header_descriptions(hdr_path, description):
    hdr = envi.read_envi_header(hdr_path)
    hdr["description"] = description
    envi.write_envi_header(hdr_path, hdr)


# In[9]:


# Define paths and variables
from pathlib import Path
sister_isofit_dir = Path('.')
#os.path.realpath(__file__)
isofit_dir = os.path.join(os.path.dirname(sister_isofit_dir),sister_isofit_dir.name ,"isofit")
isofit_dir


# In[10]:


for f in data_filenames:
    if f.endswith(".bin"):
      if "_OBS" in f:
        continue
      elif "_LOC" in f:
        continue
      else:
        input_dir = os.path.dirname(f)
        rdn_name_wbin = os.path.basename(f)
        rdn_basename = rdn_name_wbin[:-4]

rfl_basename = get_rfl_basename(rdn_basename, crid)




loc_basename = f"{rdn_basename}_LOC"
obs_basename = f"{rdn_basename}_OBS"
print("INPUTS: " + input_dir)
print("RAD: " + rdn_basename)
print("OBS: " + obs_basename)
print("LOC: " + loc_basename )
print("RFL: " + rfl_basename )

instrument = "EMIT"
sensor = 'emit'

temp_basename = f'{sensor}{os.path.basename(rdn_basename).split("_")[4]}'
surface_config = tmp_work+"/emit_surface_20221020.json"

print("TEMP BASENAME: " + temp_basename)


# In[11]:


#Temporary input filenames without .bin extension
    
rdn_img_path = f"{tmp_work}/{temp_basename}"
rdn_hdr_path = f"{tmp_work}/{temp_basename}.hdr"
loc_img_path = f"{tmp_work}/{temp_basename}_LOC"
loc_hdr_path = f"{tmp_work}/{temp_basename}_LOC.hdr"
obs_img_path = f"{tmp_work}/{temp_basename}_OBS"
obs_hdr_path = f"{tmp_work}/{temp_basename}_OBS.hdr"

# Copy the input files into the work directory (don't use .bin)
shutil.copyfile(f"{input_dir}/{rdn_basename}.bin" ,rdn_img_path)
shutil.copyfile(f"{input_dir}/{rdn_basename}.hdr" ,rdn_hdr_path)
shutil.copyfile(f"{input_dir}/{loc_basename}.bin" ,loc_img_path)
shutil.copyfile(f"{input_dir}/{loc_basename}.hdr" ,loc_hdr_path)
shutil.copyfile(f"{input_dir}/{obs_basename}.bin" ,obs_img_path)
shutil.copyfile(f"{input_dir}/{obs_basename}.hdr" ,obs_hdr_path)


# In[12]:


#Update radiance basename
rdn_basename = os.path.basename(rdn_img_path)

# Generate wavelengths file
wavelengths_path = tmp_work + "/wavelengths.txt"
print(f"Generating wavelengths from radiance header path at {rdn_hdr_path} to {wavelengths_path}")
generate_wavelengths(rdn_hdr_path, wavelengths_path)


# In[13]:


# Copy surface model files to input folder and generate surface model
print("Generating surface model using work/surface.json config")
subprocess.run(f"cp {sister_isofit_dir}/surface_model/* {tmp_work}/", shell=True)
surface_model_path = tmp_work+"/surface.mat"
surface_model(surface_config)


# In[14]:


os.environ['SIXS_DIR'] = "/home/ssm-user/SBG-unity-isofit/6s"
print(str(sister_isofit_dir) + "/6s")


# In[15]:


apply_oe_exe = f"{sister_isofit_dir}/isofit/isofit/utils/apply_oe.py"
log_basename = f"{rfl_basename}.log"


# In[16]:


cmd = [
    "python",
    apply_oe_exe,
    rdn_img_path,
    loc_img_path,
    obs_img_path,
    tmp_work,
    sensor,
    "--presolve=1",
    "--analytical_line=0",
    "--empirical_line=1",
    "--emulator_base="+str(sister_isofit_dir)+"/sRTMnet_v120.h5",
    f"--n_cores={cores}",
    f"--wavelength_path={wavelengths_path}",
    f"--surface_path={surface_model_path}",
    f"--segmentation_size={segmentation_size}",
    f"--log_file={tmp_work}/{log_basename}"
]

print("Running apply_oe command: " + " ".join(cmd))

start_time = time.time()
subprocess.run(" ".join(cmd), shell=True)
end_time = time.time()




# other files



disclaimer = ""
if not os.path.exists(output_stac_catalog_dir):
    #os.mkdirs(output_stac_catalog_dir, exist_ok=True)
    import pathlib
    pathlib.Path(output_stac_catalog_dir).mkdir(parents=True, exist_ok=True)

rfl_description = f"{disclaimer}Surface reflectance (unitless)"
unc_description = f"{disclaimer}Surface reflectance uncertainties (unitless)"
# atm_description ="Atmospheric state AOT550, Pressure Elevation, H2O"

# Generate quicklook
rfl_ql_path = f"{output_stac_catalog_dir}/{rfl_basename}.png"
print(f"Generating quicklook to {rfl_ql_path}")
generate_quicklook(f"{tmp_work}/output/{rdn_basename}_rfl", rfl_ql_path)

# Move/rename outputs to output dir
rfl_img_path = f"{output_stac_catalog_dir}/{rfl_basename}.bin"
rfl_hdr_path = f"{output_stac_catalog_dir}/{rfl_basename}.hdr"
unc_img_path = f"{output_stac_catalog_dir}/{rfl_basename}_UNC.bin"
unc_hdr_path = f"{output_stac_catalog_dir}/{rfl_basename}_UNC.hdr"
# atm_img_path = f"output/{rfl_basename}_ATM.bin"
# atm_hdr_path = f"output/{rfl_basename}_ATM.hdr"

shutil.copyfile(f"{tmp_work}/output/{rdn_basename}_rfl", rfl_img_path)
shutil.copyfile(f"{tmp_work}/output/{rdn_basename}_rfl.hdr", rfl_hdr_path)
shutil.copyfile(f"{tmp_work}/output/{rdn_basename}_uncert", unc_img_path)
shutil.copyfile(f"{tmp_work}/output/{rdn_basename}_uncert.hdr", unc_hdr_path)

# isofit_config_file = f"work/config/{rdn_basename}_modtran.json"
# shutil.copyfile(isofit_config_file, f"output/{rfl_basename}_modtran.json")

# Update descriptions in ENVI headers
update_header_descriptions(rfl_hdr_path, rfl_description)
update_header_descriptions(unc_hdr_path, unc_description)

# Also move log file and runconfig
shutil.copyfile(f"{tmp_work}/{log_basename}", f"{output_stac_catalog_dir}/{rfl_basename}.log")

import json
# stage_in packages
from unity_sds_client.resources.collection import Collection

# stage_out packages
from datetime import datetime, timezone
from unity_sds_client.resources.dataset import Dataset
from unity_sds_client.resources.data_file import DataFile

# Create a collection
out_collection = Collection(output_collection)

#SISTER_EMIT_L2A_RFL_20231206T160939_001_UNC.bin
data_files = glob.glob(output_stac_catalog_dir+"/SISTER*UNC.bin") 
# hack to get the radiance file
data_file = os.path.basename(data_files[0].replace("_UNC",""))
name=os.path.splitext(data_file)[0]

orig_dataset = inp_collection.datasets[0]

dataset = Dataset(
    name=name, 
    collection_id=out_collection.collection_id, 
    start_time=orig_dataset.data_begin_time, 
    end_time=orig_dataset.data_end_time,
    creation_time=datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
)

# Add output file(s) to the dataset
for file in glob.glob(output_stac_catalog_dir+"/SISTER*"):
    #type, location, roles = [], title = "", description = "" 
    if file.endswith(".bin"):
        dataset.add_data_file(DataFile("binary",file, ["data"]))
    elif file.endswith(".png"):
        dataset.add_data_file(DataFile("image/png",file, ["browse"]))
    else:
        dataset.add_data_file(DataFile(None,file, ["metadata"]))
        
#Add the STAC file we are creating

# the future metadata file needs to be added to the STAC as well
    # will eventually be moved into the to_stac() function
dataset.add_data_file(DataFile("text/json",os.path.join(output_stac_catalog_dir, name + ".json"), ["metadata"]))

# the future metadata file needs to be added to the STAC as well
    # will eventually be moved into the to_stac() function
dataset.add_data_file(DataFile("metadata", output_stac_catalog_dir + '/' +  name +'.json' ))


# Add the dataset to the collection
#out_collection.add_dataset(dataset)
out_collection._datasets.append(dataset)

Collection.to_stac(out_collection, output_stac_catalog_dir)

