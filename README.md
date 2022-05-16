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

