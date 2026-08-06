import os
import json
import logging
from confluent_kafka import Producer
from typing import Any, Dict

logger = logging.getLogger(__name__)


class KafkaProducerWrapper:
    """
    A simple wrapper around confluent_kafka Producer to standardize message production.
    Automatically uses SSL when KAFKA_SSL_* env vars are present (e.g. Aiven).
    """
    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        conf = {'bootstrap.servers': bootstrap_servers}

        # SSL support — automatically enabled when cert env vars are present
        ca   = os.environ.get('KAFKA_SSL_CA_LOCATION')
        cert = os.environ.get('KAFKA_SSL_CERT_LOCATION')
        key  = os.environ.get('KAFKA_SSL_KEY_LOCATION')
        if ca and cert and key:
            conf.update({
                'security.protocol':        'SSL',
                'ssl.ca.location':          ca,
                'ssl.certificate.location': cert,
                'ssl.key.location':         key,
                'acks':                     'all',
                'retries':                  3,
                'retry.backoff.ms':         500,
                'socket.timeout.ms':        10000,
                'message.timeout.ms':       30000,
                'metadata.request.timeout.ms': 15000,
            })

        self.producer = Producer(conf)

    def _delivery_report(self, err, msg):
        if err is not None:
            print(f'❌ Message delivery failed: {err}', flush=True)
            logger.error(f'❌ Message delivery failed: {err}')
        else:
            print(f'✅ Delivered to {msg.topic()} [{msg.partition()}]', flush=True)
            logger.debug(f'✅ Delivered to {msg.topic()} [{msg.partition()}]')

    def produce(self, topic: str, key: str, value: Dict[str, Any]):
        try:
            def json_serializer(obj):
                if hasattr(obj, 'isoformat'):
                    return obj.isoformat()
                return str(obj)

            self.producer.produce(
                topic,
                key=key,
                value=json.dumps(value, default=json_serializer),
                callback=self._delivery_report
            )
            self.producer.poll(0)
        except Exception as e:
            logger.error(f"❌ Error producing to Kafka: {e}")

    def flush(self):
        self.producer.flush()
