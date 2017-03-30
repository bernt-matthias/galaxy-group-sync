import ldap
from bioblend import galaxy

import sys

# TODO check for mail changes

def galaxy_users( guc ):
    """
    get all galaxy users  
    @param guc galaxy user connector
    @return dict name -> id
    """
    gusers = guc.get_users()

    u2id = {}
    for u in gusers:
        u2id[ u['username'] ] = u['id']

    return u2id

def galaxy_group_members(guc, ggc, name):
    """
    get the members of a given group
    @param guc galaxy user connector
    @param ggc galaxy group connector
    @param name group name
    @return set of user names 
    """
    groups = ggc.get_groups( )
    for g in groups: 

        if g["name"] != name:
            continue

        return set([ guc.show_user( u["id"])["username"] for u in ggc.get_group_users( g["id"] ) ])
    return set()

def galaxy_groups( guc, ggc, name = None ):
    """
    get galaxy groups. if a user is given get only the groups where the user is
    member. otherwise get all groups.  where a user is member
    @param guc galaxy user connector
    @param ggc galaxy group connector
    @param name 
    @return dictionary group name -> group id
    """
    ggroup = ggc.get_groups()

    groups = {}
    for g in ggroup:
        if name == None:
            groups[ g['name'] ] = g['id'] 
        else:
            gusers = ggc.get_group_users( g['id'] )
            for gu in gusers: 
                user = guc.show_user( gu['id'] )
                if user['username'] == name:
                    groups[ g['name'] ] = g['id'] 

    return groups

def ldap_groups( lcon, gbase, mempro, namepro, gfilter, name ):
    """
    get the LDAP groups associated with a user
    @param lcon LDAP connection 
    @param gbase group search base 
    @param mempro ldap group property that is used to list group members
    @param namepro ldap group property that is used to specify group name 
    @param gfilter additional filter for groups
    @param name user name
    @return set of names of groups that contain the user
    """

    fltr = "(&({mempro}={user})({gfilter}))".format( mempro = mempro, user = name, gfilter = gfilter )
    lr = lcon.search_s(gbase, ldap.SCOPE_SUBTREE, fltr, [ namepro ])
    return set([ x[1][ namepro ][0] for x in lr ])

def ldap_group_members( lcon, gbase, mempro, namepro, gfilter, gname ):
    """
    get all members of a group 
    @param lcon LDAP connection 
    @param gbase group search base 
    @param mempro ldap group property that is used to list group members
    @param namepro ldap group property that is used to specify group name 
    @param gfilter additional filter for groups
    @param gname group name
    @return set of names of users that are in the group 
    """
    fltr = '(&({namepro}={name})({gfilter}))'.format( namepro = namepro, name = gname, gfilter = gfilter )

    lr = lcon.search_s(gbase, ldap.SCOPE_SUBTREE, fltr, [mempro])

    return set( lr[0][1][mempro] ) 

def ldap_users( lcon, ubase, ufilter ):
    """
    get users from ldap

    @param uri LDAP uri
    @param ubase base string for users
    @param ufilter filter for all allowed users
    @return users as set
    """
    lr = lcon.search_s(ubase, ldap.SCOPE_SUBTREE, ufilter, ['uid'])
    i = 0
    while i < len(lr):
        if lr[i][1] == {}:
            del lr[i]
        else:
            i+= 1
    return set( [ x[1]['uid'][0] for x in lr ] )

