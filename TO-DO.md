# TO-DO List for Opendata-Datasets

## RPKI Roadata
1. enrich prefix information with the classic {type,start,end,equiv}
2. further enrich prefix information with country code information {as_cc, pfx_cc}

# Completed items

## Add support for RIPE NCC RPKI Validator ROA export
Process the exported CSV and create a dump out of it.

## Multiple tables in a single database file.
This probably works already... if the same db_filename is specified. Maybe just write a simple test for it.

## Open already existing db dumps non-destructively
Use already existing dbs without dropping current data. Add a flag
