# Defining a Dataset container class. It will hold the data representations (training,
# validation, testing), the learned model parameters (and hyperparameters), and other
# relevant information.

import numpy as np
import json
from . import train
from . import datahelper
from . import krr

class PES(object):
    """
    A class for holding the information necessary for generating a potential 
    energy surface. Base geometries, displacements, etc. are included here.
    Run pes.generate() to generate input files across the PES, and pes.run()
    to automatically go through the directories and run each input file.
    Check the respective fn docstrings to see extra capabilities.
    """

    def __init__(self,inp):
    # {{{
        if isinstance(inp,str): # if str, unpack it as a json file
            with open(inp) as f:
                inpf = json.load(f)
            self.inpf = inp
            if 'name' in inpf:
                self.name = inpf['name'] # Name of PES 
            else:
                self.name = 'PES'
            self.geom = inpf['geom'] # Base geometry
            self.gvar = inpf['gvar'] # Variable name in geometry
            self.dis = inpf['dis'] # Displacement range of geometry
            self.pts = inpf['pts'] # Number of points on PES
            self.method = inpf['method']
            self.basis = inpf['basis']
            self.generated = inpf['generated']
            self.complete = inpf['complete']
            print("PES generated from {}.".format(inp))
        elif isinstance(inp,dict): # if a dict, unpack it to class variables
            self.inpf = None
            if 'name' in inp:
                self.name = inp['name'] # Name of PES 
            else:
                self.name = 'PES'
            self.geom = inp['geom'] # Base geometry
            self.gvar = inp['gvar'] # Variable name in geometry
            self.dis = inp['dis'] # Displacement range of geometry
            self.pts = inp['pts'] # Number of points on PES
            self.method = inp['method']
            self.basis = inp['basis']
            self.generated = inp['generated']
            self.complete = inp['complete']
            print("PES generated from input dictionary.")
        else: # initialize an empty database
            self.inpf = None 
            self.name = None
            self.geom = None
            self.gvar = None
            self.dis = None
            self.pts = None
            self.method = None
            self.basis = None
            self.generated = False
            self.complete = False
            print("Empty PES generated. Please supply variables.")
        self.dirlist = None # directory list, may be generated or pushed in later
    # }}}

    def save(self, loc=False):
        # {{{
        if self.inpf:
            loc_str = self.inpf
        else:
            loc_str = loc
        settings = {
           "inpf": loc_str,
           "name": self.name,
           "geom": self.geom,
           "method": self.method,
           "pts": self.pts,
           "gvar": self.gvar,
           "dis": self.dis,
           "basis": self.basis,
           "generated": self.generated,
           "complete": self.complete 
        }
        with open(loc_str,'w') as f:
            json.dump(settings,f,indent=4)
        # }}}

    def generate(self, global_options=False, regen=False,**kwargs):
        # {{{
        '''
        Generate the input files across a PES.
        Require the method and psi4.set_options dictionary.
        Pass kwargs forward into the input file generation.
        Note that datahelper.grabber() can get any variable from a Psi4 output 
        JSON, as well as load data from any arbitrarily-named NumPy file!
        Example: if you pass `extra = "np.save('amps.npy',t1_amps)`,
        this will be placed at the bottom of every input file.
        Then, you can run grabber(dirlist,fnames=['amps.npy']) and the
        returned result dict will include your amplitudes!
        '''
        # generate the grand data set representations
        # 'pts' evenly-spaced representations on the PES
        bot = float(self.dis[0])
        top = float(self.dis[1])
        base = self.geom
        gvar = self.gvar
        pes = np.linspace(bot,top,self.pts) 
    
        if not global_options:
            global_options = {
            'basis':self.basis,
            'scf_type':'pk',
            'mp2_type':'conv',
            'freeze_core':'false',
            'e_convergence':1e-8,
            'd_convergence':1e-8}
    
        if 'directory' in kwargs:
            bdir = kwargs['directory']
        else:
            bdir = '.'
                
        if (self.generated == True) and (regen == False):
            dlist = [(bdir + '/{}'.format(dis)) for dis in pes]
            self.dirlist = dlist
            print('PES input files already generated! Pass `regen=True` '
                  ' to regenerate.')
            return dlist
        
        dlist = [] # list of directories
    
        for dis in pes:
            ndir = bdir + '/{}'.format(dis)
            dlist.append(ndir)
            kwargs['directory'] = ndir
            new_geom = base.replace(gvar,str(dis))
            datahelper.write_psi4_input(new_geom,self.method,global_options,**kwargs)

        self.dirlist = dlist
        self.generated = True
    
        print('PES input files generated! Please run them using the given directory '
              'list. Once complete, you may parse them with dataheler.grabber().')
    
        return dlist
        # }}}

    def run(self,infile='input.dat',outfile='output.dat',restart=False):
        # {{{
        '''
        Run all jobs listed in self.dirlist (may be set manually or by PES.generate())
        NOTE: This simply runs all jobs one-by-one. This is not recommended for large
        datasets, as you are better served running the generated input files
        in parallel. Use at your own risk!
        '''
        if self.dirlist == None:
            print('Please pass a directory list into PES.dirlist or have it set '
                  'by running PES.generate().')
            return 0
        elif (self.complete == True) and (restart == False):
            print('PES jobs already complete! Pass `restart=True` to rerun.')
            return 0
        else:
            datahelper.runner(self.dirlist,infile=infile,outfile=outfile)
            self.complete = True
            return 0
        # }}}

