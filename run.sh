#!/usr/bin/with-contenv bashio

export MQTT_HOST=$(bashio::services mqtt "host")
export MQTT_PORT=$(bashio::services mqtt "port")
export MQTT_USERNAME=$(bashio::services mqtt "username")
export MQTT_PASSWORD=$(bashio::services mqtt "password")

export GODAIKIN_USERNAME=$(bashio::config "godaikin_username")
export GODAIKIN_PASSWORD=$(bashio::config "godaikin_password")
export REFRESH_INTERVAL=$(bashio::config "refresh_interval")

python -u -m godaikin.main