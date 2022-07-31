import argparse
import csv
import datetime as dt
import logging
import os
import re
import sqlite3
from getpass import getpass
from lxml import etree
from multiprocessing import Pool
from ncclient import manager
from time import sleep

logging.basicConfig(level=logging.INFO,
                    filename='mw_checker.log',
                    format='%(asctime)s, %(levelname)s, %(message)s')
logger = logging.getLogger(__name__)


class MwcheckerError(BaseException):
    pass


class DBHandler:
    def __init__(self, dbname):
        self.dbname = dbname

    def create_table(self, table_name, fields):
        try:
            with sqlite3.connect(self.dbname) as con:
                task = (f'CREATE TABLE IF NOT EXISTS '
                        f'{table_name} ({fields}) ')
                con.execute(task)
        except sqlite3.Error as error:
            logger.error(error, exc_info=True)

    def execute(self, sql_request, parameters=None):
        try:
            with sqlite3.connect(self.dbname) as con:
                con.row_factory = sqlite3.Row
                cursor = con.cursor()
                if parameters is not None:
                    cursor.execute(sql_request, parameters)
                else:
                    cursor.execute(sql_request)
                return cursor.fetchall()
        except sqlite3.Error as error:
            logger.error(error, exc_info=True)

    def execute_many(self, sql_request, parameters_deck):
        try:
            with sqlite3.connect(self.dbname) as con:
                cursor = con.cursor()
                for parameters in parameters_deck:
                    cursor.execute(sql_request, parameters)
        except sqlite3.IntegrityError as error:
            logger.error(error, exc_info=True)
            raise MwcheckerError(error)
        except sqlite3.Error as error:
            logger.error(error, exc_info=True)

    def execute_many_scripts(self, querry_list, parameters_deck):
        try:
            with sqlite3.connect(self.dbname) as con:
                cursor = con.cursor()
                for parameters in parameters_deck:
                    for querry in querry_list:
                        cursor.execute(querry, parameters)
        except sqlite3.Error as error:
            logger.error(error, exc_info=True)

    def get_many(self, sql_list):
        list_of_responses = []
        try:
            with sqlite3.connect(self.dbname) as con:
                con.row_factory = sqlite3.Row
                cursor = con.cursor()
                for querry in sql_list:
                    cursor.execute(querry)
                    result = cursor.fetchall()
                    list_of_responses.append(tuple(result))
            return list_of_responses
        except sqlite3.Error as error:
            logger.error(error, exc_info=True)


