import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import List, Optional


class Notifier:
    """Base notifier interface."""

    def send(self, subject: str, body: str, to_addrs: List[str]) -> None:
        raise NotImplementedError


class NullNotifier(Notifier):
    """No-op notifier (used for dry-run)."""

    def send(self, subject: str, body: str, to_addrs: List[str]) -> None:
        return


@dataclass
class SmtpConfig:
    host: str
    port: int
    user: Optional[str]
    password: Optional[str]
    mail_from: str
    use_tls: bool = True


def load_smtp_config_from_env() -> Optional[SmtpConfig]:
    host = os.getenv("AUTOOPS_SMTP_HOST")
    port = os.getenv("AUTOOPS_SMTP_PORT")
    mail_from = os.getenv("AUTOOPS_EMAIL_FROM")

    if not host or not port or not mail_from:
        return None

    try:
        port_i = int(port)
    except ValueError:
        return None

    return SmtpConfig(
        host=host,
        port=port_i,
        user=os.getenv("AUTOOPS_SMTP_USER"),
        password=os.getenv("AUTOOPS_SMTP_PASS"),
        mail_from=mail_from,
        use_tls=True,
    )


class EmailNotifier(Notifier):
    """SMTP-based email notifier."""

    def __init__(self, cfg: SmtpConfig):
        self.cfg = cfg

    def send(self, subject: str, body: str, to_addrs: List[str]) -> None:
        if not to_addrs:
            return

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.cfg.mail_from
        msg["To"] = ", ".join(to_addrs)
        msg.set_content(body)

        with smtplib.SMTP(self.cfg.host, self.cfg.port, timeout=30) as s:
            if self.cfg.use_tls:
                s.starttls()
            if self.cfg.user and self.cfg.password:
                s.login(self.cfg.user, self.cfg.password)
            s.send_message(msg)
