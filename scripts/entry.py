#!/usr/bin/env python
# This script takes command line options and
# starts up mysqld

########################################################################################################################
# LIBRARY IMPORT                                                                                                       #
########################################################################################################################
# Import required libaries
import sys, os, pwd, grp  # OS Libraries
import argparse  # Parse Arguments
from subprocess import Popen, PIPE, STDOUT, call
# Open up a process

# Important required templating libarires
from jinja2 import Environment as TemplateEnvironment, \
    FileSystemLoader, Template
# Import the jinja2 libaries required by this script
from jinja2.exceptions import TemplateNotFound
# Import any exceptions that are caught by the Templates section

# Specific to to this script
from IPy import IP
from shutil import copyfile
import MySQLdb


# Functions
def isIP(address):
    try:
        IP(address)
        ip = True
    except ValueError:
        ip = False
    return ip


# Variables/Consts
mysql_path = '/var/lib/mysql'
mysql_init_check_file = mysql_path + '/ibdata1'
mysql_user = 'mysql'
mysql_group = 'mysql'
mysql_my_cnf = '/etc/mysql/my.cnf'
mysql_default_cnf = '/usr/share/mysql/my-default.cnf'
first_run = False

########################################################################################################################
# ARGUMENT PARSER                                                                                                      #
# This is where you put the Argument Parser lines                                                                      #
########################################################################################################################
# A minimum of 2 positional arguments required:
# rep_addr - The replication IP address of this node in the cluster
# member_addr - Replication IP address(es) of other member(s) of the cluster
# These are used to create the wsrep.cnf file used by wsrep for write synchronous replication
argparser = argparse.ArgumentParser(description='Run a docker container containing a MySQL wsrep Instance')

argparser.add_argument('rep_addr',
                       action='store',
                       help='The replication IP address for this node in the cluster')

argparser.add_argument('member_addr',
                       action='store',
                       nargs='+',
                       help='Replication IP address(es) for other member(s) of the cluster')

argparser.add_argument('--cluster-name', '-c',
                       action='store',
                       nargs='?',
                       help='The MySQL wsrep cluster name, "DBCluster"')

argparser.add_argument('--rep-user', '-u',
                       action='store',
                       nargs='?',
                       help='The MySQL wsrep replication user, "wsrep_sst-user"')

argparser.add_argument('--rep-pass', '-p',
                       action='store',
                       nargs='?',
                       help='The password for the MySQL wsrep replication user, "changeme"')

argparser.add_argument('--root-pass', '-P',
                       action='store',
                       nargs='?',
                       help='The password for the MySQL wsrep root user, "changeme2"')

argparser.add_argument('--mon-user', '-m',
                       action='store',
                       nargs='?',
                       help='The MySQL monitor user, "clustercheckuser"')

argparser.add_argument('--mon-pass', '-M',
                       action='store',
                       nargs='?',
                       help='The password for the MySQL monitor user, "clustercheckpassword"')

argparser.add_argument('--max-connections', '-C',
                       action='store',
                       type=int,
                       nargs='?',
                       help='The maximum number of open connections to MySQL, "256"')

argparser.add_argument('--boot-strap-cluster', '-b',
                       action='store_true',
                       help='Boot strap the cluster, run mysqld with --wsrep-new-cluster')

try:
    args = argparser.parse_args()
except SystemExit:
    sys.exit(0)  # This should be a return 0 to prevent the container from restarting.

########################################################################################################################
# ARGUMENT VERIRIFCATION                                                                                               #
# This is where you put any logic to verify the arguments, and failure messages                                        #
########################################################################################################################
#
# Check that rep_addr is a valid IP address
if not isIP(args.rep_addr):
    print "The argument %s must be a valid IP address" % args.rep_addr
    sys.exit(0)  # This should be a return 0 to prevent the container from restarting.

# Check that other cluster addresses are valid
for addr in args.member_addr:
    if not isIP(addr):
        print "The argument %s must be a valid IP address" % addr
        sys.exit(0)  # This should be a return 0 to prevent the container from restarting.

# If no value passed to cluster-name then warn that default value will be used
cluster_name = args.cluster_name
if cluster_name is None:
    print "Warning! Default value of DBCluster being used for the MySQL wsrep cluster name"
    cluster_name = 'DBCluster'

# If no value passed to rep-user then warn that default value will be used
rep_user = args.rep_user
if rep_user is None:
    print "Warning! Default value of wsrep_sst-user being used for the wsrep replication user"
    rep_user = 'wsrep_sst-user'

# If no value passed to rep-pass then warn that default value will be used
rep_pass = args.rep_pass
if rep_pass is None:
    print "Warning! Default value of changeme being used for the wsrep replication user password"
    rep_pass = 'changeme'

# If no value passed to mon-user then warn that default value will be used
mon_user = args.mon_user
if mon_user is None:
    print "Warning! Default value of clustercheckuser being used for the MySQL monitor user"
    mon_user = 'clustercheckuser'

