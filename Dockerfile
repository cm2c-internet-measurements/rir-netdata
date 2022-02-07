# Compilar imagen con el netdata

FROM python:2.7
RUN mkdir -p /opt/rir-netdata
WORKDIR /opt/rir-netdata
COPY requirements.txt Pipfile /opt/rir-netdata
COPY bin /opt/rir-netdata/bin
COPY lib /opt/rir-netdata/lib
COPY var /opt/rir-netdata/var
COPY tmp /opt/rir-netdata/tmp
RUN pip install -r requirements.txt
ENTRYPOINT ["/opt/rir-netdata/bin/netdata.py"]
