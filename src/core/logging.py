from __future__ import annotations
import contextvars,json,logging,logging.handlers,re,sys
from datetime import datetime,timezone
from typing import Any,Dict,Mapping,Optional
from core.config import settings

_LOG_CONTEXT=contextvars.ContextVar("forgeforce_log_context",default={})
_CONFIGURED=False
SENSITIVE_KEYS={"api_key","apikey","authorization","approval_code","password","secret","token","access_token","refresh_token"}
EMAIL_PATTERN=re.compile(r"(?P<local>[A-Za-z0-9._%+-]{1,64})@(?P<domain>[A-Za-z0-9.-]+\.[A-Za-z]{2,})")

def _utc_now()->str:return datetime.now(timezone.utc).isoformat()
def _redact_email(value:str)->str:
    def repl(m):
        local=m.group("local");visible=local[:2] if len(local)>2 else local[:1]
        return f"{visible}***@{m.group('domain')}"
    return EMAIL_PATTERN.sub(repl,value)

def sanitize_for_logging(value:Any,*,max_string_length:int=2000,max_collection_items:int=100)->Any:
    if value is None or isinstance(value,(bool,int,float)):return value
    if isinstance(value,str):
        value=_redact_email(value)
        return value if len(value)<=max_string_length else value[:max_string_length]+"...[TRUNCATED]"
    if isinstance(value,Mapping):
        out={}
        for i,(k,v) in enumerate(value.items()):
            if i>=max_collection_items:out["_truncated"]=True;break
            nk=str(k).strip().lower()
            out[str(k)]="[REDACTED]" if nk in SENSITIVE_KEYS or any(x in nk for x in ("password","secret","approval_code","api_key")) else sanitize_for_logging(v,max_string_length=max_string_length,max_collection_items=max_collection_items)
        return out
    if isinstance(value,(list,tuple,set)):
        items=list(value);out=[sanitize_for_logging(v,max_string_length=max_string_length,max_collection_items=max_collection_items) for v in items[:max_collection_items]]
        if len(items)>max_collection_items:out.append("[TRUNCATED]")
        return out
    if hasattr(value,"model_dump"):return sanitize_for_logging(value.model_dump(),max_string_length=max_string_length,max_collection_items=max_collection_items)
    return sanitize_for_logging(str(value),max_string_length=max_string_length,max_collection_items=max_collection_items)

class JsonFormatter(logging.Formatter):
    standard={"name","msg","args","levelname","levelno","pathname","filename","module","exc_info","exc_text","stack_info","lineno","funcName","created","msecs","relativeCreated","thread","threadName","processName","process","message","taskName"}
    def format(self,record):
        payload={"timestamp":_utc_now(),"level":record.levelname,"logger":record.name,"application":settings.application_name,"application_version":settings.application_version,"environment":settings.environment}
        payload.update(_LOG_CONTEXT.get())
        data=getattr(record,"event_data",None)
        if isinstance(data,Mapping):payload.update(data)
        if "event" not in payload:payload["event"]=record.getMessage()
        if record.exc_info:
            payload["exception"]={"type":record.exc_info[0].__name__ if record.exc_info[0] else "Exception","message":str(record.exc_info[1]),"stack_trace":self.formatException(record.exc_info)}
        return json.dumps(sanitize_for_logging(payload),ensure_ascii=False,default=str)

class ForgeForceLogger:
    def __init__(self,logger):self._logger=logger
    def _log(self,level,event,*,component=None,status=None,duration_ms=None,payload=None,error=None,**fields):
        data={"event":event}
        if component:data["component"]=component
        if status:data["status"]=status
        if duration_ms is not None:data["duration_ms"]=round(duration_ms,3)
        if payload is not None:data["payload"]=payload
        data.update(fields)
        self._logger.log(level,event,extra={"event_data":data},exc_info=(type(error),error,error.__traceback__) if error else None)
    def debug(self,event,**kwargs):self._log(logging.DEBUG,event,**kwargs)
    def info(self,event,**kwargs):self._log(logging.INFO,event,**kwargs)
    def warning(self,event,**kwargs):self._log(logging.WARNING,event,**kwargs)
    def error(self,event,**kwargs):self._log(logging.ERROR,event,**kwargs)
    def exception(self,event,error,**kwargs):self._log(logging.ERROR,event,error=error,**kwargs)

def configure_logging(force:bool=False)->None:
    global _CONFIGURED
    if _CONFIGURED and not force:return
    root=logging.getLogger("forgeforce");root.handlers.clear();root.setLevel(getattr(logging,settings.log_level,logging.INFO));root.propagate=False
    fmt=JsonFormatter();settings.log_directory.mkdir(parents=True,exist_ok=True)
    fh=logging.handlers.RotatingFileHandler(settings.log_directory/settings.log_filename,maxBytes=settings.log_max_bytes,backupCount=settings.log_backup_count,encoding="utf-8");fh.setFormatter(fmt);root.addHandler(fh)
    if settings.log_to_console:
        ch=logging.StreamHandler(sys.stdout);ch.setFormatter(fmt);root.addHandler(ch)
    _CONFIGURED=True

def get_logger(component:str)->ForgeForceLogger:
    configure_logging();return ForgeForceLogger(logging.getLogger(f"forgeforce.{component}"))
def bind_log_context(**fields):return _LOG_CONTEXT.set({**_LOG_CONTEXT.get(),**{k:v for k,v in fields.items() if v is not None}})
def reset_log_context(token):_LOG_CONTEXT.reset(token)
def clear_log_context():_LOG_CONTEXT.set({})
def current_log_context()->Dict[str,Any]:return dict(_LOG_CONTEXT.get())