# If no value passed to mon-pass then warn that default value will be used
mon_pass = args.mon_pass
if rep_pass is None:
    print "Warning! Default value of clustercheckpassword being used for the MySQL monitor user password"
    mon_pass = 'clustercheckpassword'

# If no value passed to root-pass then warn that default value will be used
root_pass = args.root_pass
if root_pass is None:
    print "Warning! Default value of changeme2 being used for the MySQL root user password"
    root_pass = 'changeme2'

# If no value passed to max-connections then warn that default value will be used
max_connections = args.max_connections
if max_connections is None:
    print "Warning! Default value of 256 being used for the maximum number of open connections for  MySQL"
    max_connections = '256'

########################################################################################################################
# Variables                                                                                                            #
# Construct Variables from arguments passed                                                                            #
########################################################################################################################
# Create list of cluster hosts from replication address and the other member address(es)
cluster_hosts = [args.rep_addr] + args.member_addr
# Sort this list by IP address
for i in range(len(cluster_hosts)):
    cluster_hosts[i] = "%3s.%3s.%3s.%3s" % tuple(cluster_hosts[i].split("."))
cluster_hosts.sort()
for i in range(len(cluster_hosts)):
    cluster_hosts[i] = cluster_hosts[i].replace(" ", "")
# Define value for wsrep_cluster_address in wsrep.cnf
cluster_addr = "gcomm://" + ','.join(cluster_hosts)

########################################################################################################################
# Initialize MySQL on first run                                                                                        #
########################################################################################################################
# If ibdata1 does not exist under the mysql path then this is the first time the container has been run
# so mysql_install_db needs to be run to initialize the DB using the volume mounted from a directory on the host
# We also set up the replication DB user and the root DB user password
# Once run, this does not need to run again for the life of the container (assuming the DB data mount does not get blatted!)
if not os.path.isfile(mysql_init_check_file):
    print "No existing databases found under %s" % mysql_path
    first_run = True
    # Flush anything on the buffer
    sys.stdout.flush()
    # Reopen stdout as unbuffered. This will mean log messages will appear as soon as they become available.
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
    if not os.path.isfile(mysql_default_cnf):
        copyfile(mysql_my_cnf, mysql_default_cnf)

    print "Creating initial system tables for MySQL"
    # Initialize system tables
    call(["/usr/bin/mysql_install_db"])

    uid = pwd.getpwnam(mysql_user).pw_uid
    gid = grp.getgrnam(mysql_group).gr_gid
    # DB path
    for root, dirs, files in os.walk(mysql_path):
        for name in dirs:
            dirname = os.path.join(root, name)
            os.chown(dirname, uid, gid)
        for name in files:
            fname = os.path.join(root, name)
            os.chown(fname, uid, gid)

    call(["/etc/init.d/mysql", "start"])

    print "Creating replication and monitor DB users and setting password for root DB user"
    # Open database connection
    host = 'localhost'
    user = 'root'
    location = '%'
    db = MySQLdb.connect(host, user)

    # Prepare a cursor object using cursor method
    cursor = db.cursor()

    try:
        # Set wsrep_on to OFF
        wsrep_on_off = "SET wsrep_on=OFF"
        results = cursor.execute(wsrep_on_off)
        print "Setting wsrep_on to OFF returned %s" % results

        # Remove user accounts with empty user names
        remove_user_accounts = "DELETE FROM mysql.user WHERE user=''"
        results = cursor.execute(remove_user_accounts)
        print "Removing MySQL user accounts with empty user names returned %s" % results

        # Grant privileges to replication user
        rep_user_privs = "GRANT ALL ON *.* TO '%s'@'%s' IDENTIFIED BY '%s'" % (rep_user, location, rep_pass)
        results = cursor.execute(rep_user_privs)
        print "Granting privlieges to MySQL replication user %s returned %s" % (rep_user, results)

        # Grant privileges to monitor user
        mon_user_privs = "GRANT PROCESS on *.* TO '%s'@'%s' IDENTIFIED BY '%s'" % (mon_user, location, mon_pass)
        results = cursor.execute(mon_user_privs)
        print "Granting privlieges to MySQL monitor user %s returned %s" % (mon_user, results)

        # Grant privileges to root user including the Grant privilege
        root_user_pass = "GRANT ALL ON *.* TO '%s'@'%s' IDENTIFIED BY '%s' with GRANT OPTION" % (
        user, location, root_pass)
        results = cursor.execute(root_user_pass)
        print "Granting privlieges to MySQL %s user returned %s" % (user, results)

    except MySQLdb.Error, e:
        print e
        sys.exit(0)  # This should be a return 0 to prevent the container from restarting

    # Close cursor
    cursor.close
    # Close connection
    db.close

    # Stop MySQL
    call(["/etc/init.d/mysql", "stop"])

########################################################################################################################
# TEMPLATES                                                                                                            #
# This is where you manage any templates                                                                               #
########################################################################################################################
# Configuration Location goes here
template_location = '/mysql-templates'

# Create the template list
template_list = {}

