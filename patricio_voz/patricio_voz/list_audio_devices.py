#!/usr/bin/env python3
"""Lista micrófonos PyAudio (útil para configurar Konobo / ICE)."""

import sys


def main():
    try:
        import speech_recognition as sr
    except ImportError:
        print('Instala dependencias: pip install SpeechRecognition PyAudio', file=sys.stderr)
        sys.exit(1)

    print('Índice | Nombre del dispositivo')
    print('-' * 60)
    for i, name in enumerate(sr.Microphone.list_microphone_names()):
        mark = ''
        low = (name or '').lower()
        if 'konobo' in low or 'ice' in low or 'usb' in low:
            mark = '  <-- posible Konobo USB'
        print(f'{i:6} | {name}{mark}')
    print('\nUsa en el launch: microphone_device_index:=<índice>')
    print('  o microphone_name_contains:=konobo')


if __name__ == '__main__':
    main()
