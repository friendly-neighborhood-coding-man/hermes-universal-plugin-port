"""Local developer harness. Does not install or enable Hermes plugins."""
import argparse
import json
from port_core import analyze, stage, fetch_github, PortError


def main():
    p=argparse.ArgumentParser(description='Preview and stage ports without modifying Hermes')
    sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('probe');q.add_argument('source')
    q=sub.add_parser('fetch');q.add_argument('url');q.add_argument('output_dir');q.add_argument('--approve',action='store_true')
    q=sub.add_parser('stage');q.add_argument('source');q.add_argument('output_dir')
    q.add_argument('--approve',action='store_true',help='User requested staging of this particular plugin')
    q.add_argument('--execute-foreign',action='store_true',help='Separately consented to running source JS; NOT SANDBOXED')
    q.add_argument('--allow-partial',action='store_true',help='User accepted loss of listed unsupported capabilities')
    args=p.parse_args()
    try:
        if args.command=='probe':r=analyze(args.source)
        elif args.command=='fetch':r=fetch_github(args.url,args.output_dir,approved=args.approve)
        else:r=stage(args.source,args.output_dir,approved=args.approve,run_foreign_code=args.execute_foreign,allow_partial=args.allow_partial)
        print(json.dumps(r,ensure_ascii=False,indent=2));return 0
    except PortError as e:
        print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False,indent=2));return 1

if __name__=='__main__':raise SystemExit(main())
