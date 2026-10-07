"""Allowlisted metadata adapters. Never read transcripts or tool arguments."""
import hashlib
import json
from bridge_store import make_event


def hook_event(source, payload):
    if not isinstance(payload, dict):
        raise ValueError('hook payload must be an object')
    name = payload.get('hook_event_name') or payload.get('type')
    thread = (payload.get('conversation_id') if source == 'cursor' else
              payload.get('session_id') or payload.get('thread-id'))
    if not isinstance(thread, str) or not thread:
        return None
    run = payload.get('generation_id') or payload.get('turn_id') or payload.get('turn-id')
    kind, request = None, None
    if source == 'cursor':
        if name == 'beforeSubmitPrompt':
            kind = 'started'
        elif name == 'stop':
            kind = {'completed': 'completed', 'error': 'failed', 'aborted': 'cancelled'}.get(payload.get('status'))
        elif name == 'sessionEnd':
            kind = 'disconnected'
    elif source in {'codex', 'claude', 'zcode'}:
        kind = {'UserPromptSubmit': 'started', 'PermissionRequest': 'waiting',
                'Stop': 'completed', 'StopFailure': 'failed',
                'SessionEnd': 'disconnected', 'Interrupt': 'cancelled',
                'agent-turn-complete': 'completed'}.get(name)
        if name == 'Notification' and payload.get('notification_type') == 'permission_prompt':
            kind = 'waiting'
        if name == 'PostToolUse':
            kind = 'resolved'
        request = payload.get('tool_use_id')
        # An uncorrelated tool completion cannot clear an unrelated approval.
        if kind == 'resolved' and not request:
            return None
    else:
        raise ValueError('unsupported hook provider')
    if not kind:
        return None
    fields = {'managed':True}
    if isinstance(run, str) and run:
        fields['run_id'] = run
    if isinstance(request, str) and request:
        fields['request_id'] = request
    if isinstance(payload.get('agent_id'), str) and payload['agent_id']:
        fields['agent_id'] = payload['agent_id']
    if kind == 'waiting':
        fields['summary'] = source + ' 等候确认'
    event = make_event(source, thread, kind, **fields)
    # Native run/request IDs make repeat delivery idempotent; never hash message text.
    if run:
        identity = [source, thread, run, name, request, payload.get('status')]
        event['event_id'] = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    return event


def app_server_event(payload, source='codex', agent_id=None):
    """For an owner of a real App Server connection, not a second desktop connection."""
    if not isinstance(payload, dict) or not isinstance(payload.get('params'), dict):
        return None
    params, method = payload['params'], payload.get('method')
    thread = params.get('threadId')
    if not thread:
        return None
    kinds = {'turn/started': 'started', 'turn/completed': 'completed',
             'item/commandExecution/requestApproval': 'waiting',
             'item/fileChange/requestApproval': 'waiting',
             'item/tool/requestUserInput': 'waiting', 'serverRequest/resolved': 'resolved'}
    kind = kinds.get(method)
    if not kind:
        return None
    turn = params.get('turn') or {}
    if not isinstance(turn, dict):
        return None
    if method == 'turn/completed':
        kind = {'completed': 'completed', 'failed': 'failed', 'interrupted': 'cancelled'}.get(turn.get('status'))
        if not kind:
            return None
    fields = {}
    run = params.get('turnId') or turn.get('id')
    if isinstance(run, str):
        fields['run_id'] = run
    request = params.get('requestId') if method == 'serverRequest/resolved' else payload.get('id')
    if request is not None:
        fields['request_id'] = str(request)
    if agent_id:
        fields['agent_id'] = agent_id
    event = make_event(source, thread, kind, **fields)
    if run or request is not None:
        event['event_id'] = hashlib.sha256(json.dumps([source, thread, agent_id, method, run, request]).encode()).hexdigest()
    return event
