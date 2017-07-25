#!/usr/bin/env python
"""
db_export:   Read datasets from daily sqlite3 dumps and export each entry to json_export
             Optionally exports to kibana and/or influxdb

             Usage:

             ./json_export --src=./var/data.db [--limit=100] \
                [--dst=json|elastic | --url="http://localhost:5200 | filename.json " ] \
                [--extra="field1:v1" --extra="field2:v2"]

             The tool converts each row of the database into a json document having keys corresponding to database field names.

             The tool also adds some metadata fields:
                 - __import_date: YYYYMMDD
                 - __import_time_utc: <utc time of import run>
                 - The list of fields expressed in the --extra parameter

"""

import sqlite3
from sqlite3 import Error
import json
import click

from datetime import datetime
from elasticsearch import Elasticsearch
es = Elasticsearch()

## begin
def create_connection(db_file):
    """ create a database connection to the SQLite database
        specified by the db_file
    :param db_file: database file
    :return: Connection object or None
    """
    try:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        return conn
    except Error as e:
        print(e)

    return None
## end def

## begin
def get_dict(row):
    r = {}
    for key in row.keys():
        r[key] = row[key]
    return r
## end def

@click.command()
@click.option("--src", help="Source database file, mandatory.", required=True)
@click.option("--limit", help="Limit the records to process.", default=10)
@click.option("--dst", type=click.Choice(["json", "elastic"]), help="Destination, can be either json file or elastic server.", required=True)
def dbimport(src, limit, dst):
    con = create_connection(src)
    cursor = con.cursor()
    #cursor.execute("SELECT * FROM roadata LIMIT 50000")
    cursor.execute("SELECT * FROM roadata LIMIT %s" % (limit) )

    # iterate rows
    eid = 1
    for r in cursor.fetchall():
        # print json.dumps(r)
        w = get_dict(r)
        print json.dumps(w)
        # res = es.index(index="roadata", doc_type='prefix', id=eid, body=w)
        eid = eid + 1
        #print(res['created'])
# end command

if __name__ == "__main__":
    dbimport()


## END
