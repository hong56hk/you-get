#!/usr/bin/env python

import getopt
import json
import locale
import os
import re
import sys
from urllib import request, parse
import platform
import threading

from .version import __version__
from .util import log
from .util.strings import get_filename, unescape_html

dry_run = False
force = False
player = None
extractor_proxy = None
cookies_txt = None

fake_headers = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Charset': 'UTF-8,*;q=0.5',
    'Accept-Encoding': 'gzip,deflate,sdch',
    'Accept-Language': 'en-US,en;q=0.8',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:13.0) Gecko/20100101 Firefox/13.0'
}

if sys.stdout.isatty():
    default_encoding = sys.stdout.encoding.lower()
else:
    default_encoding = locale.getpreferredencoding().lower()

def tr(s):
    try:
        s.encode(default_encoding)
        return s
    except:
        return str(s.encode('utf-8'))[2:-1]

# DEPRECATED in favor of match1()
def r1(pattern, text):
    m = re.search(pattern, text)
    if m:
        return m.group(1)

# DEPRECATED in favor of match1()
def r1_of(patterns, text):
    for p in patterns:
        x = r1(p, text)
        if x:
            return x

def match1(text, *patterns):
    """Scans through a string for substrings matched some patterns (first-subgroups only).

    Args:
        text: A string to be scanned.
        patterns: Arbitrary number of regex patterns.

    Returns:
        When only one pattern is given, returns a string (None if no match found).
        When more than one pattern are given, returns a list of strings ([] if no match found).
    """

    if len(patterns) == 1:
        pattern = patterns[0]
        match = re.search(pattern, text)
        if match:
            return match.group(1)
        else:
            return None
    else:
        ret = []
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                ret.append(match.group(1))
        return ret

def launch_player(player, urls):
    import subprocess
    import shlex
    subprocess.call(shlex.split(player) + list(urls))

def parse_query_param(url, param):
    """Parses the query string of a URL and returns the value of a parameter.

    Args:
        url: A URL.
        param: A string representing the name of the parameter.

    Returns:
        The value of the parameter.
    """

    try:
        return parse.parse_qs(parse.urlparse(url).query)[param][0]
    except:
        return None

def unicodize(text):
    return re.sub(r'\\u([0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f])', lambda x: chr(int(x.group(0)[2:], 16)), text)

# DEPRECATED in favor of util.legitimize()
def escape_file_path(path):
    path = path.replace('/', '-')
    path = path.replace('\\', '-')
    path = path.replace('*', '-')
    path = path.replace('?', '-')
    return path

# DEPRECATED in favor of util.legitimize()
def filenameable(text):
    """Converts a string to a legal filename through various OSes.
    """
    # All POSIX systems
    text = text.translate({
        0: None,
        ord('/'): '-',
    })
    if platform.system() == 'Windows': # For Windows
        text = text.translate({
            ord(':'): '-',
            ord('*'): '-',
            ord('?'): '-',
            ord('\\'): '-',
            ord('\"'): '\'',
            ord('<'): '-',
            ord('>'): '-',
            ord('|'): '-',
            ord('+'): '-',
            ord('['): '(',
            ord(']'): ')',
        })
    else:
        if text.startswith("."):
            text = text[1:]
        if platform.system() == 'Darwin': # For Mac OS
            text = text.translate({
                ord(':'): '-',
            })
    return text

def ungzip(data):
    """Decompresses data for Content-Encoding: gzip.
    """
    from io import BytesIO
    import gzip
    buffer = BytesIO(data)
    f = gzip.GzipFile(fileobj=buffer)
    return f.read()

def undeflate(data):
    """Decompresses data for Content-Encoding: deflate.
    (the zlib compression is used.)
    """
    import zlib
    decompressobj = zlib.decompressobj(-zlib.MAX_WBITS)
    return decompressobj.decompress(data)+decompressobj.flush()

# DEPRECATED in favor of get_content()
def get_response(url, faker = False):
    if faker:
        response = request.urlopen(request.Request(url, headers = fake_headers), None)
    else:
        response = request.urlopen(url)

    data = response.read()
    if response.info().get('Content-Encoding') == 'gzip':
        data = ungzip(data)
    elif response.info().get('Content-Encoding') == 'deflate':
        data = undeflate(data)
    response.data = data
    return response

