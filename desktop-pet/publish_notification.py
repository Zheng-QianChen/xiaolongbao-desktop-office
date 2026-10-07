"""Send a project update through the running local bridge, without copying its token."""
import argparse
import json
from pathlib import Path
from pet_mcp import Client
from app_paths import runtime_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=runtime_dir()/'bridge')
    parser.add_argument('--channel', required=True)
    parser.add_argument('--create', metavar='NAME', help='Create/update the channel name before sending')
    parser.add_argument('--id', required=True, help='Stable event identity; retries use the same ID')
    parser.add_argument('--title', required=True)
    parser.add_argument('--summary', default='')
    parser.add_argument('--url', default='')
    args = parser.parse_args()
    client = Client(args.runtime)
    try:
        if args.create:
            client.call('create_push_channel', {'id':args.channel, 'name':args.create})
        result = client.call('publish_notification', {'connector_id':args.channel, 'item_id':args.id,
                            'title':args.title, 'summary':args.summary, 'url':args.url})
    except Exception:
        raise SystemExit('Notification was not sent. Check that Wang Bun is running and the channel is enabled.') from None
    print(json.dumps(result))


if __name__ == '__main__': main()
