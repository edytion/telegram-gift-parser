from collector.i18n import tr
import sys
from pathlib import Path
from collector.runner import main

if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    try:
        raise SystemExit(main(Path(__file__).resolve().parent))
    except EOFError:
        print(tr("Ввод закрыт. Запустите скрипт в интерактивном терминале.", "Input closed. Run the script in an interactive terminal."), file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print(tr('Остановлено. Уже записанные данные сохранены.', 'Stopped. Previously written data has been saved.'))
        raise SystemExit(130)
    except Exception as exc:
        print(tr(f'СТОП: {type(exc).__name__}: {exc}\nПодробности: logs/errors.log', f'STOP: {type(exc).__name__}: {exc}\nDetails: logs/errors.log'), file=sys.stderr)
        raise SystemExit(1)
