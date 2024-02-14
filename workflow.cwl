#!/usr/bin/env cwl-runner

#cwltool --no-match-user  workflow.cwl --download_dir .

class: CommandLineTool
id: "BAMStats"
label: "BAMStats tool"
cwlVersion: v1.2

requirements:
  - class: DockerRequirement
    dockerPull: "gangl/unity-isofit:latest"


arguments:
- $(inputs.download_dir.path)/stage-in-results.json
- $(runtime.outdir)/process_output
- $(inputs.crid)
- $(inputs.output_collection)
- $(inputs.cores)
inputs:
  crid:
    default: '001'
    type: string
  download_dir:
    type:  Directory
  output_collection:
    default: L1B_processed
    type: string
  cores:
    default: 4 
    type: int
  sensor:
    default: EMIT
    type: string
  temp_directory:
    default: /unity/ads/temp/nb_l1b_preprocess
    type: string

outputs:
  process_output_dir:
    outputBinding:
      glob: $(runtime.outdir)
    type: Directory

baseCommand: ["python", "/app/process.py"]
