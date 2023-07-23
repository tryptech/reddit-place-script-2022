FROM python:3.10.4-alpine

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN set -eux; \
    apk add --no-cache \
        python3-dev \
        py3-setuptools \
        gcc \
        linux-headers \
        libc-dev \
        tiff-dev jpeg-dev openjpeg-dev zlib-dev freetype-dev lcms2-dev \
        libwebp-dev tcl-dev tk-dev harfbuzz-dev fribidi-dev libimagequant-dev \
        libxcb-dev libpng-dev \
    ; \
    pip install --no-cache-dir -r requirements.txt

COPY . .

ARG CONFIG="config.json"
COPY ./$CONFIG ./config.json

CMD [ "python", "main.py" ]
