from __future__ import annotations
import asyncio,functools,time
from typing import Any,Callable,Optional,TypeVar,cast
from core.logging import get_logger
F=TypeVar("F",bound=Callable[...,Any])

def timed(*,component:str,event:Optional[str]=None,log_payload:bool=False)->Callable[[F],F]:
    logger=get_logger(component)
    def decorator(func:F)->F:
        event_name=event or f"{func.__name__}_completed"
        failed_event=event_name.replace("_completed","_failed")
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args,**kwargs):
                started=time.perf_counter()
                try:result=await func(*args,**kwargs)
                except Exception as exc:
                    logger.exception(failed_event,error=exc,component=component,status="failed",duration_ms=(time.perf_counter()-started)*1000);raise
                logger.info(event_name,component=component,status="success",duration_ms=(time.perf_counter()-started)*1000,payload={"result":result} if log_payload else None)
                return result
            return cast(F,async_wrapper)
        @functools.wraps(func)
        def sync_wrapper(*args,**kwargs):
            started=time.perf_counter()
            try:result=func(*args,**kwargs)
            except Exception as exc:
                logger.exception(failed_event,error=exc,component=component,status="failed",duration_ms=(time.perf_counter()-started)*1000);raise
            logger.info(event_name,component=component,status="success",duration_ms=(time.perf_counter()-started)*1000,payload={"result":result} if log_payload else None)
            return result
        return cast(F,sync_wrapper)
    return decorator
