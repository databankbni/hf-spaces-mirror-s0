<?php

namespace App\Notifications;

use Illuminate\Bus\Queueable;
use Illuminate\Notifications\Messages\MailMessage;
use Illuminate\Notifications\Notification;

class LoginAlertNotification extends Notification
{
    use Queueable;

    public function __construct(
        public string $ip,
        public string $userAgent,
        public bool $success,
    ) {}

    public function via(object $notifiable): array
    {
        return ['mail'];
    }

    public function toMail(object $notifiable): MailMessage
    {
        $subject = $this->success
            ? 'New login to your account'
            : 'Failed login attempt on your account';

        $mail = (new MailMessage)
            ->subject($subject)
            ->greeting('Hello ' . $notifiable->name . '!');

        if ($this->success) {
            $mail->line('A new login was detected on your account.');
        } else {
            $mail->line('A failed login attempt was detected on your account.');
        }

        $mail->line('IP Address: ' . $this->ip)
            ->line('Browser/Device: ' . $this->userAgent)
            ->line('Time: ' . now()->format('Y-m-d H:i:s'))
            ->line('If this was not you, please secure your account immediately.');

        return $mail;
    }
}