# DEPRECATED in favor of get_content()
def get_html(url, encoding = None, faker = False):
    content = get_response(url, faker).data
    return str(content, 'utf-8', 'ignore')

# DEPRECATED in favor of get_content()
def get_decoded_html(url, faker = False):
    response = get_response(url, faker)
    data = response.data
    charset = r1(r'charset=([\w-]+)', response.headers['content-type'])
    if charset:
        return data.decode(charset, 'ignore')
    else:
        return data

def get_content(url, headers={}, decoded=True):
    """Gets the content of a URL via sending a HTTP GET request.

    Args:
        url: A URL.
        headers: Request headers used by the client.
        decoded: Whether decode the response body using UTF-8 or the charset specified in Content-Type.

    Returns:
        The content as a string.
    """

    req = request.Request(url, headers=headers)
    if cookies_txt:
        cookies_txt.add_cookie_header(req)
        req.headers.update(req.unredirected_hdrs)
    response = request.urlopen(req)
    data = response.read()

    # Handle HTTP compression for gzip and deflate (zlib)
    content_encoding = response.getheader('Content-Encoding')
    if content_encoding == 'gzip':
        data = ungzip(data)
    elif content_encoding == 'deflate':
        data = undeflate(data)

    # Decode the response body
    if decoded:
        charset = match1(response.getheader('Content-Type'), r'charset=([\w-]+)')
        if charset is not None:
            data = data.decode(charset)
        else:
            data = data.decode('utf-8')

    return data

def url_size(url, faker = False):
    if faker:
        response = request.urlopen(request.Request(url, headers = fake_headers), None)
    else:
        response = request.urlopen(url)

    size = int(response.headers['content-length'])
    return size

# TO BE DEPRECATED
# urls_size() does not have a faker
# also it takes too long time
def urls_size(urls):
    return sum(map(url_size, urls))

def url_info(url, faker = False):
    if faker:
        response = request.urlopen(request.Request(url, headers = fake_headers), None)
    else:
        response = request.urlopen(request.Request(url))

    headers = response.headers

    type = headers['content-type']
    mapping = {
        'video/3gpp': '3gp',
        'video/f4v': 'flv',
        'video/mp4': 'mp4',
        'video/MP2T': 'ts',
        'video/quicktime': 'mov',
        'video/webm': 'webm',
        'video/x-flv': 'flv',
        'video/x-ms-asf': 'asf',
        'audio/mpeg': 'mp3'
    }
    if type in mapping:
        ext = mapping[type]
    else:
        type = None
        if headers['content-disposition']:
            try:
                filename = parse.unquote(r1(r'filename="?([^"]+)"?', headers['content-disposition']))
                if len(filename.split('.')) > 1:
                    ext = filename.split('.')[-1]
                else:
                    ext = None
            except:
                ext = None
        else:
            ext = None

    if headers['transfer-encoding'] != 'chunked':
        size = int(headers['content-length'])
    else:
        size = None

    return type, ext, size

def url_locations(urls, faker = False):
    locations = []
    for url in urls:
        if faker:
            response = request.urlopen(request.Request(url, headers = fake_headers), None)
        else:
            response = request.urlopen(request.Request(url))

        locations.append(response.url)
    return locations

