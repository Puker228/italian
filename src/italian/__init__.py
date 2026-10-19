"""ИС «Школа изучения итальянского языка» (вариант 9): PyQt6 + SQLite."""

import argparse
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QDialog

from italian.db import DEFAULT_DB_PATH, init_db, make_engine
from italian.ui.main_window import LoginDialog, MainWindow


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ИС «Школа изучения итальянского языка»"
    )
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB_PATH, help="путь к файлу БД SQLite"
    )
    parser.add_argument(
        "--no-demo", action="store_true", help="не заполнять новую БД тестовыми данными"
    )
    args, qt_args = parser.parse_known_args()

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("Школа итальянского языка")
    app.setStyle("Fusion")

    engine = make_engine(args.db)
    session_factory = init_db(engine, with_demo_data=not args.no_demo)

    while True:
        login = LoginDialog(session_factory)
        if login.exec() != QDialog.DialogCode.Accepted or login.user is None:
            break
        window = MainWindow(session_factory, engine, login.user)
        window.show()
        app.exec()
        if not window.switch_user:
            break
