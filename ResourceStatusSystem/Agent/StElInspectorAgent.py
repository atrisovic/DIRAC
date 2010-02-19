########################################################################
# $HeadURL:  $
########################################################################

import threading
from DIRAC import gLogger, gConfig, S_OK, S_ERROR
from DIRAC.Core.Base.AgentModule import AgentModule
from DIRAC.Core.Utilities.ThreadPool import ThreadPool,ThreadedJob
from DIRAC.ResourceStatusSystem.Utilities.Exceptions import *
from DIRAC.ResourceStatusSystem.Utilities.Utils import *
from DIRAC.ResourceStatusSystem.PolicySystem.PEP import PEP
from DIRAC.ResourceStatusSystem.DB.ResourceStatusDB import *
from DIRAC.ResourceStatusSystem.Policy import Configurations

__RCSID__ = "$Id:  $"

AGENT_NAME = 'ResourceStatus/StElInspectorAgent'

class StElInspectorAgent(AgentModule):
  """ Class StElInspectorAgent is in charge of going through StorageElements
      table, and pass StorageElement and Status to the PEP
  """

  def initialize(self):
    """ Standard constructor
    """
    
    try:
      try:
        self.rsDB = ResourceStatusDB()
      except RSSDBException, x:
        gLogger.error(whoRaised(x))
      except RSSException, x:
        gLogger.error(whoRaised(x))
      
      self.am_setOption( "PollingTime", 60 )
      self.StorageElementsToBeChecked = []
      self.StorageElementNamesInCheck = []
      #self.maxNumberOfThreads = gConfig.getValue(self.section+'/NumberOfThreads',1)
      #self.threadPoolDepth = gConfig.getValue(self.section+'/ThreadPoolDepth',1)
      
      self.maxNumberOfThreads = self.am_getOption( 'maxThreadsInPool', 1 )
      #self.threadPool = ThreadPool(1,self.maxNumberOfThreads)
  
      #vedi taskQueueDirector
      self.threadPool = ThreadPool( self.am_getOption('minThreadsInPool', 1),
                         self.am_getOption('maxThreadsInPool', 1),
                         self.am_getOption('totalThreadsInPool', 1) )
      if not self.threadPool:
        self.log.error('Can not create Thread Pool:')
        return S_ERROR('Can not create Thread Pool')
      
      self.lockObj = threading.RLock()
      
      self.setup = gConfig.getValue("DIRAC/Setup")
      
      return S_OK()
    
    except Exception, x:
      errorStr = where(self, self.execute)
      gLogger.exception(errorStr,lException=x)
      return S_ERROR(errorStr)


  def execute(self):
    """ The main SSInspectorAgent execution method
    """
    
    try:
      storageElementsGetter = ThreadedJob(self._getStorageElementsToCheck)
      self.threadPool.queueJob(storageElementsGetter)
      
      for i in range(self.maxNumberOfThreads - 1):
        checkExecutor = ThreadedJob(self._executeCheck)
        self.threadPool.queueJob(checkExecutor)
    
      self.threadPool.processAllResults()
      return S_OK()

    except Exception, x:
      errorStr = where(self, self.execute)
      gLogger.exception(errorStr,'', x)
      return S_ERROR(errorStr)
      
  def _getStorageElementsToCheck(self):
    """ 
    Call :meth:`DIRAC.ResourceStatusSystem.DB.ResourceStatusDB.getStorageElementsToCheck` 
    and put result in list
    """
    
    try:
      
      try:
        res = self.rsDB.getStuffToCheck('StorageElements', 
                                        Configurations.StorageElements_check_freq, 
                                        self.maxNumberOfThreads - 1)
      except RSSDBException, x:
        gLogger.error(whoRaised(x))
      except RSSException, x:
        gLogger.error(whoRaised(x))
  
      for storageElementTuple in res:
        if storageElementTuple[0] in self.StorageElementNamesInCheck:
          break
        storageElementL = ['StorageElement']
        for x in storageElementTuple:
          storageElementL.append(x)
        self.lockObj.acquire()
        try:
          self.StorageElementNamesInCheck.insert(0, storageElementL[1])
          self.StorageElementsToBeChecked.insert(0, storageElementL)
        finally:
          self.lockObj.release()

    except Exception, x:
      gLogger.exception(whoRaised(x),'',x)


  def _executeCheck(self):
    """ 
    Create istance of a PEP, instantiated popping a storageElement from lists.
    """
    
    try:
    
      if len(self.StorageElementsToBeChecked) > 0:
          
        self.lockObj.acquire()
        try:
          toBeChecked = self.StorageElementsToBeChecked.pop()
        finally:
          self.lockObj.release()
        
        granularity = toBeChecked[0]
        storageElementName = toBeChecked[1]
        status = toBeChecked[2]
        formerStatus = toBeChecked[3]
        siteType = toBeChecked[4]
        
        gLogger.info("Checking StorageElement %s, with status %s" % (storageElementName, status))
        newPEP = PEP(granularity = granularity, name = storageElementName, status = status, 
                     formerStatus = formerStatus, siteType = siteType)
        newPEP.enforce(rsDBIn = self.rsDB, setupIn = self.setup)
  
    except Exception, x:
      gLogger.exception(whoRaised(x),'',x)
    finally:
      try:
        self.lockObj.acquire()
        try:
          self.StorageElementNamesInCheck.remove(storageElementName)
        finally:
          self.lockObj.release()
      except NameError:
        pass
        