def url_save(url, filepath, bar, refer = None, is_part = False, faker = False):
    file_size = url_size(url, faker = faker)

    if os.path.exists(filepath):
        if not force and file_size == os.path.getsize(filepath):
            if not is_part:
                if bar:
                    bar.done()
                print('Skipping %s: file already exists' % tr(os.path.basename(filepath)))
            else:
                if bar:
                    bar.update_received(file_size)
            return
        else:
            if not is_part:
                if bar:
                    bar.done()
                print('Overwriting %s' % tr(os.path.basename(filepath)), '...')
    elif not os.path.exists(os.path.dirname(filepath)):
        os.mkdir(os.path.dirname(filepath))

    temp_filepath = filepath + '.download'
    received = 0
    if not force:
        open_mode = 'ab'

        if os.path.exists(temp_filepath):
            received += os.path.getsize(temp_filepath)
            if bar:
                bar.update_received(os.path.getsize(temp_filepath))
    else:
        open_mode = 'wb'

    if received < file_size:
        if faker:
            headers = fake_headers
        else:
            headers = {}
        if received:
            headers['Range'] = 'bytes=' + str(received) + '-'
        if refer:
            headers['Referer'] = refer

        response = request.urlopen(request.Request(url, headers = headers), None)
        try:
            range_start = int(response.headers['content-range'][6:].split('/')[0].split('-')[0])
            end_length = end = int(response.headers['content-range'][6:].split('/')[1])
            range_length = end_length - range_start
        except:
            range_length = int(response.headers['content-length'])

        if file_size != received + range_length:
            received = 0
            if bar:
                bar.received = 0
            open_mode = 'wb'

        with open(temp_filepath, open_mode) as output:
            while True:
                buffer = response.read(1024 * 256)
                if not buffer:
                    if received == file_size: # Download finished
                        break
                    else: # Unexpected termination. Retry request
                        headers['Range'] = 'bytes=' + str(received) + '-'
                        response = request.urlopen(request.Request(url, headers = headers), None)
                output.write(buffer)
                received += len(buffer)
                if bar:
                    bar.update_received(len(buffer))

    assert received == os.path.getsize(temp_filepath), '%s == %s == %s' % (received, os.path.getsize(temp_filepath), temp_filepath)

    if os.access(filepath, os.W_OK):
        os.remove(filepath) # on Windows rename could fail if destination filepath exists
    os.rename(temp_filepath, filepath)

def url_save_chunked(url, filepath, bar, refer = None, is_part = False, faker = False):
    if os.path.exists(filepath):
        if not force:
            if not is_part:
                if bar:
                    bar.done()
                print('Skipping %s: file already exists' % tr(os.path.basename(filepath)))
            else:
                if bar:
                    bar.update_received(os.path.getsize(filepath))
            return
        else:
            if not is_part:
                if bar:
                    bar.done()
                print('Overwriting %s' % tr(os.path.basename(filepath)), '...')
    elif not os.path.exists(os.path.dirname(filepath)):
        os.mkdir(os.path.dirname(filepath))

    temp_filepath = filepath + '.download'
    received = 0
    if not force:
        open_mode = 'ab'

        if os.path.exists(temp_filepath):
            received += os.path.getsize(temp_filepath)
            if bar:
                bar.update_received(os.path.getsize(temp_filepath))
    else:
        open_mode = 'wb'

    if faker:
        headers = fake_headers
    else:
        headers = {}
    if received:
        headers['Range'] = 'bytes=' + str(received) + '-'
    if refer:
        headers['Referer'] = refer

    response = request.urlopen(request.Request(url, headers = headers), None)

    with open(temp_filepath, open_mode) as output:
        while True:
            buffer = response.read(1024 * 256)
            if not buffer:
                break
            output.write(buffer)
            received += len(buffer)
            if bar:
                bar.update_received(len(buffer))

    assert received == os.path.getsize(temp_filepath), '%s == %s == %s' % (received, os.path.getsize(temp_filepath))

    if os.access(filepath, os.W_OK):
        os.remove(filepath) # on Windows rename could fail if destination filepath exists
    os.rename(temp_filepath, filepath)

class SimpleProgressBar:
    def __init__(self, total_size, total_pieces = 1):
        self.displayed = False
        self.total_size = total_size
        self.total_pieces = total_pieces
        self.current_piece = 1
        self.received = 0

    def update(self):
        self.displayed = True
        bar_size = 40
        percent = round(self.received * 100 / self.total_size, 1)
        if percent > 100:
            percent = 100
        dots = bar_size * int(percent) // 100
        plus = int(percent) - dots // bar_size * 100
        if plus > 0.8:
            plus = '='
        elif plus > 0.4:
            plus = '>'
        else:
            plus = ''
        bar = '=' * dots + plus
        bar = '{0:>5}% ({1:>5}/{2:<5}MB) [{3:<40}] {4}/{5}'.format(percent, round(self.received / 1048576, 1), round(self.total_size / 1048576, 1), bar, self.current_piece, self.total_pieces)
        sys.stdout.write('\r' + bar)
        sys.stdout.flush()

    def update_received(self, n):
        self.received += n
        self.update()

    def update_piece(self, n):
        self.current_piece = n

    def done(self):
        if self.displayed:
            print()
            self.displayed = False

