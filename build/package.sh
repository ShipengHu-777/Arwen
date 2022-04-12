#!/bin/bash

workdir=$(cd $(dirname $0); pwd)
cd $workdir

if [ ! -d "$workdir/temp" ]
then
  mkdir -p $workdir/temp
fi

if [ "$#" -ne 3 ]
then
  echo "[error]: $0 need three parameters {version minversion lastversion}"
  exit 1;
fi

function package_cp() {
  parm1=$1
  parm2=$2
  echo -e "----$parm1 md5 has changed----\n"
  echo -e "cp -vf ${parm1} ${workdir}../roles/${parm2}/files/${parm1}"
  cp -vf ${parm1} "${workdir}/../roles/${parm2}/files/${parm1}"
  ls -l "${workdir}/../roles/${parm2}/files/${parm1}"
  echo -e "\n"
}

version=$1
minversion=$2
lastversion=$3
url="https://webank-ai-1251170195.cos.ap-guangzhou.myqcloud.com/"

if [ -n "$minversion" ]
then
  fname="FATE_install_${version}_${minversion}.tar.gz"
  echo "---------------Download $fname---------------"
  wget ${url}${fname}
fi

if [ -n "$lastversion" ]
then
  lname="FATE_install_${version}_${lastversion}.tar.gz"
  echo "---------------Download $lname---------------"
  wget ${url}${lname}
fi

if [[ ! -f "${workdir}/$fname" || ! -f "${workdir}/$lname" ]]
then
  echo "${workdir}/$fname or ${workdir}/$lname not exists"
  exit 1
else
  tar xf $fname
  tar xf $lname -C ./temp
  cd FATE_install_${version};
  packages_md5=()
  value=`cat packages_md5.txt`
  for name in "bin" "conf" "python" "examples" "fateboard" "eggroll" "proxy"
  do
    package_name=$name".tar.gz"
    package_md5=`md5sum ${package_name} |awk '{print $1}'`
    packages_md5=( ${packages_md5[*]} $name':'$package_md5 )
   done
  declare -a result_list
  t=0
  flag=0
  for m in ${packages_md5[@]};do
    for n in ${value[*]};do
      if [ "$m" = "$n" ];then
        echo -e "The $m md5 value matches successfully\n"
        flag=1
        break
      fi
    done
    if [ $flag -eq 0 ]; then
      result_list[t]=$m
      t=$((t+1))
    else
      flag=0
    fi
  done
  if [[ -n $result_list ]];then
    echo -e "The ${result_list[*]} md5 value matches failed\n"
    exit 1
  fi
  if [ $? -eq 0 ];then
    mv examples.tar.gz fate_examples-${version}.tar.gz
    mv python.tar.gz fate_flow-${version}.tar.gz
    mv fateboard.tar.gz fateboard-${version}.tar.gz
    mv eggroll.tar.gz eggroll-${version}.tar.gz
    mv ${workdir}/temp/FATE_install_${version}/examples.tar.gz ${workdir}/temp/FATE_install_${version}/fate_examples-${version}.tar.gz
    mv ${workdir}/temp/FATE_install_${version}/python.tar.gz ${workdir}/temp/FATE_install_${version}/fate_flow-${version}.tar.gz
    mv ${workdir}/temp/FATE_install_${version}/fateboard.tar.gz ${workdir}/temp/FATE_install_${version}/fateboard-${version}.tar.gz
    mv ${workdir}/temp/FATE_install_${version}/eggroll.tar.gz ${workdir}/temp/FATE_install_${version}/eggroll-${version}.tar.gz
  fi

  for pkname in "eggroll-${version}.tar.gz" "fate_examples-${version}.tar.gz" "fateboard-${version}.tar.gz" "fate_flow-${version}.tar.gz" "RELEASE.md" "requirements.txt" "fate.env" "conf.tar.gz" "bin.tar.gz"
  do
    md5_new=`md5sum $pkname | awk '{print $1}'`
    md5_old=`md5sum ${workdir}/temp/FATE_install_${version}/${pkname} | awk '{print $1}'`
    if [ ${md5_new} = ${md5_old} ];then
      echo -e "****${pkname} md5 no change****\n"
      continue
    fi
    if [ $pkname = "conf.tar.gz" ];then
      tar xf $pkname
      echo -e "----$pkname md5 has changed----\n"
      echo -e "cp -vf conf/transfer_conf.yaml ${workdir}/../roles/fate_flow/files/transfer_conf.yaml"
      cp -vf conf/transfer_conf.yaml ${workdir}/../roles/fate_flow/files/transfer_conf.yaml
      ls -l ${workdir}/../roles/fate_flow/files/transfer_conf.yaml
      echo -e "cp -vf conf/rabbitmq_route_table.yaml ${workdir}/../roles/fate_flow/files/rabbitmq_route_table.yaml"
      cp -vf conf/rabbitmq_route_table.yaml ${workdir}/../roles/fate_flow/files/rabbitmq_route_table.yaml
      ls -l ${workdir}/../roles/fate_flow/files/rabbitmq_route_table.yaml
      echo -e "\n"
      continue
    fi
    if [ $pkname = "bin.tar.gz" ];then
      tar xf $pkname
      echo -e "----$pkname md5 has changed----\n"
      echo -e "cp -vf install_os_dependencies.sh ${workdir}/../roles/base/files/install_os_dependencies.sh"
      cp -vf bin/install_os_dependencies.sh "${workdir}/../roles/base/files/install_os_dependencies.sh"
      ls -l "${workdir}/../roles/base/files/install_os_dependencies.sh"
      echo -e "\n-----please check manually init_env.sh is there ant change----------\n"
      continue
    fi
    if [ $pkname = "eggroll-${version}.tar.gz" ];then
      package_cp $pkname eggroll
      continue
    fi
    if [ $pkname = "fateboard-${version}.tar.gz" ];then
      package_cp $pkname fateboard
      continue
    fi
    if [ $pkname = "requirements.txt" ];then
      package_cp $pkname python
      wget -P ${workdir}/ ${url}pip-packages-fate-${version}.tar.gz
      echo -e "\ncp -vf ${workdir}/pip-packages-fate-${version}.tar.gz ${workdir}/../roles/python/files/\n"
      cp -vf ${workdir}/pip-packages-fate-${version}.tar.gz ${workdir}/../roles/python/files/
      ls -l ${workdir}/../roles/python/files/
      echo -e "\n"
      continue
    fi
    package_cp $pkname fate_flow
  done
fi

cd $workdir
rm -rf $fname $lname FATE_install_${version} ./temp pip-packages-fate-${version}.tar.gz
