"""Local JSON file or HTTP interface; start explicitly, bound to loopback only."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from modeling.datasets import FEATURES
from modeling.inference import ReleasePredictor


def request(predictor,payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('records'),list):
        raise ValueError('Expected {family, records: [objects]}')
    if len(payload['records'])>10000 or any(not isinstance(r,dict) for r in payload['records']):
        raise ValueError('At most 10000 record objects')
    family=payload.get('family','pitching')
    if not isinstance(family,str):raise ValueError('family must be a string')
    return dict(release_id=predictor.lock['release_id'],records=predictor.records(payload['records'],family))


def handler(predictor):
    class Handler(BaseHTTPRequestHandler):
        def send(self,status,data):
            body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

        def do_GET(self):
            if self.path=='/health':self.send(200,dict(status='ok',release_id=predictor.lock['release_id']))
            elif self.path=='/schema':self.send(200,dict(features=FEATURES,physical_bounds=predictor.contract['physical_review_bounds'],
                inputs='observable features, no outcomes required; numeric values or numeric strings; count integers',
                units=dict(rel_speed='mph',spin_rate='rpm',rel_height='feet',rel_side='feet',extension='feet',
                           plate_loc_height='feet',plate_loc_side='feet',induced_vert_break='inches',horz_break='inches',
                           spin_axis_sin='unitless',spin_axis_cos='unitless'),
                policy='A base; no arsenal or environment adjustment',max_records=10000))
            else:self.send(404,dict(error='not_found'))

        def do_POST(self):
            if self.path!='/predict':self.send(404,dict(error='not_found'));return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=5_000_000:raise ValueError('Body size must be 1..5000000 bytes')
                payload=json.loads(self.rfile.read(length))
                self.send(200,request(predictor,payload))
            except (ValueError,TypeError) as exc:self.send(400,dict(error=str(exc)))
    return Handler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',required=True)
    parser.add_argument('--input');parser.add_argument('--output')
    parser.add_argument('--serve',action='store_true');parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    predictor=ReleasePredictor(args.release)
    if args.serve:
        with HTTPServer(('127.0.0.1',args.port),handler(predictor)) as server:
            print('Local inference: http://127.0.0.1:'+str(args.port),flush=True)
            server.serve_forever()
    else:
        if not args.input or not args.output:parser.error('--input and --output required unless --serve')
        result=request(predictor,json.loads(Path(args.input).read_text(encoding='utf-8')))
        with Path(args.output).open('x',encoding='utf-8') as file:json.dump(result,file,indent=2,ensure_ascii=False,allow_nan=False)


if __name__=='__main__':main()
