from __future__ import print_function
import numpy as np

from hyperion.model import Model
import matplotlib as mpl
mpl.use('Agg')
import powderday.config as cfg

from powderday.grid_construction import yt_octree_generate
from powderday.find_order import find_order
import powderday.powderday_test_octree as pto
import powderday.hyperion_octree_stats as hos

from hyperion.dust import SphericalDust

from powderday.helpers import energy_density_absorbed_by_CMB
from powderday.analytics import dump_cell_info



def sph_m_gen(fname,field_add):
    
    refined,dustdens,fc1,fw1,pf,ad = yt_octree_generate(fname,field_add)
    xmin = (fc1[:,0]-fw1[:,0]/2.).convert_to_units('cm') #in proper cm 
    xmax = (fc1[:,0]+fw1[:,0]/2.).convert_to_units('cm')
    ymin = (fc1[:,1]-fw1[:,1]/2.).convert_to_units('cm')
    ymax = (fc1[:,1]+fw1[:,1]/2.).convert_to_units('cm')
    zmin = (fc1[:,2]-fw1[:,2]/2.).convert_to_units('cm')
    zmax = (fc1[:,2]+fw1[:,2]/2.).convert_to_units('cm')
    

    #dx,dy,dz are the edges of the parent grid
    dx = (np.max(xmax)-np.min(xmin)).value
    dy = (np.max(ymax)-np.min(ymin)).value
    dz = (np.max(zmax)-np.min(zmin)).value


    xcent = np.mean([np.min(xmin),np.max(xmax)]) #kpc
    ycent = np.mean([np.min(ymin),np.max(ymax)])
    zcent = np.mean([np.min(zmin),np.max(zmax)])
    
    boost = np.array([xcent,ycent,zcent])
    print ('[pd_front end] boost = ',boost)

    
    #Tom Robitaille's conversion from z-first ordering (yt's default) to
    #x-first ordering (the script should work both ways)

    refined_array = np.array(refined)
    refined_array = np.squeeze(refined_array)
    
    order = find_order(refined_array)
    refined_reordered = []
    dustdens_reordered = np.zeros(len(order))
    
    
    
    for i in range(len(order)): 
        refined_reordered.append(refined[order[i]])
        dustdens_reordered[i] = dustdens[order[i]]


    refined = refined_reordered
    dustdens=dustdens_reordered

    #hyperion octree stats
    max_level = hos.hyperion_octree_stats(refined)


    pto.test_octree(refined,max_level)

    dump_cell_info(refined,fc1,fw1,xmin,xmax,ymin,ymax,zmin,zmax)
    np.save('refined.npy',refined)
    np.save('density.npy',dustdens)
    

    #========================================================================
    #Initialize Hyperion Model
    #========================================================================

    m = Model()
    
    if cfg.par.FORCE_RANDOM_SEED == True: m.set_seed(cfg.par.seed)

    print ('Setting Octree Grid with Parameters: ')



    #m.set_octree_grid(xcent,ycent,zcent,
    #                  dx,dy,dz,refined)
    m.set_octree_grid(0,0,0,dx/2,dy/2,dz/2,refined)    


    #get CMB:
    
    energy_density_absorbed=energy_density_absorbed_by_CMB()
    specific_energy = np.repeat(energy_density_absorbed.value,dustdens.shape)

    if cfg.par.PAH == True:
        
        # load PAH fractions for usg, vsg, and big (grain sizes)
        frac = cfg.par.PAH_frac

        # Normalize to 1
        total = np.sum(list(frac.values()))
        frac = {k: v / total for k, v in frac.items()}

        for size in frac.keys():
            d = SphericalDust(cfg.par.dustdir+'%s.hdf5'%size)
            if cfg.par.SUBLIMATION == True:
                d.set_sublimation_temperature('fast',temperature=cfg.par.SUBLIMATION_TEMPERATURE)
            #m.add_density_grid(dustdens * frac[size], cfg.par.dustdir+'%s.hdf5' % size)
            m.add_density_grid(dustdens*frac[size],d,specific_energy=specific_energy)
        m.set_enforce_energy_range(cfg.par.enforce_energy_range)
    else:
        d = SphericalDust(cfg.par.dustdir+cfg.par.dustfile)
        if cfg.par.SUBLIMATION == True:
            d.set_sublimation_temperature('fast',temperature=cfg.par.SUBLIMATION_TEMPERATURE)
        m.add_density_grid(dustdens,d,specific_energy=specific_energy)
        #m.add_density_grid(dustdens,cfg.par.dustdir+cfg.par.dustfile)  
    m.set_specific_energy_type('additional')








    return m,xcent,ycent,zcent,dx,dy,dz,pf,boost