if __name__ == "__main__":

    import argparse
    import yaml

    parser = argparse.ArgumentParser(prog='galaxy-ldap-sync.py',
            description='Sync LDAP and galaxy users and groups.')

    parser.add_argument('--config', metavar='YML', type=file, help='configuration yml file', required=True)
    args = parser.parse_args()

    try:
        conf = yaml.load(args.config)
    except yaml.YAMLError as exc:
        sys.stderr.write("could not parse configuration")
        print(exc)
        sys.exit()
    
    # connect to galaxy and LDAP
    gi = galaxy.GalaxyInstance(url=conf["galaxyuri"], key=conf["galaxyapikey"])
    ggc = galaxy.groups.GroupsClient( gi )
    guc = galaxy.users.UserClient(gi)
    lcon = ldap.initialize( conf["ldapuri"] )

    # get LDAP users
    lusers = ldap_users( lcon, conf["ldapuserbase"], conf["ldapuserfilter"] )

    # get galaxy users
    gusers = galaxy_users( guc )

    # check for galaxy users that are not present in LDAP anymore
    for gu in gusers.keys():
        if not gu in lusers:
            try:
                delete_user(gusers[gu], purge=conf["purgeuser"])
                sys.stderr.write("user {user} has been deleted\n".format(user=gu))
            except NameError:
                sys.stderr.write("user {user} can be deleted (needs to be done MANUALLY)\n".format(user=gu))
            del gusers[gu]
    
    # get available galaxy groups
    ggroups = galaxy_groups( guc, ggc )

    # get necessary groups from ldap 
    # (all groups that include registered users from galaxy)
    lgroups = set()
    for gu in gusers:
        lgroups |= ldap_groups( lcon, conf["ldapgroupbase"], 
                    conf["ldapgroupmemberpro"],  conf["ldapgroupnamepro"],
                    conf["ldapgroupfilter"], gu )

    # remove all groups from galaxy that are not longer in galaxy
    for g in set(ggroups.keys()) - lgroups:
        ggc.update_group( ggroups[g] )  # remove user/role - group associations
        sys.stderr.write("group {group} not longer in LDAP (only user-role association have been removed)\n".format(group=g))
        del ggroups[g]

    # add groups to galaxy that are in LDAP 
    # (and associated to galaxy users but not present in galaxy)
    nggroups = {}
    for g in lgroups - set( ggroups.keys() ):
        ng = ggc.create_group( g )
        ggroups[ g ] = ng['id']
        sys.stderr.write("group {group} added)\n".format(group=g))
        
    # update group user associations for all galaxy groups 
    for gg in ggroups:
        # get all LDAP users in the group 
        lmem = ldap_group_members( lcon, conf["ldapgroupbase"], 
                conf["ldapgroupmemberpro"], conf["ldapgroupnamepro"], 
                conf["ldapgroupfilter"] , gg )
        # get common users 
        newmem = lmem & set(gusers.keys())
        
        # get current users (for reporting changes)
        gmem = galaxy_group_members( guc, ggc, gg )

        tmp = set(newmem) - gmem
        if len(tmp) > 0:
            sys.stderr.write("adding to group {group} <- {users}\n".format(group=gg, users = ",".join(tmp) ))
        tmp = gmem - set(newmem)
        if len(tmp) > 0:
            sys.stderr.write("delete from group {group} <- {users}\n".format(group=gg, users = ",".join(tmp) ))

        # remove the current users of the group 
        # (update_group seems to be buggy at the moment: lead to duplicates of
        # user-group associations)
        for m in gmem: 
            ggc.delete_group_user( ggroups[gg], gusers[m])

        # add new members as in ldap (before: and translate to user ids)
        newmem = [ gusers[x] for x in newmem ]
        ggc.update_group( ggroups[gg], group_name=None, user_ids=newmem )


# def galaxy_add_group( ggc, gname, ggroups ):
#     """
#     
#     """
#     try:
#         g = ggc.create_group( gname )
#     except:
#         return 
# 
#     ggroups[ gname ] = g['id']
# def galaxy_remove_user_group( guc, gcc, uid, gid ):
#     """
#     remove a galaxy user from a group
#     """
# 
#     sys.stderr.write( "\tremove user %s from group %s\n"%(
#         guc.show_user(uid)["username"], 
#         gcc.show_group(gid)["name"]) )
#     gcc.delete_group_user(gid, uid)

# def galaxy_remove_user(guc, uid):
#     """
#     remove a galaxy user 
#     """
#     sys.stderr.write( "\tremove user %s MANUALLY!!!\n"%(guc.show_user(uid)["username"]) )
#     # guc.delete_user(uid) 

# def is_ldap_user( lcon, ubase, name ):
#     """
#     check if a given user is present in ldap
#     """
#     lr = lcon.search_s(ubase, ldap.SCOPE_SUBTREE,'(uid=%s)'%name, ['uid', 'cn','mail'])
#     lusers = [ x[1] for x in lr ]
# 
#     if len(lusers) == 0:
#         return False
#     elif len(lusers) == 1:
#         return True
#     else:
#         raise Exception( "LDAP user %s found multiple times"%name )
