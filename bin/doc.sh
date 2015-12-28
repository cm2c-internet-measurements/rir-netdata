#!/bin/bash
####################################################################
# Python wrapper - sets env variables appropiately
# v2 - 20151109
####################################################################

# change this PYTHON variable if using an alternative python 
# interpreter
export PYTHON="/usr/bin/python"
export SRCHOME=$(pwd)

####
export PYTHONPATH="$SRCHOME/lib:$SRCHOME/lib/cm2c:$SRCHOME/bin:$PYTHONPATH"

cd doc
make $1

