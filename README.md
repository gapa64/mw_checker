# MW Checker
MW Checker script is the simple solution to control hosts reachability before and after maitanence window, and identify hosts which lost reachability.
The script may be treated as the most trivial and lightweight monitoring system.


###Install
The script requires the only one external library which is the  [Netconf Client](https://github.com/ncclient/ncclient) and should work with any ncclient version.
The script could simply copy and pasted as a single file.
However the generic install procedure is the following
```bash
git clone https://github.com/gapa64/mw_checker
pip3 install -r requirements.txt
```

###Script Workflow
- MW checker fetches ARP table from a router to figure out what the hosts at least persist in the Network, and store this information in SQLite database
- Then the script pings the hosts from the ARP table and stores the results in the database as a pre-check table
- Once a maintenance window is finished user starts the script, to perform a post-check procedure. 
- The script pings reachable hosts from the pre-check table and stores these results in the SQLite database as a post-check table.
- After pings, the script fetches the ARP table from a box just for reference
- The Third phase is report generation. The script compares particular pre-check and post-check tables displays summary statistics, and lost hosts




##How to use
### Quick start
The for the most simple scenario with the default parameters
```bash

```

###Detailed description
###Precheck Operations

- Specify router as a positional argument to perform MW check procedures
- Use help at any stage of script usage, to get more details on what to do next

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

- Select a task  PING\ARP or get all in one command
- Sometimes it could be helpful to separate ARP and PING tasks for separated actions

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
- By default, –-user is the only mandatory argument for precheck, which is required to login to the router and fetch the ARP table.
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
  --ifl IFL    Set ifl interface which hosts to ping, use * for patterns, use _ as placeholder for pattern. examples: ge-_/0/1* (1/0/1, 2/0/1)ge-1/1/1* (1/1/1.100, 1/1/1.101
```



###Postchek Operations

###Report Operations

### Author
[Sergey K](https://github.com/gapa64)