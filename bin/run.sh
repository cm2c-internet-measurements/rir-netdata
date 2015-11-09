#!/bin/bash
####################################################################
# Python wrapper - sets env variables appropiately
# v2 - 20151109
####################################################################

# change this PYTHON variable if using an alternative python 
# interpreter
PYTHON="/usr/bin/python"
export SRCHOME=$(pwd)

####
export PYTHONPATH="$SRCHOME/lib:$SRCHOME/bin:$PYTHONPATH"

$PYTHON $*
