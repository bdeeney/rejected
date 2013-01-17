"""Generate test messages for the example consumer."""
import logging
import random
import time
import uuid

from pika.adapters import BlockingConnection
from pika.connection import ConnectionParameters
from pika import BasicProperties

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)

MESSAGE_COUNT = 100

HTML_VALUE = '<html><head><title>Hi</title></head><body>Hello %i</body></html>'
JSON_VALUE = '{"json_encoded": true, "value": "here", "random": %i}'
XML_VALUE = '<?xml version="1.0"><document><node><item>True</item><other attr' \
            '="foo">Bar</other><value>%i</value></node></document>'
YAML_VALUE = """%%YAML 1.2
---
Application:
  poll_interval: 10.0
  log_stats: True
  name: Example
  value: %i
"""

if __name__ == '__main__':
    connection = BlockingConnection(ConnectionParameters())

    # Open the channel
    channel = connection.channel()

    channel.exchange_declare(exchange='example')

    # Declare the queue
    channel.queue_declare(queue='generated_messages', durable=True,
                          exclusive=False, auto_delete=False)

    channel.queue_bind(exchange='example', queue='generated_messages',
                       routing_key='rejected_example')

    channel.queue_declare(queue='consumer_replies', durable=True,
                          exclusive=False, auto_delete=False)

    channel.queue_bind(exchange='example', queue='consumer_replies',
                       routing_key='rejected_reply')

    # Initialize our timers and loop until external influence stops us
    for iteration in xrange(0, MESSAGE_COUNT):
        msg_type = random.randint(1, 4)
        if msg_type == 1:
            body = HTML_VALUE % random.randint(1, 32768)
            content_type = 'text/html'
        elif msg_type == 2:
            body = JSON_VALUE % random.randint(1, 32768)
            content_type = 'application/json'
        elif msg_type == 3:
            body = XML_VALUE % random.randint(1, 32768)
            content_type = 'text/xml'
        elif msg_type == 4:
            body = YAML_VALUE % random.randint(1, 32768)
            content_type = 'text/x-yaml'
        else:
            body = 'Plain text value %i' % random.randint(1, 32768)
            content_type = 'text/text'

        properties = BasicProperties(timestamp=int(time.time()),
                                     app_id=__file__,
                                     user_id='guest',
                                     content_type=content_type,
                                     message_id=str(uuid.uuid4()),
                                     type='Example message',
                                     reply_to='rejected_reply',
                                     delivery_mode=1)

        # Send the message
        channel.basic_publish(exchange='example',
                              routing_key="rejected_example",
                              body=body,
                              properties=properties)

    connection.close()