class PiecesProgressBar:
    def __init__(self, total_size, total_pieces = 1):
        self.displayed = False
        self.total_size = total_size
        self.total_pieces = total_pieces
        self.current_piece = 1
        self.received = 0

    def update(self):
        self.displayed = True
        bar = '{0:>5}%[{1:<40}] {2}/{3}'.format('?', '?' * 40, self.current_piece, self.total_pieces)
        sys.stdout.write('\r' + bar)
        sys.stdout.flush()

    def update_received(self, n):
        self.received += n
        self.update()

    def update_piece(self, n):
        self.current_piece = n

    def done(self):
        if self.displayed:
            print()
            self.displayed = False

class DummyProgressBar:
    def __init__(self, *args):
        pass
    def update_received(self, n):
        pass
    def update_piece(self, n):
        pass
    def done(self):
        pass

def download_urls(urls, title, ext, total_size, output_dir='.', refer=None, merge=True, faker=False):
    assert urls
    if dry_run:
        print('Real URLs:\n%s\n' % urls)
        return

    if player:
        launch_player(player, urls)
        return

    if not total_size:
        try:
            total_size = urls_size(urls)
        except:
            import traceback
            import sys
            traceback.print_exc(file = sys.stdout)
            pass

    title = get_filename(title)

    filename = '%s.%s' % (title, ext)
    filepath = os.path.join(output_dir, filename)
    if total_size:
        if not force and os.path.exists(filepath) and os.path.getsize(filepath) >= total_size * 0.9:
            print('Skipping %s: file already exists' % tr(filepath))
            print()
            return
        bar = SimpleProgressBar(total_size, len(urls))
    else:
        bar = PiecesProgressBar(total_size, len(urls))

    if len(urls) == 1:
        url = urls[0]
        print('Downloading %s ...' % tr(filename))
        url_save(url, filepath, bar, refer = refer, faker = faker)
        bar.done()
    else:
        parts = []
        print('Downloading %s.%s ...' % (tr(title), ext))
        for i, url in enumerate(urls):
            filename = '%s[%02d].%s' % (title, i, ext)
            filepath = os.path.join(output_dir, filename)
            parts.append(filepath)
            #print 'Downloading %s [%s/%s]...' % (tr(filename), i + 1, len(urls))
            bar.update_piece(i + 1)
            url_save(url, filepath, bar, refer = refer, is_part = True, faker = faker)
        bar.done()

        if not merge:
            print()
            return
        if ext == 'flv':
            try:
                from .processor.ffmpeg import has_ffmpeg_installed
                if has_ffmpeg_installed():
                    from .processor.ffmpeg import ffmpeg_concat_flv_to_mp4
                    ffmpeg_concat_flv_to_mp4(parts, os.path.join(output_dir, title + '.mp4'))
                else:
                    from .processor.join_flv import concat_flv
                    concat_flv(parts, os.path.join(output_dir, title + '.flv'))
            except:
                raise
            else:
                for part in parts:
                    os.remove(part)

        elif ext == 'mp4':
            try:
                from .processor.ffmpeg import has_ffmpeg_installed
                if has_ffmpeg_installed():
                    from .processor.ffmpeg import ffmpeg_concat_mp4_to_mp4
                    ffmpeg_concat_mp4_to_mp4(parts, os.path.join(output_dir, title + '.mp4'))
                else:
                    from .processor.join_mp4 import concat_mp4
                    concat_mp4(parts, os.path.join(output_dir, title + '.mp4'))
            except:
                raise
            else:
                for part in parts:
                    os.remove(part)

        else:
            print("Can't merge %s files" % ext)

    print()

