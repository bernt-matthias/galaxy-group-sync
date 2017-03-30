Small python script to sync groups and users from a LDAP server to a galaxy server,  
for environments where galaxy authentication is via LDAP. 

* Users that are not present in LDAP are deleted.
* For all galaxy users the user-group associations are taken from LDAP. therefore: 
** Groups not present in galaxy are created
** Groups without users are deleted 

Note that, user and group deletion does not delete but only sets the deleted flag. 
All variables are stored in config.yml. 

__Usage:__ 

* Make sure to configure config.yml (use the sample as template). 
* Call via the shell script with a single parameter giving the root directory of the 
galaxy instance (another instance should also work -- the python script only uses the 
venv to get bioblend). 


