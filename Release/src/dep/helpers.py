import numpy as np
 
def negateDict(sensorState):    
    returnDict = {}
    for i,item in sensorState.items():
        if type(item)==dict:
            returnDict[i] = negateDict(item)
        else:
            returnDict[i] =-item
    return returnDict


def addDicts(DictA,DictB):
    for i,item in DictA.items():
        if type(item) == dict:
            addDicts(item,DictB[i])
        else:
            DictA[i] = item +DictB[i]
        
class Controller:
    def __init__(self):
        pass
    def update(self,droneState,clockState,target):
        pass
    def reset(self,droneState,clockState,target):
        pass
    def __call__(self):
        return np.array([0.,0.,0.])

class PhaseManager:
    def __init__(self,name):
        self.name = name
        self.status = False #false means inactive

    def setController(self,controller):
        """
        A controller is an object that takes upacked dicos as input,
        they are fed every loop the controller is active through the self.update() method
        The controller must have a self.reset() method called to reset their state
        The controller must generate a 3x1 vector of control inputs [vx,vy,vz] through __call__
        """
        self.controller = controller
    def toggle(self):
        self.status = not self.status
    
    def getController(self):
        return self.controller

class FlightManager(PhaseManager):
    def __init__(self,name,aboveGround,target,tol = 0.1,nextPhase = 'land',**kwargs):
        self.name = name
        self.target = np.array(target)
        self.count = 0
        self.tol = tol #position tolerance in meters
        self.newPhase  = None
        self.status    = False
        self.onRamp    = False
        self.onDrop    = False
        self.heightMem = None
        
    def update(self,droneState,clockState,**kwargs):
        #if we are steady around the target wait
        rampHeight = (droneState['pos'][2] - droneState['height'])
        if self.count == 0 and self.name == 'ramp':
            self.controller.minVel = 0.2
            self.count += 1

            
        if not self.heightMem == None:
            gradient = -self.heightMem + droneState['height']
            self.heightMem = droneState['height']
        else:
            self.heightMem = droneState['height']
            return 0



        
        if gradient < 0.3 and not self.onRamp:#detect the ramp

            self.onRamp = True
            
        if self.name == 'fly':
            self.controller.minVel = 0.
            self.onRamp = False

        
        if not self.onDrop and self.onRamp and gradient > 0.4:# must be smaller than the tolerance
            self.controller.minVel = 0.
            self.target[0] = droneState['pos'][0]+0.05
            self.target[1] = 0.
            self.target[2] = 1.5
            self.controller.reset(clockState)
            self.onDrop = True


        
        if all(np.abs(droneState['pos'] - self.target) < self.tol) and all(np.abs(droneState['velLinear']<0.2)):
            self.count += 1
        
        #if hover has been achieved for 1 second, land
        if not self.onDrop and self.count > kwargs['rate']*1:

            self.controller.reset(clockState)
            self.status = False
            self.newPhase = 'land'
        elif self.onDrop and self.count > 1:
            self.controller.reset(clockState)
            self.status = False
            self.newPhase = 'fly'
        
        return 0


class LandingManager(PhaseManager):#for landing and ending the program
    def __init__(self,name,target,tol = 0.1,**kwargs):
        self.name = name
        self.target = np.array(target)
        self.count = 0
        self.tol = tol #position tolerance in meters
        self.newPhase = None
        self.status = False
        
    def update(self,droneState,clockState,**kwargs):
        #if we are steady around the target wait
        if droneState['height'] < 0.2:
            return 1
        return 0

class takeOffManager(PhaseManager): #for taking off
    def __init__(self,name,target,tol = 0.1,**kwargs):
        self.name = name
        self.target = np.array(target)
        self.count = 0
        self.tol = tol #position tolerance in meters
        self.newPhase = None
        self.status = True
        
    def update(self,droneState,clockState,**kwargs):

        #if we are steady around the target wait

        if droneState['pos'][2] > 1.45: #wait one second
            self.controller.reset(clockState)
            self.status = False
            self.newPhase = 'tune'
        return 0

def getMaxFreq(npArray,**kwargs):
    transform = np.fft.fft(npArray-np.average(npArray))
    n =len(npArray)
    #frequency range
    freq = kwargs['rate']*np.arange(n)/(2*float(n))
    amps = np.absolute(transform)
    pos = np.where(amps==max(amps))
    return freq[pos][0]
    