def download_urls_chunked(urls, title, ext, total_size, output_dir='.', refer=None, merge=True, faker=False):
    assert urls
    if dry_run:
        print('Real URLs:\n%s\n' % urls)
        return

    if player:
        launch_player(player, urls)
        return

    assert ext in ('ts')

    title = get_filename(title)

    filename = '%s.%s' % (title, 'ts')
    filepath = os.path.join(output_dir, filename)
    if total_size:
        if not force and os.path.exists(filepath[:-3] + '.mkv'):
            print('Skipping %s: file already exists' % tr(filepath[:-3] + '.mkv'))
            print()
            return
        bar = SimpleProgressBar(total_size, len(urls))
    else:
        bar = PiecesProgressBar(total_size, len(urls))

    if len(urls) == 1:
        parts = []
        url = urls[0]
        print('Downloading %s ...' % tr(filename))
        filepath = os.path.join(output_dir, filename)
        parts.append(filepath)
        url_save_chunked(url, filepath, bar, refer = refer, faker = faker)
        bar.done()

        if not merge:
            print()
            return
        if ext == 'ts':
            from .processor.ffmpeg import has_ffmpeg_installed
            if has_ffmpeg_installed():
                from .processor.ffmpeg import ffmpeg_convert_ts_to_mkv
                if ffmpeg_convert_ts_to_mkv(parts, os.path.join(output_dir, title + '.mkv')):
                    for part in parts:
                        os.remove(part)
                else:
                    os.remove(os.path.join(output_dir, title + '.mkv'))
            else:
                print('No ffmpeg is found. Conversion aborted.')
        else:
            print("Can't convert %s files" % ext)
    else:
        parts = []
        print('Downloading %s.%s ...' % (tr(title), ext))
        for i, url in enumerate(urls):
            filename = '%s[%02d].%s' % (title, i, ext)
            filepath = os.path.join(output_dir, filename)
            parts.append(filepath)
            #print 'Downloading %s [%s/%s]...' % (tr(filename), i + 1, len(urls))
            bar.update_piece(i + 1)
            url_save_chunked(url, filepath, bar, refer = refer, is_part = True, faker = faker)
        bar.done()

        if not merge:
            print()
            return
        if ext == 'ts':
            from .processor.ffmpeg import has_ffmpeg_installed
            if has_ffmpeg_installed():
                from .processor.ffmpeg import ffmpeg_concat_ts_to_mkv
                if ffmpeg_concat_ts_to_mkv(parts, os.path.join(output_dir, title + '.mkv')):
                    for part in parts:
                        os.remove(part)
                else:
                    os.remove(os.path.join(output_dir, title + '.mkv'))
            else:
                print('No ffmpeg is found. Merging aborted.')
        else:
            print("Can't merge %s files" % ext)

    print()

def download_rtmp_url(url,title, ext,params={}, total_size=0, output_dir='.', refer=None, merge=True, faker=False):
    assert url
    if dry_run:
        print('Real URL:\n%s\n' % [url])
        if params.get("-y",False): #None or unset ->False
            print('Real Playpath:\n%s\n' % [params.get("-y")])
        return

    if player:
        from .processor.rtmpdump import play_rtmpdump_stream
        play_rtmpdump_stream(player, url, params)
        return

    from .processor.rtmpdump import has_rtmpdump_installed, download_rtmpdump_stream
    assert has_rtmpdump_installed(), "RTMPDump not installed."
    download_rtmpdump_stream(url,  title, ext,params, output_dir)

def playlist_not_supported(name):
    def f(*args, **kwargs):
        raise NotImplementedError('Playlist is not supported for ' + name)
    return f

