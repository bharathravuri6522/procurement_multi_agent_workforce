from core.logging import bind_log_context,get_logger,reset_log_context
from core.observability import build_trace_metadata,langsmith_extra,log_observability_status,traceable_if_enabled,tracing_status
from core.timing import timed

logger=get_logger("smoke_test")

@traceable_if_enabled(name="ForgeForce Observability Smoke Test",run_type="chain",tags=["smoke-test","section-1"])
@timed(component="smoke_test",event="smoke_test_completed")
def run_smoke_test(session_id:str,run_id:str,*,langsmith_extra=None):
    logger.info("smoke_test_started",component="smoke_test",status="running",payload={"approval_code":"must-not-appear","item_count":3})
    return {"status":"ok","session_id":session_id,"run_id":run_id}

if __name__=="__main__":
    log_observability_status()
    token=bind_log_context(session_id="PRC-SMOKE-001",run_id="RUN-SMOKE-001",product_id="RS-240")
    try:
        result=run_smoke_test("PRC-SMOKE-001","RUN-SMOKE-001",langsmith_extra=langsmith_extra(metadata=build_trace_metadata(component="smoke_test",demand_forecast=80,required_date="2026-07-31"),tags=["forgeforce","smoke-test"]))
        print("Smoke test result:",result)
        print("Tracing status:",tracing_status())
    finally:
        reset_log_context(token)
