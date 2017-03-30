#!/bin/bash

## 
# small wrapper for the python script to activate the virtual env
# 
# $1: path to the galaxy root

if [$# -ne 1]; 
    then echo "illegal number of parameters. usage: galaxy-ldap-sync.sh GALAXY-ROOT-DIR."
fi

if [ ! -f $1/.venv/bin/activate ]
then
	>&2 echo "the given galaxy root seems to contain no venv"
	exit 1
fi


if [ ! -f config.yml ]
then
	>&2 echo "no config.yml file found."
	exit 1
fi

# activate venv
source $1/.venv/bin/activate
if (( $? ))
then
	>&2 echo "could not source "$1
	exit 1
fi

# run the script
python galaxy-ldap-sync.py --config config.yml

# deactivate venv
deactivate
