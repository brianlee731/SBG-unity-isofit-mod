from continuumio/miniconda3:23.10.0-1
workdir /app
run conda install -y python=3.8; conda install -y gdal; conda install -y -c conda-forge gfortran awscli;conda install -y -c anaconda make; conda clean -ay
#run conda install -y gdal; conda clean -ay
#run conda install -y -c conda-forge gfortran awscli; conda clean -ay
#run conda install -y -c anaconda make
run mkdir s6 && cd s6 && wget --no-check-certificate https://salsa.umd.edu/files/6S/6sV2.1.tar && tar xvf 6sV2.1.tar && sed -i 's/FFLAGS=  $(EXTRA)/FFLAGS=  $(EXTRA) -std=legacy/' Makefile && make 
#copy s6 /app/s6
#workdir s6
#run make
workdir /app
run git clone https://github.com/isofit/isofit.git -b v2.9.8; cd isofit; pip install -e .
run pip install hy_tools_lite==1.1.1 Pillow==9.2.0 ray==1.9.2 pystac==1.8.4 unity_sds_client==0.3.0
env SIXS_DIR=/app/6s
workdir /app

copy process.py .
#ENTRYPOINT ["python", "process.py"]
