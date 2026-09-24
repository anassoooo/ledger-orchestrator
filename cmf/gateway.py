"""Loopback-published gateway; no source/output volume and one fixed backend."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
import re


class Handler(BaseHTTPRequestHandler):
    def proxy(self):
        if re.fullmatch(r'/(health|openapi\.json|runs|jobs/[a-f0-9]{32}|runs/\d{8}T\d{6}_[a-f0-9]{8}/(report|agents|workbook))',self.path) is None:
            self.send_error(404)
            return
        try:
            size=int(self.headers.get('Content-Length','0'))
        except ValueError:
            self.send_error(400)
            return
        if size<0 or size>4096:
            self.send_error(413)
            return
        body=self.rfile.read(size) if self.command=='POST' else None
        request=Request('http://engine:8000'+self.path,data=body,method=self.command,
                        headers={'Content-Type':'application/json'})
        try:
            response=urlopen(request,timeout=30)
        except HTTPError as exc:
            response=exc
        except URLError:
            self.send_error(502)
            return
        with response:
            payload=response.read()
            self.send_response(response.status)
            for header in ('Content-Type','Content-Disposition'):
                if response.headers.get(header):
                    self.send_header(header,response.headers[header])
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    do_GET=proxy
    do_POST=proxy


if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
