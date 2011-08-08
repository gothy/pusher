Unite Pusher
========

###What for?
Pusher is currently a dependency for uni_mail only. In future, there's a plan to use it for all system notifications like chat, uploads and so on.

uni_mail prototype web client uses Pusher for receiving realtime notifications about changes in user's mailbox, like thread or a new message in existing thread.

###How's it work?
So basically Pusher is a light webserver, build on tornadio( https://github.com/MrJoes/tornadio ) comet framework 
with a TornadoWeb( http://www.tornadoweb.org/ ) ioloop in its core.

Pusher establises a connection with RabbitMQ on start and starts listening to the event queue.<br/>
Each web client, that would like to receive notifications can connect to Pusher using socket.IO (http://socket.io/) 
client library using one of the transports(like websocket, flashsocket, xhr-multipart, xhr-polling). <br/>
For each successfully connected client, there's a username. We use this name as a routing key to add binding to the queue events.

So for example, user "gothy" connects, Pusher adds 'gothy' to the list of the routing keys it consumes messages for. 
When new event pops Pusher looks up meta info of the event and send a command to the connected client.<br/>
When this client disconnects - Pusher unbinds this routing_key and stops listening for these events.