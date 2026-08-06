<?php

namespace App\Notifications;

use Illuminate\Bus\Queueable;
use Illuminate\Notifications\Messages\MailMessage;
use Illuminate\Notifications\Notification;

class BackupCompleteNotification extends Notification
{
    use Queueable;

    public function __construct(
        public string $filename,
        public bool $success,
        public ?string $error = null,
    ) {}

    public function via(object $notifiable): array
    {
        return ['mail'];
    }

    public function toMail(object $notifiable): MailMessage
    {
        $mail = (new MailMessage)
            ->subject($this->success ? 'Backup Completed Successfully' : 'Backup Failed');

        if ($this->success) {
            $mail->greeting('Backup Complete!')
                ->line("Backup file: {$this->filename}")
                ->line('Your database has been backed up successfully.');
        } else {
            $mail->greeting('Backup Failed!')
                ->line("Error: {$this->error}")
                ->line('Please check the system logs for more details.');
        }

        return $mail;
    }
}
