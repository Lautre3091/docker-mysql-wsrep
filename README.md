# docker-mysql-wsrep
Galera Cluster for MySQL is a true Multimaster Cluster based on synchronous replication.  Galera Cluster is an easy-to-use, high-availability solution, which provides high system uptime, no data loss and scalability for future growth.

More details can be found at the Galera Cluster website at http://galeracluster.com

This Docker build builds on top of a Ubuntu image to provide a working MySQL instance patched for wsrep (Write Set REPlication) which can be used to form a cluster.

Under the most basic usage you will make sure this container is operating in the same network (i.e. same machine) as the cluster it will be connected to. You can utilise <a href="https://github.com/weaveworks/weave">Weave</a> and other technologies to distribute multiple nodes over multiple hosts using a dedicated MySQL wsrep replication network (This is recommeded to provide true redundancy).  You will provide the replication IP address for this node in the cluster and for other member(s) of the cluster.  It is recommend you use restart on-failure.

    docker run -d --restart=on-failure solnetcloud/mysql-wsrep:latest 172.20.20.1 172.20.20.2 172.20.20.3

For the first node in a cluster you should tell it to bootstrap the cluster using --boot-strap-cluster

    usage: entry [-h] [--cluster-name [CLUSTER_NAME]] [--rep-user [REP_USER]]
                 [--rep-pass [REP_PASS]] [--root-pass [ROOT_PASS]]
                 [--mon-user [MON_USER]] [--mon-pass [MON_PASS]]
                 [--boot-strap-cluster]
                 rep_addr member_addr [member_addr ...]

    Run a docker container containing a MySQL Galera Instance

    positional arguments:
      rep_addr              The IP address for this node in cluster
      member_addr           IP address(es) for other member(s) of the cluster

    optional arguments:
      -h, --help            show this help message and exit
      --cluster-name [CLUSTER_NAME], -c [CLUSTER_NAME]
                            The MySQL Galera cluster name, "DBCluster"
      --rep-user [REP_USER], -u [REP_USER]
                            The MySQL Galera replication user, "wsrep_sst-user"
      --rep-pass [REP_PASS], -p [REP_PASS]
                            The password for the MySQL Galera replication user,
                            "changeme"
      --root-pass [ROOT_PASS], -P [ROOT_PASS]
                            The password for the MySQL Galera root user,
                            "changeme2"
      --mon-user [MON_USER], -m [MON_USER]
                            The MySQL monitor user, "clustercheckuser"
      --mon-pass [MON_PASS], -M [MON_PASS]
                            The password for the MySQL monitor user,
                            "clustercheckpassword"
      --boot-strap-cluster, -b
                            Boot strap the cluster, run mysqld with --wsrep-new-
                            cluster

Once you have another node in the cluster it is recommended to destroy the first container and recreate it without --boot-strap-cluster (or else on automatic restart it will form a new cluster leading to a split brain).  The initial set up of the cluster is designed to be orchestrated by a tool such as Puppet.  
