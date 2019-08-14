# RIR NETDATA

## Abstract

Pipeline for producing a consolidated sqlite3 file containing:

- an imported version of all five RIRs "delegated-extended" files
- an imported version of a current snapshot of a RIPE RPKI validator 
- an imported version of a current RIPE "riswhois" dump

All imported data is enriched in different ways, adding convenience fields to make querying easier.

*Author(s)*: Carlos M. Martinez (carlos@lacnic.net)
*Date*: July 19, 2017

## Tables and fields

1. CSV import of all "delegated-extended" files

Schema:

```
CREATE TABLE numres (id INTEGER PRIMARY KEY, rir text, cc text, type text, block text, length integer, date integer, status text, orgid integer, istart INTEGER, iend INTEGER, prefix VARCHAR(80), equiv INTEGER);
```

2. CSV import of a RIPE RPKI validator instance output

```
CREATE TABLE roadata (id INTEGER PRIMARY KEY, origin_as text, prefix text, maxlen integer, ta text, origin_as2 VARCHAR(10), istart UNSIGNED BIG INT, iend UNSIGNED BIG INT, type VARCHAR(5), pfxlen INTEGER, equiv INTEGER, cc CHAR(2), origin_as_cc CHAR(2));
```

3. CSV import of a current RIPE "riswhois" dump

```
CREATE TABLE riswhois (id INTEGER PRIMARY KEY, origin_as text, prefix text, viewed_by integer, istart UNSIGNED BIG INT, iend UNSIGNED BIG INT, type VARCHAR(5), pfxlen INTEGER);
```
