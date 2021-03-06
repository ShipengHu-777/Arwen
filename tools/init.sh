#!/bin/bash

workdir=$( cd $( dirname $0 ); pwd )
myenv=$1

eip="192.168.0.88"
hip="192.168.0.1"
gip="192.168.0.2"
cip="192.168.0.99"

if [ "$myenv" !=  "test" -a "$myenv" != "prod" ]
then
  echo "usage: $0 [test|prod]"
  exit 1;
fi

echo "clean old config"
now=$( date "+%s" )
cd ${workdir}/../

mkdir -p backups/${now}/{var_files,environments,playbooks} var_files environments logs build 

ls project_*.yml 2>>/dev/null
[ $? -eq 0 ] && mv project_*.yml backups/${now}/;
ls playbooks/*.yml 2>>/dev/null
[ $? -eq 0 ] && mv playbooks/*.yml backups/${now}/playbooks/;

num=$( ls var_files|wc -l )
[ "$num" -gt 0 ] && mv var_files/* backups/${now}/var_files/;
num=$( ls environments |wc -l )
[ "$num" -gt 0 ] && mv environments/* backups/${now}/environments;

if [ ! -d environments/$myenv  ] 
then
  echo "init environments/$myenv"
  cp -r example/environments/exp environments/$myenv
fi
if [ ! -d var_files/$myenv  ]
then
  echo "init var_files/$myenv"
  cp -r example/var_files/exp var_files/$myenv
fi
if [ ! -f project_${myenv}.yml ]
then
  echo "init project_${myenv}.yml"
  cp example/project_exp.yml project_${myenv}.yml
  cp example/playbooks/* playbooks/
  sed -i 's#var_files/exp#var_files/'"${myenv}"'#g' project_${myenv}.yml
  sed -i 's#var_files/exp#var_files/'"${myenv}"'#g' playbooks/*.yml
fi

if [ -n  "$hip" -a "$hip" != "192.168.0.1" ]
then
  sed -i 's#192.168.0.1#'"$hip"'#g'  var_files/$myenv/fate_host
  sed -i 's#192.168.0.1#'"$hip"'#g'  environments/${myenv}/hosts
else
  sed -i 's/\(192.168.0.1.*\)/#\1/g'  environments/${myenv}/hosts
fi

if [ -n  "$gip" -a "$gip" != "192.168.0.2" ]
then
  sed -i 's#192.168.0.2#'"$gip"'#g'  var_files/$myenv/fate_guest
  sed -i 's#192.168.0.2#'"$gip"'#g'  environments/${myenv}/hosts 
else
  sed -i 's/\(192.168.0.2.*\)/#\1/g'  environments/${myenv}/hosts
fi

if [ -n  "$cip" -a "$cip" != "192.168.0.99" ]
then
  sed -i 's#192.168.0.99#'"$cip"'#g'  environments/${myenv}/hosts 
else
  sed -i 's/\(192.168.0.99.*\)/#\1/g'  environments/${myenv}/hosts
fi

if [ -n  "$eip" -a "$eip" != "192.168.0.88" ]
then
  sed -i 's#192.168.0.88#'"$eip"'#g'  var_files/$myenv/fate_exchange
  sed -i 's#192.168.0.88#'"$eip"'#g'  environments/${myenv}/hosts 
else
  sed -i 's/\(192.168.0.88.*\)/#\1/g'  environments/${myenv}/hosts
fi


