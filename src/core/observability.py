from __future__ import annotations
import functools,os
from typing import Any,Callable,Dict,Mapping,Optional,TypeVar,cast
from core.config import settings
from core.logging import current_log_context,get_logger,sanitize_for_logging
F=TypeVar("F",bound=Callable[...,Any])
logger=get_logger("observability")
try:
    from langsmith import traceable as _traceable
    LANGSMITH_AVAILABLE=True
except ImportError:
    _traceable=None;LANGSMITH_AVAILABLE=False

def configure_langsmith_environment()->None:
    os.environ.setdefault("LANGSMITH_TRACING","true" if settings.langsmith_tracing else "false")
    os.environ.setdefault("LANGSMITH_PROJECT",settings.langsmith_project)
    os.environ.setdefault("LANGSMITH_ENDPOINT",settings.langsmith_endpoint)
    if settings.langsmith_api_key:os.environ.setdefault("LANGSMITH_API_KEY",settings.langsmith_api_key)
    os.environ.setdefault("LANGSMITH_HIDE_INPUTS","true" if settings.langsmith_hide_inputs else "false")
    os.environ.setdefault("LANGSMITH_HIDE_OUTPUTS","true" if settings.langsmith_hide_outputs else "false")
    os.environ.setdefault("LANGSMITH_HIDE_METADATA","true" if settings.langsmith_hide_metadata else "false")
configure_langsmith_environment()

def tracing_status()->Dict[str,Any]:
    return {"enabled":settings.langsmith_tracing,"configured":settings.langsmith_configured,"sdk_available":LANGSMITH_AVAILABLE,"project":settings.langsmith_project,"endpoint":settings.langsmith_endpoint}

def build_trace_metadata(*,session_id=None,run_id=None,product_id=None,demand_forecast=None,required_date=None,component=None,**extra)->Dict[str,Any]:
    metadata={"application":settings.application_name,"application_version":settings.application_version,"environment":settings.environment,**current_log_context()}
    explicit={"session_id":session_id,"run_id":run_id,"product_id":product_id,"demand_forecast":demand_forecast,"required_date":required_date,"component":component,**extra}
    metadata.update({k:v for k,v in explicit.items() if v is not None})
    return cast(Dict[str,Any],sanitize_for_logging(metadata))

def langsmith_extra(*,metadata:Optional[Dict[str,Any]]=None,tags:Optional[list[str]]=None,run_name:Optional[str]=None)->Dict[str,Any]:
    out={"metadata":sanitize_for_logging(metadata or {})}
    if tags:out["tags"]=tags
    if run_name:out["name"]=run_name
    return out

def _process_inputs(inputs:Mapping[str,Any])->Dict[str,Any]:
    return {} if settings.langsmith_hide_inputs else cast(Dict[str,Any],sanitize_for_logging(dict(inputs)))
def _process_outputs(outputs:Any)->Any:
    return {} if settings.langsmith_hide_outputs else sanitize_for_logging(outputs)

def traceable_if_enabled(*,name:Optional[str]=None,run_type:str="chain",tags:Optional[list[str]]=None,metadata:Optional[Dict[str,Any]]=None)->Callable[[F],F]:
    def decorator(func:F)->F:
        if not LANGSMITH_AVAILABLE or not settings.langsmith_tracing:return func
        traced=_traceable(func,name=name or func.__name__,run_type=run_type,tags=tags,metadata=metadata,process_inputs=_process_inputs,process_outputs=_process_outputs)
        return cast(F,functools.wraps(func)(traced))
    return decorator

def log_observability_status()->None:
    status=tracing_status()
    if status["enabled"] and not status["sdk_available"]:
        logger.warning("langsmith_sdk_unavailable",component="observability",status="degraded",payload=status);return
    if status["enabled"] and not status["configured"]:
        logger.warning("langsmith_api_key_missing",component="observability",status="degraded",payload=status);return
    logger.info("observability_initialized",component="observability",status="success",payload=status)