class Mwchecker(DBHandler):
    WORKERS_NUMBER = 8
    GET_ARP_RPC = etree.fromstring('<get-arp-table-information>'
                                   '<no-resolve/>'
                                   '</get-arp-table-information>')
    ARP_XPATH = '//arp-table-entry'
    ARP_IRB_IFL_PATTERN = re.compile(r'(?P<irb>irb\.\d+)\s+\[(?P<ifl>.+)\]')
    OUTPUT_TASKS = {
        'arp': GET_ARP_RPC,
    }
    CONDITION_EXPRESSION = '{field}{operator}{pattern}'
    PING_COMMAND = 'ping -c 2 {} -w 1'
    PING_PATTERN_STR = (r'\d+\s+bytes\s+from\s+'
                        r'(?P<host1>{})\:\s+'
                        r'icmp_seq=\d+\s+ttl=\d+\s+'
                        r'time=\d+.?\d+\s+ms')
    PRECHECK_DB_NAME = 'precheck_mwc'
    POSTCHECK_DB_NAME = 'postcheck_mwc'
    PRECHECK_FIELDS = ('arp_ip text , '
                       'arp_mac text, '
                       'arp_irb text, '
                       'arp_ifl text, '
                       'ping text,'
                       'PRIMARY KEY (arp_ip, arp_mac, arp_irb)')
    POSTCHECK_FIELDS = ('ip text PRIMARY KEY, '
                        'arp_ip text, '
                        'arp_mac text, '
                        'arp_irb text, '
                        'arp_ifl text, '
                        'ping text ')
    PRECHECK_ARP_SQL = ('INSERT INTO {} '
                        '(arp_ip, arp_mac, arp_ifl, arp_irb) '
                        'VALUES '
                        '(:arp_ip, :arp_mac, :arp_ifl, :arp_irb)')
    PRECHECK_PING_SQL = ('UPDATE {} SET ping=:ping '
                         'WHERE arp_ip=:arp_ip AND ping is NULL')
    GET_IP_SQL = 'SELECT DISTINCT arp_ip from {} '
    GET_PINGABLE_SQL = 'SELECT DISTINCT arp_ip FROM {} WHERE ping="OK"'
    POSTCEHCK_PING_SQL = 'INSERT into {} (ip, ping) VALUES (:arp_ip, :ping)'
    POST_UPDATE_ARP_SQL = ('UPDATE {db} SET '
                           'arp_ip=:arp_ip, arp_mac=:arp_mac,'
                           'arp_ifl=:arp_ifl, arp_irb=:arp_irb '
                           'WHERE ip=:arp_ip ')
    POST_INSERT_ARP_SQL = ('INSERT OR IGNORE INTO {db} '
                           '(arp_ip, arp_mac, arp_ifl, arp_irb) '
                           'SELECT :arp_ip, :arp_mac, :arp_ifl, :arp_irb '
                           'WHERE NOT EXISTS '
                           '(SELECT * from {db} where ip=:arp_ip or arp_ip=:arp_ip)')
    LOSTED_HOST_SQL = ('SELECT ' 
                       '{precheck}.arp_ip as pre_arp, '
                       '{precheck}.arp_mac as pre_mac, '
                       '{precheck}.arp_irb as pre_irb, '
                       '{precheck}.arp_ifl as pre_ifl, '
                       '{precheck}.ping as pre_ping, '
                       '{postcheck}.arp_ip as post_arp, '
                       '{postcheck}.arp_mac as post_mac, '
                       '{postcheck}.arp_irb as post_irb, '
                       '{postcheck}.arp_ifl as post_ifl, '
                       '{postcheck}.ping as post_ping '
                       'FROM '
                       '{precheck} '
                       'INNER JOIN {postcheck} ON '
                       '{precheck}.arp_ip = {postcheck}.ip '
                       'WHERE '
                       '{precheck}.ping = "OK" AND '
                       '{postcheck}.ping = "FAILED"')
    COUNT_REACHABLE_SQL = ('SELECT COUNT (ping) '
                           'as {parameter}_reachable '
                           'FROM {table} WHERE ping="OK"')
    COUNT_UNREACHABLE_SQL = ('SELECT COUNT (ping) '
                             'as {parameter}_unreachable '
                             'FROM {table} WHERE ping="FAILED"')
    COUNT_ALL_ARP_SQL = ('SELECT DISTINCT COUNT (arp_ip) ' 
                         'as {parameter}_arps FROM {table} '
                         'WHERE ping IS NOT NULL ')
    POST_ARP_UPSERT_SQL_SCRIPT = (POST_UPDATE_ARP_SQL,
                                  POST_INSERT_ARP_SQL)
    REPORT_PARAMETERS = (COUNT_REACHABLE_SQL,
                         COUNT_UNREACHABLE_SQL,
                         COUNT_ALL_ARP_SQL)

    def __init__(self, router):
        self.router = router
        self.dbname = 'db_{}.db'.format(router)

    def init_precheck_database(self, table_name):
        super().create_table(table_name, self.PRECHECK_FIELDS)

    def init_postcheck_database(self, table_name):
        super().create_table(table_name, self.POSTCHECK_FIELDS)

    def fetch_precheck_arp(self, username, password,
                           destination_table, port=22):
        from_box_data = self.get_frombox_data(username=username,
                                              password=password,
                                              port=port)
        arp_entries = self.parse_arp(input_xml=from_box_data['arp'])
        sql_querry = self.PRECHECK_ARP_SQL.format(destination_table)
        self.execute_many(sql_querry, arp_entries)

    def fetch_postcheck_arp(self, username, password,
                            destination_table, port=22):
        from_box_data = self.get_frombox_data(username=username,
                                              password=password,
                                              port=port)
        arp_entries = self.parse_arp(input_xml=from_box_data['arp'])
        query_list = []
        for querry in self.POST_ARP_UPSERT_SQL_SCRIPT:
            query_list.append(querry.format(db=destination_table))
        self.execute_many_scripts(query_list, arp_entries)

    def fetch_precheck_pings(self, table, irb=None, ifl=None):
        source_sql = self.GET_IP_SQL.format(table)
        conditions_sql = self.get_conditions_sql(arp_irb=irb, arp_ifl=ifl)
        if conditions_sql:
            source_sql += ' WHERE {} '.format(conditions_sql)
        dest_sql = self.PRECHECK_PING_SQL.format(table)
        self.fetch_pings(source_sql, dest_sql)

    def fetch_postcheck_pings(self, source_table, destination_table):
        source_sql = self.GET_IP_SQL.format(source_table)
        dest_sql = self.POSTCEHCK_PING_SQL.format(destination_table)
        conditions_sql = self.get_conditions_sql(ping='OK')
        if conditions_sql:
            source_sql += ' WHERE {} '.format(conditions_sql)
        self.fetch_pings(source_sql, dest_sql)

    def fetch_pings(self, source_sql, dest_sql):
        hosts_list = self.get_ip_address(source_sql)
        pings = self.get_pings_runner(hosts_list)
        self.execute_many(dest_sql, pings)

    def get_pings_runner(self, hosts_lists, workers=WORKERS_NUMBER):
        print('{}: Starting to ping hosts connected to '
              'router {}'.format(self.ttime(), self.router))
        if len(hosts_lists) // workers >= 2:
            with Pool(workers) as p:
                ping_results = p.map(self.pinger_worker, hosts_lists)
        else:
            ping_results = map(self.pinger_worker, hosts_lists)
        return ping_results

    def pinger_worker(self, host):
        ping_task = self.PING_COMMAND.format(host)
        print(ping_task)
        ping_output = os.popen(ping_task).read()
        ping_result = self.response_checker(ping_output, host)
        return {'arp_ip': host,
                'ping': ping_result}

    def response_checker(self, output, host):
        host_pattern = re.compile(self.PING_PATTERN_STR.format(host))
        for found in host_pattern.finditer(output):
            if found:
                return "OK"
        return "FAILED"

    def get_frombox_data(self, username, password, port=22):
        print('{}: Connecting to router {}'.format(self.ttime(), self.router))
        response = {}
        with manager.connect(host=self.router,
                             port=port,
                             username=username,
                             password=password,
                             hostkey_verify=False,
                             device_params={'name': 'junos'}) as mgr:
            sleep(1)
            for task, rpc_querry in self.OUTPUT_TASKS.items():
                response[task] = mgr.rpc(rpc_querry)
                sleep(1)
            return response

    def parse_arp(self, input_xml):
        all_arp_entries = input_xml.xpath(self.ARP_XPATH)
        parsed_entries = []
        for arp_entry in all_arp_entries:
            entry = {}
            entry['arp_ip'] = self.get_xpath(arp_entry, 'ip-address')
            entry['arp_mac'] = self.get_xpath(arp_entry, 'mac-address')
            interface = self.get_xpath(arp_entry, 'interface-name')
            parsed_interface = self.ARP_IRB_IFL_PATTERN.search(interface)
            if parsed_interface:
                entry['arp_ifl'] = parsed_interface.group('ifl')
                entry['arp_irb'] = parsed_interface.group('irb')
            else:
                entry['arp_ifl'] = interface
                entry['arp_irb'] = 'n_a'
            parsed_entries.append(entry)
        return parsed_entries

    def get_conditions_sql(self, **conditions):
        condition_list = []
        for field, pattern in conditions.items():
            if not field or not pattern:
                continue
            if pattern.endswith('*'):
                operator = ' LIKE '
                pattern = '"%{}%"'.format(pattern.rstrip('*'))
            else:
                operator = '='
                pattern = '"{}"'.format(pattern)
            expression = self.CONDITION_EXPRESSION.format(field=field,
                                                          operator=operator,
                                                          pattern=pattern)
            condition_list.append(expression)
        return ' AND '.join(condition_list)

    def get_ip_address(self, hosts_sql_querry):
        collumn = self.execute(sql_request=hosts_sql_querry)
        if not collumn:
            return ()
        return [row['arp_ip'] for row in collumn]

    def get_report(self, precheck='', postcheck=''):
        unreachable_sql = self.LOSTED_HOST_SQL.format(precheck=precheck,
                                                      postcheck=postcheck)
        sql_list = [unreachable_sql]
        tables = {'precheck': precheck,
                  'postcheck': postcheck}

        for stage, table in tables.items():
            for sql_template in self.REPORT_PARAMETERS:
                sql_query = sql_template.format(parameter=stage,
                                                table=table)
                sql_list.append(sql_query)

        result_list = self.get_many(sql_list)
        unreachable_hosts = result_list.pop(0)
        for result in result_list:
            for row in result:
                for field, value in dict(row).items():
                    print(field, value)
        out_file = '{db}_{pre}_{post}'.format(db=self.dbname,
                                              pre=precheck,
                                              post=postcheck)
        if unreachable_hosts:
            self.write_report(out_file, unreachable_hosts)
        else:
            print('no unreacheable hosts')

    def write_report(self, output, report):
        output += '.csv'
        fieldnames = report[0].keys()
        with open(output, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in report:
                writer.writerow(dict(row))

    @staticmethod
    def ttime():
        return dt.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")

    @staticmethod
    def get_xpath(xml, path, else_return='n_a', ignore_namespaces=False):
        if ignore_namespaces:
            path = './*[local-name() = "{}"]'.format(path)
        raw_result = xml.xpath(path)
        if not raw_result:
            return else_return
        if not raw_result[0].text:
            return else_return
        return raw_result[0].text.strip()


def precheck_arp(mwc_object, args):
    table = 'precheck_{}'.format(str(args.dest))
    password = getpass()
    mwc_object.init_precheck_database(table)
    mwc_object.fetch_precheck_arp(username=args.user,
                                  password=password,
                                  destination_table=table,
                                  port=args.port)


def precheck_ping(mwc_object, args):
    table = 'precheck_{}'.format(str(args.dest))
    mwc_object.fetch_precheck_pings(table=table,
                                    irb=args.irb,
                                    ifl=args.ifl)


def precheck_all(mwc_object, args):
    precheck_arp(mwc_object, args)
    precheck_ping(mwc_object, args)


def postcheck_ping(mwc_object, args):
    source_table = 'precheck_{}'.format(str(args.source))
    destination_table = 'postcheck_{}'.format(str(args.dest))
    mwc_object.init_postcheck_database(destination_table)
    mwc_object.fetch_postcheck_pings(source_table=source_table,
                                     destination_table=destination_table)


def postcheck_arp(mwc_object, args, password=None):
    table = 'postcheck_{}'.format(str(args.dest))
    if password is None:
        password = getpass()
    mwc_object.init_postcheck_database(table)
    mwc_object.fetch_postcheck_arp(username=args.user,
                                   password=password,
                                   destination_table=table,
                                   port=args.port)


def postcheck_all(mwc_object, args):
    password = getpass()
    postcheck_ping(mwc_object, args)
    postcheck_arp(mwc_object, args, password=password)


def report_get(mwc_object, args):
    precheck_table = 'precheck_{}'.format(str(args.precheck))
    postcheck_table = 'postcheck_{}'.format(str(args.postcheck))
    mwc_object.get_report(precheck=precheck_table,
                          postcheck=postcheck_table)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(dest='router',
                        type=str,
                        help='Set router for analysis')
    subparser = parser.add_subparsers()
    precheck = subparser.add_parser('precheck',
                                    help='Run precheck tasks')
    precheck_subparser = precheck.add_subparsers()
    arp_precheck = precheck_subparser.add_parser('arp',
                                                 help='fetch precheck arp table')
    arp_precheck.add_argument('--user',
                              type=str,
                              required=True,
                              help='Set user to fetch data from box')
    arp_precheck.add_argument('--dest',
                              type=int,
                              default=0,
                              help='ID of precheck table')
    arp_precheck.add_argument('--port',
                              default=22,
                              help='specify port to connect device 22 is default')
    arp_precheck.set_defaults(function=precheck_arp)
    ping_precheck = precheck_subparser.add_parser('ping',
                                                  help='run pings for previously fetched arp')
    ping_precheck.add_argument('--dest',
                               type=int,
                               default=0,
                               help='ID of precheck table')
    ping_precheck.add_argument('--irb',
                               type=str,
                               default='',
                               help=('Set ifl interface which hosts to ping, '
                                     'use * for patterns, '
                                     'use _ as placeholder for pattern.\n'
                                     'examples:\n'
                                     'irb.1__1* (irb.1991, irb.19911) '
                                     'irb.101* (irb.1011, irb.1012)'))
    ping_precheck.add_argument('--ifl',
                               type=str,
                               default='',
                               help=('Set ifl interface which hosts to ping, '
                                     'use * for patterns, '
                                     'use _ as placeholder for pattern.\n'
                                     'examples:\n'
                                     'ge-_/0/1* (1/0/1, 2/0/1)'
                                     'ge-1/1/1* (1/1/1.100, 1/1/1.101'))
    ping_precheck.set_defaults(function=precheck_ping)
    all_precheck = precheck_subparser.add_parser('all',
                                                 help='run all precheck tests')
    all_precheck.add_argument('--port',
                              default=22,
                              help='specify port to connect device 22 is default')
    all_precheck.add_argument('--user',
                              type=str,
                              required=True,
                              help='Set user to fetch data from box')
    all_precheck.add_argument('--dest',
                              type=int,
                              default=0,
                              help='ID of precheck table')
    all_precheck.add_argument('--irb',
                              type=str,
                              default='',
                              help=('Set ifl interface which hosts to ping, '
                                    'use * for patterns, '
                                    'use _ as placeholder for pattern.\n'
                                    'examples:\n'
                                    'irb.1__1* (irb.1991, irb.19911) '
                                    'irb.101* (irb.1011, irb.1012)'))
    all_precheck.add_argument('--ifl',
                              type=str,
                              default='',
                              help=('Set ifl interface which hosts to ping, '
                                    'use * for patterns, '
                                    'use _ as placeholder for pattern.\n'
                                    'examples:\n'
                                    'ge-_/0/1* (1/0/1, 2/0/1)'
                                    'ge-1/1/1* (1/1/1.100, 1/1/1.101'))
    all_precheck.set_defaults(function=precheck_all)

    postcheck = subparser.add_parser('postcheck',
                                     help='Run postcheck tasks')
    postcheck_subparser = postcheck.add_subparsers()
    arp_postcheck = postcheck_subparser.add_parser('arp',
                                                   help='fetch postcheck arp table')
    arp_postcheck.add_argument('--dest',
                               type=int,
                               default=0,
                               help='ID of destination POST check table')
    arp_postcheck.add_argument('--user',
                               type=str,
                               required=True,
                               help='Set user to fetch data from box')
    arp_postcheck.add_argument('--port',
                               default=22,
                               help='specify port to connect device 22 is default')
    arp_postcheck.set_defaults(function=postcheck_arp)

    ping_postcheck = postcheck_subparser.add_parser('ping',
                                                    help='run pings for hosts reachable in precheck')
    ping_postcheck.add_argument('--dest',
                                type=int,
                                default=0,
                                help='ID of destination POST check table ')
    ping_postcheck.add_argument('--source',
                                type=int,
                                default=0,
                                help='ID of source PRE CHECK Table ')
    ping_postcheck.set_defaults(function=postcheck_ping)

    all_postcheck = postcheck_subparser.add_parser('all',
                                                   help='Run all Postcheck tasks in one click')
    all_postcheck.add_argument('--user',
                               type=str,
                               required=True,
                               help='Set user to fetch data from box')
    all_postcheck.add_argument('--source',
                               type=int,
                               default=0,
                               help='ID of source PRE CHECK Table ')
    all_postcheck.add_argument('--dest',
                               type=int,
                               default=0,
                               help='ID of destination POST check table ')
    all_postcheck.add_argument('--port',
                               default=22,
                               help='specify port to connect device 22 is default')
    all_postcheck.set_defaults(function=postcheck_all)

    report = subparser.add_parser('report',
                                  help='Run report tasks')
    report.add_argument('--precheck',
                        type=int,
                        default=0,
                        help='ID of source PRE CHECK Table ')
    report.add_argument('--postcheck',
                        type=int,
                        default=0,
                        help='ID of destination POST check table ')
    report.set_defaults(function=report_get)
    arguments = parser.parse_args()
    mwc = Mwchecker(router=arguments.router)
    arguments.function(mwc, arguments)
