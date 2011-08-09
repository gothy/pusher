from os import path as op
from optparse import OptionParser

import json
import tornado.web
import tornadio
import tornadio.router
import tornadio.server

from pika.adapters.tornado_connection import TornadoConnection
import pika

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

    def remove_listener(self, rkey):
        'Remove callback for a routing key'
        
        del self._listeners[rkey]
        self.channel.queue_unbind(exchange='mail', routing_key=str(rkey), queue='mailq')

    def connect(self):
        'Establish RabbitMQ connection.'
        
        self.connection = TornadoConnection(pika.ConnectionParameters(host=self._host, port=self._port), 
                                            on_open_callback=self.on_connected)

    def on_connected(self, connection):
        'Callback for successfully established connecction'
        
        print 'on_connected'
        self.connection.channel(self.on_channel_open)

    def on_channel_open(self, channel):
        'Callback for successfully opened connection channel'
        
        print 'on_channel_open'
        self.channel = channel
        self.channel.exchange_declare(exchange='mail', type='direct')
        self.channel.queue_declare(queue='mailq',
                callback=self.on_queue_declared,
                arguments={'x-message-ttl':30000})

    def on_queue_declared(self, frame):
        'Callback for successfull exchange hub and a queue on it declaration'
        
        print 'on_queue_declared'
        self.channel.basic_consume(self.on_message, queue='mailq', no_ack=True)

    def on_message(self, ch, method, properties, body):
        'Callback on incoming event for some binded routing_key'
        
        print " [x] Received %s %s" % (method.routing_key, body,)
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
        print 'on_open'

    def on_message(self, cmd):
        print cmd
        if cmd['cmd'] == 'auth' and 'username' in cmd:
            print 'new user login'
            self.username = cmd['username']
            self.send(json.dumps({'cmd': 'auth', 'code': 0}))
            notipikator.add_listener(self.username, lambda cmd: self.send(cmd))

    def on_close(self):
        print 'connection closed'
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
    parser.add_option("--log", default=op.join(pathname, 'pserv.log'), help="log destination")
    
    (opts, args) = parser.parse_args()
    
    notipikator = NotiPikator(host=opts.mqhost, port=opts.mqport)
    notipikator.connect()
    
    application.settings['socket_io_port'] = opts.bind_port
    
    print application.__dict__
    
    tornadio.server.SocketServer(application)
    
