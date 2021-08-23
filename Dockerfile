FROM python:3.7-bullseye

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt

RUN apt-get update && apt-get clean

# Install ffmpeg
RUN apt-get install --no-install-recommends -y ffmpeg

RUN pip install -r /app/requirements.txt \
    && rm -rf /root/.cache/pip

COPY . /app/
