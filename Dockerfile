FROM ubuntu:20.04

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt

RUN apt-get update && apt-get clean

# Install ffmpeg
# RUN apt-get install --no-install-recommends -y ffmpeg \
#  && rm -rf /var/lib/apt/lists/* \
#  && apt-get clean

RUN apt-get install -y python3-pip

RUN pip install -r /app/requirements.txt \
    && rm -rf /root/.cache/pip

COPY . /app/
