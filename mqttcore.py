#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim tabstop=4 expandtab shiftwidth=4 softtabstop=4

#
# mqtt-core
#
#


__author__ = "Dennis Sell"
__copyright__ = "Copyright (C) Dennis Sell"


import sys
import os
import mosquitto
from mosquitto import error_string
import socket
import time
import subprocess
import logging
import signal
from config import Config
import datetime
from daemon import daemon_version


COREVERSION = 0.8


class MQTTClientCore:
    """
    A generic MQTT client framework class

    """
    def __init__(self, appname, clienttype, clean_session=True):
        self.running = True
        self.connectcount = 0
        self.starttime=datetime.datetime.now()
        self.connecttime=0 
        self.disconnecttime=0 
        self.persist = False
        self.mqtt_connected = False
        self.clienttype = clienttype
        self.clean_session = clean_session
        self.clientversion = "unknown"
        self.coreversion = COREVERSION
        homedir = os.path.expanduser("~")
        self.configfile = homedir + "/." + appname + '.conf'
        self.mqtttimeout = 60    # seconds

        if ('single' == self.clienttype):
            from daemon import daemon_version
            self.clientname = appname
            self.persist = True
        elif ('multi' == self.clienttype):
            from daemon import daemon_version
            self.persist = True
            self.clientname = appname + "[" + socket.gethostname() + "]"
        elif ('app' == self.clienttype):
            self.clientname = appname + "[" + socket.gethostname() + "_" +\
                              str(os.getpid()) + "]"
            self.persist = False
        else: # catchall
            from daemon import daemon_version
            self.clientname = appname
            self.persist = False
        self.clientbase = "/clients/" + self.clientname + "/"
        LOGFORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

        #TODO  need to deal with no config file existing!!!
        #read in configuration file
        f = self.configfile
        try:
            self.cfg = Config(f)
        except:
            try:
                self.cfg = Config('/etc/mqttclients/.' + appname + '.conf')
            except:
                try:
                    self.cfg = Config('/etc/mqttclients/mqtt.conf')
                except:
                    print "Config file not found."
                    sys.exit(99)

        self.mqtthost = self.cfg.MQTT_HOST
        self.mqttport = self.cfg.MQTT_PORT
        self.mqtttimeout = 60  # get from config file  TODO
        self.logfile = os.path.expanduser(self.cfg.LOGFILE)
        self.loglevel = self.cfg.LOGLEVEL
        try:
            self.ca_path = cfg.CA_PATH
        except:
            self.ca_path = None
        try:
            self.ssh_port = cfg.SSH_PORT
            self.ssh_host = cfg.SSH_HOST
        except:
            self.ssh_port = None
            self.ssh_host = None
        try:
            self.username = self.cfg.USERNAME
        except:
            self.username = None
        try:
            self.password = self.cfg.PASSWORD
        except:
            self.password = None

        logging.basicConfig(filename=self.logfile, level=self.loglevel,
                            format=LOGFORMAT)

        #create an mqtt client
        self.mqttc = mosquitto.Mosquitto(self.clientname, clean_session=self.clean_session)

        #trap kill signals including control-c
        signal.signal(signal.SIGTERM, self.cleanup)
        signal.signal(signal.SIGINT, self.cleanup)

    def getifip(ifn):
        # print ip
        import socket, fcntl, struct

        sck = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return socket.inet_ntoa(fcntl.ioctl(sck.fileno(),0x8915,struct.pack('256s', ifn[:15]))[20:24])

    def identify(self):
        self.mqttc.publish(self.clientbase + "version",
                            self.clientversion, qos=1, retain=self.persist)
        self.mqttc.publish(self.clientbase + "core-version", self.coreversion, qos=1, retain=self.persist)
        if ('app' != self.clienttype):
            self.mqttc.publish(self.clientbase + "daemon-version", daemon_version(), qos=1, retain=self.persist)
#        p = subprocess.Popen("curl ifconfig.me/forwarded", shell=True,
        p = subprocess.Popen("ip -f inet  addr show | tail -n 1 | cut -f 6 -d' ' | cut -f 1 -d'/'", shell=True,
                              stdout=subprocess.PIPE)
        ip = p.stdout.readline()
        self.mqttc.publish(self.clientbase + "locip", ip.strip('\n'), qos=1, retain=self.persist)
        p = subprocess.Popen("curl -s ifconfig.me/ip", shell=True,
                             stdout=subprocess.PIPE)
        extip = p.stdout.readline()
        self.mqttc.publish(self.clientbase + "extip", extip.strip('\n'), qos=1, retain=self.persist)
        self.mqttc.publish(self.clientbase + "pid", os.getpid(), qos=1, retain=self.persist)
        self.mqttc.publish(self.clientbase + "status", "online", qos=1, retain=self.persist)
        self.mqttc.publish(self.clientbase + "class", self.clienttype, qos=1, retain=self.persist)
        self.mqttc.publish(self.clientbase + "start", str(self.starttime), qos=1, retain=self.persist)
        self.mqttc.publish(self.clientbase + "disconnecttime", str(self.disconnecttime), qos=1, retain=self.persist)
        self.mqttc.publish(self.clientbase + "connecttime", str(self.connecttime), qos=1, retain=self.persist)
        self.mqttc.publish(self.clientbase + "count", self.connectcount, qos=1, retain=self.persist)