# Templates go here
### wsrep.cnf ###
template_name = 'wsrep.cnf'
template_dict = {'context': {  # Substitutions to be performed
    'cluster_name': args.cluster_name,
    'cluster_addr': cluster_addr,
    'rep_addr': args.rep_addr,
    'rep_user': args.rep_user,
    'rep_pass': args.rep_pass,
},
    'path': '/etc/mysql/conf.d/wsrep.cnf',
    'user': 'root',
    'group': 'root',
    'mode': 0644}
template_list[template_name] = template_dict

### my.cnf ###
template_name = 'my.cnf'
template_dict = {'context': {  # Substitutions to be performed
    'max_connections': args.max_connections,
},
    'path': '/etc/mysql/my.cnf',
    'user': 'root',
    'group': 'root',
    'mode': 0644}
template_list[template_name] = template_dict

# Load in the files from the folder
template_loader = FileSystemLoader(template_location)
template_env = TemplateEnvironment(loader=template_loader,
                                   lstrip_blocks=True,
                                   trim_blocks=True,
                                   keep_trailing_newline=True)

# Load in expected templates
for template_item in template_list:
    # Attempt to load the template
    try:
        template_list[template_item]['template'] = template_env.get_template(template_item)
    except TemplateNotFound as e:
        errormsg = "The template file %s was not found in %s (returned %s)," % template_item, template_list, e
        errormsg += " terminating..."
        print errormsg
        sys.exit(0)  # This should be a return 0 to prevent the container from restarting

    # Attempt to open the file for writing
    try:
        template_list[template_item]['file'] = open(template_list[template_item]['path'], 'w')
    except IOError as e:
        errormsg = "The file %s could not be opened for writing for template" % template_list[template_item]['path']
        errormsg += " %s (returned %s), terminating..." % template_item, e
        print errormsg
        sys.exit(0)  # This should be a return 0 to prevent the container from restarting

    # Stream
    try:
        template_list[template_item]['render'] = template_list[template_item]['template']. \
            render(template_list[template_item]['context'])

        # Submit to file

        template_list[template_item]['file'].write(template_list[template_item]['render'].encode('utf8'))
        template_list[template_item]['file'].close()
    except:
        e = sys.exc_info()[0]
        print "Unrecognised exception occured, was unable to create template (returned %s), terminating..." % e
        sys.exit(0)  # This should be a return 0 to prevent the container from restarting.

    # Change owner and group
    try:
        template_list[template_item]['uid'] = pwd.getpwnam(template_list[template_item]['user']).pw_uid
    except KeyError as e:
        errormsg = "The user %s does not exist for template %s" % template_list[template_item]['user'], template_item
        errormsg += "(returned %s), terminating..." % e
        print errormsg
        sys.exit(0)  # This should be a return 0 to prevent the container from restarting

    try:
        template_list[template_item]['gid'] = grp.getgrnam(template_list[template_item]['group']).gr_gid
    except KeyError as e:
        errormsg = "The group %s does not exist for template %s" % template_list[template_item]['group'], template_item
        errormsg += "(returned %s), terminating..." % e
        print errormsg
        sys.exit(0)  # This should be a return 0 to prevent the container from restarting

    try:
        os.chown(template_list[template_item]['path'],
                 template_list[template_item]['uid'],
                 template_list[template_item]['gid'])
    except OSError as e:
        errormsg = "The file %s could not be chowned for template" % template_list[template_item]['path']
        errormsg += " %s (returned %s), terminating..." % template_item, e
        print errormsg
        sys.exit(0)  # This should be a return 0 to prevent the container from restarting

    # Change permissions
    try:
        os.chmod(template_list[template_item]['path'],
                 template_list[template_item]['mode'])
    except OSError as e:
        errormsg = "The file %s could not be chmoded for template" % template_list[template_item]['path']
        errormsg += " %s (returned %s), terminating..." % template_item, e
        print errormsg
        sys.exit(0)  # This should be a return 0 to prevent the container from restarting

########################################################################################################################
# Fix permissons on /var/lib/mysql                                                                                     #
########################################################################################################################
uid = pwd.getpwnam(mysql_user).pw_uid
gid = grp.getgrnam(mysql_group).gr_gid
# DB path
for root, dirs, files in os.walk(mysql_path):
    for name in dirs:
        dirname = os.path.join(root, name)
        os.chown(dirname, uid, gid)
    for name in files:
        fname = os.path.join(root, name)
        os.chown(fname, uid, gid)

########################################################################################################################
# SPAWN CHILD                                                                                                          #
########################################################################################################################
# Spawn the child
child_path = ['/usr/sbin/mysqld']
if args.boot_strap_cluster is True:
    child_path.append('--wsrep-new-cluster')

if first_run is False:
    # Flush anything on the buffer
    sys.stdout.flush()
    # Reopen stdout as unbuffered. This will mean log messages will appear as soon as they become avaliable.
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

child = Popen(child_path, stdout=PIPE, stderr=STDOUT, shell=True)

# Output any log items to Docker
for line in iter(child.stdout.readline, ''):
    sys.stdout.write(line)

# If the process terminates, read its errorcode and return it
sys.exit(child.returncode)
