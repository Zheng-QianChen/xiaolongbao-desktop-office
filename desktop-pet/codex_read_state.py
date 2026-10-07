"""Read Codex's persisted blue dots, scoped to its current local identity.

The hash format is verified against Codex 26.1002. Never merge account buckets.
Missing/ambiguous metadata is unknown, never implicitly 'read'. No auth tokens
are opened; the provider config and non-secret app identity cache suffice.
"""
import hashlib
import json
from pathlib import Path
import tomllib


def read_blue_dots(home):
    try:
        home=Path(home)
        state=json.loads((home/'.codex-global-state.json').read_text(encoding='utf-8'))
        config=tomllib.loads((home/'config.toml').read_text(encoding='utf-8'))
        profile=config.get('profiles',{}).get(config.get('profile'),{})
        provider=profile.get('model_provider',config.get('model_provider','openai'))
        provider_config=config.get('model_providers',{}).get(provider,{})
        if provider_config.get('requires_openai_auth') is False:
            identity=['execution-storage','none']
        else:
            # A custom provider with unspecified auth has no proven GUI identity.
            if provider!='openai':return None
            cache=state.get('environment-catalog-cache-v1',{})
            if not cache.get('accountId') or not cache.get('userId'):return None
            identity=['chatgpt',cache['accountId'],cache['userId']]
        key=hashlib.sha256(json.dumps(identity,separators=(',',':')).encode()).hexdigest()
        read=state.get('electron-thread-read-state-v1',{})
        if read.get('version')!=1:return None
        buckets=read.get('unreadByIdentity',{}).get(key)
        if not isinstance(buckets,dict):return None
        local=[v for k,v in buckets.items() if k.startswith('local:')]
        if len(local)!=1 or not isinstance(local[0],list):return None
        if not all(isinstance(i,str) for i in local[0]):return None
        return set(local[0])
    except (OSError,ValueError,TypeError,AttributeError):
        return None