#add broker port connection type?

    #define what happens after connection
    def on_connect(self, mself, obj, rc):
        self.mqtt_connected = True
        self.connectcount = self.connectcount+1
        self.connecttime=datetime.datetime.now()
        print "MQTT Connected"
        logging.info("MQTT connected")
        self.mqttc.subscribe(self.clientbase + "ping", qos=2)
        self.mqttc.subscribe("/clients/global/#", qos=2)
        self.identify()

    def on_disconnect( self, mself, obj, rc ):
        self.disconnecttime=datetime.datetime.now()
        self.mqtt_connected = False
        logging.info("MQTT disconnected: " + error_string(rc))
        print "MQTT Disconnected"

    #On recipt of a message create a pynotification and show it
    def on_message( self, mself, obj, msg):
        if ((( msg.topic == self.clientbase + "ping" ) and
            ( msg.payload == "request" )) or
            (( msg.topic == "/clients/global/ping" ) and
            ( msg.payload == "request" ))):
            self.mqttc.publish(self.clientbase + "ping", "response", qos=1,
                               retain=0)
        if (( msg.topic == "/clients/global/identify" ) and
            ( msg.payload == "request" )):
            self.identify()

    def on_log(self, mself, obj, level, buffer):
        logging.info(buffer)
#TODO add level filtering here

    def mqtt_connect(self):
        if ( True != self.mqtt_connected ):
                print "Attempting connection..."
                logging.info("Attempting connection.")
                if(self.ssh_port != None):
                    logging.info("Building SSH tunnel.")
                    print "Using ssh for security"
                    self.sshpid = subprocess.Popen("ssh -f -n -N -L 127.0.0.1:%d:localhost:%d user@%s"
                             % (self.ssh_port, self.mqtt_port, self.ssh_host),
                                 shell=True, close_fds=True)
                    self.mqtt_host = "localhost"
                    self.mqtt_port = self.ssh_port
                else: 
                    self.sshpid = None
                if(self.ca_path != None):
                    logging.info("Assigning certificate for security.")
                    print "Using CA for security"
                    self.mqttc.tls_set(self.ca_path)
                if self.username != None:
                    if self.password != None:
                        logging.info("Using username for login")
                        print "Logging in as " + self.username + " with password."
                        self.mqttc.username_pw_set(self.username, self.password)
                    else:
                        logging.info("Using password for login")
                        print "Logging in as " + self.username
                        self.mqttc.username_pw_set(self.username)
                self.mqttc.will_set(self.clientbase + "/status", "disconnected", qos=1, retain=self.persist)
                
                #define the mqtt callbacks
                self.mqttc.on_message = self.on_message
                self.mqttc.on_connect = self.on_connect
                self.mqttc.on_disconnect = self.on_disconnect
                self.mqttc.on_log = self.on_log

                #connect
                self.mqttc.connect_async(self.mqtthost, self.mqttport,
                                        self.mqtttimeout)

    def mqtt_disconnect(self):
        if ( self.mqtt_connected ):
            self.mqtt_connected = False
            logging.info("MQTT disconnecting")
            print "MQTT Disconnecting"
            self.mqttc.publish ( self.clientbase + "status" , "offline", qos=1, retain=self.persist )
            self.mqttc.disconnect()
            try:
                logging.info("Destroying SSH tunnel.")
                print "Destroying SSH tunnel."
                os.kill(self.sshpid, 15) # 15 = SIGTERM
            except:
                print "PID invalid"

    def cleanup(self, signum, frame):
        self.running = False
        self.mqtt_disconnect()
        sys.exit(signum)

    def main_loop(self):
        self.mqtt_connect()
        self.mqttc.loop_forever()


def main(daemon):
    if len(sys.argv) == 2:
        if 'start' == sys.argv[1]:
            daemon.start()
        elif 'stop' == sys.argv[1]:
            daemon.stop()
        elif 'restart' == sys.argv[1]:
            daemon.restart()
        elif 'run' == sys.argv[1]:
            daemon.run()
        else:
            print "Unknown command"
            sys.exit(2)
        sys.exit(0)
    else:
        print "usage: %s start|stop|restart" % sys.argv[0]
        sys.exit(2)
