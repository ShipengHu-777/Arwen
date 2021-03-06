#!/bin/bash
workdir=$(cd $(dirname $0); pwd)
cd $workdir
now=$( date +%s )


model="$1-$2"
case $model in
  "host-guest"|"guest-host")
    echo "cp host & guest"
    
    mkdir -pv keys/backups/$model
    if [ -d  ../roles/eggroll/files/keys/guest ]
    then
      mv ../roles/eggroll/files/keys/guest keys/backups/${model}/guest-$now 
    fi
    mkdir -p ../roles/eggroll/files/keys/guest 
    
    cp keys/guest/ca.pem  ../roles/eggroll/files/keys/guest/guest-ca.pem
    cp keys/guest/server.key  ../roles/eggroll/files/keys/guest/guest-server.key
    cp keys/guest/server.pem  ../roles/eggroll/files/keys/guest/guest-server.pem
    cp keys/host/ca.pem  ../roles/eggroll/files/keys/guest/host-client-ca.pem
    cp keys/host/client.pem  ../roles/eggroll/files/keys/guest/host-client.pem
    cp keys/host/client.key  ../roles/eggroll/files/keys/guest/host-client.key
    
    if [ -d  ../roles/eggroll/files/keys/host ]
    then
      mv ../roles/eggroll/files/keys/host keys/backups/${model}/host-$now
    fi
    mkdir -p ../roles/eggroll/files/keys/host 
    
    cp keys/host/ca.pem  ../roles/eggroll/files/keys/host/host-ca.pem
    cp keys/host/server.key ../roles/eggroll/files/keys/host/host-server.key
    cp keys/host/server.pem ../roles/eggroll/files/keys/host/host-server.pem
    cp keys/guest/ca.pem  ../roles/eggroll/files/keys/host/guest-client-ca.pem
    cp keys/guest/client.pem ../roles/eggroll/files/keys/host/guest-client.pem
    cp keys/guest/client.key ../roles/eggroll/files/keys/host/guest-client.key
    
    if [ -d  ../roles/eggroll/files/keys/exchange ]
    then
      mv ../roles/eggroll/files/keys/exchange keys/backups/${model}/exchange-$now
    fi
    
  
  
    ;;

  "exchange-host"|"host-exchange")
    echo "cp exchange & host"
    
    mkdir -p keys/backups/${model}
    
    if [ -d  ../roles/eggroll/files/keys/exchange ]
    then
      mv ../roles/eggroll/files/keys/exchange keys/backups/${model}/exchange-$now
    fi
    mkdir -p ../roles/eggroll/files/keys/exchange
    
    cp keys/exchange/ca.pem  ../roles/eggroll/files/keys/exchange/exchange-ca.pem
    cp keys/exchange/server.key  ../roles/eggroll/files/keys/exchange/exchange-server.key
    cp keys/exchange/server.pem  ../roles/eggroll/files/keys/exchange/exchange-server.pem
    cp keys/host/ca.pem  ../roles/eggroll/files/keys/exchange/host-client-ca.pem
    cp keys/host/client.pem  ../roles/eggroll/files/keys/exchange/host-client.pem
    cp keys/host/client.key  ../roles/eggroll/files/keys/exchange/host-client.key
    
    if [ -d  ../roles/eggroll/files/keys/host ]
    then
      mv ../roles/eggroll/files/keys/host keys/backups/${model}/host-$now
    fi
    mkdir -p ../roles/eggroll/files/keys/host
    
    cp keys/host/ca.pem  ../roles/eggroll/files/keys/host/host-ca.pem
    cp keys/host/server.pem  ../roles/eggroll/files/keys/host/host-server.pem
    cp keys/host/server.key  ../roles/eggroll/files/keys/host/host-server.key
    cp keys/exchange/ca.pem  ../roles/eggroll/files/keys/host/exchange-client-ca.pem
    cp keys/exchange/client.key  ../roles/eggroll/files/keys/host/exchange-client.key
    cp keys/exchange/client.pem  ../roles/eggroll/files/keys/host/exchange-client.pem
    
    if [ -d  ../roles/eggroll/files/keys/guest ]
    then
      mv ../roles/eggroll/files/keys/guest keys/backups/${model}/guest-$now
    fi
    
        ;;
    
  "exchange-guest"|"guest-exchange")
    echo "cp exchange & guest"

    
    mkdir -p keys/backups/${model}
    
    if [ -d  ../roles/eggroll/files/keys/exchange ]
    then
      mv ../roles/eggroll/files/keys/exchange keys/backups/${model}/exchange-$now
    fi
    mkdir -p ../roles/eggroll/files/keys/exchange
    
    cp keys/exchange/ca.pem  ../roles/eggroll/files/keys/exchange/exchange-ca.pem
    cp keys/exchange/server.key  ../roles/eggroll/files/keys/exchange/exchange-server.key
    cp keys/exchange/server.pem  ../roles/eggroll/files/keys/exchange/exchange-server.pem
    cp keys/guest/ca.pem  ../roles/eggroll/files/keys/exchange/guest-client-ca.pem
    cp keys/guest/client.pem  ../roles/eggroll/files/keys/exchange/guest-client.pem
    cp keys/guest/client.key  ../roles/eggroll/files/keys/exchange/guest-client.key
    
    if [ -d ../roles/eggroll/files/keys/guest ]
    then
      mv ../roles/eggroll/files/keys/guest keys/backups/${model}/guest-$now
    fi
    mkdir -p ../roles/eggroll/files/keys/guest
    
    
    cp keys/guest/ca.pem  ../roles/eggroll/files/keys/guest/guest-ca.pem
    cp keys/guest/server.pem  ../roles/eggroll/files/keys/guest/guest-server.pem
    cp keys/guest/server.key  ../roles/eggroll/files/keys/guest/guest-server.key
    cp keys/exchange/ca.pem  ../roles/eggroll/files/keys/guest/exchange-client-ca.pem
    cp keys/exchange/client.key  ../roles/eggroll/files/keys/guest/exchange-client.key
    cp keys/exchange/client.pem  ../roles/eggroll/files/keys/guest/exchange-client.pem
    
    if [ -d ../roles/eggroll/files/keys/host ]
    then
      mv ../roles/eggroll/files/keys/host keys/backups/${model}/host-$now
    fi 
    
        ;;

  *)
    echo "Usage: $0 role1 role2"
    ;;
esac >> ${workdir}/../logs/keys.log 2>&1 



