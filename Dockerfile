ARG BUILD_FROM
FROM $BUILD_FROM

ENV PATH="/opt/venv/bin:$PATH" \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY godaikin /app/godaikin

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD [ "/run.sh" ]