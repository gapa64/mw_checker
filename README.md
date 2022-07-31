# MW Checker
MW Checker script is the simple solution to control hosts reachability before and after maitanence window, and identify hosts which lost reachability on Juniper routers.
The script may be treated as the most trivial and lightweight monitoring system.

###Install
The script requires the only one external library which is the  [Netconf Client](https://github.com/ncclient/ncclient) and should work with any ncclient version.
Please get more details on the Ncclient library requirements.  
The script could simply copy and pasted as a single file.  
However the generic install procedure is the following.
```bash
git clone https://github.com/gapa64/mw_checker
#install Ncclient by:
pip install ncclient
#or
pip3 install -r requirements.txt
```
### Script Workflow
- MW checker fetches ARP table from a router to figure out what the hosts at least persist in the Network, and store this information in SQLite database
- Then the script pings the hosts from the ARP table and stores the results in the database as a pre-check table
- Username for router connection is passed as argument --user, password is inserted from the keyboard manually
- Once a maintenance window is finished user starts the script, to perform a post-check procedure. 
- The script pings reachable hosts from the pre-check table and stores these results in the SQLite database as a post-check table.
- After pings, the script fetches the ARP table from a box just for reference
- The Third phase is report generation. The script compares particular pre-check and post-check tables displays summary statistics, and lost hosts
## How to use
## Quick start
The for the most simple scenario with the default parameters
```bash
python3 mw_checker.py <router> precheck all --user <user_name>
python3 mw_checker.py <router> postcheck all --user <user_name>
python3 mw_checker.py report
```
## Detailed description
### Precheck Operations
Specify router as a positional argument to perform MW check procedures  
Use help at any stage of script usage, to get more details on what to do next

```bash
python3 mw_checker.py --help
usage: mw_checker.py [-h] router {precheck,postcheck,report} ...
positional arguments:
  router                Set router for analysis
  {precheck,postcheck,report}
    precheck            Run precheck tasks
    postcheck           Run postcheck tasks
    report              Run report tasks
optional arguments:
  -h, --help            show this help message and exit
```

Select a task  PING\ARP or get all in one command.  
Sometimes it could be helpful to use ARP and PING tasks as separated actions

```bash
python3 mw_checker.py 10.10.10.1 precheck --help
usage: mw_checker.py router precheck [-h] {arp,ping,all} ...
positional arguments:
  {arp,ping,all}
    arp           fetch precheck arp table
    ping          run pings for previously fetched arp
    all           run all precheck tests

optional arguments:
  -h, --help      show this help message and exit
```
By default, –-user is the only mandatory argument for precheck, which is required to login to the router and fetch the ARP table.
- The Script creates SQLite file db_{router}.db to store pre-checks and post-checks results.
- By default, the script fetches the entire Arp table and performs ping checks for each host in it
- By default, the script stores all the Precheck results into table precheck_0
- --dest (integer) argument allows user to store pre-check results into alternative table precheck_1, precheck_2 e.t.c

```bash
python3 mw_checker.py 10.10.10.1 precheck all --help
usage: mw_checker.py router precheck all [-h] --user USER [--dest DEST] [--irb IRB] [--ifl IFL]
optional arguments:
  -h, --help   show this help message and exit
  --user USER  Set user to fetch data from box
  --dest DEST  ID of precheck table
  --irb IRB    Set ifl interface which hosts to ping, use * for patterns, use _ as placeholder for pattern. examples: irb.1__1* (irb.1991, irb.19911) irb.101* (irb.1011, irb.1012)
  --ifl IFL    Set ifl interface which hosts to ping, use * for patterns, use _ as placeholder for pattern. examples: ge-_/0/1* (1/0/1, 2/0/1)ge-1/1/1* (1/1/1.100, 1/1/1.101)
```
System allows filter which interface to ping by manipulations with the --irb and --ifl argumnets.  
This arguments refer to the Interface column in the ARP table.  
It allows users to perform distinct pre-checks for distinct interfaces, or just to limit the hosts which the host need to ping
```bash
root@r1-mx-1_RE> show arp no-resolve 
MAC Address       Address         Interface         Flags
56:68:a3:1e:06:82 10.1.12.2       ge-0/0/0.0               none
56:68:a3:1e:06:4a 10.1.14.4       ge-0/0/3.0               none
56:68:a3:1e:08:05 10.49.225.105   fxp0.0                   none
00:00:00:11:11:10 10.52.10.6      irb.10 [ge-0/0/2.10]     none
00:00:00:11:11:10 10.52.10.7      irb.10 [ge-0/0/2.10]     none
```
The * sing at the end of passed value inform script that value should be treated as pattern, and translated into SQL operator “LIKE %pattern%”,  e,g for the  above command the following host from arp table will selected for ping checks
```bash
python3 mw_checker.py 10.10.10.1 precheck all –-user root –-irb irb.5* --dest 5 
SELECT arp_ip from precheck_5 where arp_irb like ”%irb.5%” ;  
# e.g. (irb.5, irb.51, irb.500 e.t.c)
```

SQLite also support placeholders _ in patterns.  
Lack of * informs script that only host bound to particular interface should be chosen for ping checks e.g:
```bash
SELECT arp_ip from precheck_5 where arp_irb=“irb.5” ;
```
In case of a mistake and an attempt to store a second copy of the ARP table into the same precheck table, the script raises an alarm.  
Use another precheck ID to avoid this
```bash
python3 mw_checker.py 10.10.10.1 precheck all --dest 10 --user root --irb irb.20
Password: 
2021_06_15_06_52_20: Connecting to router 10.10.10.1
Traceback (most recent call last):
  File "mw_checker.py", line 57, in execute_many
    cursor.execute(sql_request, parameters)
sqlite3.IntegrityError: UNIQUE constraint failed: precheck_10.arp_ip, precheck_10.arp_mac, precheck_10.arp_irb

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "mw_checker.py", line 570, in <module>
    arguments.function(mwc, arguments)
  File "mw_checker.py", line 391, in precheck_all
    precheck_arp(mwc_object, args)
  File "mw_checker.py", line 379, in precheck_arp
    mwc_object.fetch_precheck_arp(username=args.user,
  File "mw_checker.py", line 204, in fetch_precheck_arp
    self.execute_many(sql_querry, arp_entries)
  File "mw_checker.py", line 60, in execute_many
    raise MwcheckerError(error)
__main__.MwcheckerError: UNIQUE constraint failed: precheck_10.arp_ip, precheck_10.arp_mac, precheck_10.arp_irb
```
In case of a mistake and attempt to store PING results for the same host into the same precheck table, the action is ignored.  
The initial ping result is not overwritten. Use another precheck ID to save distinct ping results for the same host

The following listing illustrates example of precheck phase execution
```bash
python3 mw_checker.py 10.10.10.1 precheck all --irb irb.6* --dest 6 --user root
2021_06_09_02_44_05: Connecting to router 10.10.10.1
2021_06_09_02_44_08: Starting to ping hosts connected to router 10.10.10.1
ping -c 2 10.52.60.5 -w 1
ping -c 2 10.52.60.6 -w 1
ping -c 2 10.52.60.7 -w 1
ping -c 2 10.52.60.8 -w 1
```

### Postchek Operations

- Post-check is a validation of a particular precheck table
- Script selects the hosts reachable at a precheck phase and pings them.
- By default, the script selects reachable hosts from the precheck_0 table and stores a result in the postcheck_0 table
- --source (integer) argument should be used to choose a particular precheck table
- --dest (integer) argument allows user to store post-check results into alternative table postcheck_1, postcheck_2 e.t.c

```bash
python3 mw_checker.py 10.10.10.1 postcheck all --help 
usage: mw_checker.py router postcheck all [-h] --user USER [--source SOURCE] [--dest DEST]

optional arguments:
  -h, --help       show this help message and exit
  --user USER      Set user to fetch data from box
  --source SOURCE  ID of source PRE CHECK Table
  --dest DEST      ID of destination POST check table
```
Example bellow illustrates the post-check tasks for the hosts within precheck_6 table which were reachable at precheck phase

```bash
python3 mw_checker.py 10.10.10.1 postcheck all --user root --source 6 --dest 6
Password: 
2021_06_09_02_57_36: Starting to ping hosts connected to router 10.10.10.1
ping -c 2 10.52.60.5 -w 1
ping -c 2 10.52.60.6 -w 1
ping -c 2 10.52.60.7 -w 1
2021_06_09_02_57_39: Connecting to router 10.10.10.1
```

In case of mistake  and attempt to store a second copy of PING result  within the same post check table, script raises an alarm.  
Use another postcheck ID to avoid this sittuation

```bash
2021_06_15_06_55_41: Starting to ping hosts connected to router 10.10.10.1
ping -c 2 10.52.20.10 -w 1
Traceback (most recent call last):
  File "mw_checker.py", line 57, in execute_many
    cursor.execute(sql_request, parameters)
sqlite3.IntegrityError: UNIQUE constraint failed: postcheck_10.ip
```
In case of mistake and attempt to store a second copy of ARP table into the same post-check table, data is updated. 


### Report Operations
- Report Compares 1 pre-check and 1 post-check table
- By-default script compares precheck_0 and postcheck_0 
- User may specify which particular tables should be compared
```bash
python3 mw_checker.py 10.10.10.1 report --help
usage: mw_checker.py router report [-h] [--precheck PRECHECK] [--postcheck POSTCHECK]
optional arguments:
  -h, --help            show this help message and exit
  --precheck PRECHECK   ID of source PRE CHECK Table
  --postcheck POSTCHECK
                        ID of destination POST check table
```
- Provides summary statistics of host reachable at pre-check and post-check phases
```bash
python3 mw_checker.py 10.10.10.1 report --precheck 5 --postcheck 5 
precheck_reachable 110
precheck_unreachable 1
precheck_arps 111
postcheck_reachable 106
postcheck_unreachable 4
postcheck_arps 110
```
- Provides detailed report of host which were reachable at a pre-check phase and became  unreachable at a post-check  phase
- Detailed report appears as csv files
```bash
-rw-r--r-- 1 root root    524 Jun  9 03:27 db_10.10.10.1.db_precheck_5_postcheck_5.csv
```
Outptput file example  

| pre_arp | pre_mac | pre_irb | pre_ifl | pre_ping | post_arp | post_mac | post_irb | post_ifl | post_ping
| --- | --- | --- | --- | --- |--- | --- | --- | --- | --- |
| 10.52.50.12 | 00:00:00:11:11:50 | irb.50 | ge-0/0/2.50 | OK | 10.52.50.12 | 00:00:00:11:11:50 | irb.50 | ge-0/0/2.50 | FAILED
| 10.52.50.13 | 00:00:00:11:11:50 | irb.50 | ge-0/0/2.50 | OK | 10.52.50.13 | 00:00:00:11:11:50 | irb.50 | ge-0/0/2.50 | FAILED
| 10.52.50.14 | 00:00:00:11:11:50 | irb.50 | ge-0/0/2.50 | OK | 10.52.50.14 | 00:00:00:11:11:50 | irb.50 | ge-0/0/2.50 | FAILED
| 10.52.50.15 | 00:00:00:11:11:50 | irb.50 | ge-0/0/2.50 | OK | 10.52.50.15 | 00:00:00:11:11:50 | irb.50 | ge-0/0/2.50 | FAILED

### Author
[Sergey K](https://github.com/gapa64)