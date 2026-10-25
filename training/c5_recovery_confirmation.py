"""Owner preload confirmation. Invalid input pauses; it never retires a study."""
import sys
import unicodedata
from training.c5_reuse_evidence import canonical,exact,is_sha,require,sha
from training.c5_recovery_policy import POLICY,validate_scope
CONFIRM='确认并保管'

def input_status(raw):
    if type(raw) is not str or len(raw)>64:return 'invalid_length',[]
    hidden=[{'position':i,'codepoint':'U+%04X'%ord(c)}
            for i,c in enumerate(raw) if unicodedata.category(c) in ('Cf','Cc') and c not in '\t\r\n']
    if hidden:return 'invisible_or_control_character',hidden
    text=raw.strip()
    if text=='取消':return 'cancelled',[]
    return ('confirmed' if text==CONFIRM else 'text_mismatch'),[]

def snapshot(scope,host_anchor,nonce):
    validate_scope(scope)
    require(is_sha(host_anchor) and is_sha(nonce),'recovery_preload_anchor')
    return {'scope_sha256':sha(scope),'host_preload_anchor_sha256':host_anchor,
            'nonce_sha256':nonce}

def validate_receipt(scope,snap,receipt):
    exact(snap,('scope_sha256','host_preload_anchor_sha256','nonce_sha256'))
    require(snap['scope_sha256']==sha(validate_scope(scope))
            and all(is_sha(v) for v in snap.values()),'recovery_preload_scope')
    expected={'actor':'repository_owner',**snap,'before_model_loading':True,
              'public_attempts_authorized':POLICY['public_attempts_max'] if scope['phase']=='public_engineering' else 0,
              'human_origin_cryptographically_proven':False}
    require(canonical(receipt)==canonical(expected),'recovery_preload_receipt_changed')
    return receipt

def confirm_preload(scope,snap,guard,*,input_fn=input,output=print,isatty=None):
    require((sys.stdin.isatty() if isatty is None else isatty()) is True,
            'owner_private_interactive_terminal_required')
    validate_scope(scope);guard()
    exact(snap,('scope_sha256','host_preload_anchor_sha256','nonce_sha256'))
    require(snap['scope_sha256']==sha(scope) and all(is_sha(v) for v in snap.values()),
            'recovery_preload_scope')
    output(canonical({'scope':scope,'preload_snapshot':snap,'public_attempts_max':POLICY['public_attempts_max'],
                      'before_model_loading':True,'formal_generation_start_approved':False}).decode())
    output('请先核对完整冻结、公开工程重试上限及宿主材料。确认在模型加载前完成；可输入“取消”暂停。')
    for _ in range(POLICY['confirmation_inputs_per_invocation']):
        guard()
        try:raw=input_fn('输入“确认并保管”：')
        except (EOFError,KeyboardInterrupt):
            output('确认已暂停，尚未加载模型；可稍后重新打开本人确认入口。');return None
        status,hidden=input_status(raw)
        if status=='confirmed':
            guard()
            receipt={'actor':'repository_owner',**snap,'before_model_loading':True,
                     'public_attempts_authorized':POLICY['public_attempts_max'] if scope['phase']=='public_engineering' else 0,
                     'human_origin_cryptographically_proven':False}
            return validate_receipt(scope,snap,receipt)
        if status=='cancelled':
            output('已暂停，尚未加载模型。');return None
        # Never echo an accidentally pasted password, key or terminal escape.
        output('输入未匹配，请手动键入确认文字。'+
               (' 检测到不可见字符：'+','.join(v['codepoint'] for v in hidden) if hidden else ''))
    output('本次确认已暂停；未消费工程尝试，可稍后重新确认。')
    return None
