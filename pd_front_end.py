#Code:  pd_front_end.py

#=========================================================
#IMPORT STATEMENTS
#=========================================================

import sys
script,pardir,parfile = sys.argv
import numpy as np
import scipy.interpolate
import scipy.ndimage


from hyperion.model import Model
import matplotlib as mpl
import matplotlib.pyplot as plt
from hyperion.model import ModelOutput
import h5py

import constants as const
import pdb

sys.path.insert(0,pardir)
par = __import__(parfile) 
import random
import config as cfg
cfg.par = par #re-write cfg.par for all modules that read this in now

import error_handling as eh


from astropy.table import Table
from astropy.io import ascii



import pfh_readsnap
from grid_construction import yt_octree_generate,grid_coordinate_boost,grid_center
import SED_gen as sg
from find_order import *
import powderday_test_octree as pto
import hyperion_octree_stats as hos

import os.path


#=========================================================
#CHECK FOR THE EXISTENCE OF A FEW CRUCIAL FILES FIRST
#=========================================================

eh.file_exist(par.hydro_dir+par.Gadget_snap_name)
eh.file_exist(par.dustfile)


#=========================================================
#GRIDDING
#=========================================================


print 'Octree grid is being generated by yt'

'''
refined,dustdens,xmin,xmax,ymin,ymax,zmin,zmax,boost = yt_octree_generate()
xmin *= 1.e3*const.pc
xmax *= 1.e3*const.pc
ymin *= 1.e3*const.pc
ymax *= 1.e3*const.pc
zmin *= 1.e3*const.pc
zmax *= 1.e3*const.pc

xcent = np.mean([min(xmin),max(xmax)])
ycent = np.mean([min(ymin),max(ymax)])
zcent = np.mean([min(zmin),max(zmax)])
'''
refined,dustdens,fc1,fw1,boost = yt_octree_generate()
xmin = fc1[:,0]-fw1[:,0]/2.
xmax = fc1[:,0]+fw1[:,0]/2.
ymin = fc1[:,1]-fw1[:,1]/2.
ymax = fc1[:,1]+fw1[:,1]/2.
zmin = fc1[:,2]-fw1[:,2]/2.
zmax = fc1[:,2]+fw1[:,2]/2.






#dx,dy,dz are the edges of the parent grid
dx = (max(xmax)-min(xmin))*1.e3*const.pc
dy = (max(ymax)-min(ymin))*1.e3*const.pc
dz = (max(zmax)-min(zmin))*1.e3*const.pc

xcent = np.mean([min(xmin),max(xmax)])
ycent = np.mean([min(ymin),max(ymax)])
zcent = np.mean([min(zmin),max(zmax)])

#DEBUG 061314
#boost = np.array([xcent_orig,ycent_orig,zcent_orig])*1.e3*const.pc
#xmin,xmax,ymin,ymax,zmin,zmax = grid_coordinate_boost(xmin,xmax,ymin,ymax,zmin,zmax)
print '[pd_front end] boost = ',boost





#Tom Robitaille's conversion from z-first ordering (yt's default) to
#x-first ordering (the script should work both ways)

#refined.insert(0,True) #hyperion expects an extra True at the beginning to establish the first refining
refined_array = np.array(refined)
refined_array = np.squeeze(refined_array)

order = find_order(refined_array)
refined_reordered = []
dustdens_reordered = np.zeros(len(order))


#dustdens = np.insert(dustdens,0,0) #to match the size of the new refined


for i in range(len(order)): 
    refined_reordered.append(refined[order[i]])
    dustdens_reordered[i] = dustdens[order[i]]


refined = refined_reordered
dustdens=dustdens_reordered

#hyperion octree stats
max_level = hos.hyperion_octree_stats(refined)


pto.test_octree(refined,max_level)


np.save('refined.npy',refined)
np.save('density.npy',dustdens)






#========================================================================
#Initialize Hyperion Model
#========================================================================