def print_info(site_info, title, type, size):
    if type:
        type = type.lower()
    if type in ['3gp']:
        type = 'video/3gpp'
    elif type in ['asf', 'wmv']:
        type = 'video/x-ms-asf'
    elif type in ['flv', 'f4v']:
        type = 'video/x-flv'
    elif type in ['mkv']:
        type = 'video/x-matroska'
    elif type in ['mp3']:
        type = 'audio/mpeg'
    elif type in ['mp4']:
        type = 'video/mp4'
    elif type in ['mov']:
        type = 'video/quicktime'
    elif type in ['ts']:
        type = 'video/MP2T'
    elif type in ['webm']:
        type = 'video/webm'

    if type in ['video/3gpp']:
        type_info = "3GPP multimedia file (%s)" % type
    elif type in ['video/x-flv', 'video/f4v']:
        type_info = "Flash video (%s)" % type
    elif type in ['video/mp4', 'video/x-m4v']:
        type_info = "MPEG-4 video (%s)" % type
    elif type in ['video/MP2T']:
        type_info = "MPEG-2 transport stream (%s)" % type
    elif type in ['video/webm']:
        type_info = "WebM video (%s)" % type
    #elif type in ['video/ogg']:
    #    type_info = "Ogg video (%s)" % type
    elif type in ['video/quicktime']:
        type_info = "QuickTime video (%s)" % type
    elif type in ['video/x-matroska']:
        type_info = "Matroska video (%s)" % type
    #elif type in ['video/x-ms-wmv']:
    #    type_info = "Windows Media video (%s)" % type
    elif type in ['video/x-ms-asf']:
        type_info = "Advanced Systems Format (%s)" % type
    #elif type in ['video/mpeg']:
    #    type_info = "MPEG video (%s)" % type
    elif type in ['audio/mpeg']:
        type_info = "MP3 (%s)" % type
    else:
        type_info = "Unknown type (%s)" % type

    print("Video Site:", site_info)
    print("Title:     ", unescape_html(tr(title)))
    print("Type:      ", type_info)
    print("Size:      ", round(size / 1048576, 2), "MiB (" + str(size) + " Bytes)")
    print()

def parse_host(host):
    """Parses host name and port number from a string.
    """
    if re.match(r'^(\d+)$', host) is not None:
        return ("0.0.0.0", int(host))
    if re.match(r'^(\w+)://', host) is None:
        host = "//" + host
    o = parse.urlparse(host)
    hostname = o.hostname or "0.0.0.0"
    port = o.port or 0
    return (hostname, port)

def set_proxy(proxy):
    proxy_handler = request.ProxyHandler({
        'http': '%s:%s' % proxy,
        'https': '%s:%s' % proxy,
    })
    opener = request.build_opener(proxy_handler)
    request.install_opener(opener)

def unset_proxy():
    proxy_handler = request.ProxyHandler({})
    opener = request.build_opener(proxy_handler)
    request.install_opener(opener)

# DEPRECATED in favor of set_proxy() and unset_proxy()
def set_http_proxy(proxy):
    if proxy == None: # Use system default setting
        proxy_support = request.ProxyHandler()
    elif proxy == '': # Don't use any proxy
        proxy_support = request.ProxyHandler({})
    else: # Use proxy
        proxy_support = request.ProxyHandler({'http': '%s' % proxy, 'https': '%s' % proxy})
    opener = request.build_opener(proxy_support)
    request.install_opener(opener)

def download_main(download, download_playlist, urls, playlist, **kwargs):
    for url in urls:
        if url.startswith('https://'):
            url = url[8:]
        if not url.startswith('http://'):
            url = 'http://' + url

        if playlist:
            download_playlist(url, **kwargs)
        else:
            download(url, **kwargs)