class tuneManager(PhaseManager):
    def __init__(self,name,target,tol = 0.1,**kwargs):
        self.name = name
        self.target = np.array(target)
        self.count = 0
        self.tol = tol #position tolerance in meters
        self.newPhase = None
        self.status = True
        self.n = 50 #must be even
        self.zarray = np.zeros((self.n,))
        self.nTunes = 0
        self.maxTunes = 1
        
    def update(self,droneState,clockState,**kwargs):
        #counting 
        self.zarray[self.count] = droneState['pos'][2]
        self.count += 1
        
        #when the count is over
        if self.count >= self.n:
            #first compute the transform
            group1 = self.zarray[0:self.n/2]
            group2 = self.zarray[(self.n/2+1):]
            
            #get the freqencies
            freq1 = getMaxFreq(group1,**kwargs)
            freq2 = getMaxFreq(group2,**kwargs)

            if abs(freq1 - freq2) < freq2*0.1:
                #average the values
                freq = (freq1 + freq2)/2.
                Kp = self.controller.k_p[2]
                self.controller.k_p[2] *= 0.5
                self.controller.k_d[2] = 0.01*Kp
                self.controller.k_i[2] = 0.01*Kp
            else:
                self.controller.k_p[2] *= 0.25
                self.controller.k_d[2] = -0.01
                self.controller.k_i[2] = -0.01

            
            #pass the controller back
            self.controller.reset(clockState)
            self.status = False
            self.newPhase = 'ramp'
        
        return 0


class safeMode(PhaseManager): #for safemode
    def __init__(self,name,**kwargs):
        self.name = name
        self.count = 0
        self.status = True
        self.target = [0,0,0]
        self.newPhase = None
    def update(self,droneState,clockState,**kwargs):
	return 0



class MissionManager:
    """
    In charge of switching model states
    """
    def __init__(self, killFunc =None):
        initialPhase = safeMode('safe')
        initialPhase.setController(Controller())
        self.segments = {'safe' : initialPhase}
        self.currentState = 'safe'
        self.killfunc = killFunc
        
    def addSegment(self,phaseManager): #plan a new waypoint
        self.segments[phaseManager.name] = phaseManager
    def initialSegment(self,name):
        self.currentState = name#a way to set the controler state
    def controller(self): #get current controller
        return self.segments[self.currentState].getController()
    def phase(self): #get phase manger for current segment
        return self.segments[self.currentState]
    def update(self,droneState,clockState,**kwargs): #update manager status (change phase)
        phase = self.segments[self.currentState]
        #check if the phase is still active
        if not self.segments[self.currentState].status: #change phase
            #phase change logic goes here
            if phase.newPhase == None:
                pass
            else:
                name = phase.newPhase
                self.segments[name].status = True 
                self.currentState = name

            
        else: 
            status = phase.update(droneState,clockState,**kwargs)#update the phase 
            if status == 1:
                if self.killfunc == None:#If you forgot to define a kill function
                    raise Exception("Define a shudown function in __init__")
                else:
                    self.killfunc(0)#if not proceed
                
    def check(self):
        assert(self.segments[self.currentState].status)



def updateState(droneState,sensorState,clockState):
    #add sensor fusion here
    droneState['pos'] = sensorState['linearPose']
    droneState['height'] =sensorState['height']
    droneState['quaternion'] = sensorState['quatPose']
    droneState['velLinear'] = sensorState['linearVel']
    droneState['velAngular'] = sensorState['angularVel']


def logDict(phase,droneState,clockState,nodeState,sensorState,inVel):
    result = {  'phase'         : phase                         ,
                'time_sonar'    : clockState['sonar']           ,
                'h_sonar'       : droneState['height']          ,
                'time_pose'     : clockState['pose']            , 
                'x'             : droneState['pos'][0]          ,
                'y'             : droneState['pos'][1]          ,
                'z'             : droneState['pos'][2]          ,
                'quat_x'        : droneState['quaternion'][0]   ,
                'quat_y'        : droneState['quaternion'][1]   ,
                'quat_z'        : droneState['quaternion'][2]   ,
                'quat_w'        : droneState['quaternion'][3]   ,
                'time_vel'      : clockState['vel']             ,
                'x_dot'         : droneState['velLinear'][0]    ,
                'y_dot'         : droneState['velLinear'][1]    ,
                'z_dot'         : droneState['velLinear'][2]    ,
                'ang_x_dot'     : droneState['velAngular'][0]   ,
                'ang_y_dot'     : droneState['velAngular'][1]   ,
                'ang_z_dot'     : droneState['velAngular'][2]   ,
                'time_imu'      : clockState['IMU']             ,
                'x_dot2'        : sensorState['linearAcc'][0]   ,
                'y_dot2'        : sensorState['linearAcc'][1]   ,
                'z_dot2'        : sensorState['linearAcc'][2]   ,
                'in_x_dot'      : inVel[0]                      ,
                'in_y_dot'      : inVel[1]                      ,
                'in_z_dot'      : inVel[2]                      }
    return result