m = Model()


''' DEBUG 061214
dx = np.max([(dx,dy,dz)])
dy = dx
dz = dx
'''

print 'Setting Octree Grid with Parameters: '
print '[xcent,ycent,zcent] (kpc) = ',xcent/(const.pc*1.e3),ycent/(const.pc*1.e3),zcent/(const.pc*1.e3)
print '[dx,dy,dz] (kpc) = ',dx/(const.pc*1.e3),dy/(const.pc*1.e3),dz/(const.pc*1.e3)

#print 'NOTE the dx,dy,dz are fixed \n'






m.set_octree_grid(xcent,ycent,zcent,
                  dx,dy,dz,refined)
    

m.add_density_grid(dustdens,par.dustfile)
        



  


#generate dust model. This needs to preceed the generation of sources
#for hyperion since the wavelengths of the SEDs need to fit in the dust opacities.

df = h5py.File(par.dustfile,'r')
o = df['optical_properties']
df_nu = o['nu']
df_chi = o['chi']

df.close()



#add sources to hyperion



stars_list,diskstars_list,bulgestars_list = sg.star_list_gen(boost,xcent,ycent,zcent,dx,dy,dz)
nstars = len(stars_list)




from source_creation import add_newstars,add_binned_seds


#figure out N_METAL_BINS:
fsps_metals = np.loadtxt(cfg.par.metallicity_legend)
N_METAL_BINS = len(fsps_metals)

if nstars <= N_METAL_BINS*par.N_STELLAR_AGE_BINS*par.N_MASS_BINS:
    stellar_nu,stellar_fnu,disk_fnu,bulge_fnu = sg.allstars_sed_gen(stars_list,diskstars_list,bulgestars_list)
    m=add_newstars(df_nu,stellar_nu,stellar_fnu,disk_fnu,bulge_fnu,stars_list,diskstars_list,bulgestars_list,m)
    

#potentially write the stellar SEDs to a npz file
    if par.STELLAR_SED_WRITE == True:
        np.savez('stellar_seds.npz',par.COSMOFLAG,stellar_nu,stellar_fnu,disk_fnu,bulge_fnu)
        
else:
#note - the generation of the SEDs is called within
#add_binned_seds itself, unlike add_newstars, which requires
#that sg.allstars_sed_gen() be called first.

    m=add_binned_seds(df_nu,stars_list,diskstars_list,bulgestars_list,m)




nstars = len(stars_list)
nstars_disk = len(diskstars_list)
nstars_bulge = len(bulgestars_list)


   

    

if par.SOURCES_IN_CENTER == True:
    for i in range(nstars):
        stars_list[i].positions[:] = 0
        bulgestars_list[i].positions[:] = 0
        diskstars_list[i].positions[:] = 0 





   
print 'Done adding Sources'

print 'Setting up Model'
#set up the SEDs and images
m.set_raytracing(True)
m.set_n_photons(initial=par.n_photons_initial,imaging=par.n_photons_imaging,
                raytracing_sources=par.n_photons_raytracing_sources,raytracing_dust=par.n_photons_raytracing_dust)
#m.set_n_initial_iterations(7)
m.set_convergence(True,percentile=99.,absolute=1.1,relative=1.02)


image = m.add_peeled_images(sed = True,image=False)
image.set_wavelength_range(250,0.01,5000.)
#image.set_wavelength_range(50,0.01,5000.)
image.set_viewing_angles(np.linspace(0,90,par.NTHETA),np.repeat(20,par.NTHETA))
#image.set_track_origin('basic')

#image.set_image_size(128,128)
#image.set_image_limits(-10.e3*const.pc,10.e3*const.pc,-10.e3*const.pc,10.e3*const.pc)


print 'Beginning RT Stage'
#Run the Model
m.write(par.inputfile,overwrite=True)
m.run(par.outputfile,mpi=True,n_processes=par.n_processes,overwrite=True)














