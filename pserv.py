from os import path as op
from optparse import OptionParser
import logging
import sys

import json
import tornado.web
import tornadio
import tornadio.router
import tornadio.server

from pika.adapters.tornado_connection import TornadoConnection
import pika

logger = logging.getLogger('pusher')

class NotiPikator(object):
    '''
    This is a singleton-wannabe class for connecting, listening and triggering events from RabbitMQ.
    It uses the <pika> library with adapter to internal Tornado ioloop for non-blocking operations on MQ.
    '''
    _listeners = {}
    _host = 'localhost'
    _port = 5672
    
    def __init__(self, *args, **kwargs):
        self._host = kwargs.get('host', 'localhost')
        self._port = kwargs.get('port', 5672)
    
    def add_listener(self, rkey, callback):
        'Add listener callback for a specific routing key'
        
        self._listeners[rkey] = callback
        self.channel.queue_bind(exchange='mail', routing_key=str(rkey), queue='mailq')
        logging.debug('new listener for <%s> was set' % (rkey, ))

    def remove_listener(self, rkey):
        'Remove callback for a routing key'
        
        if rkey in self._listeners:
            del self._listeners[rkey]
        self.channel.queue_unbind(exchange='mail', routing_key=str(rkey), queue='mailq')
        logger.debug('listener for <%s> was removed' % (rkey, ))

    def connect(self):
        'Establish RabbitMQ connection.'
        
        self.connection = TornadoConnection(pika.ConnectionParameters(host=self._host, port=self._port), 
                                            on_open_callback=self.on_connected)
        logger.info('connecting to RabbitMQ...')

    def on_connected(self, connection):
        'Callback for successfully established connecction'
        
        logger.info('connection with RabbitMQ is established')
        self.connection.channel(self.on_channel_open)

    def on_channel_open(self, channel):
        'Callback for successfully opened connection channel'
        
        logger.debug('RabbitMQ channel is opened')
        self.channel = channel
        self.channel.exchange_declare(exchange='mail', type='direct')
        self.channel.queue_declare(queue='mailq',
                callback=self.on_queue_declared,
                arguments={'x-message-ttl':30000})

    def on_queue_declared(self, frame):
        'Callback for successfull exchange hub and a queue on it declaration'
        
        logger.debug('queue_declared event fired')
        self.channel.basic_consume(self.on_message, queue='mailq', no_ack=True)

    def on_message(self, ch, method, properties, body):
        'Callback on incoming event for some binded routing_key'
        
        logger.debug('message received: %s %s' % (method.routing_key, body,))
        self._listeners[method.routing_key](body)


class IndexHandler(tornado.web.RequestHandler):
    """Regular HTTP handler to serve the chatroom page"""
    pass


class PushConnection(tornadio.SocketConnection):
    '''
    Per-user connection class with basic events for socket connect and close, message received.
    '''
    username = None

    def on_open(self, *args, **kwargs):
        logger.debug('new socket.io client connection opened')

    def on_message(self, cmd):
        logger.debug('cmd from %s: %s', self.username, cmd)
        if cmd['cmd'] == 'auth' and 'username' in cmd:
            self.username = cmd['username']
            self.send(json.dumps({'cmd': 'auth', 'code': 0}))
            notipikator.add_listener(self.username, lambda cmd: self.send(cmd))

    def on_close(self):
        logger.debug('socket.io connection closed with %s', self.username)
        notipikator.remove_listener(self.username)

#use the routes classmethod to build the correct resource
PushRouter = tornadio.get_router(PushConnection)

#config the Tornado application
application = tornado.web.Application(
    [(r"/", IndexHandler), PushRouter.route()],
    enabled_protocols = ['websocket',
                         'flashsocket',
                         'xhr-multipart',
                         'xhr-polling'],
    #flash_policy_port = 843,
    #flash_policy_file = op.join(ROOT, 'flashpolicy.xml'),
    socket_io_port = 8001,
)

if __name__ == "__main__":
    pathname = op.realpath(op.dirname(__file__))
    parser = OptionParser()
    parser.add_option("--mqhost", default='localhost', help="RabbitMQ host")
    parser.add_option("--mqport", default=5672, help="RabbitMQ port")
    parser.add_option("--bind_port", default=8001, help="socket.io listening port")
    parser.add_option("--lpath", default=op.join(pathname, 'pusher.log'), help="log destination")
    parser.add_option("--llevel", default='DEBUG', help="logging level (critical, error, warning, info, debug)")
    parser.add_option("--lstdout", default=False, help="also print logs to stdout")
    
    (opts, args) = parser.parse_args()
    
    # logging setup
    loglevel = getattr(logging, opts.llevel.upper())
    logger.setLevel(loglevel)
    logger.propagate = False
    fh = logging.FileHandler(opts.lpath)
    formatter = logging.Formatter('%(asctime)s : %(name)s : %(levelname)s : %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    if opts.lstdout:
        soh = logging.StreamHandler(sys.stdout)
        soh.setFormatter(formatter)
        soh.setLevel(loglevel)
        logger.addHandler(soh)
    
    # connect to rabbit
    notipikator = NotiPikator(host=opts.mqhost, port=opts.mqport)
    notipikator.connect()
    
    application.settings['socket_io_port'] = opts.bind_port
    
    # start listening
    tornadio.server.SocketServer(application)
    
