#!/bin/bash


myenv=$1;
args=$2;

case $myenv in 
  test|prod) 
    if [ ! -d environments/$myenv  -o ! -d var_files/$myenv -o ! -f project_${myenv}.yml ]
    then
      echo "please run init.sh and do some setups."
      exit 1;
    fi

    start=$( date "+%s" )
    startStr=$(date)
     ansible-playbook -i environments/$myenv   project_${myenv}.yml $args
    end=$( date "+%s" )
    endStr=$(date)
    echo "start: $startStr end: $endStr last: $(( $end - $start ))s" > logs/count
  ;;
 
  *)
    echo "Usage: $0 [test|prod] args"
    echo "  args:"
    echo "    -C  don't make any changes; instead, try to predict some of the changes that may occur"
    echo "    -D when changing (small) files and templates, show the differences in those files; works great with --check"
  ;;

esac > logs/boot-$( date "+%s" ).log


