"""Stage 12 Telegram entry point.

Stage 12 changes the desktop/dashboard read model and GUI. Telegram transport and
its hardened timeout/retry behavior intentionally remain the proven Stage 10/9.1
implementation.
"""
from telegram_stage10 import main

if __name__ == '__main__':
    main()
