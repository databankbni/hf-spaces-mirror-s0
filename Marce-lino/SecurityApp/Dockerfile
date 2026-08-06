FROM php:8.4-cli

RUN apt-get update && apt-get install -y \
    libpq-dev \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && docker-php-ext-install pdo_pgsql

RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

WORKDIR /app

COPY . .

RUN mkdir -p storage/app/backups storage/framework/cache/data \
    storage/framework/sessions storage/framework/views storage/logs \
    && chmod -R 777 storage bootstrap/cache

RUN composer install --no-dev --no-interaction

RUN cp .env.example .env && php artisan key:generate --force --no-interaction

RUN chmod +x start.sh

EXPOSE 7860

CMD ["./start.sh"]
