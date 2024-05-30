"""

+-+-+-+-+-------+-+-------------+-------------------------------+
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-------+-+-------------+-------------------------------+
|F|R|R|R| opcode|M| Payload len |    Extended payload length    |
|I|S|S|S|  (4)  |A|     (7)     |             (16/64)           |
|N|V|V|V|       |S|             |   (if payload len==126/127)   |
| |1|2|3|       |K|             |                               |
+-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
|     Extended payload length continued, if payload len == 127  |
+ - - - - - - - - - - - - - - - +-------------------------------+
|                     Payload Data continued ...                |
+---------------------------------------------------------------+

###
+-+-+-+-+-------+-+-------------+-
|F|R|R|R| opcode|M| Payload len |  
|I|S|S|S|  (4)  |A|     (7)     |  
|N|V|V|V|       |S|             | 
| |1|2|3|       |K|             |
+-+-+-+-+-------+-+-------------+

可以根据需要扩展,仅仅是简单的逻辑demo

"""
import base64,hashlib,zlib,struct,socket,flask

SUPPORTED_VERSIONS = ("13", "8", "7")
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


# websocket OPCODES
OPCODE_CONTINUATION = 0x00
OPCODE_TEXT = 0x01
OPCODE_BINARY = 0x02
OPCODE_CLOSE = 0x08
OPCODE_PING = 0x09
OPCODE_PONG = 0x0A
FIN_MASK = 0x80
OPCODE_MASK = 0x0F
MASK_MASK = 0x80
LENGTH_MASK = 0x7F
RSV0_MASK = 0x40
RSV1_MASK = 0x20
RSV2_MASK = 0x10
HEADER_FLAG_MASK = RSV0_MASK | RSV1_MASK | RSV2_MASK



class WebSocketObj(object):
    """
    Base class for supporting websocket operations.
    """

    origin = None
    protocol = None
    version = None
    path = None

    def __init__(self, environ, read, write, handler, do_compress,on_ping=None,on_pong=None,on_close=None,on_message=None,on_error=None,on_connect=None) -> None:
        self.environ = environ
        self.closed = False
        self.write = write
        self.read = read
        self.handler = handler
        self.do_compress = do_compress
        self.origin = self.environ.get(
            "HTTP_SEC_WEBSOCKET_ORIGIN") or self.environ.get("HTTP_ORIGIN")
        self.protocols = list(
            map(str.strip,
                self.environ.get("HTTP_SEC_WEBSOCKET_PROTOCOL","").split(",")))
        self.version = int(
            self.environ.get("HTTP_SEC_WEBSOCKET_VERSION", "0").strip())
        self.path = self.environ.get("PATH_INFO", "/")
        if do_compress:
            self.compressor = zlib.compressobj(7, zlib.DEFLATED,-zlib.MAX_WBITS)
            self.decompressor = zlib.decompressobj(-zlib.MAX_WBITS)

        self.on_ping = on_ping
        self.on_pong = on_pong
        self.on_close = on_close
        self.on_message = on_message
        self.on_error = on_error
        self.on_connect = on_connect

    def receive(self):
        while not self.closed:
            self.read_message()
        if self.on_close:
            self.on_close(self)

    def read_message(self):
        opcode = None
        message = bytearray()

        while True:
            data = self.read(2)
            if len(data) != 2:
                first_byte, second_byte = 0, 0
            else:
                first_byte, second_byte = struct.unpack("!BB", data)

            fin = first_byte & FIN_MASK
            f_opcode = first_byte & OPCODE_MASK
            flags = first_byte & HEADER_FLAG_MASK
            length = second_byte & LENGTH_MASK
            has_mask = second_byte & MASK_MASK == MASK_MASK

            if f_opcode > 0x07:
                if not fin:
                    raise RuntimeError(
                        "Received fragmented control frame: {0!r}".format(
                            data))
                # Control frames MUST have a payload length of 125 bytes or less
                if length > 125:
                    raise RuntimeError(
                        "Control frame cannot be larger than 125 bytes: "
                        "{0!r}".format(data))

            if length == 126:
                # 16 bit length
                data = self.read(2)
                if len(data) != 2:
                    raise RuntimeError(
                        "Unexpected EOF while decoding header")
                length = struct.unpack("!H", data)[0]

            elif length == 127:
                # 64 bit length
                data = self.read(8)
                if len(data) != 8:
                    raise RuntimeError(
                        "Unexpected EOF while decoding header")
                length = struct.unpack("!Q", data)[0]

            if has_mask:
                mask = self.read(4)
                if len(mask) != 4:
                    raise RuntimeError(
                        "Unexpected EOF while decoding header")

            if self.do_compress and (flags & RSV0_MASK):
                flags &= ~RSV0_MASK
                compressed = True

            else:
                compressed = False

            if flags:
                raise RuntimeError(str(flags))

            if not length:
                payload = b""
            ## read data
            else:
                try:
                    payload = self.read(length)
                except socket.error:
                    payload = b""

                except Exception:
                    raise RuntimeError("Could not read payload")

                if len(payload) != length:
                    raise RuntimeError(
                        "Unexpected EOF reading frame payload")

                if has_mask:
                    payload = self.mask_payload(mask, length, payload)

                if compressed:
                    payload = b"".join((
                        self.decompressor.decompress(bytes(payload)),
                        self.decompressor.decompress(b"\0\0\xff\xff"),
                        self.decompressor.flush(),
                    ))

            if f_opcode in (OPCODE_TEXT, OPCODE_BINARY):
                # a new frame
                if opcode:
                    raise RuntimeError("The opcode in non-fin frame is "
                                        "expected to be zero, got "
                                        "{0!r}".format(f_opcode))

                opcode = f_opcode

            elif f_opcode == OPCODE_CONTINUATION:
                if not opcode:
                    raise RuntimeError("Unexpected frame with opcode=0")

            elif f_opcode == OPCODE_PING:
                # self.handle_ping(payload)
                self.on_ping(self)
                continue

            elif f_opcode == OPCODE_PONG:
                # self.handle_pong(payload)
                self.on_pong(self)
                continue

            elif f_opcode == OPCODE_CLOSE:
                print('opcode close')
                self.on_close(self)
                return

            else:
                raise RuntimeError("Unexpected opcode={0!r}".format(f_opcode))

            if opcode == OPCODE_TEXT:
                payload.decode("utf-8")

            message += payload

            if fin:
                break

        if opcode == OPCODE_TEXT:
            message =  self._decode_bytes(message)

        if self.on_message:
            self.on_message(self,message)

    def _decode_bytes(self, message):
        try:
            return message.decode("utf-8")
        except UnicodeDecodeError:
            return message.decode("latin-1")

    def mask_payload(self, mask, length, payload):
        payload = bytearray(payload)
        mask = bytearray(mask)
        for i in range(length):
            payload[i] ^= mask[i % 4]

        return payload


    def send(self, message, opcode=OPCODE_TEXT):
        if isinstance(message, str):
            message = message.encode("utf-8")

        length = len(message)
        header = bytearray()
        if length < 126:
            header.append(FIN_MASK | opcode)
            header.append(length)

        elif length < 65536:
            header.append(FIN_MASK | opcode)
            header.append(126)
            header.extend(struct.pack("!H", length))

        else:
            header.append(FIN_MASK | opcode)
            header.append(127)
            header.extend(struct.pack("!Q", length))

        self.write(bytes(header))
        self.write(message)


