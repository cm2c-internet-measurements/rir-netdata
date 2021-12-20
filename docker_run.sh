#!/bin/bash

cd /opt/rir-netdata
pip install -r requirements.txt
./bin/netdata.py get
