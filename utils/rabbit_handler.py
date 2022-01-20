import json
import pika

from utils import config


def send_message(message: dict) -> None:
    # Setup connection
    connection = pika.BlockingConnection(pika.ConnectionParameters(config.load_rabbitmq_config()["broker"]))
    channel = connection.channel()

    # Create a message queue
    channel.queue_declare(queue=config.load_rabbitmq_config()["queue"], durable=True)

    # Send message
    channel.basic_publish(
        exchange="",
        routing_key=config.load_rabbitmq_config()["queue"],
        body=json.dumps(message).encode(),
        properties=pika.BasicProperties(delivery_mode=2)  # Persistent messages
    )

    # Closing properly
    connection.close()
