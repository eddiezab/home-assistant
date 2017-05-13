import asyncio
import logging
import json

import voluptuous as vol

from datetime import datetime

CONF_ROOMBAS = 'roombas'

from homeassistant.components.switch import PLATFORM_SCHEMA
from homeassistant.helpers.entity import ToggleEntity
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_SWITCHES, STATE_UNKNOWN, STATE_ON, STATE_OFF
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = ['paho-mqtt']


_LOGGER = logging.getLogger(__name__)

ROOMBA_SCHEMA = vol.Schema({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_ROOMBAS): vol.Schema({cv.slug: ROOMBA_SCHEMA}),
})

@asyncio.coroutine
def async_setup_platform(hass, config, add_devices, discovery_info=None):

    roomba_conf = config.get(CONF_ROOMBAS, [config])   
    
    roombas = []
    
    for roomba, conf in roomba_conf.items():
        username = conf.get(CONF_USERNAME)
        host = conf.get(CONF_HOST)
        password = conf.get(CONF_PASSWORD)

        roombas.append(RoombaSwitch(host, username, password, roomba))

    add_devices(roombas)

class RoombaSwitch(ToggleEntity):
    def __init__(self, host, username, password, name):
        import paho.mqtt.client as paho
        import ssl

        self._host = host
        self._username = username
        self._password = password
        self._name = name
        self._state = {}

        self._locked = False

        mqtt_client = paho.Client(self._username, False)
        mqtt_client.tls_set("/etc/ssl/certs/ca-certificates.crt",
              tls_version=ssl.PROTOCOL_TLSv1_2, cert_reqs=ssl.CERT_NONE)
        mqtt_client.tls_insecure_set(True)
        mqtt_client.username_pw_set(self._username, self._password)

        mqtt_client.on_connect = self._get_state
        mqtt_client.on_message = self._get_state_callback

        self.mqtt_client = mqtt_client
        self.mqtt_client.connect(self._host, 8883)
        self.mqtt_client.loop_start()


    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return STATE_ON if self._state.get('state', {}).get('reported', {}).get(
            'cleanMissionStatus', {'phase': STATE_UNKNOWN})['phase'] == 'run' else STATE_OFF

    @property
    def is_on(self):
        _LOGGER.info('Checking is_on for {0.name} ({0.state})'.format(self))
        return self.state

    def turn_off(self, **kwargs):
        self.send_api_command('stop')
        self.send_api_command('dock')

    def turn_on(self, **kwargs):
        self.send_api_command('start')

    def send_api_command(self, command):
        _LOGGER.info('Sending {0} to {1.name}'.format(command,self))
        self.mqtt_client.publish('cmd', json.dumps({'command': command, 'time': int(datetime.now().strftime("%s")), 'initiator': 'localApp'}))

    def _get_state(self, client, userdata, flags, rc):
        client.subscribe("mission")

    def _get_state_callback(self, client, userdata, msg):        
        roomba_state = json.loads(msg.payload.decode("utf-8"))
        self._state.update(roomba_state)

        _LOGGER.debug('{0.name} update received. {1}'.format(self, roomba_state))

    def update(self):
        _LOGGER.info('{0.name} performing complete update.'.format(self))
        self.mqtt_client.publish('mission')
