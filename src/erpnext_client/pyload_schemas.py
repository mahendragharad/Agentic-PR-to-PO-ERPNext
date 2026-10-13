from datetime import date
from typing import List, Optional, Set
from pydantic import BaseModel, Field, field_validator, model_validator

def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Invalid {field_name} format. Expected YYYY-MM-DD.")

def _validate_future_date_string(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return value
    
    parsed_date = _parse_date(value, field_name)
    today = date.today()
    
    if parsed_date < today:
        raise ValueError(f"{field_name} '{value}' cannot be a past date. It must be today or a future date.")
    return value

class MaterialRequestItemSchema(BaseModel):
    item_code: str = Field(..., description="Item Code in ERPNext")
    qty: float = Field(..., description="Quantity requested", gt=0)
    uom: str = Field(default="Nos", description="Unit of Measure")
    schedule_date: Optional[str] = Field(None, description="Delivery date (YYYY-MM-DD)")
    warehouse: Optional[str] = Field(None, description="Target warehouse")
    rate: float = Field(default=0.0, description="Estimated rate per unit", ge=0.0)

    @field_validator("schedule_date")
    @classmethod
    def validate_item_schedule_date(cls, value: Optional[str]) -> Optional[str]:
        return _validate_future_date_string(value, "schedule_date")

class MaterialRequestDocSchema(BaseModel):
    doctype: str = Field(default="Material Request", description="Target DocType")
    material_request_type: str = Field(default="Purchase", description="Type of requisition")
    transaction_date: str = Field(..., description="Posting date (YYYY-MM-DD)")
    schedule_date: str = Field(..., description="Required delivery date (YYYY-MM-DD)")
    company: str = Field(..., description="Company name")
    department: str = Field(..., description="Department name")
    set_warehouse: str = Field(default="All Warehouses - MF", description="Default warehouse")
    title: str = Field(..., description="Requisition title")
    remark: str = Field(..., description="Remarks or justification")
    items: List[MaterialRequestItemSchema] = Field(..., description="List of items to request")

    @field_validator("material_request_type")
    @classmethod
    def validate_request_type(cls, value: str) -> str:
        allowed_types: Set[str] = {"Purchase", "Material Transfer", "Material Issue", "Manufacture", "Customer Provided"}
        if value not in allowed_types:
            raise ValueError(f"Invalid material_request_type. Must be one of: {allowed_types}")
        return value

    @field_validator("items")
    @classmethod
    def validate_items_list(cls, items: List[MaterialRequestItemSchema]) -> List[MaterialRequestItemSchema]:
        if not items:
            raise ValueError("The child table transaction list array cannot be left empty.")
        return items

    @field_validator("transaction_date")
    @classmethod
    def validate_transaction_date(cls, value: str) -> str:
        # Transaction dates are typically today's date, not strictly future dates
        _parse_date(value, "transaction_date")
        return value

    @field_validator("schedule_date")
    @classmethod
    def validate_schedule_date(cls, value: str) -> str:
        _validate_future_date_string(value, "schedule_date")
        return value

    @model_validator(mode="after")
    def validate_schedule_after_transaction(self) -> "MaterialRequestDocSchema":
        trans_d = _parse_date(self.transaction_date, "transaction_date")
        sched_d = _parse_date(self.schedule_date, "schedule_date")

        if sched_d < trans_d:
            raise ValueError(
                f"schedule_date ({self.schedule_date}) cannot be earlier than transaction_date ({self.transaction_date})."
            )
        return self

class CreateMaterialRequestInput(BaseModel):
    doc: MaterialRequestDocSchema

class ConvertPRToPOInput(BaseModel):
    material_request_id: str = Field(..., description="The unique ID of the Material Request (PR)")
    supplier: str = Field(..., description="The registered Name of the Supplier/Vendor")
    currency: str = Field(default="INR", description="Currency code")

class Purchase_Order_Id_Validator(BaseModel):
    purchase_order_id: str = Field(..., description="The purchase order id to submit the final version of purchase order.")

class Material_Request_Id_Validator(BaseModel):
    material_request_id: str = Field(..., description="The material request id to validate or process.")



