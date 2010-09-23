# -*- coding: utf-8 -*-
"""
    edacc.constants
    ---------------

    Application logic constants used in the database and the Java Swing
    application.
"""

# tuples since there are 3 codes that mean 'finished'
JOB_ERROR = (-2,)
JOB_WAITING = (-1,)
JOB_RUNNING = (0,)
JOB_FINISHED = (1,2,3)

# status id to string map
JOB_STATUS = {
    -5: 'launcher crash',
    -4: 'watcher crash',
    -3: 'solver crash',
    -2: 'verifier crash',
    -1: 'not started',
    0:  'running',
    1:  'finished',
    2:  'terminated by ulimit',
}

JOB_RESULT_CODE = {
    11: 'SAT',
    10: 'UNSAT',
    0: 'UNKNOWN',
    -1: 'wrong answer',
    #-2: 'limit exceeded',
    -21: 'cpu time limit exceeded',
    -22: 'wall clock time limit exceeded',
    -23: 'memory limit exceeded',
    -24: 'stack size limit exceeded',
    -25: 'output size limit exceeded',
}

JOB_STATUS_COLOR = {
    -5: '#FF0000',
    -4: '#FF0000',
    -3: '#FF0000',
    -2: '#FF0000',
    -1: '#4169E1',
    0:  'orange',
    1:  '#00CC33',
    2:  '#FF6600',
}