def script_main(script_name, download, download_playlist = None):
    version = 'You-Get %s, a video downloader.' % get_version()
    help = 'Usage: %s [OPTION]... [URL]...\n' % script_name
    help += '''\nStartup options:
    -V | --version                           Display the version and exit.
    -h | --help                              Print this help and exit.
    '''
    help += '''\nDownload options (use with URLs):
    -f | --force                             Force overwriting existed files.
    -i | --info                              Display the information of videos without downloading.
    -u | --url                               Display the real URLs of videos without downloading.
    -c | --cookies                           Load NetScape's cookies.txt file.
    -n | --no-merge                          Don't merge video parts.
    -F | --format <STREAM_ID>                Video format code.
    -o | --output-dir <PATH>                 Set the output directory for downloaded videos.
    -p | --player <PLAYER [options]>         Directly play the video with PLAYER like vlc/smplayer.
    -x | --http-proxy <HOST:PORT>            Use specific HTTP proxy for downloading.
    -y | --extractor-proxy <HOST:PORT>       Use specific HTTP proxy for extracting stream data.
         --no-proxy                          Don't use any proxy. (ignore $http_proxy)
         --debug                             Show traceback on KeyboardInterrupt.
    '''

    short_opts = 'Vhfiuc:nF:o:p:x:y:'
    opts = ['version', 'help', 'force', 'info', 'url', 'cookies', 'no-merge', 'no-proxy', 'debug', 'format=', 'stream=', 'itag=', 'output-dir=', 'player=', 'http-proxy=', 'extractor-proxy=', 'lang=']
    if download_playlist:
        short_opts = 'l' + short_opts
        opts = ['playlist'] + opts

    try:
        opts, args = getopt.getopt(sys.argv[1:], short_opts, opts)
    except getopt.GetoptError as err:
        log.e(err)
        log.e("try 'you-get --help' for more options")
        sys.exit(2)

    global force
    global dry_run
    global player
    global extractor_proxy
    global cookies_txt
    cookies_txt = None

    info_only = False
    playlist = False
    merge = True
    stream_id = None
    lang = None
    output_dir = '.'
    proxy = None
    extractor_proxy = None
    traceback = False
    for o, a in opts:
        if o in ('-V', '--version'):
            print(version)
            sys.exit()
        elif o in ('-h', '--help'):
            print(version)
            print(help)
            sys.exit()
        elif o in ('-f', '--force'):
            force = True
        elif o in ('-i', '--info'):
            info_only = True
        elif o in ('-u', '--url'):
            dry_run = True
        elif o in ('-c', '--cookies'):
            from http import cookiejar
            cookies_txt = cookiejar.MozillaCookieJar(a)
            cookies_txt.load()
        elif o in ('-l', '--playlist'):
            playlist = True
        elif o in ('-n', '--no-merge'):
            merge = False
        elif o in ('--no-proxy',):
            proxy = ''
        elif o in ('--debug',):
            traceback = True
        elif o in ('-F', '--format', '--stream', '--itag'):
            stream_id = a
        elif o in ('-o', '--output-dir'):
            output_dir = a
        elif o in ('-p', '--player'):
            player = a
        elif o in ('-x', '--http-proxy'):
            proxy = a
        elif o in ('-y', '--extractor-proxy'):
            extractor_proxy = a
        elif o in ('--lang',):
            lang = a
        else:
            log.e("try 'you-get --help' for more options")
            sys.exit(2)
    if not args:
        print(help)
        sys.exit()

    set_http_proxy(proxy)

    try:
        if stream_id:
            download_main(download, download_playlist, args, playlist, stream_id=stream_id, lang=lang, output_dir=output_dir, merge=merge, info_only=info_only)
        else:
            download_main(download, download_playlist, args, playlist, lang=lang, output_dir=output_dir, merge=merge, info_only=info_only)
    except KeyboardInterrupt:
        if traceback:
            raise
        else:
            sys.exit(1)



def mime_to_container(mime):
    mapping = {
        'video/3gpp': '3gp',
        'video/mp4': 'mp4',
        'video/webm': 'webm',
        'video/x-flv': 'flv',
    }
    if mime in mapping:
        return mapping[mime]
    else:
        return mime.split('/')[1]



