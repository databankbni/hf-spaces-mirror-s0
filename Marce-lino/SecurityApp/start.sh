#!/bin/bash
set -e

chmod -R 777 storage bootstrap/cache 2>/dev/null || true

# Update .env with runtime values (replace or append)
update_env() {
    local key="$1" value="$2"
    # Quote value if it contains whitespace
    if [[ "$value" =~ [[:space:]] ]]; then
        value="\"$value\""
    fi
    if grep -q "^${key}=" .env 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" .env
    else
        echo "${key}=${value}" >> .env
    fi
}

update_env APP_URL "https://Marce-lino-SecurityApp.hf.space"
update_env GOOGLE_REDIRECT_URI "https://Marce-lino-SecurityApp.hf.space/auth/google/callback"

[ -n "$DB_URL" ] && update_env DB_URL "$DB_URL"
[ -n "$GOOGLE_CLIENT_ID" ] && update_env GOOGLE_CLIENT_ID "$GOOGLE_CLIENT_ID"
[ -n "$GOOGLE_CLIENT_SECRET" ] && update_env GOOGLE_CLIENT_SECRET "$GOOGLE_CLIENT_SECRET"
[ -n "$GITHUB_CLIENT_ID" ] && update_env GITHUB_CLIENT_ID "$GITHUB_CLIENT_ID"
[ -n "$GITHUB_CLIENT_SECRET" ] && update_env GITHUB_CLIENT_SECRET "$GITHUB_CLIENT_SECRET"
if [ -n "$RESEND_API_KEY" ]; then
    update_env RESEND_API_KEY "$RESEND_API_KEY"
    update_env MAIL_MAILER "resend"
else
    update_env MAIL_MAILER "log"
fi

php artisan config:clear

php artisan migrate --force

export HTTPS=on
php artisan serve --host=0.0.0.0 --port=7860
