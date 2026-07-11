from __future__ import annotations
from typing import Optional
class ForgeForceError(Exception):
    default_public_message="ForgeForce could not complete the requested operation."
    def __init__(self,message:Optional[str]=None,*,component:Optional[str]=None,run_id:Optional[str]=None)->None:
        super().__init__(message or self.default_public_message)
        self.public_message=message or self.default_public_message
        self.component=component
        self.run_id=run_id
    def user_message(self)->str:
        return self.public_message+(f" Reference run: {self.run_id}." if self.run_id else "")
class ConfigurationError(ForgeForceError): default_public_message="Application configuration is invalid."
class WorkflowExecutionError(ForgeForceError): default_public_message="The procurement workflow could not be completed."
class PersistenceError(ForgeForceError): default_public_message="The application could not save or load the requested data."
class DemandAnalysisError(WorkflowExecutionError): default_public_message="Demand and inventory analysis could not be completed."
class SupplierIntelligenceError(WorkflowExecutionError): default_public_message="Supplier intelligence could not be completed."
class SupplierReasoningError(WorkflowExecutionError): default_public_message="Supplier reasoning could not be completed."
class PlannerError(WorkflowExecutionError): default_public_message="The procurement planner could not select a route."
class DecisionAggregationError(WorkflowExecutionError): default_public_message="The procurement decision could not be aggregated."
class ConversationError(ForgeForceError): default_public_message="The procurement follow-up could not be answered."
class ReviewError(ForgeForceError): default_public_message="The procurement review could not be saved."
class PRCreationError(ForgeForceError): default_public_message="The Purchase Requisition could not be created."
class ApprovalError(ForgeForceError): default_public_message="The Purchase Requisition approval could not be completed."
class POGenerationError(ForgeForceError): default_public_message="Purchase Orders could not be generated."