class VideoExtractor():
    def __init__(self, *args):
        self.url = None
        self.title = None
        self.vid = None
        self.streams = {}
        self.streams_sorted = []
        self.audiolang = None

        if args:
            self.url = args[0]

    def download_by_url(self, url, **kwargs):
        self.url = url

        global extractor_proxy
        if extractor_proxy:
            set_proxy(parse_host(extractor_proxy))
        self.prepare(**kwargs)

        try:
            self.streams_sorted = [dict([('id', stream_type['id'])] + list(self.streams[stream_type['id']].items())) for stream_type in self.__class__.stream_types if stream_type['id'] in self.streams]
        except:
            self.streams_sorted = [dict([('itag', stream_type['itag'])] + list(self.streams[stream_type['itag']].items())) for stream_type in self.__class__.stream_types if stream_type['itag'] in self.streams]

        self.extract(**kwargs)
        if extractor_proxy:
            unset_proxy()

        self.download(**kwargs)

    def download_by_vid(self, vid, **kwargs):
        self.vid = vid

        global extractor_proxy
        if extractor_proxy:
            set_proxy(parse_host(extractor_proxy))
        self.prepare(**kwargs)

        try:
            self.streams_sorted = [dict([('id', stream_type['id'])] + list(self.streams[stream_type['id']].items())) for stream_type in self.__class__.stream_types if stream_type['id'] in self.streams]
        except:
            self.streams_sorted = [dict([('itag', stream_type['itag'])] + list(self.streams[stream_type['itag']].items())) for stream_type in self.__class__.stream_types if stream_type['itag'] in self.streams]

        self.extract(**kwargs)
        if extractor_proxy:
            unset_proxy()

        self.download(**kwargs)

    def prepare(self, **kwargs):
        pass
        #raise NotImplementedError()

    def extract(self, **kwargs):
        pass
        #raise NotImplementedError()

    def p_stream(self, stream_id):
        stream = self.streams[stream_id]
        if 'itag' in stream:
            print("    - itag:          \033[7m%s\033[0m" % stream_id)
        else:
            print("    - format:        \033[7m%s\033[0m" % stream_id)

        if 'container' in stream:
            print("      container:     %s" % stream['container'])

        if 'video_profile' in stream:
            print("      video-profile: %s" % stream['video_profile'])

        if 'quality' in stream:
            print("      quality:       %s" % stream['quality'])

        if 'size' in stream:
            print("      size:          %s MiB (%s bytes)" % (round(stream['size'] / 1048576, 1), stream['size']))

        if 'itag' in stream:
            print("    # download-with: \033[4myou-get --itag=%s [URL]\033[0m" % stream_id)
        else:
            print("    # download-with: \033[4myou-get --format=%s [URL]\033[0m" % stream_id)

        print()

    def p_i(self, stream_id):
        stream = self.streams[stream_id]
        print("    - title:         %s" % self.title)
        print("       size:         %s MiB (%s bytes)" % (round(stream['size'] / 1048576, 1), stream['size']))
        print("        url:         %s" % self.url)
        print()

    def p(self, stream_id=None):
        print("site:                %s" % self.__class__.name)
        print("title:               %s" % self.title)
        if stream_id:
            # Print the stream
            print("stream:")
            self.p_stream(stream_id)

        elif stream_id is None:
            # Print stream with best quality
            print("stream:              # Best quality")
            stream_id = self.streams_sorted[0]['id'] if 'id' in self.streams_sorted[0] else self.streams_sorted[0]['itag']
            self.p_stream(stream_id)

        elif stream_id == []:
            # Print all available streams
            print("streams:             # Available quality and codecs")
            for stream in self.streams_sorted:
                self.p_stream(stream['id'] if 'id' in stream else stream['itag'])

        if self.audiolang:
            print("audio-languages:")
            for i in self.audiolang:
                print("    - lang:          {}".format(i['lang']))
                print("      download-url:  {}\n".format(i['url']))

    def p_playlist(self, stream_id=None):
        print("site:                %s" % self.__class__.name)
        print("playlist:            %s" % self.title)
        print("videos:")

    def download(self, **kwargs):
        if 'info_only' in kwargs and kwargs['info_only']:
            if 'stream_id' in kwargs and kwargs['stream_id']:
                # Display the stream
                stream_id = kwargs['stream_id']
                if 'index' not in kwargs:
                    self.p(stream_id)
                else:
                    self.p_i(stream_id)
            else:
                # Display all available streams
                if 'index' not in kwargs:
                    self.p([])
                else:
                    stream_id = self.streams_sorted[0]['id'] if 'id' in self.streams_sorted[0] else self.streams_sorted[0]['itag']
                    self.p_i(stream_id)

        else:
            if 'stream_id' in kwargs and kwargs['stream_id']:
                # Download the stream
                stream_id = kwargs['stream_id']
            else:
                # Download stream with the best quality
                stream_id = self.streams_sorted[0]['id'] if 'id' in self.streams_sorted[0] else self.streams_sorted[0]['itag']

            if 'index' not in kwargs:
                self.p(None)
            else:
                self.p_i(stream_id)

            urls = self.streams[stream_id]['src']
            if not urls:
                log.e('[Failed] Cannot extract video source.')
                log.e('This is most likely because the video has not been made available in your country.')
                log.e('You may try to use a proxy via \'-y\' for extracting stream data.')
                exit(1)
            download_urls(urls, self.title, self.streams[stream_id]['container'], self.streams[stream_id]['size'], output_dir=kwargs['output_dir'], merge=kwargs['merge'])

        self.__init__()
