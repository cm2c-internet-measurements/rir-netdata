"""
Airflow DAG for importing netdata information:
(c) carlos@lacnic.net 2017-07-15 @ietf99 hackathon (Prage, CZ)


Taken from:
Code that goes along with the Airflow located at:
http://airflow.readthedocs.org/en/latest/tutorial.html
"""

from airflow import DAG
from airflow.operators.bash_operator import BashOperator
from datetime import datetime, timedelta
import os


default_args = {
    'owner': 'airflow',
    'depends_on_past': True,
    'start_date': datetime(2017, 6, 1),
    'email': ['carlosm3011@gmail.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    # 'queue': 'bash_queue',
    # 'pool': 'backfill',
    # 'priority_weight': 10,
    # 'end_date': datetime(2016, 1, 1),
}

dag = DAG(
    'labs-opendata-datasets', default_args=default_args, schedule_interval=timedelta(1))


# '''
#     {% for i in range(5) %}
#         echo "{{ ds }}"
#         echo "{{ macros.ds_add(ds, 7)}}"
#         echo "{{ params.my_param }}"
#     {% endfor %}
# '''

netdata_tmpl_command = """
    /usr/bin/env python "{{ params.path }}"/bin/netdata.py get --basename "{{ params.path }}"/"{{ params.basename }}"
"""

# t1, t2 and t3 are examples of tasks created by instantiating operators
t2 = BashOperator(
    task_id='print_files',
    bash_command='ls -l %s/var/netdata' % (os.getcwd()),
    dag=dag)

t1 = BashOperator(
    task_id='import_base_datasets',
    bash_command=netdata_tmpl_command,
    params={'rir': 'lacnic', 'path': os.getcwd(), 'basename': 'var/netdata' },
    dag=dag)

t2.set_upstream(t1)
