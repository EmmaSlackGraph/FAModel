# class for a dynamic subsea power cable

import numpy as np
from copy import deepcopy
from moorpy.subsystem import Subsystem
from moorpy import helpers
from famodel.mooring.connector import Connector, Section
from famodel.famodel_base import Edge
from famodel.cables import Cable

class DynamicCable(Edge):
    '''
    Class for a dynamic power cable. It inherits from Cable(Edge, dict)
    which describes the bare uniform cable before accessories are added.
    A DynamicCable object will likely be within a SubseaCable object, which could
    also include a StaticCable.
    End A of the dynamic cable could attach to a subsea Joint, or in the case
    of a suspended cable it would attach to another Platform.
    '''
    
    def __init__(self, dd=None, subsystem=None, anchor=None, rA=[0,0,0], rB=[0,0,0],
                 rad_anch=500, rad_fair=58, z_anch=-100, z_fair=-14, 
                 rho=1025, g=9.81, id=None):
        '''
        Parameters
        ----------
 
        '''
        Edge.__init__(self, id)  # initialize Edge base class
        # Design description dictionary for this dynamic cable
        self.dd = dd
        
        self.n_sec = 1
        
        # Store the cable type properties dict here for easy access (temporary - may be an inconsistent coding choice)
        self.cableType = self.makeCableType(self.dd['cable_type'])  # Process/check it into a new dict

        # Save some constants for use when computing buoyancy module stuff
        self.d0 = self.cableType['d_vol']  # diameter of bare dynamic cable
        self.m0 = self.cableType['m']      # mass/m of bare dynamic cable
        self.w0 = self.cableType['w']      # weight/m of bare dynamic cable
        
        
        # Turn what's in dd and turn it into Sections and Connectors
        for i, con in enumerate(self.dd['connectors']):
            if con:
                Cid = con['type']+str(i)
            else:
                Cid = i
            self.dd['connectors'][i] = Connector(Cid,**self.dd['connectors'][i])
        
        for i, sec in enumerate(self.dd['sections']):
            self.dd['sections'][i] = Section(i,**self.dd['sections'][i])
            #self.dd['connectors'][i  ].attach(self.dd['sections'][i], end=0)
            #self.dd['connectors'][i+1].attach(self.dd['sections'][i], end=1)
        
        # Connect them and store them in self(Edge).subcomponents!
        subcons = []  # list of node-edge-node... to pass to the function
        for i in range(self.n_sec):
            subcons.append(self.dd['connectors'][i])
            subcons.append(self.dd['sections'][i])
        subcons.append(self.dd['connectors'][-1])
        self.addSubcomponents(subcons)  # Edge method to connect and store em
        
        # Indices of connectors and sections in self.subcomponents list
        self.i_con = list(range(0, 2*self.n_sec+1, 2))
        self.i_sec = list(range(1, 2*self.n_sec+1, 2))
        
        # MoorPy subsystem that corresponds to the dynamic cable
        self.ss = subsystem
        
        # end point absolute coordinates, to be set later
        self.rA = rA
        self.rB = rB
        self.heading = 0
        
        # relative positions (variables could be renamed)
        self.rad_anch = rad_anch
        self.rad_fair = rad_fair
        self.z_anch   = z_anch  
        self.z_fair   = z_fair
        
        self.adjuster = None  # custom function that can adjust the mooring
        
        self.shared = False # boolean for if the mooring line is a fully suspended cable
        self.symmetric = False # boolean for if the mooring line is a symmetric suspended cable
        
        # relevant site info
        self.rho = rho
        self.g = g
        
        # Dictionaries for addition information
        self.loads = {}
        self.reliability = {}
        self.cost = {}
    
    
    def setSectionLength(self, L, i):
        '''Sets length of section, including in the subdsystem if there is
        one.'''
        
        # >>> PROBABLY NEED TO REVISE HOW THIS WORKS TO CONSIDER BUOYANCY MODULES <<<
        
        self.dd['sections'][i]['L'] = L  # set length in dd (which is also Section/subcomponent)
        
        if self.ss:  # is Subsystem exists, adjust length there too
            self.ss.lineList[i].setL(L)
    
    
    def reposition(self, r_center=None, heading=None, project=None, degrees=False, **kwargs):
        '''Adjusts mooring position based on changed platform location or
        heading. It can call a custom "adjuster" function if one is
        provided. Otherwise it will just update the end positions.
        
        Parameters
        ----------
        r_center
            The x, y coordinates of the platform (undisplaced) [m].
        heading : float
            The absolute heading of the mooring line [deg or rad] depending on
            degrees parameter (True or False).
        project : FAModel Project, optional
            A Project-type object for site-specific information used in custom
            mooring line adjustment functions (mooring.adjuster).
        **kwargs : dict
            Additional arguments passed through to the designer function.
        '''
        
        # Adjust heading if provided
        if not heading == None:
            if degrees:
                self.heading = np.radians(heading)
            else:
                self.heading = heading
            
        # heading 2D unit vector
        u = np.array([np.cos(self.heading), np.sin(self.heading)])
        #print(u)
        r_center = np.array(r_center)[:2]
        # Set the updated fairlead location
        self.setEndPosition(np.hstack([r_center + self.rad_fair*u, self.z_fair]), 'b')
        
        # Run custom function to update the mooring design (and anchor position)
        # this would also szie the anchor maybe?
        if self.adjuster:
            self.adjuster(self, project, r_center, u, **kwargs)
        
        else: # otherwise just set the anchor position based on a set spacing
            self.setEndPosition(np.hstack([r_center + self.rad_anch*u, self.z_anch]), 'a', sink=True)
        
    
    
    def setEndPosition(self, r, end, sink=False):
        '''Set the position of an end of the mooring.
        
        Parameters
        ----------
        r : list
            Cordinates to set the end at [m].
        end
            Which end of the edge is being positioned, 'a' or 'b'.
        sink : bool
            If true, and if there is a subsystem, the z position will be on the seabed.
        '''
        
        if end in ['a', 'A', 0]:
            self.rA = np.array(r)
            
            if self.ss:
                self.ss.setEndPosition(self.rA, False, sink=sink)
            
        elif end in ['b', 'B', 1]:
            self.rB = np.array(r)
            
            if self.ss:
                self.ss.setEndPosition(self.rB, True, sink=sink)
                
        else:
            raise Exception('End A or B must be specified with either the letter, 0/1, or False/True.')
    
    
    def getCost(self):
        
        # >>> UPDATE FROM CABLEDESIGN2 <<<
        
        # sum up the costs in the dictionary and return
        return sum(self.cost.values()) 
    
    
    def createSubsystem(self, case=0):
        ''' Create a subsystem for a line configuration from the design dictionary
        
        Parameters
        ----------
        case : int
            Selector shared/suspended cases:
                - 0 (default): end A is on the seabed
                - 1: assembly is suspended and end A is at another floating system
                - 2: the assembly is suspended and assumed symmetric, end A is the midpoint
        '''
        
        # >>> USE SOME METHODS FROM CABLEDESIGN2 TO CONVERT BUOYANCY MODULES TO SECTIONS! <<<
        
        # check if a subsystem already exists
        if self.ss:
            print('A subsystem for this Mooring class instance already exists, this will be overwritten.')
        self.ss=Subsystem(depth=-self.dd['zAnchor'], rho=self.rho, g=self.g, span=self.dd['span'], rBfair=self.rB)
        lengths = []
        types = []
        # run through each line section and collect the length and type
        for sec in self.dd['sections']:
            lengths.append(sec['length'])
            types.append(sec['type']['name'])
            self.ss.lineTypes[types[-1]] = sec['type']  # points to existing type dict in self.dd for now

        
        # make the lines and set the points 
        self.ss.makeGeneric(lengths,types,suspended=case)
        self.ss.setEndPosition(self.rA,endB=0)
        self.ss.setEndPosition(self.rB,endB=1)
        
        
        # note: next bit has similar code/function as Connector.makeMoorPyConnector <<<
        
        # add in connector info to subsystem points
        if case == 0: # has an anchor - need to ignore connection for first point
            startNum = 1
        else: # no anchor - need to include all connections
            startNum = 0 

        for i in range(startNum,len(self.ss.pointList)):                               
            point = self.ss.pointList[i]
            point.m = self.dd['connectors'][i]['m']
            point.v = self.dd['connectors'][i]['v']
            point.CdA = self.dd['connectors'][i]['CdA']
        # solve the system
        self.ss.staticSolve()
        
        return(self.ss)      
    

    """  Could have similar marine growth method as Mooring, but need to also consider buoyancy modules
    def addMarineGrowth(self, mgDict, project=None, idx=None):
        '''Re-creates sections part of design dictionary to account for marine 
        growth on the subystem, then calls createSubsystem() to recreate the line

        Parameters
        ----------
        mgDict : dictionary
            Provides marine growth thicknesses and the associated depth ranges
            {
                th : list with 3 values in each entry - thickness, range lower z-cutoff, range higher z-cutoff [m]
                    *In order from sea floor to surface*
                    example, if depth is 200 m: - [0.00,-200,-100]
                                                - [0.05,-100,-80]
                                                - [0.10,-80,-40]
                                                - [0.20,-40,0]
                rho : list of densities for each thickness, or one density for all thicknesses, [kg/m^3] (optional - default is 1325 kg/m^3)
                }
        project : object, optional
            A FAModel project object, with the mooringListPristine used as the basis
            to build the marine growth model, necessary if the addMarineGrowth method
            will be called in a loop (or even just multiple times) to improve accuracy 
            of change depths, which may decrease significantly after solveEquilibrium() 
            for the moorpy model. The default is None.
        idx : tuple, optional
            A key for the pristineMooringList in the project object that is associated
            with this mooring object. Since the pristineMooringList is a deepcopy of the 
            project mooringList, the mooring objects are not the same and therefore if the 
            project object is provided in the method call, the index must also be provided.

        Returns
        -------
        changePoints : list
            List of point indices in the moorpy subsystem that are at the changeDepth
        changeDepths : list
            List of cutoff depths the changePoints should be located at

        '''
        
        return(changeDepths,changePoints)
    """