class SimpleWebsocketMiddleWare:

    def __init__(self,wsgi_app,on_ping,on_pong,on_close,on_message,on_error,on_connect) -> None:
        self.wsgi_app = wsgi_app
        self.protocols = []
        self.on_ping = on_ping
        self.on_pong = on_pong
        self.on_close = on_close
        self.on_message = on_message
        self.on_error = on_error
        self.on_connect = on_connect

    def __call__(self, environ, start_response):
        ## check if request is websocket
        if environ.get("REQUEST_METHOD","") != "GET" or \
            "websocket" not in environ.get("HTTP_UPGRADE","").lower() or \
                "upgrade" not in environ.get("HTTP_CONNECTION","").lower():
        ### ws request
            print("request using http protocol")   
            return self.wsgi_app(environ, start_response)
        else:
            ### ws request    
            version = environ.get("HTTP_SEC_WEBSOCKET_VERSION",None)
            if not version:
                start_response("426 Upgrade Required", [])
                return [b"Upgrade Required"]
            if version not in SUPPORTED_VERSIONS:
                start_response("400 Bad Request", [])
                return [b"Bad Request,Versions Supported: 13, 8, 7"]
            

            ws_key = environ.get("HTTP_SEC_WEBSOCKET_KEY",None)
            if not ws_key:
                start_response("400 Bad Request", [])
                return [b"Bad Request,Sec-WebSocket-Key Missing"]
            
            try:
                key_len = len(base64.b64decode(ws_key))

            except TypeError:
                start_response("400 Bad Request", [])
                return [b"Bad Request,Invalid Sec-WebSocket-Key"]

            if key_len != 16:
                start_response("400 Bad Request", [])
                return [b"Bad Request,Invalid Sec-WebSocket-Key Length"]

            # Sec-WebSocket-Protocol
            requested_protocols = list(
                map(str.strip,environ.get("HTTP_SEC_WEBSOCKET_PROTOCOL", "").split(",")))
            protocols = None
            protocols = set(requested_protocols) and set(self.protocols)

            extensions = list(
                map(lambda ext: ext.split(";")[0].strip(),
                    environ.get("HTTP_SEC_WEBSOCKET_EXTENSIONS", "").split(",")))

            do_compress = "permessage-deflate" in extensions

            accept = base64.b64encode( 
                hashlib.sha1((ws_key + GUID).encode("latin-1")).digest()).decode("latin-1")


            headers = [
                ("Upgrade", "websocket"),
                ("Connection", "Upgrade"),
                ("Sec-WebSocket-Accept", accept),
            ]

            if do_compress:
                headers.append(("Sec-WebSocket-Extensions", "permessage-deflate"))

            if protocols:
                headers.append(("Sec-WebSocket-Protocol", ", ".join(protocols)))

            write = start_response("101 Switching Protocols", headers) ## 握手响应返回

            read = environ["wsgi.input"].read
            write(b"")
            websocket = WebSocketObj(
                environ, 
                read, 
                write, 
                self,
                do_compress,
                on_ping=self.on_ping,
                on_pong=self.on_pong,
                on_close=self.on_close,
                on_message=self.on_message,
                on_error=self.on_error,
                on_connect=self.on_connect
            )
            environ.update({
                "wsgi.websocket_version": version,
                "wsgi.websocket": websocket
            })
            if self.on_connect:
                self.on_connect(websocket)

            try:
                # receive message from client
                return websocket.receive()
            except Exception as e:
                if self.on_error:
                    self.on_error(websocket, e)
                raise e from None