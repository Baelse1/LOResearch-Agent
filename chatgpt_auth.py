"""Official Sign in with ChatGPT public-client integration.

Documentation checked 2026-10-27. No browser-cookie extraction or borrowed client ID.
Tokens stay outside the project: Windows DPAPI; owner-only files on Unix.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
import base64
import ctypes
import hashlib
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
import os
from pathlib import Path
import secrets
import tempfile
import time
from urllib.parse import urlencode,urlparse,parse_qs
import uuid
import webbrowser
import httpx
import jwt

ISSUER='https://auth.openai.com'
AUTHORIZE=ISSUER+'/api/accounts/authorize'
TOKEN=ISSUER+'/api/accounts/oauth/token'
RESOURCE='https://api.openai.com/v1'
SCOPES='openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
PLAN_SCOPE='chatgpt.tokens.use.direct'
APP_NAME='LOResearch-Agent'


class AuthError(RuntimeError):
    """Safe-to-display message: never include tokens or HTTP response bodies."""


def request_json(method,url,**kwargs):
    try:
        with httpx.Client(timeout=30,follow_redirects=False) as client:
            response=client.request(method,url,**kwargs)
            if response.status_code!=200:
                code=''
                try:
                    error=response.json().get('error','')
                    if isinstance(error,dict): error=error.get('code','')
                    if error in {'invalid_grant','invalid_client','access_denied','insufficient_scope'}:
                        code=' '+error
                except (ValueError,AttributeError): pass
                raise AuthError(f'OpenAI HTTP {response.status_code}{code}; no automatic retry.')
            return response.json()
    except (httpx.RequestError,ImportError):
        raise AuthError('Network/proxy error. Check connectivity; if SOCKS proxy is used, install httpx[socks].') from None
    except ValueError:
        raise AuthError('OpenAI returned an invalid JSON response.') from None


def atomic_write(path,data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,tmp=tempfile.mkstemp(prefix='.write-',dir=path.parent)
    try:
        if os.name!='nt': os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
        if os.name!='nt': path.chmod(0o600)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def windows_dpapi(data,decrypt=False):
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)))
    result=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    function=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.POINTER(Blob),
                       ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    function.restype=wintypes.BOOL
    kernel.LocalFree.argtypes=[ctypes.c_void_p]
    kernel.LocalFree.restype=ctypes.c_void_p
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(result)):
        raise AuthError('Windows credential protection failed; no plaintext fallback was used.')
    try: return ctypes.string_at(result.data,result.size)
    finally: kernel.LocalFree(result.data)


class CredentialStore:
    def __init__(self,directory=None):
        if directory is None:
            if os.name=='nt':
                base=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))
            else: base=Path.home()/'.config'
            directory=base/APP_NAME/'siwc'
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        if os.name!='nt': self.directory.chmod(0o700)

    def public(self):
        p=self.directory/'accounts.json'
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else dict(accounts=[],active=None,models={})

    def save_public(self,value):
        atomic_write(self.directory/'accounts.json',json.dumps(value).encode())

    def host_id(self):
        p=self.directory/'host.json'
        if p.exists(): return json.loads(p.read_text())['ext_agent_host_id']
        host='urn:uuid:'+str(uuid.uuid4())
        atomic_write(p,json.dumps(dict(ext_agent_host_id=host)).encode())
        return host

    def path(self,client_id):
        return self.directory/(hashlib.sha256(client_id.encode()).hexdigest()+'.credential')

    def read(self,client_id):
        p=self.path(client_id)
        if not p.exists(): raise AuthError('This registration is signed out. Run 05_chatgpt_login.py.')
        data=p.read_bytes()
        if os.name=='nt': data=windows_dpapi(data,decrypt=True)
        elif p.stat().st_mode & 0o077:
            raise AuthError('Credential permissions are not owner-only. Refusing to read.')
        return json.loads(data)

    def save(self,record):
        data=json.dumps(record).encode()
        if os.name=='nt': data=windows_dpapi(data)
        atomic_write(self.path(record['client_id']),data)
        public=self.public()
        public['accounts']=[x for x in public['accounts'] if x['client_id']!=record['client_id']]
        public['accounts'].append({k:record.get(k) for k in ['client_id','subject','email']})
        public['active']=record['client_id']
        self.save_public(public)

    def clear_tokens(self,client_id):
        self.path(client_id).unlink(missing_ok=True)
        # Keep account/client mapping and host ID for reauthorization.
        public=self.public()
        if public['active']==client_id: public['active']=None
        self.save_public(public)

    @contextmanager
    def session_lock(self):
        """Serialize refresh+rotation across local processes."""
        p=self.directory/'refresh.lock'
        with p.open('a+b') as f:
            if p.stat().st_size==0: f.write(b'0');f.flush()
            deadline=time.monotonic()+15
            while True:
                try:
                    f.seek(0)
                    if os.name=='nt':
                        import msvcrt
                        msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    break
                except (OSError,BlockingIOError):
                    if time.monotonic()>deadline: raise AuthError('Another login/refresh is in progress.')
                    time.sleep(.1)
            try: yield
            finally:
                f.seek(0)
                if os.name=='nt': msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
                else: fcntl.flock(f.fileno(),fcntl.LOCK_UN)


def authorization_parameters(host_id,redirect_uri,previous=None):
    state=secrets.token_urlsafe(32)
    nonce=secrets.token_urlsafe(32)
    verifier=secrets.token_urlsafe(64)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    params=dict(client_id=previous['client_id'] if previous else 'dynamic_agent_client',
      ext_agent_host_id=host_id,response_type='code',redirect_uri=redirect_uri,scope=SCOPES,
      resource=RESOURCE,state=state,nonce=nonce,code_challenge_method='S256',code_challenge=challenge)
    if previous:
        if previous.get('id_token'): params['id_token_hint']=previous['id_token']
        if previous.get('email'): params['login_hint']=previous['email']
    else: params['agent_name_hint']=APP_NAME
    pending=dict(state=state,nonce=nonce,verifier=verifier,redirect_uri=redirect_uri,
                 host_id=host_id,previous=previous)
    return params,pending


def validate_callback(query,pending):
    def one(key):
        value=query.get(key,[])
        if len(value)>1: raise AuthError('Duplicate OAuth callback parameter.')
        return value[0] if value else None
    if not secrets.compare_digest(one('state') or '',pending['state']):
        raise AuthError('OAuth state mismatch; authorization stopped.')
    if one('error'):
        raise AuthError('Authorization was declined or unavailable. No inference request was made.')
    code=one('code')
    if not code: raise AuthError('Missing authorization code.')
    previous=pending['previous']
    issued=one('client_id')
    if previous:
        if issued and issued!=previous['client_id']: raise AuthError('Returning client ID mismatch.')
        issued=previous['client_id']
    if not issued or issued=='dynamic_agent_client':
        raise AuthError('Registration incomplete: no issued client ID was returned.')
    return code,issued


def validate_identity(id_token,client_id,nonce,jwks):
    try:
        header=jwt.get_unverified_header(id_token)
        alg=header.get('alg')
        if alg not in ('RS256','ES256'): raise ValueError('Unsupported signing algorithm')
        key=next(k for k in jwks['keys'] if k.get('kid')==header.get('kid'))
        decoded=jwt.decode(id_token,jwt.PyJWK.from_dict(key).key,algorithms=[alg],
            issuer=ISSUER,audience=client_id,
            options={'require':['iss','aud','exp','sub','nonce','iat']})
        if not secrets.compare_digest(str(decoded['nonce']),nonce): raise ValueError('nonce mismatch')
        return decoded
    except (jwt.PyJWTError,ValueError,KeyError,StopIteration,TypeError):
        raise AuthError('ID token validation failed; credentials were not saved.') from None


def token_record(tokens,client_id,host_id,identity):
    if tokens.get('token_type','').lower()!='bearer' or not tokens.get('access_token'):
        raise AuthError('Invalid OAuth token response.')
    expires=float(tokens.get('expires_in',0))
    if not 0<expires<=86400*365: raise AuthError('Invalid token expiry.')
    return dict(client_id=client_id,ext_agent_host_id=host_id,issuer=ISSUER,
      subject=identity['sub'],email=identity.get('email',''),id_token=tokens.get('id_token'),
      access_token=tokens['access_token'],refresh_token=tokens.get('refresh_token'),
      token_type='Bearer',scopes=tokens.get('scope','').split(),expires_at=time.time()+expires,
      saved_at=datetime.now(timezone.utc).isoformat())


def sign_in(store,client_id=None,opener=webbrowser.open):
    previous=None
    if client_id:
        try: previous=store.read(client_id)
        except AuthError:
            previous=next((dict(x) for x in store.public()['accounts'] if x['client_id']==client_id),None)
            if previous is None: raise AuthError('Unknown account registration.')
    callback={}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass # Never log authorization codes or token hints.
        def do_GET(self):
            parsed=urlparse(self.path)
            if parsed.path!='/auth/callback':
                self.send_response(404);self.end_headers();return
            callback['query']=parse_qs(parsed.query,keep_blank_values=True)
            self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8');self.end_headers()
            self.wfile.write(b'Return to LOResearch-Agent. The app will validate this authorization.')
    server=HTTPServer(('127.0.0.1',0),Handler)
    server.timeout=.5
    redirect=f'http://127.0.0.1:{server.server_address[1]}/auth/callback'
    params,pending=authorization_parameters(store.host_id(),redirect,previous)
    try:
        if not opener(AUTHORIZE+'?'+urlencode(params)):
            raise AuthError('Could not open the browser. Check the default browser and try again.')
        deadline=time.monotonic()+300
        while 'query' not in callback:
            if time.monotonic()>deadline: raise AuthError('Browser authorization timed out. Run login again.')
            server.handle_request()
    finally: server.server_close()
    code,issued=validate_callback(callback['query'],pending)
    tokens=request_json('POST',TOKEN,data=dict(grant_type='authorization_code',client_id=issued,
         code=code,code_verifier=pending['verifier'],redirect_uri=redirect,resource=RESOURCE))
    discovery=request_json('GET',ISSUER+'/.well-known/openid-configuration')
    if discovery.get('issuer')!=ISSUER: raise AuthError('Unexpected OpenID issuer.')
    jwks_uri=discovery.get('jwks_uri','')
    parsed=urlparse(jwks_uri)
    if parsed.scheme!='https' or parsed.hostname!='auth.openai.com':
        raise AuthError('Unexpected OpenID signing-key endpoint.')
    identity=validate_identity(tokens.get('id_token',''),issued,pending['nonce'],request_json('GET',jwks_uri))
    if previous and previous.get('subject')!=identity['sub']:
        raise AuthError('Account identity changed during reauthorization; no credentials replaced.')
    record=token_record(tokens,issued,pending['host_id'],identity)
    with store.session_lock(): store.save(record)
    return dict(client_id=issued,email=record['email'],plan_enabled=PLAN_SCOPE in record['scopes'])


def access_record(store,client_id=None):
    with store.session_lock():
        selected=client_id or store.public()['active']
        if not selected: raise AuthError('No active account. Run 05_chatgpt_login.py first.')
        record=store.read(selected)
        if PLAN_SCOPE not in record['scopes']:
            raise AuthError('Signed in, but ChatGPT plan usage was not granted. Reauthorize in 05_chatgpt_login.py.')
        if record['expires_at']<=time.time()+90:
            if not record.get('refresh_token'): raise AuthError('Session expired; sign in again.')
            tokens=request_json('POST',TOKEN,data=dict(grant_type='refresh_token',client_id=selected,
                           refresh_token=record['refresh_token'],resource=RESOURCE))
            if tokens.get('token_type','').lower()!='bearer' or not tokens.get('access_token'):
                raise AuthError('Invalid refresh response; sign in again.')
            lifetime=float(tokens.get('expires_in',0))
            if not 0<lifetime<=86400*365: raise AuthError('Invalid refreshed token expiry.')
            record['access_token']=tokens['access_token']
            record['refresh_token']=tokens.get('refresh_token',record['refresh_token'])
            record['expires_at']=time.time()+lifetime
            if 'scope' in tokens: record['scopes']=tokens['scope'].split()
            # Keep the validated original ID token as a reauthorization hint.
            # A refreshed ID token is not used to switch identity.
            record['saved_at']=datetime.now(timezone.utc).isoformat()
            store.save(record)
            if PLAN_SCOPE not in record['scopes']: raise AuthError('ChatGPT plan permission was removed.')
        return record


def list_models(store,client_id=None):
    record=access_record(store,client_id)
    data=request_json('GET',RESOURCE+'/models',headers={'Authorization':'Bearer '+record['access_token']})
    models=[dict(slug=x['slug'],display_name=x.get('display_name',x['slug']))
            for x in data.get('models',[]) if x.get('visibility')=='list' and x.get('slug')]
    if not models: raise AuthError('No eligible models returned for this account; check plan/workspace permissions.')
    return models


def sign_out(store,client_id):
    confirmed=False
    try:
        record=store.read(client_id)
        discovery=request_json('GET',ISSUER+'/.well-known/openid-configuration')
        endpoint=discovery.get('revocation_endpoint','')
        parsed=urlparse(endpoint)
        if parsed.scheme=='https' and parsed.hostname=='auth.openai.com' and record.get('refresh_token'):
            with httpx.Client(timeout=20,follow_redirects=False) as client:
                response=client.post(endpoint,data=dict(token=record['refresh_token'],token_type_hint='refresh_token',client_id=client_id))
                confirmed=response.status_code==200
    except (AuthError,httpx.RequestError,ImportError): pass
    finally:
        with store.session_lock(): store.clear_tokens(client_id)
    return confirmed
