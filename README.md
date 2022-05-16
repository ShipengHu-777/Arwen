# Arwen
We provide ansible scripts to automatically deploy the federated cluster adopted in the experiments in a convenient manner.

First, execute the following command to clean old configuration and init new configuration. 
```
sh ./tools/init.sh prod
```

Then change the /environments/prod/hosts file to match the actual ip address of tested machines. 

To specify the roles of each machine, files in /varfiles/prod folder match the ip address to their role. 

Then, run the following command to install the environment.
```
sh ./boot.sh prod -D 
```

If you already have installed FATE v1.6, you can skip above installation process and directly use `basic_algorithms` and `boosting` to replace the original folders under the path of `/fate/python/federatedml/ensemble` for our optimizations to be applied. Since our system is implemented based on FATE, the original users can apply our optimizations very conveniently without making major changes to their system.
