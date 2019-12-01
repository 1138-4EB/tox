"""

Helper functions for writing to terminals and files.

"""


import unicodedata
from os import environ
from os import name as os_name
import py
from sys import platform, version_info
from py.builtin import text, bytes
py3k = version_info[0] >= 3
py33 = version_info >= (3, 3)


IS_WINDOWS = platform == "win32"


class TerminalWriter(object):

    def __init__(self, file=None, encoding=None):
        if file is None:
            from sys import stdout as file
        elif py.builtin.callable(file) and not (
             hasattr(file, "write") and hasattr(file, "flush")):
            file = WriteFile(file, encoding=encoding)

        colors = environ.get('PY_COLORS')
        if colors:
            self.hasmarkup = colors != '0' and colors != 'false'
        else:
            self.hasmarkup = hasattr(file, 'isatty') and file.isatty() \
                             and environ.get('TERM') != 'dumb' \
                             and not (platform.startswith('java') and os_name == 'nt')

        if IS_WINDOWS:
            try:
                import colorama
                file = colorama.AnsiToWin32(file).stream
                if self.hasmarkup:
                    environ['PYCHARM_HOSTED'] = '1'
            except ImportError:
                pass
                print("INFO: Install colorama to support win32 coloured logs")

        self.encoding = encoding or getattr(file, 'encoding', "utf-8")
        self._file = file

        class CurrentLine:
            def __init__(self):
                self.chars = 0
                self.width = 0

        self._current_line = CurrentLine()

    @property
    def fullwidth(self):
        if hasattr(self, '_terminal_width'):
            return self._terminal_width

        width = 0
        try:
            if py33:
                import shutil
                width = shutil.get_terminal_size().columns
            else:
                import termios, fcntl, struct
                call = fcntl.ioctl(1, termios.TIOCGWINSZ, "\000" * 8)
                _, width = struct.unpack("hhhh", call)[:2]
        except py.builtin._sysex:
            raise
        except:
            pass

        if width == 0:
            # * some exception happened
            # * or this is emacs terminal which reports (0,0)
            width = int(environ.get('COLUMNS', 80))
        elif width < 40:
            # XXX the windows getdimensions may be bogus, let's sanify a bit
            width = 80
        return width

    @fullwidth.setter
    def fullwidth(self, value):
        self._terminal_width = value

    def sep(self, sepchar, title=None, fullwidth=None, **kw):
        if fullwidth is None:
            fullwidth = self.fullwidth
        # the goal is to have the line be as long as possible
        # under the condition that len(line) <= fullwidth
        if IS_WINDOWS:
            # if we print in the last column on windows we are on a
            # new line but there is no way to verify/neutralize this
            # (we may not know the exact line width)
            # so let's be defensive to avoid empty lines in the output
            fullwidth -= 1
        if title is not None:
            # we want 2 + 2*len(fill) + len(title) <= fullwidth
            # i.e.    2 + 2*len(sepchar)*N + len(title) <= fullwidth
            #         2*len(sepchar)*N <= fullwidth - len(title) - 2
            #         N <= (fullwidth - len(title) - 2) // (2*len(sepchar))
            N = max((fullwidth - len(title) - 2) // (2*len(sepchar)), 1)
            fill = sepchar * N
            line = "%s %s %s" % (fill, title, fill)
        else:
            # we want len(sepchar)*N <= fullwidth
            # i.e.    N <= fullwidth // len(sepchar)
            line = sepchar * (fullwidth // len(sepchar))
        # in some situations there is room for an extra sepchar at the right,
        # in particular if we consider that with a sepchar like "_ " the
        # trailing space is not important at the end of the line
        if len(line) + len(sepchar.rstrip()) <= fullwidth:
            line += sepchar.rstrip()

        self.write(line, **kw)
        self.write('\n')

    def write(self, msg, **kw):
        if msg:
            if not isinstance(msg, (bytes, text)):
                msg = text(msg)

            # update chars on current line
            newline = b'\n' if isinstance(msg, bytes) else '\n'
            current_line = msg.rsplit(newline, 1)[-1]
            if isinstance(current_line, bytes):
                current_line = current_line.decode('utf-8', errors='replace')

            char_width = {
                'A': 1,   # "Ambiguous"
                'F': 2,   # Fullwidth
                'H': 1,   # Halfwidth
                'N': 1,   # Neutral
                'Na': 1,  # Narrow
                'W': 2,   # Wide
            }
            width = sum(char_width.get(
                unicodedata.east_asian_width(c), 1) for c in
                unicodedata.normalize('NFC', current_line)
            )
            length = len(current_line)

            if newline in msg:
                self._current_line.chars = length
                self._current_line.width = width
            else:
                self._current_line.chars += length
                self._current_line.width += width

            if self.hasmarkup and kw:
                _esctable = dict(
                    black=30, red=31,    green=32, yellow=33,
                    blue=34,  purple=35, cyan=36,  white=37,
                    Black=40, Red=41,    Green=42, Yellow=43,
                    Blue=44,  Purple=45, Cyan=46,  White=47,
                    bold=1,   light=2,   blink=5,  invert=7
                )
                esc = []
                for name in kw:
                    if name not in _esctable:
                        raise ValueError("unknown markup: %r" %(name,))
                    if kw[name]:
                        esc.append(_esctable[name])

                if tuple(esc):
                    msg = (''.join(['\x1b[%sm' % cod for cod in tuple(esc)]) + msg + '\x1b[0m')

            try:
                # on py27 and above writing out to sys.stdout with an encoding
                # should usually work for unicode messages (if the encoding is
                # capable of it)
                self._file.write(msg)
            except UnicodeEncodeError:
                # on py26 it might not work because stdout expects bytes
                if self._file.encoding:
                    try:
                        self._file.write(msg.encode(self._file.encoding))
                    except UnicodeEncodeError:
                        # it might still fail if the encoding is not capable
                        pass
                    else:
                        self._file.flush()
                        return
                # fallback: escape all unicode characters
                msg = markupmsg.encode("unicode-escape").decode("ascii")
                self._file.write(msg)
            self._file.flush()


class WriteFile(object):
    def __init__(self, writemethod, encoding=None):
        self.encoding = encoding
        self._writemethod = writemethod

    def write(self, data):
        if self.encoding:
            data = data.encode(self.encoding, "replace")
        self._writemethod(data)

    def flush(self):
        return
