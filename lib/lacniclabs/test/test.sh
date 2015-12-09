#!/bin/bash
# v2, 20151201

# change python interpreter here, if necessary
PYTHON="/usr/bin/python"
export SRCHOME="$(pwd)"

####
export PYTHONPATH="$SRCHOME/..:$SRCHOME/../cm2c:$PYTHONPATH"

$PYTHON $*
