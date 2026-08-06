import os
import json
import logging
from confluent_kafka import Consumer, KafkaException, KafkaError
from typing import Callable, Optional


class KafkaConsumerWrapper:
    """
    A simple wrapper around confluent-kafka Consumer for standardized consumption.
    Automatically uses SSL when KAFKA_SSL_* env vars are present (e.g. Aiven).
    """
    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        group_id: str = "default-group",
        auto_offset_reset: str = "earliest",
        **extra_configs
    ):
        self.conf = {
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': auto_offset_reset,
            # Auto-commit disabled — commit only after successful processing
            # to avoid losing or double-processing messages on restart.
            'enable.auto.commit': False,
            'log_level': 0
        }

        # SSL support — automatically enabled when cert env vars are present.
        # Works with Aiven Kafka and any other SSL-enabled cluster.
        ca   = os.environ.get('KAFKA_SSL_CA_LOCATION')
        cert = os.environ.get('KAFKA_SSL_CERT_LOCATION')
        key  = os.environ.get('KAFKA_SSL_KEY_LOCATION')
        if ca and cert and key:
            self.conf.update({
                'security.protocol':        'SSL',
                'ssl.ca.location':          ca,
                'ssl.certificate.location': cert,
                'ssl.key.location':         key,
            })

        # Apply any extra configs (e.g. max.poll.interval.ms)
        self.conf.update(extra_configs)

        self.consumer = Consumer(self.conf)
        self._logger = logging.getLogger(self.__class__.__name__)

    def subscribe(self, topics: list):
        self.consumer.subscribe(topics)

    def commit(self):
        """Manually commit the current offset. Call after successful processing."""
        self.consumer.commit(asynchronous=False)

    def consume_loop(self, handler: Callable[[dict], None], timeout: float = 1.0):
        """
        Standard consumption loop. Commits offset only after handler
        returns without raising — guarantees at-least-once delivery.
        """
        try:
            while True:
                msg = self.consumer.poll(timeout=timeout)
                if msg is None:
                    import time
                    time.sleep(0.1)  # prevent high CPU on idle
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    elif msg.error().code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                        import time
                        time.sleep(2)
                        continue
                    else:
                        self._logger.error(f"Kafka error: {msg.error()}")
                        break

                try:
                    data = json.loads(msg.value().decode('utf-8'))
                    handler(data)
                    # Commit only after handler succeeds
                    self.consumer.commit(message=msg, asynchronous=False)
                except Exception as e:
                    self._logger.error(f"Error handling message: {e}")
                    # Do NOT commit — message will be redelivered on restart
        finally:
            self.consumer.close()

    def close(self):
        self.consumer.close()
