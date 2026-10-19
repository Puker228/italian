"""ИС «Школа изучения итальянского языка» (вариант 9): PyQt6 + PostgreSQL."""

import argparse
import sys

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
from sqlalchemy.exc import OperationalError

from italian.db import ConfigError, init_db, make_engine
from italian.ui.main_window import LoginDialog, MainWindow


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ИС «Школа изучения итальянского языка»"
    )
    parser.add_argument(
        "--db-url",
        help="адрес БД, например postgresql+psycopg://user:pass@localhost:5432/db "
        "(по умолчанию берётся из .env)",
    )
    parser.add_argument(
        "--no-demo", action="store_true", help="не заполнять новую БД тестовыми данными"
    )
    args, qt_args = parser.parse_known_args()

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("Школа итальянского языка")
    app.setStyle("Fusion")

    try:
        engine = make_engine(args.db_url)
        session_factory = init_db(engine, with_demo_data=not args.no_demo)
    except ConfigError as exc:
        QMessageBox.critical(None, "Настройки БД", str(exc))
        sys.exit(1)
    except OperationalError as exc:
        QMessageBox.critical(
            None,
            "Нет подключения к БД",
            "Не удалось подключиться к PostgreSQL.\n"
            "Запустите контейнер: docker compose up -d\n\n"
            f"{exc.orig}",
        )
        sys.exit(1)

    while True:
        login = LoginDialog(session_factory)
        if login.exec() != QDialog.DialogCode.Accepted or login.user is None:
            break
        window = MainWindow(session_factory, engine, login.user)
        window.show()
        app.exec()
        if not window.switch_user:
            break
