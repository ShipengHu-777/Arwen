#!/bin/bash

workdir=$(cd $(dirname $0); pwd)
export PATH=${workdir}/bin:$PATH

exchange_host="10.107.117.100"
host_host="10.107.117.16"
guest_host="10.107.117.168"

for role in "guest" "host" "exchange";
do
  curdir=${workdir}/keys/$role
  mkdir -p $curdir 
  cd ${curdir}

  tpl="$( cat ${workdir}/tpl/ca-csr.json.tpl )"
  variables="ca_name=fdn_test_$role"
  printf "$variables\ncat << EOF\n$tpl\nEOF" | bash > ca-csr.json
  cp ${workdir}/files/ca-config.json ${curdir}
  cfssl gencert -initca ca-csr.json | cfssljson -bare ca
  #cp -f ca.pem ${wordir}../roles/eggroll/files/keys/${role}/

  tpl="$( cat ${workdir}/tpl/server-csr.json.tpl )"
  eval variables="\"server_cn=${role}-fate.test.com server_host=\${${role}_host}\""
  echo "---------------$variables--------------"
  printf "$variables\ncat << EOF\n$tpl\nEOF" | bash > server-csr.json
  cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json -profile=server server-csr.json | cfssljson -bare server
  openssl pkcs8 -topk8 -inform PEM -in server-key.pem     -outform PEM -out server.key -nocrypt
  #cp -f server.key server.pem ${wordir}../roles/eggroll/files/keys/$role

  tpl="$( cat ${workdir}/tpl/client-csr.json.tpl )"
  variables="client_cn=${role}-client.test.com"
  printf "$variables\ncat << EOF\n$tpl\nEOF" | bash > client-csr.json
  cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json -profile=client client-csr.json | cfssljson -bare client
  openssl pkcs8 -topk8 -inform PEM -in client-key.pem     -outform PEM -out client.key -nocrypt
  #cp -f client.key client.pem ${wordir}../roles/eggroll/files/keys/$role

done > ${workdir}/../logs/keys.log 2>&1


