FROM tiangolo/uwsgi-nginx:python3.10
MAINTAINER Devloper Tools Team

WORKDIR /app

COPY . /app/

COPY .git /app/.git

RUN apt-get update -y && \
    apt-get update --fix-missing -y

RUN pip3 install --upgrade pip

RUN pip3 install -r /app/requirements.txt

RUN rm /etc/localtime
RUN ln -s /usr/share/zoneinfo/Asia/Kolkata /etc/localtime

CMD ["python3", "server.py"]