# Running DAGs with Airflow

**author**: carlos@lacnic.net
**date**: 2017-07-15

## Reference and Pre-Requisites

1. Install Apache Airflow with 
    ```pip install airflow```
3. Generate initial configuration
    ```./bin/af.sh version``` 
    _This should create an airflow.cfg file if not already present_
3. Init database
     ```./bin/af.sh initdb```
5. Init DAGs
     ```python etc/airflow/labs-datasets-dag.py```

## Test environment and configuration

**Render a command:**

```bash
./bin/af.sh render labs-opendata-datasets import_base_datasets 2017-06-01
```  

Rendering a command performs the jinja2 templating and writes the result to stdout without actually executing anything.

**Test a command:**

Testing a command actually RUNS the command and thus requires a date. 

```bash
./bin/af.sh test labs-opendata-datasets import_base_datasets 2017-06-01
```
The date used here is a "fiction" date as-if the command had been run by the Airflow scheduler.

## Backfilling

Backfilling is the process of running tasks for **past dates**:

```
# optional, start a web server in debug mode in the background
# airflow webserver --debug &

# start your backfill on a date range
airflow backfill tutorial -s 2015-06-01 -e 2015-06-07
```

This is akin to run the command in test mode (see above) for the range of dates specified (-s, start and -e, end).

## Scheduling

TBW**

## Running the webserver

Airflow includes an admin website that can be run with:

```
airflow webserver
```


