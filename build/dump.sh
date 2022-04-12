#!/bin/bash

workdir=$(cd $(dirname $0); pwd)

if [ "$#" -ne 2 ]
then
  echo "$0 version minversion"
  exit 1;
fi

version=$1
minversion=$2
url="https://webank-ai-1251170195.cos.ap-guangzhou.myqcloud.com/"
 
if [ -z "$minversion" ]
then
  fname="FATE_install_${version}.tar.gz"
else
  fname="FATE_install_${version}_${minversion}.tar.gz"
  wget ${url}${fname}
fi

if [ ! -f "${workdir}/../build/$fname" ]
then
  echo "${workdir}/../build/$fname not exists"
else
  cd "${workdir}/../build"
  tar xf $fname;
  cd FATE_install_${version};
  for name in "bin" "conf" "eggroll" "examples" "fateboard" "proxy" "python"
  do
    package_name=$name".tar.gz"
    md5=`md5sum $package_name |awk '{print $1}'`
    value=$name":"$md5
    result=`cat packages_md5.txt`
    for name2 in ${result[@]}
    do
      if [ "$name2" = "$value" ];then
        echo "The $name md5 value matches successfully"
      fi
    done
    tar xf $package_name
  done
  echo "cp -v python.tar.gz ${workdir}/../roles/fate_flow/files/fate_flow-${version}.tar.gz"
  cp -vf python.tar.gz "${workdir}/../roles/fate_flow/files/fate_flow-${version}.tar.gz"
  echo "cp -v examples.tar.gz ${workdir}/../roles/fate_flow/files/fate_examples-${version}.tar.gz"
  cp -vf examples.tar.gz "${workdir}/../roles/fate_flow/files/fate_examples-${version}.tar.gz"
  echo "cp -vf requirements.txt ${workdir}/../roles/python/files/requirements.txt"
  cp -vf requirements.txt ${workdir}/../roles/python/files/requirements.txt
  ls -l "${workdir}/../roles/python/files/"
  echo "cp -vf conf/transfer_conf.yaml ${workdir}/../roles/fate_flow/files/transfer_conf.yaml"
  cp -vf conf/transfer_conf.yaml ${workdir}/../roles/fate_flow/files/transfer_conf.yaml
  echo "cp -vf conf/rabbitmq_route_table.yaml ${workdir}/../roles/fate_flow/files/rabbitmq_route_table.yaml"
  cp -vf conf/rabbitmq_route_table.yaml ${workdir}/../roles/fate_flow/files/rabbitmq_route_table.yaml
  echo "cp -vf RELEASE.md fate.env ${workdir}/../roles/fate_flow/files/"
  cp -vf RELEASE.md fate.env ${workdir}/../roles/fate_flow/files/
  ls -l "${workdir}/../roles/fate_flow/files/"
  echo "cp -vf fateboard.tar.gz ${workdir}/../roles/fateboard/files/fateboard-${version}.tar.gz"
  cp -vf fateboard.tar.gz "${workdir}/../roles/fateboard/files/fateboard-${version}.tar.gz"
  ls -l "${workdir}/../roles/fateboard/files/fateboard-${version}.tar.gz"
  echo "cp -vf eggroll.tar.gz ${workdir}/../roles/eggroll/files/eggroll-${version}.tar.gz"
  cp -vf eggroll.tar.gz "${workdir}/../roles/eggroll/files/eggroll-${version}.tar.gz"
  ls -l "${workdir}/../roles/eggroll/files/eggroll-${version}.tar.gz"
  echo "cp -vf install_os_dependencies.sh ../roles/base/files/install_os_dependencies.sh"
  cp -vf bin/install_os_dependencies.sh "${workdir}/../roles/base/files/install_os_dependencies.sh"
  ls -l "${workdir}/../roles/base/files/install_os_dependencies.sh"
fi

cd $workdir
rm -rf $fname FATE_install_${version} 