class Dataset(object):
    """
    The main data class for training, validation, and testing representations.
    Setter will initialize a few things, then functions will split and find
    the requested method of learning, validation, etc.
    Maybe I should have a higher class than this, which holds things like the 
    training type, number of trainers (M), etc? Or should I pass the input file
    directly here?
    """

    def __init__(self, inpf=None, reps=None, vals=None):
    # {{{
        """
        Initialize the dataset. Pass in a data set or the location of one.
        """
        # for storing the grand data set representations and values 
        self.grand = { 
            "representations" : None,
            "values" : None,
            }

        if inpf is not None:
            if isinstance(inpf,str):
                with open(inpf,'r') as f:
                    inp = json.load(f)
                self.inpf = inpf
                self.setup = inp['setup']
                self.data = inp['data']
            elif isinstance(inpf,dict):
                self.inpf = None
                self.setup = inpf['setup']
                self.data = inp['data']
            else:
                print("Please pass in either a STR json filepath or DICT.")

        if reps is not None:
            if isinstance(reps,str):
                self.grand["representations"] = np.load(reps)
            elif isinstance(reps,np.ndarray):
                self.grand["representations"] = reps
            elif isinstance(reps,list):
                self.grand["representations"] = np.asarray(reps)
            else:
                raise RuntimeError("""Please pass in a STR numpy filepath, numpy.ndarray, or 
                        list of representations.""")

        if vals is not None:
            if isinstance(vals,str):
                self.grand["values"] = np.load(vals)
            elif isinstance(vals,np.ndarray):
                self.grand["values"] = vals
            elif isinstance(vals,list):
                self.grand["values"] = np.asarray(vals)
            else:
                raise RuntimeError("""Please pass in a STR numpy filepath, numpy.ndarray, or 
                        list of values.""")
        if (inpf == None) and (reps == None) and (vals == None):
            self.inpf = None
            self.setup = {}
            self.data = {}
            print("Empty Dataset loaded.")
    # }}}

    def load(self, inpf=None, reps=None, vals=None):
        # {{{
        '''
        Pass in either a STR json filepath or DICT for setup, data, and grand.
        '''
        if inpf is not None:
            if isinstance(inpf,str):
                with open(inpf,'r') as f:
                    inp = json.load(f)
                self.inpf = inpf
                self.setup = inp['setup']
                self.data = inp['data']
            elif isinstance(inpf,dict):
                self.inpf = None
                self.setup = inpf['setup']
                self.data = inp['data']
            else:
                print("Please pass in either a STR json filepath or DICT.")

        if reps is not None:
            if isinstance(reps,str):
                self.grand["representations"] = np.load(reps)
            elif isinstance(reps,np.ndarray):
                self.grand["representations"] = reps
            elif isinstance(reps,list):
                self.grand["representations"] = np.asarray(reps)
            else:
                raise RuntimeError("""Please pass in a STR numpy filepath, numpy.ndarray, or 
                        list of representations.""")

        if vals is not None:
            if isinstance(vals,str):
                self.grand["values"] = np.load(vals)
            elif isinstance(vals,np.ndarray):
                self.grand["values"] = vals
            elif isinstance(vals,list):
                self.grand["values"] = np.asarray(vals)
            else:
                raise RuntimeError("""Please pass in a STR numpy filepath, numpy.ndarray, or 
                        list of values.""")
        # }}}

    def save(self, loc=False):
        # {{{
        if self.inpf:
            loc_str = self.inpf
        else:
            loc_str = loc
        with open(loc_str,'w') as f:
            json.dump({'setup':self.setup,'data':self.data},f,indent=4)
        # }}}

    def find_trainers(self, traintype, **kwargs):
    # {{{
        '''
        Passes the dataset and any kwargs into the appropriate training set optimization.
        '''
        if "remove" in kwargs:
            print("NOTE: Trainer map will be valid for grand data set once removed points are dropped!")
        if traintype.lower() in ["kmeans","k-means","k_means"]:
            if "K" in self.setup:
                K = self.setup['K']
            else:
                K = 30

            if "trainers" in self.data:
                if self.data['trainers'] is not False:
                    print("{} training set already generated.".format(traintype))
                    return self.data['trainers']
                else:
                    pass
            self.data['trainers'] = False
            print("Determining training set via {} algorithm . . .".format(traintype))
            trainers = []
            t_map, close_pts = train.k_means_loop(self.grand["representations"],self.setup['M'],K,**kwargs)
            for pt in range(0,self.setup['M']): # loop over centers, grab positions of trainers
                trainers.append(t_map[pt][close_pts[pt]][1])
            self.data['trainers'] = sorted(trainers, reverse=True)
            return sorted(trainers, reverse=True)
        else:
            raise RuntimeError("I don't know how to get {} training points yet!".format(traintype))
    # }}}

    def train(self, traintype, **kwargs):
        # {{{
        '''
        Passes the dataset and any kwargs into the appropriate training set optimization.
        '''
        if traintype.lower() in ["krr","kernel_ridge"]:
            print("Training via the {} algorithm . . .".format(traintype))
            ds, t_AVG = krr.train(self, **kwargs) 
            return ds, t_AVG
        else:
            raise RuntimeError("Cannot train using {} yet.".format(traintype))
        # }}}
