"""Open the local RE:VERSE app, reusing its server if it is already running."""
import os
import socket
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def is_reverse(url):
    try:
        with urlopen(url, timeout=2) as response:
            return b'<title>RE:VERSE' in response.read(16384)
    except (URLError, OSError):
        return False


def main():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / '.env')
    port=int(os.environ.get('PORT','5001'))
    if not 1<=port<=65535:
        raise ValueError('PORT는 1~65535 사이여야 합니다.')
    url=f'http://127.0.0.1:{port}'
    if is_reverse(url):
        print('실행 중인 RE:VERSE를 브라우저에서 엽니다.')
        webbrowser.open(url)
        return
    # Never stop or replace an unrelated program occupying this port.
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',port))==0:
            raise RuntimeError(f'{port} 포트를 다른 프로그램이 사용 중입니다. .env의 PORT를 바꿔 주세요.')
    from werkzeug.serving import make_server
    from run import prepare_app
    server=make_server('127.0.0.1',port,prepare_app(),threaded=True)
    print(f'RE:VERSE 실행: {url}\n이 창을 열어 두세요. 종료하려면 Ctrl+C를 누르세요.')
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        print(f'실행하지 못했습니다: {error}')
        raise SystemExit(1)
